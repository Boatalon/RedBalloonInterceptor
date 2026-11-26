#!/usr/bin/env python3
"""Deterministic plotting fixture, explicitly NOT a Gazebo/ArduPilot flight log."""
import argparse
import csv
import math
from pathlib import Path
from flight_data import FIELDS

def generate(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for i in range(601):
            t = i / 20
            decay = math.exp(-t / 1.8)
            row = dict(zip(('x_m','y_m','z_m'),
                           (0.08*math.sin(t), 0.05*math.cos(0.7*t), 2*(1-decay))))
            row.update(timestamp_s=t, vx_mps=0.08*math.cos(t),
                       vy_mps=-0.035*math.sin(0.7*t), vz_mps=2/1.8*decay,
                       roll_rad=0.015*math.sin(2*t), pitch_rad=0.012*math.cos(1.7*t),
                       yaw_rad=0.04*math.sin(0.2*t), flight_mode='SYNTHETIC_HOVER',
                       simulation_health='SYNTHETIC_OK' if t < 20 else 'SYNTHETIC_STALE',
                       data_source='synthetic_plot_fixture_v1',
                       reference_x_m=0, reference_y_m=0, reference_z_m=2, rtf=1)
            writer.writerow(row)
    return output

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    print(generate(args.output))
