"""CSV contract and descriptive statistics. No actuator or network interface."""
import csv
import math
from pathlib import Path
from statistics import mean, pstdev

NUMERIC = ('timestamp_s', 'x_m', 'y_m', 'z_m', 'vx_mps', 'vy_mps', 'vz_mps',
           'roll_rad', 'pitch_rad', 'yaw_rad')
LABELS = ('flight_mode', 'simulation_health', 'data_source')
OPTIONAL = ('reference_x_m', 'reference_y_m', 'reference_z_m', 'rtf')
FIELDS = NUMERIC + LABELS + OPTIONAL

def read_csv(path):
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        missing = set(NUMERIC + LABELS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'Missing columns: {sorted(missing)}')
        rows = []
        for line, raw in enumerate(reader, 2):
            row = dict(raw)
            for name in NUMERIC + OPTIONAL:
                value = raw.get(name, '')
                if name in OPTIONAL and value in ('', None):
                    row[name] = None
                    continue
                try:
                    number = float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f'Line {line}: invalid {name}') from exc
                if not math.isfinite(number):
                    raise ValueError(f'Line {line}: non-finite {name}')
                row[name] = number
            if row['timestamp_s'] < 0 or (rows and row['timestamp_s'] <= rows[-1]['timestamp_s']):
                raise ValueError(f'Line {line}: timestamps must increase; split resets into separate logs')
            if any(not raw.get(k, '').strip() for k in LABELS):
                raise ValueError(f'Line {line}: empty provenance, flight mode, or health')
            refs = [row[k] is not None for k in OPTIONAL[:3]]
            if any(refs) and not all(refs):
                raise ValueError(f'Line {line}: provide all three reference coordinates or none')
            rows.append(row)
    if len(rows) < 2:
        raise ValueError('At least two samples are required')
    if len({r['data_source'] for r in rows}) != 1:
        raise ValueError('Mixed provenance: split sources into separate files')
    return rows

def position_errors(rows):
    result = []
    for row in rows:
        if any(row[k] is None for k in OPTIONAL[:3]):
            result.append(None)
        else:
            result.append(math.sqrt(sum((row[f'{axis}_m'] - row[f'reference_{axis}_m'])**2
                                        for axis in 'xyz')))
    return result

def metrics(rows):
    errors = position_errors(rows)
    valid = [v for v in errors if v is not None]
    source = rows[0]['data_source']
    return {
        'data_source': source,
        'synthetic': source.startswith('synthetic'),
        'samples': len(rows),
        'start_s': rows[0]['timestamp_s'], 'end_s': rows[-1]['timestamp_s'],
        'duration_s': rows[-1]['timestamp_s'] - rows[0]['timestamp_s'],
        'altitude_mean_m': mean(r['z_m'] for r in rows),
        'altitude_std_m': pstdev(r['z_m'] for r in rows),
        'roll_rms_rad': math.sqrt(mean(r['roll_rad']**2 for r in rows)),
        'pitch_rms_rad': math.sqrt(mean(r['pitch_rad']**2 for r in rows)),
        'position_rmse_m': math.sqrt(mean(v*v for v in valid)) if valid else None,
        'reference_coverage_fraction': len(valid) / len(rows),
        'max_sample_gap_s': max(b['timestamp_s']-a['timestamp_s'] for a,b in zip(rows,rows[1:])),
        'flight_modes': sorted({r['flight_mode'] for r in rows}),
        'health_counts': {v: sum(r['simulation_health']==v for r in rows)
                          for v in sorted({r['simulation_health'] for r in rows})},
        'assessment': 'DESCRIPTIVE ONLY: no flight stability or hardware performance certification',
    }
