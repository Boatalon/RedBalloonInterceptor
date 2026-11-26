#!/usr/bin/env python3
"""Build a fictional static campus. JSON-compatible YAML 1.2; stdlib only.

No GIS, flight commands, network downloads or external model assets. --write
updates only this generator's outputs; default checks their byte identity.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import random
import re
import struct
import xml.etree.ElementTree as ET
import zlib

from build_world import child, numbers, serialize, gui_config

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT/'config/ptic_environment.yaml'


def load_config(path=CONFIG):
    c = json.loads(Path(path).read_text())
    validate_config(c)
    return c


def validate_config(c):
    def require(ok, message):
        if not ok: raise ValueError(message)
    def finite(v):
        return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    def positive(v): return finite(v) and v > 0
    require(c['schema_version'] == 1, 'Unsupported schema')
    def reject_nonfinite(value):
        if isinstance(value,dict):
            for item in value.values(): reject_nonfinite(item)
        elif isinstance(value,list):
            for item in value: reject_nonfinite(item)
        elif isinstance(value,float): require(math.isfinite(value), 'Non-finite configuration value')
    reject_nonfinite(c)
    require(c['fictional_non_georeferenced'] is True, 'Scene must remain fictional')
    require(c['coordinates']['frame'] == 'local_ENU' and c['coordinates']['geodetic_origin'] is None, 'Local ENU only')
    require(re.fullmatch(r'[a-z][a-z0-9_]*', c['world_name']), 'Invalid world name')
    require(len(c['field']['size_m']) == 2 and all(positive(x) for x in c['field']['size_m']), 'Invalid field')
    require(c['field']['elevation_m'] == 0, 'Ground datum must be zero')
    require(positive(c['field']['slab_thickness_m']), 'Invalid ground thickness')
    require(len(c['gravity_mps2']) == 3 and all(finite(v) for v in c['gravity_mps2']), 'Invalid gravity')
    require(c['wind_enabled'] is False, 'Wind-free environment required')
    require(isinstance(c['seed'], int) and 0 <= c['seed'] < 2**32, 'Invalid random seed')
    require(0 < c['physics']['max_step_size_s'] <= .02 and positive(c['physics']['real_time_factor']), 'Invalid physics timing')
    require(c['default_profile'] in c['rendering_profiles'] and c['default_lighting'] in c['lighting_presets'], 'Invalid defaults')
    for name, m in c['materials'].items():
        require(len(m['rgba']) == 4 and all(finite(v) and 0 <= v <= 1 for v in m['rgba']), 'Invalid material color: '+name)
        require(m['rgba'][3] == 1, 'Only inexpensive opaque materials are supported')
        for k in ('roughness', 'metalness'): require(finite(m[k]) and 0 <= m[k] <= 1, 'Invalid '+k)
    for group, keys in [('ground', ['material']), ('roads', ['material','curb_material','path_material']), ('vegetation',['tree_material','trunk_material']), ('backdrop',['material'])]:
        for k in keys: require(c[group][k] in c['materials'], 'Unknown material reference')
    for key in ('white_concrete','light_gray_concrete','glass','aluminum','asphalt','pavement','grass','foliage','foliage_light','bark','painted_steel','road_paint','hill_green'):
        require(key in c['materials'], 'Missing required material: '+key)
    require(positive(c['ground']['grid_spacing_m']) and positive(c['ground']['texture_tile_m']), 'Invalid ground detail')
    roads = c['roads']
    for k in ('half_extent_m','width_m','corner_radius_m','path_width_m'): require(positive(roads[k]), 'Invalid road geometry')
    require(roads['width_m']/2 < roads['corner_radius_m'] < roads['half_extent_m'], 'Invalid road radius')
    require(roads['half_extent_m']+roads['width_m']+roads['path_width_m'] < min(c['field']['size_m'])/2, 'Roads exceed field')
    require(abs(roads['cross_street_y_m']) < roads['half_extent_m']-roads['corner_radius_m']-roads['width_m'], 'Cross street outside loop')
    names=set();bounds=[]
    for b in c['buildings']:
        require(re.fullmatch(r'[a-z][a-z0-9_]*',b['name']) and b['name'] not in names, 'Invalid/duplicate building name'); names.add(b['name'])
        require(b['category'] in ('office','laboratory','workshop'), 'Unknown building category')
        require(len(b['size_m']) == 3 and all(finite(v) and 8 <= v <= 100 for v in b['size_m']), 'Building sizes must be 8..100 m')
        require(len(b['position_xy_m']) == 2 and all(finite(v) for v in b['position_xy_m']) and finite(b['yaw_rad']), 'Invalid building pose')
        w,d,_=b['size_m']; a=b['yaw_rad']; ext=[abs(w*math.cos(a))+abs(d*math.sin(a)),abs(w*math.sin(a))+abs(d*math.cos(a))]
        require(all(abs(p)+s/2+8 < f/2 for p,s,f in zip(b['position_xy_m'],ext,c['field']['size_m'])), 'Building outside field')
        bx,by=b['position_xy_m'];ex,ey=ext
        require(abs(by-roads['cross_street_y_m']) > ey/2+roads['width_m']/2+8, 'Building overlaps cross street')
        for px,py,pw,pd in bounds: require(abs(bx-px)>(ex+pw)/2+3 or abs(by-py)>(ey+pd)/2+3, 'Overlapping buildings')
        bounds.append((bx,by,ex,ey))
    for p in c['rendering_profiles'].values():
        for k in ('tree_count','ornamental_count','bush_count','forest_count'): require(isinstance(p[k],int) and 0 <= p[k] <= 300, 'Invalid vegetation count')
        require(p['facade_detail'] in (1,2,3) and isinstance(p['mesh_segments'],int) and isinstance(p['mesh_rings'],int) and 8 <= p['mesh_segments'] <= 48 and 4 <= p['mesh_rings'] <= 24, 'Invalid detail')
    v=c['vegetation']; require(isinstance(v['variants'],int) and 1 <= v['variants'] <= 12, 'Invalid variant count')
    for k in ('tree_height_range_m','ornamental_height_range_m'):
        require(len(v[k])==2 and 0 < v[k][0] <= v[k][1] <= 30, 'Invalid tree size range')
    require(positive(v['setback_m']), 'Invalid setback')
    require(c['backdrop']['extent_m'] > max(c['field']['size_m'])*2 and 0 < c['backdrop']['hill_height_range_m'][0] <= c['backdrop']['hill_height_range_m'][1] <= 200, 'Invalid backdrop')
    require(.2 < c['gui']['horizontal_fov_rad'] < 2.5 and c['gui']['width_px']>=640 and c['gui']['height_px']>=480, 'Invalid GUI dimensions')
    for l in c['lighting_presets'].values():
        require(len(l['direction'])==3 and all(finite(x) for x in l['direction']) and l['direction'][2]<0, 'Invalid light direction')
        for k in ('ambient_rgba','background_rgba','diffuse_rgba'): require(len(l[k])==4 and all(finite(x) and 0 <= x <= 1 for x in l[k]), 'Invalid lighting color')
        require(finite(l['intensity']) and 0 <= l['intensity'] <= 5 and finite(l['fog_density']) and 0 <= l['fog_density'] <= .01, 'Invalid light/fog')
    for v in c['gui']['views'].values():
        require(all(len(v[k])==3 and all(finite(x) for x in v[k]) for k in ('position_m','look_at_m')), 'Invalid camera pose')
        require(0 < v['near_clip_m'] < c['gui']['far_clip_m'], 'Invalid clipping range')
        require(v['position_m'] != v['look_at_m'], 'Camera direction has zero length')
    return c


def png_texture(kind, seed, size=128):
    """Original seamless procedural RGB textures; no photographic inputs."""
    rng=random.Random(seed); rows=[]
    for y in range(size):
        row=bytearray([0])
        for x in range(size):
            # Periodic coarse variation plus fine grain. Values modulate SDF colors.
            grain=rng.uniform(-5,5)
            coarse=3*math.sin(2*math.pi*x/size)*math.cos(4*math.pi*y/size)
            if kind=='bark': grain += 12*math.sin(x*12*math.pi/size)
            val=max(0,min(255,round(247+grain+coarse)))
            row.extend((val,val,val))
        rows.append(bytes(row))
    def chunk(tag,data): return struct.pack('>I',len(data))+tag+data+struct.pack('>I',zlib.crc32(tag+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(rows),9))+chunk(b'IEND',b'')


def obj_mesh(vertices, faces, uv=None):
    normals=[[0.,0.,0.] for _ in vertices]
    good=[]
    for f in faces:
        a,b,c=[vertices[i] for i in f]; u=[b[i]-a[i] for i in range(3)]; v=[c[i]-a[i] for i in range(3)]
        n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        if sum(t*t for t in n)<1e-16: continue
        good.append(f)
        for i in f:
            for j in range(3): normals[i][j]+=n[j]
    lines=['# Original deterministic procedural mesh; metres; local ENU']
    lines += ['v '+numbers(v) for v in vertices]
    if uv is None: uv=[(v[0]/8,v[1]/8) for v in vertices]
    lines += ['vt '+numbers(t) for t in uv]
    for n in normals:
        length=math.sqrt(sum(x*x for x in n)); lines.append('vn '+numbers([x/length for x in n] if length else [0,0,1]))
    lines.append('s 1')
    lines += ['f '+' '.join(f'{i+1}/{i+1}/{i+1}' for i in f) for f in good]
    return ('\n'.join(lines)+'\n').encode()


def crown_mesh(seed, segments, rings):
    rng=random.Random(seed); vertices=[]; uv=[]; faces=[]
    for j in range(rings+1):
        phi=math.pi*j/rings
        for i in range(segments+1):
            theta=2*math.pi*(i%segments)/segments
            radius=1+.09*math.sin(theta*5+phi*3)+.07*math.cos(theta*3-phi*7)
            vertices.append((radius*math.sin(phi)*math.cos(theta),radius*math.sin(phi)*math.sin(theta),math.cos(phi)*(1+.06*math.sin(theta*3)*math.sin(phi))))
            uv.append((i/segments,j/rings))
    for j in range(rings):
        for i in range(segments):
            a=j*(segments+1)+i;b=a+1;c=a+segments+1;d=c+1
            faces += [(a,c,b),(b,c,d)]
    # Seeded rotation and asymmetry are also applied to the reusable tree models.
    return obj_mesh(vertices,faces,uv)


def ring_mesh(half, radius, width, z, segments=12):
    vertices=[]; faces=[]
    for cx,cy,start in [(half-radius,half-radius,0),(-half+radius,half-radius,90),(-half+radius,-half+radius,180),(half-radius,-half+radius,270)]:
        for i in range(segments+1):
            t=math.radians(start+i*90/segments)
            for r in (radius-width/2,radius+width/2): vertices.append((cx+r*math.cos(t),cy+r*math.sin(t),z))
    pairs=len(vertices)//2
    for i in range(pairs):
        a=2*i;b=(2*(i+1))%len(vertices);faces.extend([(a,a+1,b),(a+1,b+1,b)])
    return obj_mesh(vertices,faces)


class Builder:
    def __init__(self,c,profile=None,lighting=None):
        self.c=copy.deepcopy(c);validate_config(self.c)
        self.profile_name=profile or c['default_profile'];self.lighting_name=lighting or c['default_lighting']
        self.p=c['rendering_profiles'][self.profile_name];self.light=c['lighting_presets'][self.lighting_name]
        self.rng=random.Random(c['seed']);self.files={};self.inventory=[];self.material_use=set()

    def material(self,visual,key,tint=1,roughness=None):
        self.material_use.add(key);m=self.c['materials'][key];node=child(visual,'material')
        color=[max(0,min(1,v*tint)) for v in m['rgba'][:3]]+[1]
        child(node,'ambient',numbers(color));child(node,'diffuse',numbers(color))
        child(node,'specular',numbers((.12,.12,.12,1) if key=='glass' else (.03,.03,.03,1)))
        if self.p['pbr']:
            metal=child(child(node,'pbr'),'metal');child(metal,'roughness',roughness if roughness is not None else m['roughness']);child(metal,'metalness',m['metalness'])
            texture={'grass':'grass','asphalt':'asphalt','pavement':'concrete','white_concrete':'concrete','light_gray_concrete':'concrete','foliage':'grass','foliage_light':'grass','bark':'bark'}.get(key)
            # Primitive boxes have one stretched UV tile. Use textures only on
            # our UV-mapped meshes; keep architectural panels clean and pale.
            if texture and self.p['textures'] and visual.find('geometry/mesh') is not None:
                child(metal,'albedo_map',f'model://ptic_materials/textures/{texture}.png')

    def model(self,name):
        root=ET.Element('sdf',version='1.9');m=child(root,'model',name=name);child(m,'static','true');link=child(m,'link',name='body');return root,link

    def save_model(self,name,root):
        self.files[f'simulation/models/{name}/model.sdf']=serialize(root)
        config=ET.Element('model');child(config,'name',name);child(config,'version','1.0');child(config,'sdf','model.sdf',version='1.9');child(config,'description','Original fictional campus asset. No geographic or operational meaning.')
        self.files[f'simulation/models/{name}/model.config']=serialize(config)
        self.inventory.append({'name':name,'visuals':len(root.findall('.//visual')),'collisions':len(root.findall('.//collision'))})

    def visual(self,link,name,kind,dimensions,pose,material,collision=False,tint=1,roughness=None):
        v=child(link,'visual',name=name);child(v,'pose',numbers(pose))
        casts=self.p['shadows'] and material not in ('grass','asphalt','pavement','hill_green')
        child(v,'cast_shadows',str(casts).lower())
        g=child(child(v,'geometry'),kind)
        if kind=='box': child(g,'size',numbers(dimensions))
        elif kind=='cylinder': child(g,'radius',dimensions[0]);child(g,'length',dimensions[1])
        elif kind=='mesh': child(g,'uri',dimensions[0]);child(g,'scale',numbers(dimensions[1]))
        self.material(v,material,tint,roughness)
        if collision:
            col=child(link,'collision',name=name+'_collision');child(col,'pose',numbers(pose));col.append(copy.deepcopy(v.find('geometry')))
        return v

    def box(self,l,n,size,xyz,mat,collision=False,tint=1,yaw=0):
        return self.visual(l,n,'box',size,(*xyz,0,0,yaw),mat,collision,tint)

    def mesh(self,l,n,uri,scale,xyz,mat,tint=1,yaw=0,roughness=None):
        return self.visual(l,n,'mesh',(uri,scale),(*xyz,0,0,yaw),mat,False,tint,roughness)

    def building(self,b):
        name=b['name'];w,d,h=b['size_m'];category=b['category'];root,l=self.model(name)
        self.box(l,'structure',(w,d,h),(0,0,h/2),'white_concrete',True)
        self.box(l,'roof_edge',(w+.5,d+.5,.45),(0,0,h-.225),'white_concrete')
        self.box(l,'roof_surface',(w-1,d-1,.12),(0,0,h-.19),'light_gray_concrete')
        self.box(l,'plinth',(w+.2,d+.2,.65),(0,0,.325),'light_gray_concrete')
        front=-d/2
        if category=='office':
            self.box(l,'curtain_wall',(w*.76,.12,h-1.8),(0,front-.075,h/2),'glass')
            # Projecting vertical fins and floor frames leave glass recessed.
            spacing=3.0 if self.p['facade_detail']>1 else 6
            count=round(w*.76/spacing)
            for i in range(count+1):
                x=-w*.38+i*w*.76/count
                self.box(l,f'mullion_{i}',(.12,.32,h-1.6),(x,front-.2,h/2),'aluminum')
            for floor in range(1,round(h/4)):
                self.box(l,f'transom_{floor}',(w*.76,.25,.16),(0,front-.18,floor*4),'aluminum')
                if self.p['facade_detail']>=2: self.box(l,f'spandrel_{floor}',(w*.76,.13,.65),(0,front-.15,floor*4-.4),'glass',tint=.7)
            for side in (-1,1):
                self.box(l,f'corner_fin_{side}',(.9,1.1,h),(side*w*.4,front-.5,h/2),'white_concrete')
                self.box(l,f'side_glazing_{side}',(.12,d*.7,h*.76),(side*(w/2+.07),0,h*.48),'glass')
                for j in range(1,round(d/4)):
                    self.box(l,f'side_frame_{side}_{j}',(.35,.14,h*.8),(side*(w/2+.18),-d*.35+j*3.5,h*.48),'aluminum')
        else:
            columns=max(3,round(w/(4 if category=='laboratory' else 8)))
            floors=range(1,round(h/5)) if category=='laboratory' else [round(h/5)-1]
            for side in (-1,1):
                for i in range(columns):
                    x=-w/2+(i+.5)*w/columns
                    for j in floors:
                        ww=1.4 if category=='laboratory' else 3.2;zz=j*5
                        self.box(l,f'window_reveal_{side}_{i}_{j}',(ww+.28,.22,3.0),(x,side*(d/2+.1),zz),'painted_steel')
                        self.box(l,f'window_{side}_{i}_{j}',(ww,.10,2.7),(x,side*(d/2+.23),zz),'glass')
                    if self.p['facade_detail']>1:
                        self.box(l,f'panel_seam_{side}_{i}',(.07,.08,h-.9),(x,side*(d/2+.05),h/2),'light_gray_concrete')
            if category=='workshop':
                for i,x in enumerate((-w*.24,0,w*.24)):
                    self.box(l,f'closed_generic_door_{i}',(9,.14,7),(x,front-.12,3.5),'light_gray_concrete')
                    if self.p['facade_detail']>1:
                        for j in range(1,10): self.box(l,f'door_seam_{i}_{j}',(8.8,.04,.035),(x,front-.21,j*.65),'aluminum')
            self.box(l,'accent_band',(w,.22,.8),(0,front-.18,h-2),'painted_steel')
        canopy_width=min(w*.4,23);cy=front-3.1
        self.box(l,'canopy_frame',(canopy_width,6,.28),(0,cy,4.6),'painted_steel')
        self.box(l,'canopy_glass',(canopy_width-.3,5.7,.12),(0,cy,4.8),'glass',tint=1.3)
        for x in (-canopy_width/2+.35,canopy_width/2-.35):
            self.box(l,f'canopy_column_{x:g}',(.22,.22,4.45),(x,cy-2.6,2.225),'painted_steel')
        if self.p['facade_detail']>=2:
            for i in range(5): self.box(l,f'canopy_rafter_{i}',(.16,6,.17),(-canopy_width/2+i*canopy_width/4,cy,4.92),'aluminum')
        self.box(l,'entry_glass',(6,.16,3.4),(0,front-.22,1.7),'glass',tint=.65)
        self.box(l,'entry_divider',(.12,.24,3.4),(0,front-.28,1.7),'aluminum')
        if self.p['facade_detail']==3:
            for i in range(round(w/2)):
                self.box(l,f'upper_louver_{i}',(.15,.8,1.2),(-w/2+1+i*2,front-.5,h-1.1),'aluminum')
        self.save_model(name,root)

    def vegetation(self):
        c=self.c;segments=self.p['mesh_segments'];rings=self.p['mesh_rings'];variants=c['vegetation']['variants']
        for family in ('tropical_tree','ornamental_tree','vegetation'):
            path=f'simulation/models/{family}/meshes/crown.obj'
            self.files[path]=crown_mesh(c['seed'],segments,rings)
            for i in range(variants):
                name=family if i==0 else f'{family}_{i:02}';root,l=self.model(name);r=random.Random(c['seed']+i*97+(0 if family=='tropical_tree' else 30))
                lo,hi=c['vegetation']['tree_height_range_m' if family=='tropical_tree' else 'ornamental_height_range_m'];height=r.uniform(lo,hi)
                if family=='vegetation': height=r.uniform(.65,1.4)
                if family!='vegetation':
                    self.visual(l,'trunk','cylinder',(height*.025,height*.63),(0,0,height*.315,0,0,0),c['vegetation']['trunk_material'])
                    if self.p['facade_detail']>1:
                        for j in range(3):
                            angle=j*2*math.pi/3
                            self.visual(l,f'branch_{j}','cylinder',(height*.012,height*.31),(math.cos(angle)*height*.05,math.sin(angle)*height*.05,height*.55,.5,0,angle),'bark')
                clusters=2 if self.profile_name=='LOW' else 4 if family!='vegetation' else 2
                for j in range(clusters):
                    angle=j*2*math.pi/clusters+r.random()*.3
                    spread=height*.13 if family!='vegetation' else height*.22
                    scale=(height*r.uniform(.23,.30),height*r.uniform(.22,.29),height*r.uniform(.18,.25))
                    z=height*.73 if family!='vegetation' else height*.21
                    self.mesh(l,f'crown_{j}',f'model://{family}/meshes/crown.obj',scale,(spread*math.cos(angle),spread*math.sin(angle),z+r.uniform(-.04,.04)*height),c['vegetation']['tree_material'] if j%2==0 else 'foliage_light',r.uniform(.85,1.12),r.random()*6.28,r.uniform(.86,.99))
                self.save_model(name,root)

    def surfaces(self):
        r=self.c['roads'];half=r['half_extent_m'];radius=r['corner_radius_m'];width=r['width_m']
        root,l=self.model('road_surface')
        for name,h,rad,w,z,mat in [('asphalt',half,radius,width,.025,r['material']),('curb_outer',half+width/2+.2,radius+width/2+.2,.4,.14,r['curb_material']),('curb_inner',half-width/2-.2,radius-width/2-.2,.4,.14,r['curb_material'])]:
            uri=f'model://road_surface/meshes/{name}.obj';self.files[f'simulation/models/road_surface/meshes/{name}.obj']=ring_mesh(h,rad,w,z)
            self.mesh(l,name,uri,(1,1,1),(0,0,0),mat)
        self.box(l,'cross_street',(2*half,width,.025),(0,r['cross_street_y_m'],.025),r['material'])
        for side in (-1,1):
            for i in range(-12,13):
                self.box(l,f'dash_vertical_{side}_{i}',(.18,3,.012),(side*half,i*8,.05),'road_paint')
                self.box(l,f'dash_horizontal_{side}_{i}',(3,.18,.012),(i*8,side*half,.05),'road_paint')
        for i in range(-16,17): self.box(l,f'cross_dash_{i}',(3,.16,.012),(i*8,r['cross_street_y_m'],.05),'road_paint')
        self.save_model('road_surface',root)
        root,l=self.model('concrete_path');ph=half+width/2+4.5;pr=radius+width/2+4.5
        self.files['simulation/models/concrete_path/meshes/loop.obj']=ring_mesh(ph,pr,r['path_width_m'],.07)
        self.mesh(l,'walk_loop','model://concrete_path/meshes/loop.obj',(1,1,1),(0,0,0),r['path_material'])
        for y in (r['cross_street_y_m']-width/2-3,r['cross_street_y_m']+width/2+3):
            self.box(l,f'promenade_{y}',(2*half,r['path_width_m'],.05),(0,y,.06),r['path_material'])
        self.save_model('concrete_path',root)
        root,l=self.model('grass_surface')
        self.box(l,'grass_patch',(10,10,.03),(0,0,.015),'grass');self.save_model('grass_surface',root)
        root,l=self.model('landscaped_island')
        self.visual(l,'rim','cylinder',(5.4,.35),(0,0,.175,0,0,0),'light_gray_concrete')
        self.visual(l,'planting','cylinder',(5.0,.37),(0,0,.185,0,0,0),'grass')
        self.save_model('landscaped_island',root)
        root,l=self.model('concrete_curb');self.box(l,'curb',(4,.3,.25),(0,0,.125),'light_gray_concrete');self.save_model('concrete_curb',root)
        root,l=self.model('campus_furniture')
        self.box(l,'bench_seat',(2.3,.65,.12),(0,0,.55),'bark')
        for x in (-.8,.8): self.box(l,f'bench_leg_{x}',(.12,.55,.5),(x,0,.25),'painted_steel')
        self.box(l,'bench_back',(2.3,.1,.5),(0,.3,.9),'bark');self.save_model('campus_furniture',root)
        root,l=self.model('campus_light')
        self.visual(l,'pole','cylinder',(.075,6),(0,0,3,0,0,0),'painted_steel')
        self.box(l,'arm',(1.8,.12,.12),(.8,0,6),'painted_steel');self.box(l,'luminaire',(.8,.32,.12),(1.3,0,5.9),'white_concrete');self.save_model('campus_light',root)

    def world(self):
        c=self.c;root=ET.Element('sdf',version='1.9');w=child(root,'world',name=c['world_name'])
        child(w,'gravity',numbers(c['gravity_mps2']));child(child(w,'wind'),'linear_velocity','0 0 0')
        physics=child(w,'physics',name='static_campus_1ms',type='ignored')
        child(physics,'max_step_size',c['physics']['max_step_size_s']);child(physics,'real_time_factor',c['physics']['real_time_factor'])
        for filename,name in [('physics','Physics'),('user-commands','UserCommands'),('scene-broadcaster','SceneBroadcaster')]: child(w,'plugin',filename=f'gz-sim-{filename}-system',name=f'gz::sim::systems::{name}')
        scene=child(w,'scene');child(scene,'ambient',numbers(self.light['ambient_rgba']));child(scene,'background',numbers(self.light['background_rgba']));child(scene,'grid','false')
        shadows=self.p['shadows'] and self.light['shadows'];child(scene,'shadows',str(shadows).lower())
        fog=child(scene,'fog');child(fog,'type','exp');child(fog,'color',numbers(self.light['background_rgba']));child(fog,'density',self.light['fog_density']);child(fog,'start',200);child(fog,'end',2500)
        light=child(w,'light',name='synthetic_daylight',type='directional');child(light,'direction',numbers(self.light['direction']));child(light,'diffuse',numbers(self.light['diffuse_rgba']));child(light,'specular','.1 .1 .1 1');child(light,'intensity',self.light['intensity']);child(light,'cast_shadows',str(shadows).lower())
        def inline(name):
            m=child(w,'model',name=name);child(m,'static','true');return child(m,'link',name='body')
        def include(name,asset,xyz=(0,0,0),yaw=0):
            i=child(w,'include');child(i,'uri','model://'+asset);child(i,'name',name);child(i,'pose',numbers((*xyz,0,0,yaw)));child(i,'static','true')
        sx,sy=c['field']['size_m'];t=c['field']['slab_thickness_m'];l=inline('campus_ground')
        self.box(l,'ground',(sx,sy,t),(0,0,-t/2),c['ground']['material'],True)
        # A tiled mesh above the solid slab gives repeatable metre-scale UVs.
        v=[(-sx/2,-sy/2,.002),(sx/2,-sy/2,.002),(sx/2,sy/2,.002),(-sx/2,sy/2,.002)];tile=c['ground']['texture_tile_m']
        self.files['simulation/models/ptic_materials/meshes/lawn.obj']=obj_mesh(v,[(0,1,2),(0,2,3)],[(x/tile,y/tile) for x,y,z in v])
        self.mesh(l,'lawn','model://ptic_materials/meshes/lawn.obj',(1,1,1),(0,0,0),c['ground']['material'])
        for asset in ('road_surface','concrete_path'): include(asset,asset)
        paving=inline('entrance_paving')
        for b in c['buildings']:
            x,y=b['position_xy_m'];bw,bd,bh=b['size_m'];a=b['yaw_rad'];include(b['name'],b['name'],(x,y,0),a)
            # Transform local apron coordinates to the configured building yaw.
            ly=-bd/2-8;px=x-ly*math.sin(a);py=y+ly*math.cos(a)
            self.box(paving,b['name']+'_apron',(bw+4,16,.07),(px,py,.045),'pavement',yaw=a)
            for sign in (-1,1):
                lx=sign*(bw/2-5);ly=-bd/2-11;tx=x+lx*math.cos(a)-ly*math.sin(a);ty=y+lx*math.sin(a)+ly*math.cos(a)
                include(b['name']+f'_island_{sign}','landscaped_island',(tx,ty,0))
                include(b['name']+f'_ornamental_{sign}','ornamental_tree',(tx,ty,.37))
                include(b['name']+f'_bench_{sign}','campus_furniture',(tx,ty-6,0),a)
        # Pedestrian links and a central lawn walk are invented scene dressing.
        self.box(paving,'central_walk',(4,157,.07),(-8,43,.045),'pavement')
        for b in c['buildings'][:2]:
            x,y=b['position_xy_m'];bw,bd,_=b['size_m'];cy=y-bd/2-8
            self.box(paving,b['name']+'_walk_link',(abs(x+8),3.5,.07),((x-8)/2,cy,.045),'pavement')
        def available(x,y,margin):
            r=c['roads'];h=r['half_extent_m'];wid=r['width_m']
            # Conservative exclusions include the curved road corners and paths.
            if abs(y-r['cross_street_y_m'])<wid/2+margin+5 or abs(abs(x)-h)<wid/2+margin+7 or abs(abs(y)-h)<wid/2+margin+7:return False
            if abs(x)>h-r['corner_radius_m']-margin and abs(y)>h-r['corner_radius_m']-margin and abs(x)<h+wid+margin and abs(y)<h+wid+margin:return False
            if abs(x+8)<margin+3 and -40<y<125:return False
            for b in c['buildings']:
                dx=x-b['position_xy_m'][0];dy=y-b['position_xy_m'][1];a=b['yaw_rad'];lx=dx*math.cos(a)+dy*math.sin(a);ly=-dx*math.sin(a)+dy*math.cos(a)
                if abs(lx)<b['size_m'][0]/2+margin+5 and -b['size_m'][1]/2-20-margin<ly<b['size_m'][1]/2+margin:return False
            return True
        placements=[]
        for family,key,margin in [('tropical_tree','tree_count',c['vegetation']['setback_m']),('ornamental_tree','ornamental_count',3),('vegetation','bush_count',1)]:
            for i in range(self.p[key]):
                for attempt in range(5000):
                    x=self.rng.uniform(-sx/2+12,sx/2-12);y=self.rng.uniform(-sy/2+12,sy/2-12)
                    if available(x,y,margin) and all(math.hypot(x-px,y-py)>margin+pm for px,py,pm in placements):break
                else: raise ValueError('Cannot place configured vegetation without intersections')
                placements.append((x,y,margin));variant=i%c['vegetation']['variants'];asset=family+(f'_{variant:02}' if variant else '')
                include(f'{family}_instance_{i:03}',asset,(x,y,0),self.rng.uniform(-math.pi,math.pi))
        for i in range(12 if self.profile_name!='LOW' else 6):
            y=-115+i*21
            include(f'path_light_{i}','campus_light',(-157,y,0),0)
        if c['ground']['reference_grid']:
            l=inline('optional_reference_grid');spacing=c['ground']['grid_spacing_m']
            for axis,extent in [('x',sy),('y',sx)]:
                for i in range(math.floor(extent/spacing)+1):
                    off=-extent/2+i*spacing
                    self.box(l,f'{axis}_{i}',(sx,.12,.01) if axis=='x' else (.12,sy,.01),(0,off,.09) if axis=='x' else (off,0,.09),'road_paint')
        if c['backdrop']['enabled']:
            extent=c['backdrop']['extent_m']/2;step=30;n=round(2*extent/step);vertices=[];faces=[]
            peaks=[]
            for i in range(18):
                angle=i*math.tau/18;dist=self.rng.uniform(450,780);height=self.rng.uniform(*c['backdrop']['hill_height_range_m']);peaks.append((dist*math.cos(angle),dist*math.sin(angle),height,self.rng.uniform(85,160)))
            def height_at(x,y):
                fade=max(0,min(1,(max(abs(x),abs(y))-225)/110))
                return fade*max(h*math.exp(-((x-px)**2+(y-py)**2)/(2*s*s)) for px,py,h,s in peaks)-.06
            # Include the exact field edges in the terrain grid. Removing whole
            # 30 m cells crossing an edge would leave a visible sky-colored gap.
            xs=sorted(set([-extent+i*2*extent/n for i in range(n+1)]+[-sx/2,sx/2]))
            ys=sorted(set([-extent+i*2*extent/n for i in range(n+1)]+[-sy/2,sy/2]))
            for y in ys:
                for x in xs:vertices.append((x,y,height_at(x,y)))
            for j in range(len(ys)-1):
                for i in range(len(xs)-1):
                    a=j*len(xs)+i;b=a+1;cc=a+len(xs);d=cc+1
                    if -sx/2<=xs[i] and xs[i+1]<=sx/2 and -sy/2<=ys[j] and ys[j+1]<=sy/2:continue
                    faces.extend([(a,b,cc),(b,d,cc)])
            self.files['simulation/models/ptic_backdrop/meshes/hills.obj']=obj_mesh(vertices,faces)
            br,bl=self.model('ptic_backdrop');self.mesh(bl,'rolling_hills','model://ptic_backdrop/meshes/hills.obj',(1,1,1),(0,0,0),c['backdrop']['material'])
            # Distant forest mass is one inexpensive scalloped canopy mesh.
            fv=[];ff=[];columns=100;rows=8
            for j in range(rows+1):
                y=220+j*8
                for i in range(columns+1):
                    x=-600+i*12;edge=math.sin(math.pi*j/rows)**.5
                    z=height_at(x,y)+edge*(9+2.5*math.sin(i*2.4+j)+1.2*math.cos(j*4+i))
                    fv.append((x,y,z))
            for j in range(rows):
                for i in range(columns):
                    a=j*(columns+1)+i;b=a+1;cc=a+columns+1;d=cc+1;ff.extend([(a,b,cc),(b,d,cc)])
            self.files['simulation/models/ptic_backdrop/meshes/forest.obj']=obj_mesh(fv,ff)
            forest=self.mesh(bl,'forest_mass','model://ptic_backdrop/meshes/forest.obj',(1,1,1),(0,0,0),'foliage',tint=.85)
            forest.find('cast_shadows').text='false'
            self.save_model('ptic_backdrop',br);include('distant_landscape','ptic_backdrop')
            for i in range(self.p['forest_count']):
                # Forest fringe beyond the 400 m test surface, purely visual.
                angle=i*math.tau/self.p['forest_count'];rad=self.rng.uniform(220,250);x=rad*math.cos(angle);y=rad*math.sin(angle)
                if max(abs(x),abs(y))<205: x*=1.3;y*=1.3
                z=height_at(x,y)
                variant=i%c['vegetation']['variants'];include(f'forest_{i:03}','tropical_tree'+(f'_{variant:02}' if variant else ''),(x,y,z),angle)
        self.files['simulation/worlds/rbi_ptic_environment.sdf']=serialize(root)
        self.placements=placements
        return root

    def generate(self):
        for i,kind in enumerate(('grass','asphalt','concrete','bark')):self.files[f'simulation/models/ptic_materials/textures/{kind}.png']=png_texture(kind,self.c['seed']+i)
        mr,ml=self.model('ptic_materials');self.box(ml,'sample',(1,1,.1),(0,0,.05),'white_concrete');self.save_model('ptic_materials',mr)
        for b in self.c['buildings']: self.building(b)
        self.vegetation();self.surfaces();world=self.world()
        for view,vc in self.c['gui']['views'].items():
            pos=vc['position_m'];target=vc['look_at_m'];dx,dy,dz=[b-a for a,b in zip(pos,target)];pitch=-math.atan2(dz,math.hypot(dx,dy));yaw=math.atan2(dy,dx) if dx or dy else math.pi/2
            g=dict(self.c['gui']);g.update(near_clip_m=vc['near_clip_m'],perspective_pose=[*pos,0,pitch,yaw]);self.files[f'simulation/gui/ptic_{view}.config']=gui_config({'gui':g},'perspective')
        self.files['simulation/materials/ptic_materials.json']=(json.dumps(self.c['materials'],indent=2)+'\n').encode()
        summary={'schema_version':1,'world_name':self.c['world_name'],'profile':self.profile_name,'lighting':self.lighting_name,'seed':self.c['seed'],'fictional_non_georeferenced':True,'field_m':self.c['field']['size_m'],'building_dimensions_m':{b['name']:b['size_m'] for b in self.c['buildings']},'reusable_models':self.inventory,'world_includes':len(world.findall('.//include')),'world_inline_visuals':len(world.findall('.//visual')),'world_inline_collisions':len(world.findall('.//collision')),'placed_vegetation':len(self.placements),'materials_used':sorted(self.material_use),'mesh_triangles':sum(data.count(b'\nf ') for name,data in self.files.items() if name.endswith('.obj')),'file_sha256':{p:hashlib.sha256(d).hexdigest() for p,d in sorted(self.files.items())}}
        self.files['simulation/ptic_generation_summary.json']=(json.dumps(summary,indent=2)+'\n').encode()
        return self.files


def generated(config,profile=None,lighting=None): return Builder(config,profile,lighting).generate()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,default=CONFIG);parser.add_argument('--output-root',type=Path,default=ROOT);parser.add_argument('--profile',choices=('LOW','MEDIUM','HIGH'));parser.add_argument('--lighting',choices=('morning','midday','afternoon','overcast'));parser.add_argument('--write',action='store_true');args=parser.parse_args()
    try: files=generated(load_config(args.config),args.profile,args.lighting)
    except (ValueError,KeyError,TypeError) as e:parser.exit(2,str(e)+'\n')
    mismatches=[]
    for name,data in files.items():
        target=args.output_root/name
        if args.write:target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        elif not target.is_file() or target.read_bytes()!=data:mismatches.append(name)
    if mismatches:parser.exit(1,'Generated content mismatch: '+', '.join(mismatches)+'\n')
    summary=json.loads(files['simulation/ptic_generation_summary.json']);print(json.dumps({k:summary[k] for k in ('world_name','profile','lighting','placed_vegetation','world_includes','mesh_triangles')},indent=2));print(f'{len(files)} deterministic files '+('written' if args.write else 'verified'))

if __name__=='__main__':main()
