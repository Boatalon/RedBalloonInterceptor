#!/usr/bin/env python3
"""Deterministically generate local SDF and two GUI views from world_config.yaml.

The configuration uses the JSON-compatible YAML 1.2 subset, avoiding a new YAML
package dependency. Default mode checks generated files; --write updates them.
All dimensions below that are not in the config are rendering details, not zones.
"""
import argparse
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def numbers(values):
    return ' '.join(f'{value:.12g}' for value in values)

def child(parent, tag, text=None, **attributes):
    node = ET.SubElement(parent, tag, **attributes)
    if text is not None:
        node.text = str(text)
    return node

def load_config(path=ROOT/'config/world_config.yaml'):
    config = json.loads(Path(path).read_text())
    assert config['schema_version'] == 1, 'Unsupported configuration version'
    field = config['field']; spacing = config['grid_spacing_m']
    assert spacing > 0 and config['altitude_reference']['height_agl_m'] > 0
    for key in ('length_x_m', 'width_y_m'):
        assert field[key] > 0 and math.isclose(field[key] / spacing, round(field[key] / spacing))
    assert config['survey_references']['axis'] == 'x'
    assert 0 < config['survey_references']['separation_m'] <= field['length_x_m']
    assert not config['wind']['enabled'], 'Phase 1B baseline is wind-free'
    assert config['wind']['linear_velocity_mps'] == [0, 0, 0]
    assert config['survey_references']['passive_only'] and config['altitude_reference']['passive_only']
    assert 0 < config['gui']['near_clip_m'] < config['gui']['far_clip_m']
    return config

def static_model(world, name, pose=(0, 0, 0, 0, 0, 0)):
    model = child(world, 'model', name=name)
    child(model, 'static', 'true'); child(model, 'pose', numbers(pose))
    return child(model, 'link', name='link')

def box(link, name, size, pose, color, collision=False):
    visual = child(link, 'visual', name=name)
    child(visual, 'pose', numbers(pose)); child(visual, 'cast_shadows', 'false')
    child(child(child(visual, 'geometry'), 'box'), 'size', numbers(size))
    material = child(visual, 'material')
    child(material, 'ambient', numbers(color)); child(material, 'diffuse', numbers(color))
    if collision:
        coll = child(link, 'collision', name=name+'_collision')
        child(coll, 'pose', numbers(pose))
        child(child(child(coll, 'geometry'), 'box'), 'size', numbers(size))
    return visual

# A tiny vector stroke alphabet renders reference labels as plain visual boxes.
# No font files, textures, meshes, physics contacts or GUI text extension needed.
GLYPHS = {
    '0': [[(0,0),(.6,0),(.6,1),(0,1),(0,0)]],
    '3': [[(0,1),(.6,1),(.6,0),(0,0)],[(0,.5),(.6,.5)]],
    '4': [[(0,1),(0,.5),(.6,.5)],[(.6,1),(.6,0)]],
    '5': [[(.6,1),(0,1),(0,.5),(.6,.5),(.6,0),(0,0)]],
    '8': [[(0,0),(.6,0),(.6,1),(0,1),(0,0)],[(0,.5),(.6,.5)]],
    'A': [[(0,0),(.3,1),(.6,0)],[(.15,.5),(.45,.5)]],
    'B': [[(0,0),(0,1),(.5,1),(.6,.75),(.5,.5),(0,.5)],[(.5,.5),(.6,.25),(.5,0),(0,0)]],
    'm': [[(0,0),(0,.65),(.3,.65),(.3,0)],[(.3,.65),(.6,.65),(.6,0)]],
    'X': [[(0,0),(.6,1)],[(0,1),(.6,0)]],
    'Y': [[(0,1),(.3,.5),(.6,1)],[(.3,.5),(.3,0)]],
    'Z': [[(0,1),(.6,1),(0,0),(.6,0)]],
    'H': [[(0,0),(0,1)],[(.6,0),(.6,1)],[(0,.5),(.6,.5)]],
    '+': [[(.3,0),(.3,.8)],[(0,.4),(.6,.4)]],
    ' ': []
}

def label(world, name, text, position, height, color, vertical=False):
    # Local XY glyph plane; +pi/2 roll makes it an XZ sign facing -Y.
    link = static_model(world, name, (*position, math.pi/2 if vertical else 0, 0, 0))
    center = (len(text)-1)*.9/2+.3
    index = 0
    for letter, glyph in enumerate(text):
        for stroke in GLYPHS[glyph]:
            for a,b in zip(stroke,stroke[1:]):
                dx,dy = b[0]-a[0], b[1]-a[1]
                x = ((a[0]+b[0])/2+letter*.9-center)*height
                y = (a[1]+b[1])/2*height
                box(link,f'stroke_{index}',(math.hypot(dx,dy)*height,.085*height,.025),
                    (x,y,0,0,0,math.atan2(dy,dx)),color)
                index += 1

def world_tree(config):
    c=config; field=c['field']; viz=c['visualization']; light=c['lighting']
    length,width,z=field['length_x_m'],field['width_y_m'],field['ground_elevation_m']
    root=ET.Element('sdf',version='1.9'); world=child(root,'world',name=c['world_name'])
    child(world,'gravity',numbers(c['gravity_mps2']))
    child(child(world,'wind'),'linear_velocity',numbers(c['wind']['linear_velocity_mps']))
    physics=child(world,'physics',name='baseline_1ms',type='ignored')
    child(physics,'max_step_size',c['physics']['max_step_size_s'])
    child(physics,'real_time_factor',c['physics']['real_time_factor'])
    for filename,name in [('physics','Physics'),('user-commands','UserCommands'),('scene-broadcaster','SceneBroadcaster')]:
        child(world,'plugin',filename=f'gz-sim-{filename}-system',name=f'gz::sim::systems::{name}')
    scene=child(world,'scene')
    child(scene,'ambient',numbers(light['ambient_rgba'])); child(scene,'background',numbers(light['background_rgba']))
    child(scene,'shadows',str(light['shadows']).lower())
    child(scene,'grid','false')  # Suppress Gazebo's extra 1 m GUI grid at the origin.
    sun=child(world,'light',name='sun',type='directional')
    child(sun,'pose','0 0 100 0 0 0')
    for tag,key in [('diffuse','sun_diffuse_rgba'),('specular','sun_specular_rgba'),('direction','sun_direction')]:
        child(sun,tag,numbers(light[key]))
    child(sun,'cast_shadows',str(light['shadows']).lower())
    thickness=field['slab_thickness_m']
    ground=static_model(world,'ground_plane')
    box(ground,'surface',(length,width,thickness),(0,0,z-thickness/2,0,0,0),viz['ground_rgba'],True)
    grid=static_model(world,'reference_grid')
    spacing=c['grid_spacing_m']
    for axis,extent in [('x',width),('y',length)]:
        for i in range(round(extent/spacing)+1):
            offset=-extent/2+i*spacing
            size=(length,viz['grid_width_m'],.02) if axis=='x' else (viz['grid_width_m'],width,.02)
            pose=(0,offset,z+.08,0,0,0) if axis=='x' else (offset,0,z+.08,0,0,0)
            box(grid,f'{axis}_{i}',size,pose,viz['grid_rgba'])
    boundary=static_model(world,'mission_boundary')
    for name,size,pose in [
        ('north',(length,viz['boundary_width_m'],.025),(0,width/2,z+.04,0,0,0)),
        ('south',(length,viz['boundary_width_m'],.025),(0,-width/2,z+.04,0,0,0)),
        ('east',(viz['boundary_width_m'],width,.025),(length/2,0,z+.04,0,0,0)),
        ('west',(viz['boundary_width_m'],width,.025),(-length/2,0,z+.04,0,0,0))]:
        box(boundary,name,size,pose,(1,.72,.12,1))
    home=static_model(world,'home_marker')
    box(home,'cross_x',(3,.3,.02),(0,0,z+.05,0,0,0),(1,1,1,1))
    box(home,'cross_y',(.3,3,.02),(0,0,z+.05,0,0,0),(1,1,1,1))
    refs=c['survey_references']; center=refs['center_xy_m']; separation=refs['separation_m']
    for name,sign,color in [('a',-1,(.15,.75,1,1)),('b',1,(1,.35,.12,1))]:
        x,y=center[0]+sign*separation/2,center[1]
        link=static_model(world,'survey_reference_'+name,(x,y,z,0,0,0))
        radius,height=viz['marker_radius_m'],viz['marker_height_m']
        box(link,'cross_x',(radius*3,1,.12),(0,0,.15,0,0,0),color)
        box(link,'cross_y',(1,radius*3,.12),(0,0,.15,0,0,0),color)
        box(link,'post',(1.2,1.2,height),(0,0,height/2,0,0,0),color)
        box(link,'cap',(radius*2,radius*2,.5),(0,0,height,0,0,0),color)
        label(world,'label_survey_'+name,name.upper(),(x,y-18,z+.1),viz['label_height_m'],color)
    distance=static_model(world,'survey_distance_reference')
    # Measurement tick/line, purely visual; never published to a controller.
    box(distance,'dimension_line',(separation,.35,.02),(center[0],center[1]-30,z+.05,0,0,0),(1,1,.8,1))
    for name,sign in [('left',-1),('right',1)]:
        box(distance,name+'_tick',(.4,5,.02),(center[0]+sign*separation/2,center[1]-30,z+.05,0,0,0),(1,1,.8,1))
    label(world,'label_separation',f'{separation:g} m',(center[0],center[1]-45,z+.1),viz['label_height_m'],(1,1,.8,1))
    label(world,'label_field_width',f'{length:g} m',(0,width/2-17,z+.1),viz['label_height_m'],(1,.8,.3,1))
    label(world,'label_grid',f'{spacing:g} m',(-length/2+35,-width/2+12,z+.1),viz['label_height_m']*.75,(.8,.86,.9,1))
    altitude=c['altitude_reference']; ax,ay=altitude['position_xy_m']; height=altitude['height_agl_m']
    alt=static_model(world,'altitude_reference',(ax,ay,z,0,0,0))
    box(alt,'vertical_scale',(.45,.45,height),(0,0,height/2,0,0,0),(.25,.9,.85,1))
    box(alt,'top_reference',(15,1,.12),(0,0,height,0,0,0),(.25,.9,.85,1))
    for level in (0,height/4,height/2,3*height/4):
        box(alt,f'tick_{level:g}',(4,.5,.1),(0,0,level+.06,0,0,0),(.25,.9,.85,1))
    label(world,'label_altitude',f'{height:g} m',(ax,ay-1,z+height+3),viz['label_height_m'],(.4,1,.9,1),vertical=True)
    label(world,'label_altitude_topdown',f'{height:g} m',(ax,ay+12,z+.1),viz['label_height_m'],(.4,1,.9,1))
    axes=static_model(world,'coordinate_axes')
    for axis,size,pose,color in [
        ('x',(30,.6,.06),(15,0,z+.1,0,0,0),(1,.22,.2,1)),
        ('y',(.6,30,.06),(0,15,z+.1,0,0,0),(.2,.9,.3,1)),
        ('z',(.6,.6,25),(0,0,z+12.5,0,0,0),(.2,.45,1,1))]:
        box(axes,axis,size,pose,color)
    label(world,'label_x','+X',(35,-3,z+.1),5,(1,.25,.2,1))
    label(world,'label_y','+Y',(-9,33,z+.1),5,(.2,1,.3,1))
    label(world,'label_z','+Z',(0,-1,z+27),5,(.3,.55,1,1),vertical=True)
    pad=c['landing_pad']; px,py=pad['position_xy_m']; sx,sy,sz=pad['size_m']
    landing=static_model(world,'landing_pad',(px,py,z,0,0,0))
    box(landing,'pad',(sx,sy,sz),(0,0,sz/2,0,0,0),(.08,.12,.18,1),True)
    for name,size,pose in [('h_left',(.16,1.6,.008),(-.55,0,sz+.006,0,0,0)),
                           ('h_right',(.16,1.6,.008),(.55,0,sz+.006,0,0,0)),
                           ('h_bar',(1.1,.16,.008),(0,0,sz+.006,0,0,0))]:
        box(landing,name,size,pose,(1,1,1,1))
    return root

def serialize(root):
    ET.indent(root)
    return b'<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(root,encoding='utf-8')+b'\n'

def gui_config(config,view):
    g=config['gui']; holder=ET.Element('config')
    child(holder,'dialog',name='quick_start',show_again='false')
    window=child(holder,'window'); child(window,'width',g['width_px']); child(window,'height',g['height_px'])
    child(window,'dialog_on_exit','false')
    scene=child(holder,'plugin',filename='MinimalScene',name='3D View')
    common=child(scene,'gz-gui'); child(common,'title','3D View')
    child(common,'property','false',type='bool',key='showTitleBar')
    child(common,'property','docked',type='string',key='state')
    child(scene,'engine','ogre2'); child(scene,'scene','scene')
    child(scene,'camera_pose',numbers(g[view+'_pose']))
    clip=child(scene,'camera_clip'); child(clip,'near',g['near_clip_m']); child(clip,'far',g['far_clip_m'])
    # MinimalScene expects degrees here, unlike SDF pose angles.
    child(scene,'horizontal_fov',math.degrees(g['horizontal_fov_rad'])); child(scene,'view_controller','orbit')
    for filename,name in [('GzSceneManager','Scene Manager'),('InteractiveViewControl','View control'),('CameraTracking','Camera Tracking'),('Screenshot','Screenshot')]:
        plugin=child(holder,'plugin',filename=filename,name=name); common=child(plugin,'gz-gui')
        for key,typ,value in [('state','string','floating'),('width','double','5'),('height','double','5'),('showTitleBar','bool','false')]:
            child(common,'property',value,key=key,type=typ)
    stats=child(holder,'plugin',filename='WorldStats',name='World stats'); common=child(stats,'gz-gui')
    for key,typ,value in [('state','string','floating'),('width','double','290'),('height','double','110'),('showTitleBar','bool','false'),('resizable','bool','false')]:
        child(common,'property',value,key=key,type=typ)
    anchors=child(common,'anchors',target='3D View'); child(anchors,'line',own='right',target='right'); child(anchors,'line',own='bottom',target='bottom')
    for key in ('sim_time','real_time','real_time_factor','iterations'): child(stats,key,'true')
    # Gazebo GUI config is an XML fragment with multiple top-level elements.
    ET.indent(holder)
    return b'<?xml version="1.0"?>\n'+b'\n'.join(ET.tostring(item,encoding='utf-8') for item in holder)+b'\n'

def generated(config):
    root=world_tree(config)
    result={'simulation/worlds/rbi_phase1.sdf':serialize(root)}
    for view in ('perspective','topdown'):
        result[f'simulation/gui/{view}.config']=gui_config(config,view)
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--write',action='store_true')
    args=parser.parse_args(); mismatches=[]
    for name,data in generated(load_config()).items():
        target=ROOT/name
        if args.write:
            target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(data); print('Wrote',name)
        elif not target.is_file() or target.read_bytes()!=data: mismatches.append(name)
    if mismatches: parser.exit(1,'Config/generated-file mismatch: '+', '.join(mismatches)+'\n')
    if not args.write: print('World and GUI configurations match world_config.yaml')

if __name__=='__main__': main()
