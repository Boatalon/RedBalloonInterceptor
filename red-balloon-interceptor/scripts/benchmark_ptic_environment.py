#!/usr/bin/env python3
"""Sequential, comparable baseline/campus benchmark; no concurrent Gazebo runs.

Copies generated variants into a fresh evidence directory. Does not replace the
canonical MEDIUM/midday world. GUI screenshot files still require visual review.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from build_ptic_environment import ROOT,load_config,generated


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--duration',type=float,default=10);args=p.parse_args()
    if args.duration<2:p.error('Duration must be at least two seconds')
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False);c=load_config()
    cases=[('baseline',None,None,'overview',True,2),('MEDIUM_midday','MEDIUM','midday','overview',False,2),('MEDIUM_topdown','MEDIUM','midday','topdown',False,1),('MEDIUM_architecture','MEDIUM','midday','architecture',False,1),('MEDIUM_groundlevel','MEDIUM','midday','groundlevel',False,1),('LOW_midday','LOW','midday','overview',False,1),('HIGH_midday','HIGH','midday','overview',False,1),('MEDIUM_morning','MEDIUM','morning','overview',False,1),('MEDIUM_afternoon','MEDIUM','afternoon','overview',False,1),('MEDIUM_overcast','MEDIUM','overcast','overview',False,1)]
    assets={}
    for _,profile,lighting,_,baseline,_ in cases:
        if baseline or (profile,lighting) in assets:continue
        dest=out/'assets'/f'{profile}_{lighting}';assets[(profile,lighting)]=dest
        for name,data in generated(c,profile,lighting).items():
            target=dest/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    all_results=[]
    for name,profile,lighting,view,baseline,repeats in cases:
        asset_root=ROOT if baseline else assets[(profile,lighting)]
        command=[sys.executable,str(ROOT/'scripts/validate_ptic_environment.py'),'--asset-root',str(asset_root),'--output-dir',str(out/name),'--duration',str(args.duration),'--view',view,'--repetitions',str(repeats)]+(['--baseline'] if baseline else [])
        print('Starting '+name,flush=True)
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
        (out/(name+'.stdout')).write_text(result.stdout);(out/(name+'.stderr')).write_text(result.stderr)
        record={'case':name,'command':command,'exit_code':result.returncode,'result_path':str(out/name/'results.json')}
        all_results.append(record);(out/'benchmark_runs.json').write_text(json.dumps(all_results,indent=2)+'\n')
        print(name+': exit '+str(result.returncode),flush=True)
    return 0 if all(r['exit_code']==0 for r in all_results) else 1

if __name__=='__main__':raise SystemExit(main())
