# Historical Phase 1 test results — 2026-11-26

These are the preserved results of the earlier restricted session. Current
400 m world startup, clock, topics, GUI and WORLD-001…011 results are documented
in [Phase 1B results](phase1b_results.md). The earlier BLOCKED entries below are
historical evidence, not the current world-runtime status. Flight/hover/failsafe
integration has still not been executed.

| Test | Status | Executed evidence and scope |
| --- | --- | --- |
| SIM-001 Environment verification | PASS | OS, ARM64, existing Gazebo versions, compiler/build tools and dependencies inspected; official compatibility reviewed. `logs/environment_inspection.txt`. Integration readiness remains blocked. |
| SIM-002 SDF validation | PASS | Both project baseline and physics fixture returned exit 0 and `Valid.`. `logs/validation_initial/baseline_sdf.log`, `physics_sdf.log`. |
| SIM-003 World loading | BLOCKED | Project SDF parsed and DART plugin loaded, but transport could not bind local sockets. Bounded server timed out and was terminated. GUI rendering was not verified. `logs/validation_initial/world_server_load.log`. |
| SIM-004 Physics validation | BLOCKED | No successfully running server/real telemetry. Analytical fixture and evaluator exist, but free fall/contact was not measured. |
| SIM-005 Telemetry availability | BLOCKED | Gazebo receive-only probe ran for 3 wall seconds with no data and reported stale odometry. MAVLink probe stopped on missing pymavlink before any socket. No SITL instance available. |
| SIM-006 Hover stability observation | BLOCKED | Official Iris/SITL/plugin are not locally available and world execution is blocked. No hover or stability claim. |
| SIM-007 Offline log analysis | PASS | 601 explicitly synthetic samples analyzed; four SVG charts, HTML timeline and metrics generated. Only pipeline behavior is passed; no actual flight log analyzed. |
| SIM-008 Failsafe observation | BLOCKED | No running FCU simulation. No failure injection or FCU failsafe observed. Synthetic health label is not evidence of a failsafe. |
| SIM-009 Repeatability | BLOCKED | Real repeated simulation unavailable. Synthetic CSV regeneration is byte-identical in a separate unit test, not a pass for repeated physics or flight. |

Additional executed software checks: **14/14 unit tests PASS**. They cover
synthetic reproducibility/provenance, body/world velocity rotation, NED/ENU and
FRD/FLU conversion, fragmented JSON, timestamp resets, non-finite values, missing
and partial references, known error magnitude, world geometry, SVG structure,
status timeline, and refusal to overwrite outputs. See `logs/unit_tests_final.txt`.

The optional Iris composer missing-source guard and physics evaluator synthetic
rejection were executed successfully as negative checks. Neither is a flight or
physics execution result. Evidence: `logs/negative_checks.txt`.

Not run: Matplotlib/Pandas rendering backend, live MAVLink parsing, native plugin
build, SITL build, actual Iris world composition/load, flight, real failsafe,
rendered plot review and GUI visual review. The browser inspection host was
unavailable. SVG files were parsed as XML and checked for data/provenance labels.

One initial physics SDF validation exposed duplicate visual/collision names in
the sphere fixture. The names were corrected and validation rerun successfully.
The final files, not the first draft, are represented by SIM-002 PASS. Initial
script execute permissions were also corrected before final execution.

All test output paths refer to this project root. `logs/validation_initial/results.json`
retains the exact bounded command, return code, timeout and output. No system
packages were installed, no existing user source was overwritten, and no real
hardware flight command was sent.
