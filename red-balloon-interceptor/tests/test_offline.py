"""Meaningful checks for coordinate transforms, provenance, timing and artifacts."""
import csv
import math
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'analysis'),str(ROOT/'companion/monitoring')]
from flight_data import FIELDS, read_csv, metrics, position_errors
from generate_synthetic_data import generate
from plot_flight_data import plot
from gazebo_monitor import JSONStream, odometry_row
from mavlink_monitor import normalize

class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.csv=generate(self.directory/'synthetic.csv')

    def rewrite(self,rows):
        with self.csv.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=FIELDS)
            writer.writeheader(); writer.writerows(rows)

    def test_synthetic_fixture_is_repeatable_and_labelled(self):
        second=generate(self.directory/'second.csv')
        self.assertEqual(self.csv.read_bytes(),second.read_bytes())
        summary=metrics(read_csv(self.csv))
        self.assertTrue(summary['synthetic']); self.assertEqual(summary['samples'],601)
        self.assertEqual(summary['reference_coverage_fraction'],1)

    def test_time_reset_is_rejected(self):
        rows=read_csv(self.csv); rows[2]['timestamp_s']=0
        self.rewrite(rows)
        with self.assertRaisesRegex(ValueError,'timestamps'): read_csv(self.csv)

    def test_non_finite_is_rejected(self):
        rows=read_csv(self.csv); rows[2]['z_m']=float('nan'); self.rewrite(rows)
        with self.assertRaisesRegex(ValueError,'non-finite'): read_csv(self.csv)

    def test_mixed_provenance_is_rejected(self):
        rows=read_csv(self.csv); rows[2]['data_source']='gazebo_odometry'; self.rewrite(rows)
        with self.assertRaisesRegex(ValueError,'provenance'): read_csv(self.csv)

    def test_missing_reference_is_not_zero_error(self):
        rows=read_csv(self.csv)
        for row in rows:
            for axis in 'xyz': row[f'reference_{axis}_m']=None
        self.assertTrue(all(v is None for v in position_errors(rows)))
        self.assertIsNone(metrics(rows)['position_rmse_m'])

    def test_partial_reference_is_rejected(self):
        rows=read_csv(self.csv); rows[2]['reference_z_m']=None; self.rewrite(rows)
        with self.assertRaisesRegex(ValueError,'all three'): read_csv(self.csv)

    def test_known_position_error(self):
        rows=read_csv(self.csv)
        rows[0].update(x_m=3,y_m=4,z_m=2)
        self.assertEqual(position_errors(rows)[0],5)

    def test_stream_handles_fragmented_and_concatenated_json(self):
        decoder=JSONStream()
        self.assertEqual(decoder.feed('{"pose":'),[])
        self.assertEqual(decoder.feed('{}}\n{"value":2}'),[{'pose':{}},{'value':2}])

    def message(self):
        return {'header':{'stamp':{'sec':'1','nsec':500000000},
                          'data':[{'key':'frame_id','value':['world']}]},
                'pose':{'position':{'x':3,'y':4,'z':2},
                        'orientation':{'z':math.sqrt(0.5),'w':math.sqrt(0.5)}},
                'twist':{'linear':{'x':1}}}

    def test_body_velocity_is_rotated_to_world(self):
        row=odometry_row(self.message(),'RUNNING')
        self.assertAlmostEqual(row['vx_mps'],0)
        self.assertAlmostEqual(row['vy_mps'],1)
        self.assertAlmostEqual(row['yaw_rad'],math.pi/2)
        self.assertEqual(row['timestamp_s'],1.5)
        self.assertEqual(row['flight_mode'],'UNAVAILABLE_NO_FCU')
        self.assertEqual(row['reference_x_m'],'')

    def test_invalid_orientation_is_rejected(self):
        message=self.message(); message['pose']['orientation']={}
        with self.assertRaisesRegex(ValueError,'quaternion'): odometry_row(message,'RUNNING')

    def test_wrong_odometry_frame_is_rejected(self):
        message=self.message(); message['header']['data']=[]
        with self.assertRaisesRegex(ValueError,'frame_id'): odometry_row(message,'RUNNING')

    def test_ned_to_enu_and_frd_to_flu(self):
        position=SimpleNamespace(time_boot_ms=1000,x=10,y=20,z=-3,vx=1,vy=2,vz=-0.5)
        attitude=SimpleNamespace(roll=0.1,pitch=0.2,yaw=0)
        row=normalize(position,attitude,'LOITER')
        self.assertEqual((row['x_m'],row['y_m'],row['z_m']),(20,10,3))
        self.assertEqual((row['vx_mps'],row['vy_mps'],row['vz_mps']),(2,1,0.5))
        self.assertAlmostEqual(row['yaw_rad'],math.pi/2)
        self.assertEqual(row['pitch_rad'],-0.2)
        self.assertEqual(row['roll_rad'],0.1)
        self.assertEqual(row['simulation_health'],'UNKNOWN_GAZEBO')

    def test_all_svg_artifacts_and_provenance(self):
        output=self.directory/'plots'
        summary=plot(read_csv(self.csv),output,'svg')
        self.assertEqual(summary['plot_backend'],'svg')
        images=list(output.glob('*.svg')); self.assertEqual(len(images),4)
        for image in images:
            self.assertEqual(ET.parse(image).getroot().tag,'{http://www.w3.org/2000/svg}svg')
            self.assertIn('SYNTHETIC TEST DATA',image.read_text())
        self.assertTrue((output/'metrics.json').is_file())
        self.assertIn('SYNTHETIC_STALE',(output/'index.html').read_text())
        with self.assertRaises(FileExistsError): plot(read_csv(self.csv),output,'svg')

    def test_baseline_world_geometry(self):
        world=ET.parse(ROOT/'simulation/worlds/rbi_phase1.sdf').getroot().find('world')
        self.assertEqual(world.get('name'),'rbi_phase1')
        self.assertEqual(world.findtext('gravity'),'0 0 -9.80665')
        self.assertEqual(world.findtext('wind/linear_velocity'),'0 0 0')
        self.assertEqual(world.findtext("model[@name='ground_plane']/link/collision/geometry/box/size"),'400 400 0.2')
        self.assertEqual(len(world.findall("model[@name='reference_grid']/link/visual")),18)
        self.assertEqual(world.findall('.//uri'),[])

if __name__=='__main__': unittest.main()
