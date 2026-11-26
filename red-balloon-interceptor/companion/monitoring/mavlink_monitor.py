#!/usr/bin/env python3
"""Optional receive-only localhost MAVLink decoder for an explicit SITL stream.

Requires pymavlink. Uses socket.recvfrom and MAVLink(None) only: no heartbeat,
stream request, arming, mode change, parameter write, or actuator output.
Gazebo truth/health are captured separately by gazebo_monitor.py.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import socket
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'analysis'))
from flight_data import FIELDS

def normalize(position,attitude,mode,reference=None):
    """MAVLink LOCAL_POSITION_NED + ATTITUDE (FRD) to world ENU/body FLU."""
    row={name:'' for name in FIELDS}
    row.update(timestamp_s=position.time_boot_ms/1000,
               x_m=position.y,y_m=position.x,z_m=-position.z,
               vx_mps=position.vy,vy_mps=position.vx,vz_mps=-position.vz,
               roll_rad=attitude.roll,pitch_rad=-attitude.pitch,
               yaw_rad=math.atan2(math.sin(math.pi/2-attitude.yaw),math.cos(math.pi/2-attitude.yaw)),
               flight_mode=mode,simulation_health='UNKNOWN_GAZEBO',
               data_source='sitl_mavlink_estimate')
    if reference is not None:
        for axis,value in zip('xyz',reference): row[f'reference_{axis}_m']=value
    return row

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sitl-only',action='store_true',required=True,
                        help='Confirm this localhost stream originates from SITL')
    parser.add_argument('--port',type=int,default=14560)
    parser.add_argument('--system-id',type=int,default=1)
    parser.add_argument('--component-id',type=int,default=1)
    parser.add_argument('--duration',type=float,default=30)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--reference',type=float,nargs=3)
    args=parser.parse_args()
    if not 1024<=args.port<=65535 or args.duration<=0:
        parser.error('Use an unprivileged UDP port and positive duration')
    try:
        from pymavlink import mavutil
        from pymavlink.dialects.v20 import ardupilotmega
    except ImportError:
        parser.exit(2,'Missing optional pymavlink; no connection was made. See monitoring README.\n')
    decoder=ardupilotmega.MAVLink(None)
    decoder.robust_parsing=True
    args.output_dir.mkdir(parents=True,exist_ok=False)
    count=0; attitude=None; heartbeat=None; previous=-1
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock, \
             (args.output_dir/'telemetry.csv').open('x',newline='') as csvfile, \
             (args.output_dir/'packets.jsonl').open('x') as raw, \
             (args.output_dir/'health.jsonl').open('x') as health:
            sock.bind(('127.0.0.1',args.port)); sock.settimeout(0.25)
            writer=csv.DictWriter(csvfile,fieldnames=FIELDS); writer.writeheader()
            start=time.monotonic(); state=None
            while time.monotonic()-start<args.duration:
                now=time.monotonic()
                current='HEARTBEAT_STALE' if heartbeat is None or now-heartbeat[1]>2 else 'HEARTBEAT_FRESH'
                if current!=state:
                    health.write(json.dumps({'wall_elapsed_s':now-start,'state':current})+'\n'); health.flush()
                    print(current,flush=True); state=current
                try: packet,peer=sock.recvfrom(65535)
                except socket.timeout: continue
                if peer[0]!='127.0.0.1': continue
                raw.write(json.dumps({'wall_elapsed_s':time.monotonic()-start,'packet_hex':packet.hex()})+'\n')
                for message in decoder.parse_buffer(packet) or []:
                    if message.get_srcSystem()!=args.system_id or message.get_srcComponent()!=args.component_id: continue
                    kind=message.get_type(); now=time.monotonic()
                    if kind=='HEARTBEAT': heartbeat=(message,now)
                    elif kind=='ATTITUDE': attitude=(message,now)
                    elif kind=='LOCAL_POSITION_NED':
                        if attitude is None or heartbeat is None: continue
                        if now-attitude[1]>0.25 or now-heartbeat[1]>2: continue
                        if abs(message.time_boot_ms-attitude[0].time_boot_ms)>250: continue
                        row=normalize(message,attitude[0],mavutil.mode_string_v10(heartbeat[0]),args.reference)
                        if row['timestamp_s']<previous: raise ValueError('SITL clock reset; record a new session')
                        if row['timestamp_s']==previous: continue
                        if any(not math.isfinite(float(row[k])) for k in FIELDS[:10]): continue
                        writer.writerow(row); csvfile.flush(); previous=row['timestamp_s']; count+=1
        if count<2: raise ValueError('No synchronized position, attitude and heartbeat; receiver does not request streams')
        print('Recorded samples:',count)
    except (OSError,ValueError) as exc: parser.exit(2,f'Monitor error: {exc}\n')

if __name__=='__main__': main()
