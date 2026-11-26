"""Static acceptance checks for the fictional Phase 1C campus."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_ptic_environment import load_config, generated, validate_config
from validate_ptic_environment import check_resources

class EnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=load_config();cls.files=generated(cls.config)
        cls.world=ET.fromstring(cls.files['simulation/worlds/rbi_ptic_environment.sdf'])

    def test_ENV_001_native_sdf_syntax(self):
        env=os.environ.copy();env['SDF_PATH']=str(ROOT/'simulation/models')
        p=subprocess.run(['gz','sdf','-k',str(ROOT/'simulation/worlds/rbi_ptic_environment.sdf')],capture_output=True,text=True,env=env,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr);self.assertIn('Valid.',p.stdout)

    def test_ENV_002_committed_outputs_match_configuration(self):
        for name,data in self.files.items():
            self.assertEqual((ROOT/name).read_bytes(),data,name)
        world=self.world.find('world');self.assertEqual(world.get('name'),self.config['world_name'])
        ground=world.find("model[@name='campus_ground']/link/collision/geometry/box/size")
        self.assertEqual(list(map(float,ground.text.split())),[400,400,.3])
        self.assertEqual(world.findtext('gravity'),'0 0 -9.80665')
        self.assertEqual(world.findtext('wind/linear_velocity'),'0 0 0')
        self.assertIsNone(world.find('spherical_coordinates'))

    def test_ENV_003_local_resources_and_hashes(self):
        result=check_resources(ROOT);self.assertEqual(result['status'],'PASS',result['errors'])
        self.assertGreater(result['references_checked'],200)

    def test_ENV_004_building_dimensions_and_placements(self):
        includes={i.findtext('name'):i for i in self.world.findall('.//include')}
        for b in self.config['buildings']:
            root=ET.fromstring(self.files[f"simulation/models/{b['name']}/model.sdf"])
            size=list(map(float,root.findtext('.//collision/geometry/box/size').split()))
            self.assertEqual(size,b['size_m']);pose=list(map(float,root.findtext('.//collision/pose').split()))
            self.assertAlmostEqual(pose[2]+size[2]/2,b['size_m'][2]);self.assertAlmostEqual(pose[2]-size[2]/2,0)
            self.assertEqual(list(map(float,includes[b['name']].findtext('pose').split()))[:2],b['position_xy_m'])

    def test_ENV_005_material_values(self):
        pbr=0
        for name,data in self.files.items():
            if not name.endswith('.sdf'):continue
            for material in ET.fromstring(data).iter('material'):
                rgba=list(map(float,material.findtext('diffuse').split()))
                self.assertEqual(len(rgba),4);self.assertEqual(rgba[-1],1);self.assertTrue(all(0<=v<=1 for v in rgba))
                for tag in ('roughness','metalness'):
                    for value in material.iter(tag):self.assertTrue(0<=float(value.text)<=1);pbr+=1
        self.assertGreater(pbr,100)

    def test_ENV_006_only_ground_and_building_boxes_collide(self):
        allowed={'simulation/worlds/rbi_ptic_environment.sdf':1}
        allowed.update({f"simulation/models/{b['name']}/model.sdf":1 for b in self.config['buildings']})
        for name,data in self.files.items():
            if not name.endswith('.sdf'):continue
            cols=ET.fromstring(data).findall('.//collision')
            self.assertEqual(len(cols),allowed.get(name,0),name)
            for col in cols:self.assertIsNotNone(col.find('geometry/box'))

    def test_ENV_007_repeatable_generation(self):
        again=generated(copy.deepcopy(self.config));self.assertEqual(self.files,again)
        changed=copy.deepcopy(self.config);changed['seed']+=1
        self.assertNotEqual(self.files['simulation/worlds/rbi_ptic_environment.sdf'],generated(changed)['simulation/worlds/rbi_ptic_environment.sdf'])

    def test_all_profiles_and_lighting_presets_generate(self):
        for profile in self.config['rendering_profiles']:
            for lighting in self.config['lighting_presets']:
                files=generated(self.config,profile,lighting);root=ET.fromstring(files['simulation/worlds/rbi_ptic_environment.sdf'])
                self.assertEqual(root.findtext('world/light/direction'),' '.join(f'{x:.12g}' for x in self.config['lighting_presets'][lighting]['direction']))
                shadows=self.config['rendering_profiles'][profile]['shadows'] and self.config['lighting_presets'][lighting]['shadows']
                self.assertEqual(root.findtext('world/scene/shadows'),str(shadows).lower())
                model=ET.fromstring(files['simulation/models/research_office/model.sdf'])
                self.assertEqual(bool(model.findall('.//pbr')),profile!='LOW')

    def test_rejects_invalid_dimensions_materials_and_georeference(self):
        mutations=[lambda c:c['field'].update(size_m=[0,400]),lambda c:c['buildings'][0].update(size_m=[60,-1,20]),lambda c:c['ground'].update(material='missing'),lambda c:c['materials']['glass'].update(roughness=1.1),lambda c:c['coordinates'].update(geodetic_origin=[13,101]),lambda c:c['lighting_presets']['midday'].update(direction=[0,0,0]),lambda c:c['vegetation'].update(tree_height_range_m=[-1,10])]
        for mutate in mutations:
            c=copy.deepcopy(self.config);mutate(c)
            with self.assertRaises(ValueError):validate_config(c)

    def test_building_parameters_change_generated_dimensions(self):
        c=copy.deepcopy(self.config);c['buildings'][0]['size_m']=[54,28,22]
        f=generated(c);r=ET.fromstring(f['simulation/models/research_office/model.sdf'])
        self.assertEqual(r.findtext('.//collision/geometry/box/size'),'54 28 22')

    def test_grid_is_optional_and_has_no_collision(self):
        self.assertIsNone(self.world.find("world/model[@name='optional_reference_grid']"))
        c=copy.deepcopy(self.config);c['ground']['reference_grid']=True
        r=ET.fromstring(generated(c)['simulation/worlds/rbi_ptic_environment.sdf']);grid=r.find("world/model[@name='optional_reference_grid']")
        self.assertEqual(len(grid.findall('.//visual')),18);self.assertEqual(len(grid.findall('.//collision')),0)

    def test_mesh_indices_are_valid_and_finite(self):
        for name,data in self.files.items():
            if not name.endswith('.obj'):continue
            lines=data.decode().splitlines();vertices=[list(map(float,l.split()[1:])) for l in lines if l.startswith('v ')]
            self.assertTrue(all(math.isfinite(v) for xyz in vertices for v in xyz),name)
            for line in lines:
                if line.startswith('f '):
                    ids=[int(s.split('/')[0]) for s in line.split()[1:]]
                    self.assertEqual(len(ids),3);self.assertTrue(all(1<=i<=len(vertices) for i in ids));self.assertEqual(len(set(ids)),3)

    def test_camera_frustum_contains_complete_field(self):
        # Project four field corners into each overview camera's pinhole frustum.
        for view in ('overview','topdown'):
            c=self.config['gui'];v=c['views'][view];pos=v['position_m'];target=v['look_at_m']
            forward=[t-p for p,t in zip(pos,target)];length=math.sqrt(sum(x*x for x in forward));forward=[x/length for x in forward]
            right=[forward[1],-forward[0],0];rlen=math.hypot(right[0],right[1]);right=[x/rlen for x in right] if rlen else [1,0,0]
            up=[right[1]*forward[2]-right[2]*forward[1],right[2]*forward[0]-right[0]*forward[2],right[0]*forward[1]-right[1]*forward[0]]
            tanh=math.tan(c['horizontal_fov_rad']/2);tanv=tanh/ (c['width_px']/(c['height_px']-80))
            for x in (-200,200):
                for y in (-200,200):
                    d=[x-pos[0],y-pos[1],-pos[2]];depth=sum(a*b for a,b in zip(d,forward))
                    self.assertLessEqual(abs(sum(a*b for a,b in zip(d,right))),depth*tanh,view)
                    self.assertLessEqual(abs(sum(a*b for a,b in zip(d,up))),depth*tanv,view)

    def test_all_instances_are_static(self):
        for model in self.world.findall('.//model')+self.world.findall('.//include'):self.assertEqual(model.findtext('static'),'true')
        self.assertEqual(len(self.world.findall('.//plugin')),3)
        self.assertEqual(len(self.world.findall('.//sensor')),0)

if __name__=='__main__':unittest.main()
