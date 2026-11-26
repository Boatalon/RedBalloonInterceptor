#!/usr/bin/env python3
"""Receive Gazebo odometry and stats through CLI subscriptions; never publish.

No flight mode can be inferred from Gazebo alone. It is explicitly unavailable.
Raw JSON and wall-clock health events preserve evidence of stalls and pauses.
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'analysis'))
from flight_data import FIELDS

class JSONStream:
    def __init__(self):
        self.buffer=''
        self.decoder=json.JSONDecoder()

    def feed(self,chunk):
        self.buffer+=chunk
        if len(self.buffer)>2_000_000:
            raise ValueError('Unparseable JSON stream exceeds 2 MB')
        objects=[]
        while self.buffer.strip():
            self.buffer=self.buffer.lstrip()
            try:
                obj,end=self.decoder.raw_decode(self.buffer)
            except json.JSONDecodeError:
                break
            objects.append(obj); self.buffer=self.buffer[end:]
        return objects

def rotation(q):
    x,y,z,w=[float(q.get(k,0)) for k in ('x','y','z','w')]
    norm=math.sqrt(x*x+y*y+z*z+w*w)
    if norm<1e-12 or not math.isfinite(norm):
        raise ValueError('Invalid orientation quaternion')
    x,y,z,w=[v/norm for v in (x,y,z,w)]
    roll=math.atan2(2*(w*x+y*z),1-2*(x*x+y*y))
    pitch=math.asin(max(-1,min(1,2*(w*y-z*x))))
    yaw=math.atan2(2*(w*z+x*y),1-2*(y*y+z*z))
    matrix=((1-2*(y*y+z*z),2*(x*y-w*z),2*(x*z+w*y)),
            (2*(x*y+w*z),1-2*(x*x+z*z),2*(y*z-w*x)),
            (2*(x*z-w*y),2*(y*z+w*x),1-2*(x*x+y*y)))
    return (roll,pitch,yaw),matrix

def odometry_row(message,health,rtf=None,reference=None):
    stamp=message['header']['stamp']
    timestamp=float(stamp.get('sec',0))+float(stamp.get('nsec',0))*1e-9
    frames={d['key']:d.get('value',[]) for d in message['header'].get('data',[])}
    if frames.get('frame_id')!=['world']:
        raise ValueError('Odometry must declare frame_id=world; configure odom_frame in SDF')
    pose=message['pose']; angles,matrix=rotation(pose['orientation'])
    position=pose.get('position',{})
    linear=message.get('twist',{}).get('linear',{})
    body=[float(linear.get(axis,0)) for axis in 'xyz']
    world=[sum(m*v for m,v in zip(line,body)) for line in matrix]
    row={key:'' for key in FIELDS}
    row.update(timestamp_s=timestamp, flight_mode='UNAVAILABLE_NO_FCU',
               simulation_health=health,data_source='gazebo_odometry',rtf=rtf if rtf is not None else '')
    for i,axis in enumerate('xyz'):
        row[f'{axis}_m']=float(position.get(axis,0))
        row[f'v{axis}_mps']=world[i]
        if reference is not None: row[f'reference_{axis}_m']=reference[i]
    row.update(zip(('roll_rad','pitch_rad','yaw_rad'),angles))
    if any(not math.isfinite(float(row[k])) for k in FIELDS[:10]):
        raise ValueError('Non-finite telemetry')
    return row

def stop(process):
    if process.poll() is None:
        os.killpg(process.pid,signal.SIGTERM)
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGKILL); process.wait()

def capture(output,duration,model='iris',world='rbi_phase1',reference=None):
    if duration<=0: raise ValueError('duration must be positive')
    output=Path(output); output.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy(); env.setdefault('GZ_PARTITION','rbi_phase1'); env.setdefault('GZ_IP','127.0.0.1')
    events=queue.Queue(); processes=[]; threads=[]
    topics={'odom':f'/model/{model}/odometry','stats':f'/world/{world}/stats'}
    def reader(kind,proc):
        decoder=JSONStream()
        try:
            while chunk:=os.read(proc.stdout.fileno(),4096):
                for obj in decoder.feed(chunk.decode('utf-8')):
                    events.put((kind,obj,time.monotonic()))
        except Exception as exc:
            events.put(('error',str(exc),time.monotonic()))
    start=time.monotonic(); last_odom=start; last_stats=None; stats={}; count=0; last_t=-1
    try:
        with (output/'transport.stderr.log').open('x') as errors, \
             (output/'telemetry.csv').open('x',newline='') as csvfile, \
             (output/'raw.jsonl').open('x') as raw, (output/'health.jsonl').open('x') as healthfile:
            writer=csv.DictWriter(csvfile,fieldnames=FIELDS); writer.writeheader()
            for kind,topic in topics.items():
                proc=subprocess.Popen(['gz','topic','-e','--json-output','-t',topic],
                    stdout=subprocess.PIPE,stderr=errors,env=env,start_new_session=True)
                processes.append(proc)
                thread=threading.Thread(target=reader,args=(kind,proc),daemon=True)
                thread.start(); threads.append(thread)
            previous_health=None
            while time.monotonic()-start<duration:
                now=time.monotonic()
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError('Gazebo subscription exited; inspect transport.stderr.log')
                health=('STALE_ODOMETRY' if now-last_odom>2 else
                        'UNKNOWN_STATS' if last_stats is None else
                        'STALE_STATS' if now-last_stats>2 else
                        'PAUSED' if stats.get('paused',False) else 'RUNNING')
                if health!=previous_health:
                    healthfile.write(json.dumps({'wall_elapsed_s':now-start,'health':health})+'\n')
                    healthfile.flush(); previous_health=health
                    print(f'{now-start:.1f}s health={health}',flush=True)
                try: kind,obj,received=events.get(timeout=0.1)
                except queue.Empty: continue
                if kind=='error': raise RuntimeError(obj)
                raw.write(json.dumps({'topic':topics[kind],'wall_elapsed_s':received-start,'message':obj})+'\n')
                if kind=='stats': stats=obj; last_stats=received; continue
                last_odom=received
                # Recompute after receiving this odometry sample; no stale values are forward-filled.
                health=('UNKNOWN_STATS' if last_stats is None else 'STALE_STATS' if received-last_stats>2
                        else 'PAUSED' if stats.get('paused',False) else 'RUNNING')
                rtf=stats.get('realTimeFactor',stats.get('real_time_factor')) if last_stats and received-last_stats<=2 else None
                row=odometry_row(obj,health,rtf,reference)
                if row['timestamp_s']<=last_t:
                    raise ValueError('Simulation time reset or duplicate sample: start a new recording')
                writer.writerow(row); csvfile.flush(); count+=1; last_t=row['timestamp_s']
    finally:
        for proc in processes: stop(proc)
        for thread in threads: thread.join(timeout=1)
    if count<2: raise RuntimeError('No usable odometry; topics, permissions, or simulation may be unavailable')
    return count

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=30)
    parser.add_argument('--model',default='iris')
    parser.add_argument('--world',default='rbi_phase1')
    parser.add_argument('--reference',type=float,nargs=3,metavar=('X','Y','Z'))
    args=parser.parse_args()
    if any('/' in value for value in (args.model,args.world)):
        parser.error('Use plain entity names without slashes')
    try: print('Recorded samples:',capture(args.output_dir,args.duration,args.model,args.world,args.reference))
    except (OSError,ValueError,RuntimeError) as exc: parser.exit(2,f'Monitor error: {exc}\n')

if __name__=='__main__': main()
