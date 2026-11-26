# Phase 1 test plan

## Phase 1B world validation extension

The main mission world is 400 × 400 m; the legacy sphere fixture below is a
separate unchanged 100 m test asset. Historical SIM test results are retained,
and do not automatically become flight passes when world startup is fixed.

| ID | Acceptance procedure | Required evidence |
| --- | --- | --- |
| WORLD-001 | Validate main SDF using installed `gz sdf -k` | Exit 0 and `Valid.` |
| WORLD-002 | Check visible and collidable ground size and surface elevation | 400 × 400 m, top z=0, agreement with config |
| WORLD-003 | Measure marker-model world poses | A/B horizontal separation 350 m; same ground elevation |
| WORLD-004 | Resolve altitude reference pose above ground | Horizontal reference at 80 m AGL |
| WORLD-005 | Inspect grid positions and extent | 9 lines per axis, 50 m increments, -200…200 m; default GUI grid disabled |
| WORLD-006 | Inspect every model for collisions and motion | Only ground/pad collide; references/grid/labels/boundary/axes are static visual-only |
| WORLD-007 | Start isolated server and inspect output/return behavior | Alive throughout observation; no SDF/physics/transport error |
| WORLD-008 | Capture world clock JSON | At least two strictly increasing timestamps; >50% of requested wall duration advances in sim time |
| WORLD-009 | Discover and receive world topics | World-specific clock and stats listed and populated |
| WORLD-010 | Run two new servers with identical world hash and seed | Both startup/discovery/clock checks pass; this is startup repeatability, not deterministic flight |
| WORLD-011 | Start both saved GUI views and inspect final render captures | Complete field, grid, boundary, references and axes visible; GUI alive, no fatal errors |

Execute from the project root with new output directories:

```bash
python3 scripts/build_world.py
python3 -m unittest discover -s tests -v
python3 scripts/validate_world_runtime.py --output-dir logs/world_check_new --duration 10 --repetitions 2
python3 scripts/validate_world_runtime.py --output-dir logs/perspective_new --duration 10 --repetitions 1 --gui perspective
python3 scripts/validate_world_runtime.py --output-dir logs/topdown_new --duration 10 --repetitions 1 --gui topdown
```

The runner captures final screenshots after the observation window. A service
acknowledgement or existing PNG alone is not a visual pass: inspect the final
image for a complete, nonblank scene. Raw stdout/stderr, commands, clock/stats,
CPU/RSS samples and shutdown results are saved per run. Preserve preliminary
failures and capture provenance. No actuator or flight command is transmitted.

Performance reporting must identify observation duration, process scope and the
macOS ps averaging limitation. Do not infer dynamic-aircraft or camera-inference
performance from this static scene. See [executed Phase 1B results](phase1b_results.md).

## Original Phase 1 procedures

Only mark a test PASS after its defined procedure and acceptance checks execute
successfully. BLOCKED means a known prerequisite prevents the test. NOT RUN means
it was not attempted and no execution result exists. FAIL means the procedure
ran and violated an acceptance criterion. A parser pass, software unit test, or
synthetic plot is never evidence of a flight pass.

Use a new log directory per run. Record UTC start time, OS/architecture, component
versions, source commit IDs when applicable, SDF SHA-256, seed 42, parameters,
simulation step and GUI/server options. Keep raw telemetry as well as derived
CSV. Do not mix real hardware into any test.

| ID | Procedure | Acceptance and evidence |
| --- | --- | --- |
| SIM-001 | Run `scripts/check_environment.sh`; inspect official compatibility documents | Inventory and missing dependencies recorded accurately. This is inspection completion, not flight readiness. |
| SIM-002 | Run `gz sdf -k` on baseline and physics fixture | Exit 0 and explicit `Valid.` on both; no schema errors. |
| SIM-003 | Run bounded server check, then separate GUI from normal Terminal | Server advances 50 iterations and exits cleanly without transport/plugin errors; GUI shows ground/grid/home/pad. Record screenshot and console. |
| SIM-004 | Run sphere physics fixture and record initial free fall plus settled contact | Free-fall height error < 0.02 m during 0.05–0.8 s; settled center error < 0.01 m and vertical speed < 0.02 m/s during 3–5 s; horizontal drift < 0.01 m; healthy stats. |
| SIM-005 | Subscribe to stats/odometry; separately receive SITL heartbeat, attitude and local position | At least 30 s of nonempty finite increasing telemetry; correct frame/time units; FCU mode observed, healthy stats, raw logs preserved. Unknown fields are explicitly unavailable. |
| SIM-006 | Use official generic Iris with operator-supervised SITL hover; record >= 30 s after settling | No divergent trend or uncommanded mode changes; inspect altitude/attitude/position/velocity and report RMS/peak drift over a preselected steady window. Provisional generic observation bounds must be agreed before acceptance; never infer hardware capability. |
| SIM-007 | Generate labelled synthetic fixture and analyze it; later analyze actual logs separately | Four valid charts, provenance labels, mode/health timeline and numeric metrics; malformed logs rejected. Synthetic execution passes the analysis pipeline only. |
| SIM-008 | Observe one documented SITL failure injection after baseline hover is established | Record initial parameter snapshot, trigger and recovery times, FCU mode/STATUSTEXT/status, and configured failsafe action. Expected action must match the selected firmware/parameters; a stream timeout alone is not an FCU failsafe. |
| SIM-009 | Repeat the same real simulation at least twice with identical world, seed, source revisions and parameters | Align simulation-time samples; compare physics fixture height within 1e-5 m and document gaps. For hover, compare declared steady-window metrics with predeclared tolerance. Keep both raw runs. Synthetic regeneration is a separate determinism check only. |

## Baseline checks

```bash
./scripts/check_environment.sh
python3 scripts/validate_phase1.py
python3 -m unittest discover -s tests -v
```

`validate_phase1.py` has bounded subprocesses and saves each command, exit code,
timeout and output. It returns 2 for any non-PASS result. A blocked local bind is
reported separately and a Gazebo process with transport errors cannot be passed
just because it returns zero.

## Physics fixture acquisition (requires local sockets)

Stop any other server in the same partition. From the project root in Terminal 1,
start paused; do not use `-r`:

```bash
export GZ_PARTITION=rbi_phase1
export GZ_IP=127.0.0.1
gz sim -s -v 4 --seed 42 tests/physics_probe.sdf
```

In Terminal 2, start the observer before unpausing:

```bash
python3 companion/monitoring/gazebo_monitor.py --model physics_probe \
  --duration 15 --output-dir logs/physics_run_01
```

In Terminal 3 with the same partition and GZ_IP, unpause only this simulation:

```bash
export GZ_PARTITION=rbi_phase1
export GZ_IP=127.0.0.1
gz service -s /world/rbi_phase1/control --reqtype gz.msgs.WorldControl \
  --reptype gz.msgs.Boolean --timeout 1000 --req 'pause: false'
```

Start unpaused time promptly enough that at least five simulated seconds are
captured. The 15 s monitor duration is wall time. Evaluate the captured file:

```bash
python3 control_research/offline_analysis/check_physics.py logs/physics_run_01/telemetry.csv
```

The assessor requires early and late sample coverage and rejects synthetic
provenance. It validates only the analytical sphere fixture, not propeller thrust,
aircraft drag, inertia identification, or autopilot tuning. Repeat with a fresh
server and new output directory for SIM-009. No physics result exists yet.

## Hover and failsafe observation

First prove the unchanged upstream Iris example works, then the composed RBI
world. Select a steady hover window and a nominal height away from the landing
pad edge. Record the requested reference explicitly and observe actual FCU mode
from the separate SITL stream. Missing references, estimator/world origin
offsets, and timing gaps must be resolved before comparing tracking errors.

For failsafe work, choose a single documented **SITL-only** sensor/RC failure
supported by the exact firmware revision. Inspect its parameter definition and
configured action first. Use a fresh parameter snapshot and one fault at a time,
then restore and verify recovery. This repository supplies observation tools and
a test procedure, not an automatic failure injector or flight-command sender.
Stopping/pausing Gazebo can test logger stale/paused detection, but that is only
simulation-health testing and must not be reported as an ArduPilot failsafe test.

## Offline data limitations

Synthetic trajectories are deterministic analytic curves, not integrations of
Gazebo or the aircraft equations. Their synthetic stale label exercises chart
and transition reporting; it is not an observed telemetry failure. No gains,
overshoot specification, or flight-performance claim should be based on them.
