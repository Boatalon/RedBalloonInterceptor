#!/usr/bin/env python3
"""Bounded checks with evidence; never equate a zero exit code with working transport."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]

def bounded(command,timeout,env):
    proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,cwd=ROOT,env=env,start_new_session=True)
    timed_out=False
    try: output,_=proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True
        os.killpg(proc.pid,signal.SIGTERM)
        try: output,_=proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid,signal.SIGKILL); output,_=proc.communicate()
    return {'command':command,'exit_code':proc.returncode,'timed_out':timed_out,'output':output}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    output=args.output_dir or ROOT/'logs'/f'validation-{time.strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:6]}'
    output.mkdir(parents=True,exist_ok=False)
    env=os.environ.copy(); env['GZ_PARTITION']='rbi_validation_'+uuid.uuid4().hex
    env['GZ_IP']='127.0.0.1'; env['GZ_LOG_PATH']=str(output.resolve())
    results={}
    for name,relative in [('baseline_sdf','simulation/worlds/rbi_phase1.sdf'),('physics_sdf','tests/physics_probe.sdf')]:
        result=bounded(['gz','sdf','-k',str(ROOT/relative)],15,env)
        result['status']='PASS' if result['exit_code']==0 and 'Valid.' in result['output'] else 'FAIL'
        results[name]=result
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock: sock.bind(('127.0.0.1',0))
        results['loopback']={'status':'PASS'}
    except OSError as exc:
        results['loopback']={'status':'BLOCKED','reason':str(exc)}
    load=bounded(['gz','sim','-s','-r','--iterations','50','--seed','42','-v','4',
                  str(ROOT/'simulation/worlds/rbi_phase1.sdf')],12,env)
    blockers=('Operation not permitted','Binding to a local port failed','not been correctly initialized')
    if any(s in load['output'] for s in blockers): load['status']='BLOCKED'
    elif load['timed_out']: load['status']='FAIL'
    elif load['exit_code']==0 and 'rbi_phase1' in load['output'] and 'Error' not in load['output'] and '[Err]' not in load['output']:
        load['status']='PASS'
    else: load['status']='FAIL'
    # This is the server smoke test only. GUI rendering and flight are separate.
    results['world_server_load']=load
    for name,result in results.items():
        if 'output' in result: (output/f'{name}.log').write_text(result['output'])
    (output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({name:r['status'] for name,r in results.items()},indent=2))
    print('Evidence:',output)
    return 0 if all(r['status']=='PASS' for r in results.values()) else 2

if __name__=='__main__': raise SystemExit(main())
