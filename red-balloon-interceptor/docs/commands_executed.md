# Execution record — 2026-11-26

The commands below were actually executed. Grouped inspection commands sometimes
ran in the same child shell. Commands in `sitl_compatibility.md` are future recipes
and must not be confused with this record. No brew install/upgrade, pip install,
sudo, firmware upload, arming, mode change, or flight-command operation was run.

## Initial read-only inspection

```text
pwd
sw_vers
uname -m
uname -a
rg --files --hidden [workspace source/document filters]
ls -la
ls /Applications
ls "$HOME/Applications"
command -v gz gazebo brew python3 git cmake clang clang++
ancestor AGENTS.md existence/read checks
brew --version
brew list --versions
python3 --version
/usr/bin/python3 --version
python3 -m pip --version
git --version
cmake --version
clang --version
xcode-select -p
sysctl -n hw.memsize hw.model hw.ncpu
ls -l /opt/homebrew/bin/gz
file /opt/homebrew/opt/gz-sim8/lib/libgz-sim8.dylib
```

`sysctl` was denied. Python `importlib.util.find_spec` checked numpy, pandas,
matplotlib, pymavlink and yaml; `import numpy` verified the available NumPy
version. Standard ArduPilot paths, executables and the Gazebo Fuel cache were
checked without recursively searching unrelated user files.

```text
/opt/homebrew/bin/gz --versions
/opt/homebrew/bin/gz sim --versions
/opt/homebrew/bin/gz sdf --versions
/opt/homebrew/bin/gz sim --help
/opt/homebrew/bin/gz sdf --help
/opt/homebrew/bin/gz topic --help
pkg-config --exists opencv4
pkg-config --exists gstreamer-1.0 gstreamer-app-1.0
cmake --find-package -DNAME=OpenCV -DCOMPILER_ID=Clang -DLANGUAGE=CXX -DMODE=EXIST
curl -I --max-time 15 https://raw.githubusercontent.com/ArduPilot/ardupilot_gazebo/main/CMakeLists.txt
python3 -m pip cache list
```

The OpenCV and GStreamer probes failed; curl reported name resolution failure;
pip cache inspection reported its cache unavailable under sandbox permissions.
The CMake probe created only a local `CMakeFiles` directory, moved into
`logs/cmake_probe/` afterward. No package was installed. Official documentation
and upstream source were separately read through the web research tool.

Installed `quadcopter.sdf`, `multicopter_velocity_control.sdf`, Gazebo headers and
CMake directories were inspected with `sed`, `rg` and `ls`. The X3 example uses
Fuel assets unavailable in the inspected cache; it was not presented as a tested
flight simulation. The initial diagnostic below stalled at blocked transport:

```bash
/opt/homebrew/bin/gz sim -s -r --iterations 10 -v 4 \
  /opt/homebrew/opt/gz-sim8/share/gz/gz-sim8/worlds/empty.sdf
```

A direct Python `socket.bind(('127.0.0.1', 0))` returned permission denied.
`ps` and the exact-command `pkill` cleanup attempt also could not enumerate
processes. See the environment report for the unresolved initial diagnostic
cleanup; subsequent process launches had explicit timeouts and owned groups.

## Implementation

Created the new project directories with `mkdir -p`. New text/code files were
written with patches; a local Python XML builder wrote the two SDF files using
exclusive creation. `chmod +x` made launch/inspection scripts executable. No
pre-existing user file was opened for writing. Initial script permission and
sphere duplicate-name validation errors were fixed before the final checks.

## Final validation commands

Executed from the new project root:

```bash
./scripts/check_environment.sh > logs/environment_inspection.txt 2>&1
./scripts/launch_world.sh validate > logs/sdf_validation.txt 2>&1
gz sdf -k tests/physics_probe.sdf > logs/physics_sdf_validation.txt 2>&1
python3 -m unittest discover -s tests -v
python3 analysis/generate_synthetic_data.py --output logs/synthetic_demo.csv
python3 analysis/plot_flight_data.py logs/synthetic_demo.csv \
  --output-dir plots/synthetic_demo --backend auto
python3 scripts/validate_phase1.py --output-dir logs/validation_initial
python3 companion/monitoring/mavlink_monitor.py --sitl-only --duration 1 \
  --output-dir logs/mavlink_dependency_probe
python3 companion/monitoring/gazebo_monitor.py --duration 3 --model physics_probe \
  --output-dir logs/monitor_probe
python3 scripts/prepare_iris_world.py --plugin-source third_party/ardupilot_gazebo \
  --output logs/guard_should_not_create.sdf
python3 control_research/offline_analysis/check_physics.py logs/synthetic_demo.csv
bash -n scripts/check_environment.sh scripts/launch_world.sh
python3 -m compileall -q analysis scripts companion control_research tests
```

The monitor/physics/Iris negative probes were expected to reject unavailable
dependencies/data; they did not constitute successful live tests. Unit tests were
rerun after adding MAVLink frame conversion, with 14 passing. Shell syntax and
Python compilation also succeeded. An AST inspection found no send/sendto/sendall
or MAVLink command, parameter, stream-request, or heartbeat transmit calls in
either monitoring script; this is a source audit, not packet-capture validation.

The validation runner executed:

```bash
gz sim -s -r --iterations 50 --seed 42 -v 4 simulation/worlds/rbi_phase1.sdf
```

It used an absolute path, isolated partition, localhost GZ_IP, and project log
directory. After 12 s plus a 3 s termination grace period it killed its owned
process group. Raw command, exit -9, timeout=true and BLOCKED status are saved in
`logs/validation_initial/results.json`.

Attempted plot rasterization:

```bash
sips -s format png plots/synthetic_demo/altitude_response.svg \
  --out /tmp/rbi_altitude_preview.png
```

This returned `Cannot extract image from file`. The separate browser preview
attempt reported that the browser access host was unavailable. No visual review
is claimed. The generated SVG documents passed XML/label checks.

## Artifacts and provenance

The source inventory and SHA-256 values are in `docs/file_manifest.json` (the
manifest excludes itself and generated logs/plots). Generated evidence remains
on disk under the gitignored logs/plots directories. No git repository was
initialized and no commit or external publication was performed.
