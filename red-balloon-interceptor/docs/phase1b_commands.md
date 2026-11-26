# Phase 1B commands and evidence

Executed in the existing project at
`/Users/papajhon/Project/Red Balloon Intercepter/red-balloon-interceptor`.
Evidence root: `logs/phase1b-20261126T220119/`. New outputs use unique directories;
the existing Phase 1 logs, plots, Excel files and hardware reference were not
overwritten. No repository was initialized and no system package installed.

## Inspection and cleanup

Executed `pwd`, `rg --files`, scoped ancestor AGENTS.md checks, `sed`/`cat` of the
previous source/tests/reports, `sw_vers`, `uname -m`, `gz sim --versions`,
`gz sdf --versions`, `python3 --version`, `sysctl -n hw.memsize machdep.cpu.brand_string`,
and `ps -axo pid,ppid,%cpu,rss,etime,args`. A Python UDP loopback bind to
127.0.0.1:0 succeeded. The source tree was copied into the evidence `before/`
directory before editing; pre-existing evidence and protected files were hashed.

The old diagnostic PID 32940 was rechecked against its exact command, sent
SIGINT/SIGTERM as needed, and confirmed absent. The unrelated shapes server was
not stopped. Its later absence was observed after the user resumed work.

Official documentation was read with web research. Selected upstream source
files were downloaded read-only with Python urllib into `upstream/`, without
executing the macOS installer. Installed GUI config, SDFormat scene schema and
plugin strings were inspected to verify supported camera/grid settings.

## Generation and offline checks

```bash
python3 scripts/build_world.py --write
python3 scripts/build_world.py
python3 -m unittest discover -s tests -v
gz sdf -k tests/physics_probe.sdf
bash -n scripts/launch_world.sh scripts/check_environment.sh
python3 -m compileall -q scripts tests
```

The unit suite also invokes `gz sdf -k simulation/worlds/rbi_phase1.sdf` with an
absolute path. Tests were rerun after visualization and parser changes; final
output is `unit_tests_final.txt` (26 passed). Generation was repeated after
adjusting label/grid visibility, camera clipping, and disabling the default GUI
grid. Early snapshots and outputs were retained.

## Runtime checks

```bash
python3 scripts/validate_world_runtime.py \
  --output-dir logs/phase1b-20261126T220119/final_runtime --duration 10 --repetitions 2
python3 scripts/validate_world_runtime.py \
  --output-dir logs/phase1b-20261126T220119/final_perspective --duration 10 --repetitions 1 --gui perspective
python3 scripts/validate_world_runtime.py \
  --output-dir logs/phase1b-20261126T220119/final_topdown --duration 10 --repetitions 1 --gui topdown
python3 scripts/validate_phase1.py \
  --output-dir logs/phase1b-20261126T220119/legacy_validator
./scripts/launch_world.sh server --iterations 50
```

The launcher smoke check used a unique `GZ_PARTITION` and a 20 s subprocess
timeout. Its exact command/partition/exit code are in `launcher_server.command.json`.
Earlier runtime trials used `runtime/`, `gui_perspective/`, `gui_final/`,
`gui_perspective_v2/`, `gui_topdown/`, `perspective_verified/` and
`topdown_verified/`; these are preliminary evidence, not silently replaced final
results. The 45 s evidence-reader failure is preserved with a separate reanalysis.

For each trial the runner executes the following command forms, with exact
resolved arguments saved to JSON alongside stdout/stderr:

```bash
gz sim -s -r -v 4 --seed 42 /absolute/path/to/rbi_phase1.sdf
gz topic -l
gz topic -e --json-output -t /world/rbi_phase1/clock -d 10
gz topic -e --json-output -t /world/rbi_phase1/stats -d 10
ps -axo pid=,pgid=,%cpu=,rss=,command=
gz sim -g -v 4 --gui-config /absolute/path/to/perspective.config
gz service -s /gui/screenshot --reqtype gz.msgs.StringMsg \
  --reptype gz.msgs.Boolean --timeout 3000 --req 'data: "/absolute/evidence/screenshots"'
```

Each server has a new private partition and GZ_IP=127.0.0.1. Screenshot requests
save only a render image. Owned process groups receive bounded shutdown; no
flight or actuator message is sent. Actual PNGs were opened for visual inspection
and copied unedited to `docs/screenshots/` with provenance hashes. CUA could not
identify the unbundled gz app by name, so the purpose-built Gazebo Screenshot
service was used instead of desktop automation.

## Dependency/toolchain assessment

Executed CMake/Clang/Git version probes, `brew list --versions`, pkg-config checks
for gz-sim8/OpenCV/GStreamer, and Python import-spec checks. Configured, built and
ran a small C++17 program under `compiler_probe/` using existing CMake and Clang.
Then configured only the dependency-discovery prefix of upstream plugin CMake
under `plugin_dependency_probe/`, first normally and then with:

```text
GZ_VERSION=harmonic
cmake -S <probe> -B <probe>/build_qt -DCMAKE_PREFIX_PATH=/opt/homebrew/opt/qt@5
```

The existing Qt prefix fixes its discovery warning; configuration still stops
at missing OpenCV. Separate pkg-config probes establish missing GStreamer.
Neither probe compiles the ArduPilot plugin or SITL. No brew install, pip install,
Python upgrade/downgrade, sudo, hardware serial command or firmware operation was run.
