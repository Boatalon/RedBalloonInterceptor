# Read-only telemetry

## Gazebo truth and health

After a world containing an OdometryPublisher is running, use a fresh directory:

```bash
python3 companion/monitoring/gazebo_monitor.py \
  --model iris --duration 60 --output-dir logs/iris_observation \
  --reference 0 0 2
```

`--reference` is an explicit analysis reference in world meters. It does not
command the aircraft. Omit it when no reference is recorded; position error will
be unavailable. The baseline environment has no odometry publisher because it
has no dynamic aircraft. Use `physics_probe` for the separate sphere test or
`iris` for the generated optional Iris world.

Subscriptions are `/model/<name>/odometry` and `/world/rbi_phase1/stats`. Run with
the same `GZ_PARTITION` as the server (default `rbi_phase1`). The Gazebo odometry
plugin must use `dimensions=3`, `odom_frame=world`, no pose offsets, and a named
topic. The included fixture and Iris composer set these fields. Gazebo's body
linear twist is transformed into world axes by the monitor. See the
[upstream OdometryPublisher implementation](https://github.com/gazebosim/gz-sim/blob/gz-sim8/src/systems/odometry_publisher/OdometryPublisher.cc).

Files: `telemetry.csv`, `raw.jsonl`, `health.jsonl`, `transport.stderr.log`.
Health events use monotonic wall elapsed time, so a frozen simulation clock does
not hide a stalled stream. Odometry and stats older than two wall seconds are
reported stale. Missing stats are unknown. The flight mode is
`UNAVAILABLE_NO_FCU`: Gazebo truth alone cannot tell the ArduPilot mode.

## Optional SITL MAVLink estimate and flight mode

This receiver requires `pymavlink`, which is absent in the inspected environment.
No package installation was attempted. A future project-local virtual environment
can supply it, without changing system Python. Once a SITL instance already
forwards telemetry to `127.0.0.1:14560`:

```bash
python3 companion/monitoring/mavlink_monitor.py --sitl-only \
  --port 14560 --duration 60 --output-dir logs/sitl_observation
```

The script uses a raw UDP receive socket and a decoder with no output transport.
It filters system/component ID 1/1 by default. It never connects to serial devices,
sends commands, requests streams, or changes parameters. `HEARTBEAT`, `ATTITUDE`,
and `LOCAL_POSITION_NED` must already be in the incoming stream. Attitude must be
within 250 ms of the position timestamp and receive time; heartbeat must be under
2 s old. Stale/missing pairs produce no fabricated row. Original datagrams are
preserved as hex in `packets.jsonl`. Data source is `sitl_mavlink_estimate` and
simulation health is `UNKNOWN_GAZEBO`, because FCU heartbeat is not Gazebo health.
Flight mode comes from the received heartbeat. Raw packets preserve SYS_STATUS
and STATUSTEXT for subsequent failsafe investigation. Live decoding is **not
validated** yet; the dependency and socket blockers remain.

## CSV schema

| Column | Definition |
| --- | --- |
| `timestamp_s` | Simulation timestamp for Gazebo; FCU boot time for SITL; seconds |
| `x_m`, `y_m`, `z_m` | World ENU position; z is altitude above the local origin |
| `vx_mps`, `vy_mps`, `vz_mps` | World ENU velocity, m/s |
| `roll_rad`, `pitch_rad`, `yaw_rad` | ENU/FLU Euler angles; radians; yaw is wrapped |
| `flight_mode` | Observed FCU mode, explicit unavailability, or synthetic label |
| `simulation_health` | Observed stats state or explicitly unknown/synthetic label |
| `data_source` | Exactly one provenance label per file |
| `reference_x_m`, `reference_y_m`, `reference_z_m` | Optional explicit reference; all three or none |
| `rtf` | Optional Gazebo real time factor; blank if unavailable |

Simulation time resets require a new file. The offline validator requires at least
two finite samples and strictly increasing timestamps. Full flight performance
must not be inferred from the synthetic fixture. The two monitor clocks and
origins are not automatically synchronized or georeferenced.
