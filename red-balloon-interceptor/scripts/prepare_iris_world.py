#!/usr/bin/env python3
"""Compose the baseline with an EXISTING official Iris model; never downloads."""
import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source = args.plugin_source.resolve()
    model = source / 'models/iris_with_ardupilot/model.sdf'
    if not model.is_file():
        parser.error(f'Official Iris model missing: {model}')
    root = ET.parse(ROOT / 'simulation/worlds/rbi_phase1.sdf').getroot()
    world = root.find('world')
    for filename, name in [('gz-sim-imu-system', 'Imu'), ('gz-sim-navsat-system', 'NavSat')]:
        ET.SubElement(world, 'plugin', filename=filename, name=f'gz::sim::systems::{name}')
    coordinates = ET.SubElement(world, 'spherical_coordinates')
    # Official upstream SITL example origin; not a real aircraft location.
    for key, value in [('surface_model', 'EARTH_WGS84'), ('world_frame_orientation', 'ENU'),
                       ('latitude_deg', '-35.363262'), ('longitude_deg', '149.165237'),
                       ('elevation', '584'), ('heading_deg', '0')]:
        ET.SubElement(coordinates, key).text = value
    include = ET.SubElement(world, 'include')
    # Resolve through GZ_SIM_RESOURCE_PATH; avoid percent-encoded absolute paths
    # in workspaces whose names contain spaces.
    ET.SubElement(include, 'uri').text = 'model://iris_with_ardupilot'
    ET.SubElement(include, 'name').text = 'iris'
    ET.SubElement(include, 'pose').text = '0 0 0.3 0 0 0'
    odom = ET.SubElement(include, 'plugin', filename='gz-sim-odometry-publisher-system',
                         name='gz::sim::systems::OdometryPublisher')
    for key, value in [('dimensions', '3'), ('odom_frame', 'world'),
                       ('robot_base_frame', 'iris/base_link'),
                       ('odom_topic', '/model/iris/odometry'), ('odom_publish_frequency', '50')]:
        ET.SubElement(odom, key).text = value
    ET.indent(root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('xb') as stream:
        ET.ElementTree(root).write(stream, encoding='utf-8', xml_declaration=True)
    print(args.output)

if __name__ == '__main__':
    main()
