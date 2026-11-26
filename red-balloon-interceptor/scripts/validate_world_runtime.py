#!/usr/bin/env python3
"""Run isolated native Gazebo startup/clock/topic repetitions with raw evidence.

Does not install software, publish flight messages, or attach to existing servers.
CPU values are macOS ps lifetime-average percentages, summed for the owned group.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'companion/monitoring'),str(ROOT/'scripts')]
from gazebo_monitor import JSONStream
from build_world import load_config

def terminate(process):
    if process.poll() is not None: return process.returncode
    for sig,wait in [(signal.SIGINT,3),(signal.SIGTERM,2),(signal.SIGKILL,2)]:
        try: os.killpg(process.pid,sig)
        except ProcessLookupError: break
        try: return process.wait(timeout=wait)
        except subprocess.TimeoutExpired: continue
    return process.poll()

def execute(command,folder,name,env,timeout=10):
    start=time.monotonic()
    p=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                       cwd=ROOT,env=env,start_new_session=True)
    timed_out=False
    try: stdout,stderr=p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True; terminate(p); stdout,stderr=p.communicate(timeout=3)
    (folder/f'{name}.stdout').write_text(stdout)
    (folder/f'{name}.stderr').write_text(stderr)
    result={'command':command,'exit_code':p.returncode,'timed_out':timed_out,
            'wall_s':time.monotonic()-start}
    (folder/f'{name}.command.json').write_text(json.dumps(result,indent=2))
    return result,stdout

def parse_messages(text):
    parser=JSONStream(); messages=[]
    # The stream decoder bounds one unparsed message, not an entire long capture.
    for offset in range(0,len(text),65536):
        messages.extend(parser.feed(text[offset:offset+65536]))
    if parser.buffer.strip(): raise ValueError('Incomplete or non-JSON topic output')
    return messages

def seconds(stamp):
    return float(stamp.get('sec',0))+float(stamp.get('nsec',0))*1e-9

def distribution(values):
    return {'count':len(values),'min':min(values),'mean':statistics.mean(values),'max':max(values)} if values else None

def sample_process_group(pgid,stop,output):
    start=time.monotonic()
    with output.open('x') as stream:
        while not stop.is_set():
            p=subprocess.run(['ps','-axo','pid=,pgid=,%cpu=,rss=,command='],capture_output=True,text=True,timeout=5)
            processes=[]
            for line in p.stdout.splitlines():
                parts=line.strip().split(None,4)
                if len(parts)==5 and int(parts[1])==pgid:
                    processes.append({'pid':int(parts[0]),'cpu_percent':float(parts[2]),'rss_kib':int(parts[3]),'command':parts[4]})
            if processes:
                stream.write(json.dumps({'wall_elapsed_s':time.monotonic()-start,'processes':processes,
                    'cpu_percent_sum':sum(x['cpu_percent'] for x in processes),
                    'rss_mib_sum':sum(x['rss_kib'] for x in processes)/1024})+'\n'); stream.flush()
            stop.wait(.5)

def trial(folder,duration,gui_view=None):
    folder.mkdir(parents=True,exist_ok=False)
    c=load_config(); name=c['world_name']; world=ROOT/'simulation/worlds/rbi_phase1.sdf'
    env=os.environ.copy(); env.update(GZ_PARTITION='rbi_world_'+uuid.uuid4().hex,GZ_IP='127.0.0.1',GZ_LOG_PATH=str(folder.resolve()))
    command=['gz','sim','-s','-r','-v','4','--seed',str(c['physics']['seed']),str(world)]
    result={'partition':env['GZ_PARTITION'],'world_sha256':hashlib.sha256(world.read_bytes()).hexdigest(),
            'seed':c['physics']['seed'],'server_command':command,'gui_requested':gui_view}
    (folder/'launch.json').write_text(json.dumps(result,indent=2))
    stop=threading.Event(); gui=None; monitor=None
    with (folder/'server.stdout').open('x') as stdout,(folder/'server.stderr').open('x') as stderr:
        started=time.monotonic()
        server=subprocess.Popen(command,stdout=stdout,stderr=stderr,env=env,cwd=ROOT,start_new_session=True)
        monitor=threading.Thread(target=sample_process_group,args=(server.pid,stop,folder/'server_process_samples.jsonl'),daemon=True)
        monitor.start()
        try:
            topics=[]; discovery=[]
            for attempt in range(12):
                if server.poll() is not None: raise RuntimeError(f'Server exited early: {server.returncode}')
                info,text=execute(['gz','topic','-l'],folder,f'discovery_{attempt:02}',env,5)
                discovery.append(info); topics=text.splitlines()
                if f'/world/{name}/clock' in topics and f'/world/{name}/stats' in topics: break
                time.sleep(.25)
            else: raise RuntimeError('World clock/stats discovery deadline exceeded')
            result['startup_discovery_s']=time.monotonic()-started
            result['topics']=topics; result['WORLD-009']='PASS'
            if gui_view:
                gui_command=['gz','sim','-g','-v','4','--gui-config',str(ROOT/f'simulation/gui/{gui_view}.config')]
                # Files remain open until the GUI has exited.
                gui_stdout=(folder/'gui.stdout').open('x'); gui_stderr=(folder/'gui.stderr').open('x')
                gui=subprocess.Popen(gui_command,stdout=gui_stdout,stderr=gui_stderr,env=env,cwd=ROOT,start_new_session=True)
                result['gui_command']=gui_command; result['gui_pid']=gui.pid
                gui_stop=threading.Event()
                gui_monitor=threading.Thread(target=sample_process_group,args=(gui.pid,gui_stop,folder/'gui_process_samples.jsonl'),daemon=True)
                gui_monitor.start()
                (folder/'gui_session.json').write_text(json.dumps({'server_pid':server.pid,'gui_pid':gui.pid,'partition':env['GZ_PARTITION']},indent=2))
                print(f'GUI ready for inspection: {gui_view}; evidence {folder}',flush=True)
                screenshots=folder/'screenshots'; screenshots.mkdir()
                for attempt in range(5):
                    if gui.poll() is not None: break
                    time.sleep(1)
                    shot,_=execute(['gz','service','-s','/gui/screenshot','--reqtype','gz.msgs.StringMsg',
                        '--reptype','gz.msgs.Boolean','--timeout','2000','--req',
                        'data: '+json.dumps(str(screenshots.resolve()))],folder,f'screenshot_{attempt}',env,5)
                    time.sleep(.5)
                    if list(screenshots.glob('*.png')): break
                result['screenshots']=[str(p.relative_to(folder)) for p in screenshots.glob('*.png')]
            commands={key:['gz','topic','-e','--json-output','-t',f'/world/{name}/{key}','-d',str(duration)] for key in ('clock','stats')}
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures={key:pool.submit(execute,cmd,folder,key,env,duration+8) for key,cmd in commands.items()}
                captures={key:future.result() for key,future in futures.items()}
            messages={key:parse_messages(value[1]) for key,value in captures.items()}
            times=[seconds(m['sim']) for m in messages['clock']]
            advancing=len(times)>=2 and all(b>a for a,b in zip(times,times[1:])) and times[-1]-times[0]>duration*.5
            result['WORLD-008']='PASS' if advancing else 'FAIL'
            result['clock']={'messages':len(times),'first_s':times[0] if times else None,'last_s':times[-1] if times else None,
                             'advance_s':times[-1]-times[0] if len(times)>1 else 0,'strictly_increasing':advancing}
            rtfs=[float(m.get('realTimeFactor',m.get('real_time_factor',0))) for m in messages['stats']]
            result['real_time_factor']=distribution(rtfs)
            result['server_alive_before_shutdown']=server.poll() is None
            if gui:
                result['gui_alive_before_shutdown']=gui.poll() is None
                result['gui_exit_before_shutdown']=gui.poll()
            result['captures']={key:info for key,(info,_) in captures.items()}
            if gui and gui.poll() is None:
                # An early capture can precede scene synchronization and be black.
                # Always capture again after the clock/stats observation window.
                execute(['gz','service','-s','/gui/screenshot','--reqtype','gz.msgs.StringMsg',
                    '--reptype','gz.msgs.Boolean','--timeout','3000','--req',
                    'data: '+json.dumps(str(screenshots.resolve()))],folder,'screenshot_final',env,6)
                time.sleep(1)
                result['screenshots']=[str(p.relative_to(folder)) for p in sorted(screenshots.glob('*.png'))]
        except (RuntimeError,ValueError,OSError,KeyError) as exc:
            result['error']=str(exc); result.setdefault('WORLD-008','FAIL'); result.setdefault('WORLD-009','FAIL')
        finally:
            if gui:
                gui_stop.set(); gui_monitor.join(timeout=6)
                result['gui_stop_code']=terminate(gui); gui_stdout.close(); gui_stderr.close()
            result['server_stop_code']=terminate(server); stop.set(); monitor.join(timeout=6)
    text=(folder/'server.stdout').read_text()+(folder/'server.stderr').read_text()
    clean=re.sub(r'\x1b\[[0-9;]*m','',text)
    errors=[line for line in clean.splitlines() if '[Err]' in line or 'Error' in line or 'failed to' in line.lower()]
    result['server_errors']=errors
    result['WORLD-007']='PASS' if result.get('server_alive_before_shutdown') and not errors and 'error' not in result else 'FAIL'
    if 'Operation not permitted' in text:
        for key in ('WORLD-007','WORLD-008','WORLD-009'): result[key]='BLOCKED'
    samples=[json.loads(line) for line in (folder/'server_process_samples.jsonl').read_text().splitlines()]
    result['cpu_percent_ps_lifetime_average']=distribution([s['cpu_percent_sum'] for s in samples])
    result['rss_mib_process_group']=distribution([s['rss_mib_sum'] for s in samples])
    if gui:
        samples=[json.loads(line) for line in (folder/'gui_process_samples.jsonl').read_text().splitlines()]
        result['gui_cpu_percent_ps_lifetime_average']=distribution([s['cpu_percent_sum'] for s in samples])
        result['gui_rss_mib_process_group']=distribution([s['rss_mib_sum'] for s in samples])
        gui_text=(folder/'gui.stdout').read_text()+(folder/'gui.stderr').read_text()
        gui_clean=re.sub(r'\x1b\[[0-9;]*m','',gui_text)
        result['gui_errors']=[line for line in gui_clean.splitlines() if '[Err]' in line]
        result['gui_warnings']=[line for line in gui_clean.splitlines() if '[Wrn]' in line]
        result['gui_render_evidence']=bool(result.get('screenshots'))
    result['note']='Static world only; no flight. ps CPU is a process-lifetime average, not instantaneous total-system load.'
    (folder/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--duration',type=float,default=8)
    parser.add_argument('--repetitions',type=int,default=2)
    parser.add_argument('--gui',choices=('perspective','topdown'))
    args=parser.parse_args()
    if args.duration<2 or args.repetitions<1: parser.error('Use duration >=2 s and repetitions >=1')
    args.output_dir.mkdir(parents=True,exist_ok=False)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock: sock.bind(('127.0.0.1',0))
    results=[]
    for i in range(args.repetitions):
        result=trial(args.output_dir/f'run_{i+1:02}',args.duration,args.gui); results.append(result)
        print(json.dumps({k:v for k,v in result.items() if k.startswith('WORLD-') or k in ('clock','real_time_factor','startup_discovery_s','error')},indent=2),flush=True)
    repeat='NOT RUN' if len(results)<2 else 'PASS' if all(r['WORLD-007']==r['WORLD-008']==r['WORLD-009']=='PASS' for r in results) and len({r['world_sha256'] for r in results})==1 else 'FAIL'
    summary={'WORLD-010':repeat,'runs':results,'scope':'Repeatable world startup, not deterministic flight dynamics.'}
    (args.output_dir/'results.json').write_text(json.dumps(summary,indent=2)+'\n')
    return 0 if all(r['WORLD-007']==r['WORLD-008']==r['WORLD-009']=='PASS' for r in results) else 1

if __name__=='__main__': raise SystemExit(main())
