#!/usr/bin/env python3
"""Validate resources and run an isolated static Gazebo scene, retaining evidence.

Uses existing Phase 1B capture/cleanup helpers without modifying them. All Gazebo
processes owned by this run are stopped; unrelated sessions are never stopped.
No aircraft, control messages, hardware or package installation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import threading
import time
import uuid
import xml.etree.ElementTree as ET

from build_ptic_environment import ROOT, load_config, generated
from validate_world_runtime import execute, terminate, parse_messages, seconds, distribution, sample_process_group


def environment(asset_root,folder):
    env=os.environ.copy()
    env.update(GZ_PARTITION='rbi_ptic_'+uuid.uuid4().hex,GZ_IP='127.0.0.1',GZ_LOG_PATH=str(folder.resolve()),
               GZ_SIM_RESOURCE_PATH=str(asset_root/'simulation/models')+':'+str(asset_root/'simulation/worlds'),
               SDF_PATH=str(asset_root/'simulation/models'))
    return env


def check_resources(asset_root):
    summary=json.loads((asset_root/'simulation/ptic_generation_summary.json').read_text())
    errors=[];references=0
    for name,expected in summary['file_sha256'].items():
        path=asset_root/name
        if not path.is_file():errors.append('Missing file: '+name);continue
        if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:errors.append('Manifest mismatch: '+name)
        if not name.endswith('.sdf'):continue
        root=ET.parse(path).getroot()
        for tag in ('uri','albedo_map','roughness_map','normal_map'):
            for node in root.iter(tag):
                uri=node.text or '';references+=1
                if not uri.startswith('model://'):errors.append('Nonlocal resource: '+uri);continue
                rel=Path(uri.removeprefix('model://'))
                if '..' in rel.parts or rel.is_absolute():errors.append('Unsafe resource: '+uri);continue
                target=asset_root/'simulation/models'/rel
                if node.tag=='uri' and '/' not in str(rel):target=target/'model.sdf'
                if not target.is_file():errors.append('Unresolved resource: '+uri)
    return {'status':'FAIL' if errors else 'PASS','references_checked':references,'errors':errors}


def runtime(folder,asset_root,duration=10,view='overview',baseline=False):
    folder.mkdir(parents=True,exist_ok=False);env=environment(asset_root,folder)
    generation=None if baseline else json.loads((asset_root/'simulation/ptic_generation_summary.json').read_text())
    name='rbi_phase1' if baseline else generation['world_name'];seed=42 if baseline else generation['seed']
    world=asset_root/f'simulation/worlds/{"rbi_phase1" if baseline else "rbi_ptic_environment"}.sdf'
    gui_path=asset_root/f'simulation/gui/{"perspective" if baseline and view=="overview" else view if baseline else "ptic_"+view}.config'
    command=['gz','sim','-s','-r','-v','4','--seed',str(seed),str(world)]
    result={'world':name,'world_sha256':hashlib.sha256(world.read_bytes()).hexdigest(),'partition':env['GZ_PARTITION'],'server_command':command,'view':view,'duration_requested_s':duration,'note':'Static scene only. CPU is macOS ps process-lifetime average; RSS sums owned group processes.'}
    if not baseline:result['generation']=json.loads((asset_root/'simulation/ptic_generation_summary.json').read_text())
    (folder/'launch.json').write_text(json.dumps(result,indent=2)+'\n')
    stop=threading.Event();gui_stop=threading.Event();gui=None;gui_monitor=None;gui_files=[]
    with (folder/'server.stdout').open('x') as so,(folder/'server.stderr').open('x') as se:
        start=time.monotonic();server=subprocess.Popen(command,stdout=so,stderr=se,env=env,cwd=ROOT,start_new_session=True)
        monitor=threading.Thread(target=sample_process_group,args=(server.pid,stop,folder/'server_process_samples.jsonl'),daemon=True);monitor.start()
        try:
            for attempt in range(15):
                if server.poll() is not None:raise RuntimeError('Server exited before discovery')
                info,out=execute(['gz','topic','-l'],folder,f'discovery_{attempt:02}',env,5)
                topics=out.splitlines()
                if f'/world/{name}/clock' in topics and f'/world/{name}/stats' in topics:break
                time.sleep(.25)
            else:raise RuntimeError('Transport discovery deadline exceeded')
            result['startup_discovery_s']=time.monotonic()-start;result['topics']=topics;result['transport']='PASS'
            if view!='none':
                gc=['gz','sim','-g','-v','4','--gui-config',str(gui_path)];result['gui_command']=gc
                gui_files=[(folder/'gui.stdout').open('x'),(folder/'gui.stderr').open('x')]
                gui_start=time.monotonic();gui=subprocess.Popen(gc,stdout=gui_files[0],stderr=gui_files[1],env=env,cwd=ROOT,start_new_session=True)
                gui_monitor=threading.Thread(target=sample_process_group,args=(gui.pid,gui_stop,folder/'gui_process_samples.jsonl'),daemon=True);gui_monitor.start()
                (folder/'owned_session.json').write_text(json.dumps({'server_pid':server.pid,'gui_pid':gui.pid,'partition':env['GZ_PARTITION']},indent=2))
                shots=folder/'screenshots';shots.mkdir()
                # Initialization warmup is identical for baseline and campus.
                time.sleep(4)
                execute(['gz','service','-s','/gui/screenshot','--reqtype','gz.msgs.StringMsg','--reptype','gz.msgs.Boolean','--timeout','3000','--req','data: '+json.dumps(str(shots.resolve()))],folder,'screenshot_initial',env,6)
                time.sleep(1)
                if list(shots.glob('*.png')):result['gui_first_png_receipt_s']=time.monotonic()-gui_start
                result['gui_startup_metric_note']='PNG receipt includes 4 s warmup, CLI/service overhead and 1 s wait. An upper bound only after manual nonblank-image review; not a frame-rate metric.'
            jobs={k:['gz','topic','-e','--json-output','-t',f'/world/{name}/{k}','-d',str(duration)] for k in ('clock','stats')}
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures={k:pool.submit(execute,cmd,folder,k,env,duration+8) for k,cmd in jobs.items()};captures={k:f.result() for k,f in futures.items()}
            messages={k:parse_messages(out) for k,(info,out) in captures.items()}
            times=[seconds(m['sim']) for m in messages['clock']]
            advance=times[-1]-times[0] if len(times)>1 else 0
            advancing=len(times)>1 and all(b>a for a,b in zip(times,times[1:])) and advance>duration*.5
            result['clock_status']='PASS' if advancing else 'FAIL';result['clock']={'samples':len(times),'first_s':times[0] if times else None,'last_s':times[-1] if times else None,'advance_s':advance,'strictly_increasing':advancing}
            result['real_time_factor']=distribution([float(m.get('realTimeFactor',m.get('real_time_factor',0))) for m in messages['stats']])
            result['capture_commands']={k:info for k,(info,out) in captures.items()}
            result['server_alive']=server.poll() is None
            if gui:
                result['gui_alive']=gui.poll() is None
                execute(['gz','topic','-e','--json-output','-t','/gui/camera/pose','-d','1'],folder,'gui_camera_pose',env,5)
                execute(['gz','service','-s','/gui/screenshot','--reqtype','gz.msgs.StringMsg','--reptype','gz.msgs.Boolean','--timeout','3000','--req','data: '+json.dumps(str(shots.resolve()))],folder,'screenshot_final',env,6);time.sleep(1)
                result['screenshots']=[str(p.relative_to(folder)) for p in sorted(shots.glob('*.png'))]
                result['visual_inspection']='NOT RUN' # A file's existence does not prove correct rendering.
        except (RuntimeError,ValueError,OSError,KeyError,subprocess.SubprocessError) as exc:result['error']=str(exc)
        finally:
            if gui:
                gui_stop.set();gui_monitor.join(timeout=6);result['gui_stop_code']=terminate(gui)
                for f in gui_files:f.close()
            result['server_stop_code']=terminate(server);stop.set();monitor.join(timeout=6)
    for who in ('server','gui'):
        sample=folder/f'{who}_process_samples.jsonl'
        if not sample.is_file():continue
        samples=[json.loads(s) for s in sample.read_text().splitlines()]
        result[who+'_cpu_percent_ps']=distribution([s['cpu_percent_sum'] for s in samples]);result[who+'_rss_mib']=distribution([s['rss_mib_sum'] for s in samples])
        log=(folder/f'{who}.stdout').read_text()+(folder/f'{who}.stderr').read_text();clean=re.sub(r'\x1b\[[0-9;]*m','',log)
        result[who+'_errors']=[s for s in clean.splitlines() if '[Err]' in s or 'Error Code' in s or 'Unable to find' in s or 'failed to load' in s.lower()]
        result[who+'_warnings']=[s for s in clean.splitlines() if '[Wrn]' in s or 'warning:' in s.lower()]
    result['runtime_status']='PASS' if result.get('server_alive') and not result.get('server_errors') and not result.get('error') else 'FAIL'
    (folder/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--asset-root',type=Path,default=ROOT);parser.add_argument('--output-dir',type=Path,required=True);parser.add_argument('--duration',type=float,default=10);parser.add_argument('--view',choices=('none','overview','topdown','architecture','groundlevel'),default='overview');parser.add_argument('--baseline',action='store_true');parser.add_argument('--syntax-only',action='store_true');parser.add_argument('--repetitions',type=int,default=1);args=parser.parse_args()
    if args.duration<2 or args.repetitions<1:parser.error('duration >=2 and repetitions >=1 required')
    args.asset_root=args.asset_root.resolve();args.output_dir.mkdir(parents=True,exist_ok=False);env=environment(args.asset_root,args.output_dir)
    name='rbi_phase1' if args.baseline else 'rbi_ptic_environment';world=args.asset_root/f'simulation/worlds/{name}.sdf'
    syntax,out=execute(['gz','sdf','-k',str(world)],args.output_dir,'sdf_check',env,30)
    checks={'syntax':'PASS' if syntax['exit_code']==0 and 'Valid.' in out else 'FAIL'}
    if not args.baseline:checks['resources']=check_resources(args.asset_root)
    runs=[]
    if not args.syntax_only and checks['syntax']=='PASS' and checks.get('resources',{'status':'PASS'})['status']=='PASS':
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:s.bind(('127.0.0.1',0))
        for i in range(args.repetitions):
            run=runtime(args.output_dir/f'run_{i+1:02}',args.asset_root,args.duration,args.view,args.baseline);runs.append(run)
            print(json.dumps({k:run.get(k) for k in ('runtime_status','clock_status','startup_discovery_s','real_time_factor','server_rss_mib','gui_rss_mib','error','server_errors','gui_errors')},indent=2),flush=True)
    summary={'checks':checks,'runs':runs,'repeatable_startup':'NOT RUN' if len(runs)<2 else 'PASS' if all(r['runtime_status']==r.get('clock_status')=='PASS' for r in runs) and len({r['world_sha256'] for r in runs})==1 else 'FAIL'}
    (args.output_dir/'results.json').write_text(json.dumps(summary,indent=2)+'\n')
    failed=checks['syntax']!='PASS' or checks.get('resources',{'status':'PASS'})['status']!='PASS' or any(r['runtime_status']!='PASS' or r.get('clock_status')!='PASS' or r.get('gui_errors') or (args.view!='none' and not r.get('gui_alive')) for r in runs)
    return 1 if failed else 0

if __name__=='__main__':raise SystemExit(main())
