# Native ArduPilot SITL / Gazebo assessment

## Phase 1B local evidence, completed 2026-11-27

The world-runtime sandbox restriction no longer applies in this session. Native
Gazebo Harmonic server, Transport and Metal GUI are now verified on this Mac.
This does **not** establish a successful ArduPilot/Gazebo integration.

| Layer | Documentation / local evidence | Status |
| --- | --- | --- |
| macOS ARM64 | Official ArduPilot macOS guide addresses Apple Silicon; sysctl confirms M4 Pro; native Gazebo runs | Host/Gazebo execution verified; ArduPilot execution NOT RUN |
| Harmonic 8.15.0 | Official plugin Harmonic branch requires gz-sim8; local dependency probe finds 8.15.0 and related libraries | Matching major versions and discovery verified |
| CMake 4.5.1 / Clang 21 | Upstream minimum CMake 3.10.2, C++17; local smoke configure/build/run succeeds | Toolchain smoke PASS; full plugin/SITL builds NOT RUN |
| RapidJSON | Required upstream; version 1.1.0 discovered locally | Available |
| Qt5 | Installed keg-only; initial discovery warning resolved with local CMAKE_PREFIX_PATH | Available with explicit prefix |
| OpenCV | Upstream REQUIRED; local CMake dependency probe terminates at OpenCV discovery | BLOCKED: missing |
| GStreamer and gstreamer-app | Upstream REQUIRED; pkg-config fails for both | BLOCKED: missing |
| Python 3.15.2 | Project tests pass; upstream full SITL Python stack not installed/tested | SITL compatibility unverified |
| ArduPilot Python modules | pymavlink, MAVProxy, EmPy, lxml, pexpect and dronecan absent in inspected interpreter | BLOCKED: missing prerequisites |

The local dependency probe uses only the dependency-discovery prefix of the
official upstream CMake file. It is clearly separated from the compiler smoke
project and from a full plugin build. Its raw output is in
`logs/phase1b-20261126T220119/plugin_dependency_probe/`. Passing
`-DCMAKE_PREFIX_PATH=/opt/homebrew/opt/qt@5` removes the Qt discovery warning;
OpenCV remains the fatal missing dependency. No Gazebo downgrade or reinstall
is indicated by this evidence.

The official macOS prerequisites script was inspected, not executed. It offers
optional Python 3.10.18 and pins EmPy 3.3.4. This does not prove Python 3.15 is
incompatible. Retain the existing interpreter until an isolated package/build
test establishes a specific failure. The installer also performs package and
profile changes, so running it requires reviewing/authorizing that scope first.

Approval is required before any future system-dependency installation. No
packages were installed during Phase 1B. The next integration proposal is to
install only approved missing dependencies, pin upstream source revisions,
record an isolated Python dependency set, and build the unchanged generic Iris
example. Keep all hardware disconnected. No VM/container/ROS/Rosetta fallback
is justified by the current findings.

Official sources were re-inspected: [SITL with Gazebo](https://ardupilot.org/dev/docs/sitl-with-gazebo.html),
[plugin repository](https://github.com/ArduPilot/ardupilot_gazebo),
[plugin CMake](https://github.com/ArduPilot/ardupilot_gazebo/blob/main/CMakeLists.txt),
and [macOS prerequisites source](https://github.com/ArduPilot/ardupilot/blob/master/Tools/environment_install/install-prereqs-mac.sh).
Downloaded source hashes are retained with the evidence; moving upstream branches
are not substitutes for pinned build revisions.

## Historical assessment and future integration recipe

**Status: documented upstream compatibility; local integration BLOCKED.** The
existing native ARM64 Harmonic installation matches the official plugin's
Harmonic dependency branch. Missing packages and execution permissions prevent
a complete local build/runtime test. This is not an unsupported-platform finding.

Sources reviewed 2026-11-26:

- [Official ArduPilot Gazebo plugin and installation](https://github.com/ArduPilot/ardupilot_gazebo)
- [Actual plugin dependency selection](https://github.com/ArduPilot/ardupilot_gazebo/blob/main/CMakeLists.txt)
- [ArduPilot SITL with Gazebo](https://ardupilot.org/dev/docs/sitl-with-gazebo.html)
- [Apple Silicon build environment](https://ardupilot.org/dev/docs/building-setup-mac.html)
- [Official Iris world](https://github.com/ArduPilot/ardupilot_gazebo/blob/main/worlds/iris_runway.sdf)
- [Official Iris model without camera gimbal](https://github.com/ArduPilot/ardupilot_gazebo/blob/main/models/iris_with_ardupilot/model.sdf)

The upstream README lists more Gazebo releases than the older tutorial; the
installed version is Harmonic, supported by both. No version switch is needed.
The plugin has no ROS dependency. Its current top-level build requires OpenCV and
GStreamer even if the selected model does not use a camera. Both are missing.
RapidJSON is already installed. Do not patch out required dependencies as a
Phase 1 shortcut.

## Future native integration procedure (not executed)

Obtain approval before installing missing system packages. Review the official
ArduPilot prerequisites script before running it: it can install packages and
edit shell profiles, so it is intentionally not executed by this project. The
hardware cross-compiler is unnecessary for SITL.

Once dependencies and normal local networking are available, use new checkouts
under `third_party/`, retaining upstream licenses. Resolve and record immutable
commit IDs before accepting test results. The following commands are a future
recipe, not a claim that an integration was built here:

```bash
mkdir -p third_party
git clone https://github.com/ArduPilot/ardupilot_gazebo.git third_party/ardupilot_gazebo
git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git third_party/ardupilot
git -C third_party/ardupilot_gazebo rev-parse HEAD
git -C third_party/ardupilot rev-parse HEAD
GZ_VERSION=harmonic cmake -S third_party/ardupilot_gazebo \
  -B third_party/ardupilot_gazebo/build -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build third_party/ardupilot_gazebo/build -j4
```

Do not run `cmake --install`; the plugin can be loaded from its build directory.
Build SITL with the official source's documented native waf workflow after its
Python prerequisites are satisfied. No firmware is flashed and no hardware is
connected. Save repository commit IDs, build output, Python lockfile, parameters,
SDF hashes and random seed alongside every accepted flight run.

First validate the unmodified upstream `iris_runway.sdf` example. In the project
root, configure only the current shell:

```bash
export GZ_VERSION=harmonic
export GZ_PARTITION=rbi_phase1
export GZ_IP=127.0.0.1
export GZ_SIM_SYSTEM_PLUGIN_PATH="$PWD/third_party/ardupilot_gazebo/build${GZ_SIM_SYSTEM_PLUGIN_PATH:+:$GZ_SIM_SYSTEM_PLUGIN_PATH}"
export GZ_SIM_RESOURCE_PATH="$PWD/third_party/ardupilot_gazebo/models:$PWD/third_party/ardupilot_gazebo/worlds${GZ_SIM_RESOURCE_PATH:+:$GZ_SIM_RESOURCE_PATH}"
gz sim -s -r -v 4 iris_runway.sdf
```

Start `gz sim -g` in a second shell with the same partition/resource variables.
The official SITL invocation is:

```bash
python3 third_party/ardupilot/Tools/autotest/sim_vehicle.py \
  -v ArduCopter -f gazebo-iris --model JSON
```

This starts a software simulator, not a hardware connection. No arming or flight
command has been embedded in the testbench. Use the official upstream tutorial
for an operator-supervised generic hover only after the integration passes its
preflight checks. Map/console options can be added if their GUI dependencies are
available; they are not required for the physics-world baseline.

## Optional Iris in the RBI world

After the unchanged upstream example works, generate a separate world:

```bash
python3 scripts/prepare_iris_world.py \
  --plugin-source third_party/ardupilot_gazebo --output logs/rbi_phase1_iris.sdf
gz sdf -k logs/rbi_phase1_iris.sdf
gz sim -s -r -v 4 --seed 42 logs/rbi_phase1_iris.sdf
```

Keep the environment variables above. Stop the prior server first. The composer
uses the official `iris_with_ardupilot` model without changing its physical
parameters, adds IMU/NavSat systems and world-frame odometry, and uses the
official example's synthetic geographic origin. It omits the camera gimbal to
keep initial integration focused. Model dependencies still resolve through the
upstream models path. This generated integration has NOT been executed with an
actual upstream checkout; its missing-source guard was tested.

The Gazebo JSON interface and MAVLink are separate connections. For observation,
the SITL/MAVProxy operator can forward a telemetry-only copy to local UDP 14560;
the receiver never requests or changes streams. Confirm available position,
attitude and heartbeat messages before declaring telemetry readiness.

## Fallback decision

First run the baseline from a normal macOS Terminal; a sandbox socket error does
not justify a VM. Then install approved missing native dependencies and attempt
one clean upstream build. Keep exact error logs if that fails. Only a reproducible
native compatibility failure should trigger an alternative architecture.

If such a failure is verified later, the preferred fallback is a separate
supported Ubuntu host running **both** Gazebo and ArduPilot SITL together, with
the Mac doing read-only log analysis/visualization. A VM is a secondary option
subject to its documented graphics support and resource budget. No fallback was
installed or introduced here, and no unsupported dependency patching was done.
