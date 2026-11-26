#!/usr/bin/env python3
"""Assess ACTUAL physics_probe CSV against free fall and ground rest.

Run the separate tests/physics_probe.sdf world and record from its first second.
Sphere center starts at z=10 m. The ground top is z=0; radius is 0.1 m.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'analysis'))
from flight_data import read_csv

def assess(rows):
    if any(r['data_source']!='gazebo_odometry' for r in rows):
        raise ValueError('Physics validation requires actual gazebo_odometry data')
    falling=[r for r in rows if 0.05<=r['timestamp_s']<=0.8]
    resting=[r for r in rows if 3<=r['timestamp_s']<=5]
    if len(falling)<20 or len(resting)<20:
        raise ValueError('Insufficient early free-fall and settled samples; start monitor before simulation')
    error=max(abs(r['z_m']-(10-0.5*9.80665*r['timestamp_s']**2)) for r in falling)
    rest_error=max(abs(r['z_m']-0.1) for r in resting)
    speed=max(abs(r['vz_mps']) for r in resting)
    drift=max(((r['x_m']+5)**2+r['y_m']**2)**0.5 for r in rows)
    healthy=all(r['simulation_health']=='RUNNING' for r in falling+resting)
    return {'status':'PASS' if error<0.02 and rest_error<0.01 and speed<0.02 and drift<0.01 and healthy else 'FAIL',
            'max_freefall_error_m':error,'max_rest_height_error_m':rest_error,
            'max_rest_vertical_speed_mps':speed,'max_horizontal_drift_m':drift,
            'healthy_in_windows':healthy,
            'scope':'sphere gravity/contact fixture only; not UAV aerodynamics'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('csv',type=Path)
    args=parser.parse_args()
    try:
        result=assess(read_csv(args.csv)); print(json.dumps(result,indent=2))
        raise SystemExit(0 if result['status']=='PASS' else 1)
    except (ValueError,OSError) as exc: parser.exit(2,str(exc)+'\n')
