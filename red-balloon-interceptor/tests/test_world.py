"""Independent geometry/physics checks plus config drift and GUI framing guards."""
import math
from pathlib import Path
import re
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_world import load_config, generated

def vector(node,path):
    return [float(x) for x in node.findtext(path).split()]

class WorldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=load_config()
        cls.world=ET.parse(ROOT/'simulation/worlds/rbi_phase1.sdf').getroot().find('world')

    def model(self,name):
        return self.world.find(f"model[@name='{name}']")

    def test_WORLD_001_sdf_syntax(self):
        result=subprocess.run(['gz','sdf','-k',str(ROOT/'simulation/worlds/rbi_phase1.sdf')],
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Valid.',result.stdout)

    def test_WORLD_002_field_dimensions_and_surface(self):
        c=self.config['field']; model=self.model('ground_plane')
        self.assertEqual((c['length_x_m'],c['width_y_m']),(400,400))
        for kind in ('visual','collision'):
            size=vector(model,f'link/{kind}/geometry/box/size')
            pose=vector(model,f'link/{kind}/pose')
            self.assertEqual(size,[c['length_x_m'],c['width_y_m'],c['slab_thickness_m']])
            self.assertAlmostEqual(pose[2]+size[2]/2,c['ground_elevation_m'])

    def test_WORLD_003_marker_separation(self):
        a=vector(self.model('survey_reference_a'),'pose')
        b=vector(self.model('survey_reference_b'),'pose')
        separation=math.hypot(b[0]-a[0],b[1]-a[1])
        self.assertEqual(separation,350)
        self.assertEqual(separation,self.config['survey_references']['separation_m'])
        self.assertEqual(a[2],b[2]); self.assertEqual((a[0]+b[0])/2,0)

    def test_WORLD_004_altitude_reference(self):
        model=self.model('altitude_reference')
        top=vector(model,"link/visual[@name='top_reference']/pose")[2]
        ground=self.config['field']['ground_elevation_m']
        height=vector(model,'pose')[2]+top-ground
        self.assertEqual(height,80)
        self.assertEqual(height,self.config['altitude_reference']['height_agl_m'])

    def test_WORLD_005_grid_spacing_extent_and_count(self):
        self.assertEqual(self.world.findtext('scene/grid'),'false')
        spacing=self.config['grid_spacing_m']; self.assertEqual(spacing,50)
        grid=self.model('reference_grid')
        for axis,index in [('x',1),('y',0)]:
            visuals=[v for v in grid.findall('link/visual') if v.get('name').startswith(axis+'_')]
            coordinates=sorted(vector(v,'pose')[index] for v in visuals)
            self.assertEqual(coordinates,[-200,-150,-100,-50,0,50,100,150,200])
            self.assertTrue(all(math.isclose(b-a,spacing) for a,b in zip(coordinates,coordinates[1:])))
            for v in visuals:
                self.assertEqual(vector(v,'geometry/box/size')[0 if axis=='x' else 1],400)

    def test_WORLD_006_only_ground_and_pad_collide(self):
        collidable={m.get('name') for m in self.world.findall('model') if m.findall('.//collision')}
        self.assertEqual(collidable,{'ground_plane','landing_pad'})
        for model in self.world.findall('model'):
            self.assertEqual(model.findtext('static'),'true',model.get('name'))
        self.assertEqual(self.world.findall('.//actor'),[])
        self.assertEqual(self.world.findall('.//sensor'),[])
        self.assertEqual(self.world.findall('.//uri'),[])

    def test_config_matches_generated_sdf_and_gui(self):
        for name,data in generated(self.config).items():
            self.assertEqual((ROOT/name).read_bytes(),data,f'Regenerate with scripts/build_world.py --write: {name}')

    def test_environment_config_matches_sdf(self):
        self.assertEqual(self.world.get('name'),self.config['world_name'])
        self.assertEqual(vector(self.world,'gravity'),self.config['gravity_mps2'])
        self.assertEqual(vector(self.world,'wind/linear_velocity'),[0,0,0])
        self.assertEqual(vector(self.world,'scene/ambient'),self.config['lighting']['ambient_rgba'])
        self.assertEqual(vector(self.world,'scene/background'),self.config['lighting']['background_rgba'])
        self.assertEqual(self.world.findtext('scene/shadows'),'false')
        self.assertFalse(any('Wind' in p.get('name','') for p in self.world.findall('plugin')))

    def test_boundary_matches_field_edges(self):
        model=self.model('mission_boundary')
        for name,index,value in [('north',1,200),('south',1,-200),('east',0,200),('west',0,-200)]:
            self.assertEqual(vector(model,f"link/visual[@name='{name}']/pose")[index],value)

    def test_gui_initial_frustum_contains_entire_field(self):
        g=self.config['gui']
        # Conservative allowance for the window toolbar. +X is camera forward.
        aspect=g['width_px']/(g['height_px']-80)
        for view in ('perspective','topdown'):
            text=(ROOT/f'simulation/gui/{view}.config').read_text()
            gui=ET.fromstring('<root>'+re.sub(r'<\?xml[^>]+\?>','',text)+'</root>')
            scene=gui.find("plugin[@filename='MinimalScene']")
            self.assertAlmostEqual(float(scene.findtext('horizontal_fov')),math.degrees(g['horizontal_fov_rad']))
            self.assertEqual(float(scene.findtext('camera_clip/far')),g['far_clip_m'])
            cx,cy,cz,roll,pitch,yaw=vector(scene,'camera_pose')
            self.assertEqual(roll,0)
            points=[(x,y,0) for x in (-200,200) for y in (-200,200)]+[(0,100,91)]
            for x,y,z in points:
                dx,dy,dz=x-cx,y-cy,z-cz
                forward=math.cos(pitch)*(math.cos(yaw)*dx+math.sin(yaw)*dy)-math.sin(pitch)*dz
                left=-math.sin(yaw)*dx+math.cos(yaw)*dy
                up=math.sin(pitch)*(math.cos(yaw)*dx+math.sin(yaw)*dy)+math.cos(pitch)*dz
                self.assertGreater(forward,g['near_clip_m'])
                self.assertLess(forward,g['far_clip_m'])
                self.assertLess(abs(left/forward),math.tan(g['horizontal_fov_rad']/2),view)
                self.assertLess(abs(up/forward),math.tan(g['horizontal_fov_rad']/2)/aspect,view)

if __name__=='__main__': unittest.main()
