#!/usr/bin/env python3
"""Validated flight CSV to four response plots, status timeline and metrics.

SVG requires only Python. Matplotlib backend additionally uses NumPy and Pandas.
Existing output directories are refused to protect prior test evidence.
"""
import argparse
import html
import json
import math
from pathlib import Path
from flight_data import read_csv, position_errors, metrics

COLORS = ('#147d92', '#db6b25', '#6c4ab6', '#337a40')

def series_for(rows):
    values=lambda key: [r[key] for r in rows]
    degrees=lambda key: [math.degrees(r[key]) for r in rows]
    return [
        ('altitude_response', 'Altitude response', 'Altitude above world origin (m)',
         [('z', values('z_m')), ('reference z', values('reference_z_m'))]),
        ('attitude_response', 'Attitude response', 'Euler angle (deg, wrapped yaw)',
         [('roll',degrees('roll_rad')),('pitch',degrees('pitch_rad')),('yaw',degrees('yaw_rad'))]),
        ('position_error', 'Position error', '3D distance to recorded reference (m)',
         [('error',position_errors(rows))]),
        ('velocity_response', 'Velocity response', 'World-frame velocity (m/s)',
         [(axis,values(f'v{axis}_mps')) for axis in 'xyz']),
    ]

def svg_plot(output, title, ylabel, times, series, banner):
    # Small standalone vector plot, no external JavaScript, fonts, or packages.
    numeric=[v for _,vs in series for v in vs if v is not None]
    low,high=(min(numeric),max(numeric)) if numeric else (0,1)
    margin=max((high-low)*0.12,0.05)
    low-=margin; high+=margin
    tx=lambda t: 90+(t-times[0])/(times[-1]-times[0])*820
    ty=lambda v: 400-(v-low)/(high-low)*275
    esc=html.escape
    svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="510" viewBox="0 0 1000 510">',
         '<rect width="1000" height="510" fill="#f7fafc"/>',
         '<g font-family="Arial,sans-serif" fill="#182b3a">',
         f'<text x="90" y="38" font-size="23">{esc(title)}</text>',
         f'<text x="90" y="65" font-size="13" fill="#9a3526">{esc(banner)}</text>',
         f'<text x="90" y="96" font-size="13">{esc(ylabel)}</text>']
    for i in range(6):
        v=low+(high-low)*i/5; y=ty(v)
        svg += [f'<line x1="90" x2="910" y1="{y:.2f}" y2="{y:.2f}" stroke="#dce4e9"/>',
                f'<text x="78" y="{y+4:.2f}" text-anchor="end" font-size="12">{v:.3g}</text>']
        t=times[0]+(times[-1]-times[0])*i/5
        svg.append(f'<text x="{tx(t):.2f}" y="423" text-anchor="middle" font-size="12">{t:.3g}</text>')
    for index,(label,values) in enumerate(series):
        color=COLORS[index%len(COLORS)]
        # Missing references break curves, never silently interpolate across gaps.
        segments=[]; current=[]
        for t,value in zip(times,values):
            if value is None:
                if current: segments.append(current); current=[]
            else: current.append(f'{tx(t):.2f},{ty(value):.2f}')
        if current: segments.append(current)
        for segment in segments:
            svg.append(f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" stroke-width="1.8"/>')
        svg.append(f'<text x="{90+index*200}" y="480" font-size="13" fill="{color}">{esc(label)}</text>')
    if not numeric:
        svg.append('<text x="220" y="245" font-size="18">Unavailable: no recorded reference position</text>')
    svg += ['<text x="500" y="449" text-anchor="middle" font-size="13">Simulation timestamp (s)</text>', '</g></svg>']
    output.write_text('\n'.join(svg))

def plot(rows, output, backend):
    output=Path(output)
    output.mkdir(parents=True, exist_ok=False)
    source=rows[0]['data_source']
    banner=('SYNTHETIC TEST DATA - NOT A FLIGHT RESULT' if source.startswith('synthetic')
            else f'Recorded simulation: {source}')
    times=[r['timestamp_s'] for r in rows]
    selected=backend
    if backend=='auto':
        try:
            import matplotlib, numpy, pandas  # noqa: F401
            selected='matplotlib'
        except ImportError:
            selected='svg'
    if selected=='matplotlib':
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        import pandas as pd
        frame=pd.DataFrame(rows)
        times=frame['timestamp_s'].to_numpy(dtype=float)
    for filename,title,ylabel,series in series_for(rows):
        if selected=='svg':
            svg_plot(output/f'{filename}.svg',title,ylabel,times,series,banner)
        else:
            fig,ax=plt.subplots(figsize=(10,5))
            for label,values in series:
                ax.plot(times,np.array([np.nan if x is None else x for x in values]),label=label)
            if not any(v is not None for _,vs in series for v in vs):
                ax.text(0.5,0.5,'No recorded reference position',transform=ax.transAxes,ha='center')
            ax.set(xlabel='Simulation timestamp (s)',ylabel=ylabel,title=title)
            ax.grid(alpha=0.25); ax.legend(); fig.suptitle(banner,fontsize=10,color='#9a3526')
            fig.tight_layout(); fig.savefig(output/f'{filename}.png',dpi=160); plt.close(fig)
    # Keep state transitions as a readable timeline alongside numeric curves.
    transitions=[]; previous=None
    for r in rows:
        state=(r['flight_mode'],r['simulation_health'])
        if state!=previous:
            transitions.append({'timestamp_s':r['timestamp_s'],'flight_mode':state[0],'simulation_health':state[1]})
        previous=state
    summary=metrics(rows); summary['plot_backend']=selected; summary['transitions']=transitions
    (output/'metrics.json').write_text(json.dumps(summary,indent=2)+'\n')
    plots=''.join(f'<figure><img style="width:100%;max-width:1000px" src="{name}.{("svg" if selected=="svg" else "png")}" alt="{title}"></figure>'
                  for name,title,_,_ in series_for(rows))
    table=''.join(f'<tr><td>{r["timestamp_s"]:.3f}</td><td>{html.escape(r["flight_mode"])}</td><td>{html.escape(r["simulation_health"])}</td></tr>' for r in transitions)
    (output/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>RBI flight analysis</title>'
        '<body style="font-family:Arial;background:#f7fafc;color:#182b3a;max-width:1100px;margin:32px auto">'
        f'<h1>{html.escape(banner)}</h1><p>Descriptive statistics only. Source: {html.escape(source)}. '
        'See metrics.json for sample coverage and timing gaps.</p>'+plots+
        '<h2>Flight mode and simulation health transitions</h2><table cellpadding="8"><tr><th>Time (s)</th><th>Flight mode</th><th>Simulation health</th></tr>'+table+'</table></body></html>')
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv',type=Path)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--backend',choices=('auto','svg','matplotlib'),default='auto')
    parser.add_argument('--start-s',type=float)
    parser.add_argument('--end-s',type=float)
    args=parser.parse_args()
    try:
        rows=read_csv(args.csv)
        rows=[r for r in rows if (args.start_s is None or r['timestamp_s']>=args.start_s)
              and (args.end_s is None or r['timestamp_s']<=args.end_s)]
        if len(rows)<2: raise ValueError('Selected time window needs at least two samples')
        print(json.dumps(plot(rows,args.output_dir,args.backend),indent=2))
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(2,f'Analysis error: {exc}\n')

if __name__=='__main__':
    main()
