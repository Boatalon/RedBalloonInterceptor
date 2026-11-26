# Environment inspection — Phase 1 and Phase 1B

## Phase 1B update, 2026-11-26 through 2026-11-27

The earlier sandbox blocker is **resolved for this execution session**. A direct
UDP loopback bind succeeded. Actual Gazebo server runs, clock/stat subscriptions,
repeat startup and GUI render captures succeeded on the existing installation.
No global sandbox setting, firewall, Gazebo installation or shell profile was
changed by the implementation. Current tool permissions already permitted the
operations. The historical findings below describe the earlier session only.

The Mac now reports `Apple M4 Pro`, `arm64`, and 25,769,803,776 bytes of physical
memory (24 GiB) directly via sysctl. macOS remains 27.0.1 build 26A434. Gazebo
Sim 8.15.0 / SDFormat 14.9.0, Python 3.15.2, CMake 4.5.1 and Apple Clang 21.0.0
were rechecked. A C++17 CMake smoke project compiled and executed natively.

The initial diagnostic PID 32940 was identified by its exact `empty.sdf` command,
terminated and confirmed absent. An unrelated pre-existing `shapes.sdf` server
was left untouched. It was present during early measurements and absent when
work resumed on 2026-11-27. Final evidence was collected on the latter date.
All project-run processes used isolated partitions and were shut down after
measurement. This is not a guarantee that unrelated user processes remain closed.

Network access now allows read-only upstream source inspection. Copies of the
official plugin CMake file, macOS prerequisites script and GUI source are stored
under `logs/phase1b-20261126T220119/upstream/`, with original source metadata.
No upstream installation script was executed and no third-party repository was
initialized. A dependency-discovery prefix of the plugin CMake file was tested:
it found installed Gazebo libraries and RapidJSON, then failed on missing
OpenCV. An initial Qt5 discovery warning was resolved for the probe by passing
the existing `/opt/homebrew/opt/qt@5` as CMAKE_PREFIX_PATH. GStreamer is missing
as independently confirmed through pkg-config. This was **not a plugin build**.

Missing Python modules include pymavlink, MAVProxy, em/EmPy, lxml, pexpect,
dronecan, Pandas and Matplotlib. Their compatibility with Python 3.15.2 has not
been established; missing modules are not evidence of an unsupported Python
version. The upstream macOS installer offers Python 3.10.18 as an optional path
and pins EmPy 3.3.4, but it was read only. No Python upgrade/downgrade or package
installation occurred. [Compatibility details](sitl_compatibility.md).

GUI rendering used the installed Metal backend. Both final views remained alive
during the observation interval and exited normally on requested shutdown.
Warnings include Roboto font fallback, a WorldStats QML layout binding loop,
unsupported default 8x antialiasing falling back to 1x, and screenshot-notification
shader-effect warnings. No server SDF/physics error or fatal GUI error appeared
in the accepted final runs. This is short-run stability evidence, not a long
endurance or heavy-sensor benchmark. Actual performance and captures are in
[Phase 1B results](phase1b_results.md).

The original 45-second GUI experiment exposed an evidence-reader size limit:
valid concatenated clock JSON was passed as one oversized chunk. The reader now
parses bounded chunks, a regression test covers a capture over 2 MB, and the
original raw log was reanalyzed separately without rewriting its failed result.
The reanalysis found 44,696 monotonically increasing clock messages spanning
44.695 simulated seconds. Early black screenshots are preserved as preliminary
evidence; accepted screenshots were captured after scene initialization.

## Historical Phase 1 inspection — 2026-11-26

Inspection took place before creating project files. The workspace initially
contained `.DS_Store`, `Red balloon project.xlsx`, and its Excel lock file. No
existing source, README, SDF, repository metadata, or applicable AGENTS.md was
found in the inspected workspace/ancestor locations. Existing files were left
untouched. The implementation is under the new `red-balloon-interceptor/` folder.

## Observed tools

| Item | Observed result |
| --- | --- |
| macOS | 27.0.1, build 26A434 |
| Architecture | `arm64`; Gazebo dylib verified Mach-O arm64 |
| CPU / RAM | M4 Pro / 24 GB supplied by user; sysctl inspection denied by sandbox, not independently confirmed |
| Homebrew | 7.0.16, `/opt/homebrew/bin/brew` |
| Gazebo distribution | Harmonic (`gz-harmonic 1.0.0_5`) |
| Gazebo CLI | `/opt/homebrew/bin/gz`, symlink to gz-tools2 2.0.4 |
| Gazebo Sim | 8.15.0 (`gz-sim8 8.15.0_8`) |
| SDFormat | 14.9.0 (`sdformat14 14.9.0_8`) |
| Physics | gz-physics7 7.9.0_1, dartsim 6.20.3_1 |
| Transport / messages | gz-transport13 13.7.0 / gz-msgs10 10.4.0_8 |
| Python | Homebrew 3.15.2; Apple `/usr/bin/python3` 3.9.6 also present |
| NumPy | 2.5.5 imports successfully with Homebrew Python |
| Pandas / Matplotlib / pymavlink | Not available to inspected Python interpreters |
| Git | 2.54.0 (Apple Git-157) |
| CMake | 4.5.1 |
| Compiler | Apple Clang 21.0.0, target arm64-apple-darwin27.0.0 |
| Xcode CLI tools | `/Library/Developer/CommandLineTools` |
| RapidJSON | 1.1.0 present |
| OpenCV / GStreamer | Missing from Homebrew inventory and pkg-config probes; OpenCV CMake discovery also failed |
| ArduPilot | `sim_vehicle.py`, `arducopter`, `mavproxy.py` not on PATH; standard `$HOME/ardupilot`, `$HOME/ardupilot_gazebo`, `$HOME/gz_ws` locations absent |

This is a scoped inspection, not a recursive scan of the user's entire disk.
`gz --versions` prints general help in this installation; the component commands
`gz sim --versions` and `gz sdf --versions` provide the actual versions.
An initial shell loop used zsh's special `path` variable and temporarily changed
PATH in that one child shell; the check was immediately repeated using absolute
CLI paths. No shell profile or persistent PATH was modified.

## Compatibility evidence

The official [Gazebo macOS installation page](https://gazebosim.org/docs/harmonic/install_osx/)
documents native Apple Silicon Harmonic packages. This machine already has them;
reinstallation is unnecessary. Its exact macOS 27 version is newer than the
specific binary target described in that page, so runtime validation still
matters.

The official [ArduPilot Gazebo repository](https://github.com/ArduPilot/ardupilot_gazebo)
supports Harmonic and documents native macOS/Apple Silicon operation. Its
[CMake file](https://github.com/ArduPilot/ardupilot_gazebo/blob/main/CMakeLists.txt)
selects gz-sim8, gz-common5, gz-rendering8 and gz-cmake3 for Harmonic, matching the
installed major versions. It requires RapidJSON, OpenCV and GStreamer during
configuration. The [macOS ArduPilot setup guide](https://ardupilot.org/dev/docs/building-setup-mac.html)
is written for Apple Silicon and distinguishes SITL from the hardware firmware
cross-toolchain. Rosetta is not justified for this native SITL task.

Conclusion: **native integration is supported in principle, but has not been
built or run on this exact host**. There is no verified CPU/Gazebo incompatibility
requiring Docker, Ubuntu, ROS 2, or Rosetta. Python 3.15 dependency compatibility
has not been tested; do not describe it as an established incompatibility.
Official web sources were reviewed on 2026-11-26; upstream `main` is moving and
must be pinned to a commit for a future build.

## Verified blockers

1. A direct Python UDP bind to `127.0.0.1:0` raised `PermissionError: [Errno 1]
   Operation not permitted`. Gazebo reported `Binding to a local port failed`,
   `InitializeSockets() Error: Operation not permitted`, and failed service/topic
   advertisements. This is the execution sandbox, not proof of an invalid SDF or
   unsupported Mac. The bounded project-world probe was terminated after 12 s
   plus a 3 s shutdown grace period. Result: BLOCKED.
2. Shell `curl` could not resolve `raw.githubusercontent.com`. Upstream docs were
   accessible through the separate web research tool. No plugin checkout, SITL
   source, or Python package was downloaded. There is no local Fuel model cache
   in the inspected `~/.gz/fuel` location.
3. OpenCV/GStreamer and the ArduPilot development/runtime tools are missing.
   The unmodified upstream plugin cannot be configured with these dependencies
   absent. No unsupported build-system patch was attempted.
4. Writing Gazebo's default logs under `~/.gz` was denied by the filesystem
   sandbox. Project launch/validation commands set `GZ_LOG_PATH` and use explicit
   recording directories. They do not modify HOME or user configuration.
5. Browser visual inspection was attempted but the browser access host was
   unavailable. macOS `sips` could not rasterize SVG. SVG XML, numeric output and
   provenance checks pass; a rendered visual review is NOT RUN.

The first diagnostic used the installed `empty.sdf` directly without a timeout.
It stalled after transport initialization errors. Its input stream subsequently
closed; process enumeration (`ps`/`pkill`) is also denied in this sandbox, so its
termination could not be confirmed. Later project probes use process groups and
bounded cleanup, and the bounded world process was terminated (exit -9). From a
normal Terminal, this exact diagnostic can be cleaned up if still present:

```bash
pkill -f '^/opt/homebrew/bin/gz sim -s -r --iterations 10 -v 4 /opt/homebrew/opt/gz-sim8/share/gz/gz-sim8/worlds/empty.sdf$'
```

This targets only that diagnostic command, not other Gazebo sessions. No broad
process kill was issued.

## Dependency policy and next environment step

No system installation, upgrade, uninstall, privileged operation, shell-profile
edit, or overwrite of pre-existing project files was performed. Additional
system packages require the user's approval before installation. The core world,
SVG analysis, and offline unit tests need no additional packages.

For richer plotting, a future project-local virtual environment can install
`requirements-analysis.txt`; optional MAVLink needs `pymavlink`. These commands
are **documented, not executed**:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-analysis.txt
.venv/bin/python -m pip install pymavlink
.venv/bin/python -m pip freeze > logs/python_environment_lock.txt
```

Use an empty `.venv` destination. Package ranges are optional compatibility
requests, not a tested lockfile. Record the resolved versions after successful
installation. Prefer the existing Python first; change interpreter only after a
specific build or package compatibility failure is established.

Raw inventory: `logs/environment_inspection.txt`. SDF/runtime evidence:
`logs/validation_initial/`. See `docs/commands_executed.md` for the command record.
