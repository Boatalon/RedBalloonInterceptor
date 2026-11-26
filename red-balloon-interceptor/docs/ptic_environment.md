# Phase 1C — fictional PTIC-inspired research campus

This independently runnable scene adds a modern tropical research-campus visual
style to the project. It does not replace Phase 1B. Read the
[visual reference study](venue_visual_references.md) and
[actual validation report](ptic_validation_report.md) for provenance and results.
No actual facility footprint, geodetic origin, operational zone, flight route,
aircraft launch location or flight-control interface is present.

## Coordinates and configuration

`config/ptic_environment.yaml` uses the JSON-compatible subset of YAML 1.2,
matching the existing repository convention. Python's standard library reads it;
PyYAML and system package installation are unnecessary. All lengths are metres,
angles are radians, gravity is m/s², and color channels are linear inputs in
[0, 1]. Local +X is east, +Y north, +Z up. Origin is an arbitrary fictional point.
Ground top is z=0; the collision slab extends below it. The 400 × 400 m field
occupies x,y ∈ [-200,200]. The decorative hill/forest backdrop extends beyond the
field and has no collision. ENU directions do not imply geographic registration.

The default is MEDIUM quality, midday, seed 271827, Earth gravity -9.80665 m/s²,
1 ms physics steps, desired RTF 1, and no wind. The optional 50 m grid is disabled
for the normal landscaped view. It is purely visual when enabled.

| Synthetic asset | Size (X × Y × Z), m | Arbitrary center (X,Y), m |
|---|---:|---:|
| Research office | 60 × 32 × 20 | -72, 48 |
| Laboratory | 52 × 34 × 25 | 68, 72 |
| Generic demonstration workshop | 64 × 38 × 30 | 75, -92 |

All dimensions and placements are configurable. Heights are user-supplied
synthetic estimates, **not surveyed PTIC dimensions**. Office glazing uses a
shallow surface behind projecting mullions and corner fins; narrow laboratory
windows use shallow reveals. Canopies, frames, roof trim, windows and closed
workshop doors are visual approximations. There are no interiors or systems.

## Asset inventory and collision contract

Reusable SDF models under `simulation/models/` include the three buildings;
`tropical_tree`, `ornamental_tree`, `vegetation` (shrubs), each with six seeded
variants; `road_surface`, `concrete_path`, `concrete_curb`, `grass_surface`,
`landscaped_island`, `campus_furniture`, `campus_light`, `ptic_backdrop`, and
`ptic_materials`. The material library holds original generated PNG grain maps
and a UV-mapped lawn mesh. Every asset resolves locally through `model://`.
No Fuel download or externally licensed mesh/photograph is needed at runtime.

There are exactly four instantiated collision shapes: the 400 m ground slab
and one solid box per building. The simpler collision envelope intentionally
omits canopy overhangs and facade trim. Vegetation, hills, lamps, benches, road
paint, roads, paths, curbs, islands and grid lines have **no collision**. Paths
and roads are thin visual overlays above the physical z=0 surface; their few
centimetres of visual height are not curb/contact physics. This is a static
rendering/collision-envelope testbench, not a pedestrian or vehicle dynamics model.

`simulation/materials/ptic_materials.json` is generated from the authoritative
YAML. SDF inlines these material values because modern Gazebo does not use
Gazebo Classic Ogre material scripts. Materials cover white/light-gray concrete,
opaque blue-gray glass, aluminum, asphalt, pavement, grass, foliage, bark,
painted steel, road paint and distant hill green.

MEDIUM/HIGH use SDF PBR metalness/roughness and local albedo maps on UV-mapped
meshes. Primitive building panels stay untextured to avoid stretched grain.
Glass is opaque and cheap: no transparency, refraction, planar reflection,
reflection probes, global illumination or real optical sensor model is implied.
LOW uses ambient/diffuse fallback materials without PBR or shadows.

| Profile | Lawn broadleaf / ornamental / shrubs | Forest fringe | Facade detail |
|---|---:|---:|---|
| LOW | 28 / 16 / 28 | 36 | Basic divisions, two canopy clusters |
| MEDIUM | 58 / 28 / 60 | 60 | Frames, spandrels, panel seams, canopy rafters |
| HIGH | 86 / 40 / 90 | 88 | Additional louvers and denser/smoother vegetation |

Six additional ornamental trees sit in entrance islands in all profiles.
The summary reports unique generated mesh triangles, not the total after
instancing or Gazebo's primitive tessellation. Static collision cost is kept
independent of decorative detail.

## Generator and lighting

```bash
cd "/Users/papajhon/Project/Red Balloon Intercepter/red-balloon-interceptor"
python3 scripts/build_ptic_environment.py          # check canonical bytes
python3 scripts/build_ptic_environment.py --write  # regenerate from configuration
```

The generator validates finite/positive dimensions, material references and
ranges, building separation, clipping, local-only coordinates and procedural
placement constraints. It rejects invalid input before writing. Identical
configuration/profile/lighting produces identical bytes, including OBJ meshes,
PNG textures, SDF, GUI files, material definitions and a SHA-256 summary.
This guarantees scene generation reproducibility, not deterministic future flight
or bit-identical GPU output. Generated outputs contain no wall-clock timestamps.

Lighting presets `morning`, `midday`, `afternoon`, `overcast` control the synthetic
sun direction/intensity, ambient/background colors, shadow enable and exponential
haze. These are artistic conditions, not a solar/weather prediction. LOW turns
shadows off; overcast disables direct shadows in every profile. Ground surfaces
and distant hills receive lighting but do not cast shadows. Other static geometry
uses the profile's shadow setting. Atmospheric haze support and appearance can
vary with the renderer; no volumetric sky or cloud simulation is enabled.

To create a variation without replacing the canonical default:

```bash
python3 scripts/build_ptic_environment.py --profile LOW --lighting overcast \
  --output-root /tmp/rbi-campus-low --write
GZ_SIM_RESOURCE_PATH=/tmp/rbi-campus-low/simulation/models \
  GZ_PARTITION=rbi_campus_low GZ_IP=127.0.0.1 \
  gz sim -s -r /tmp/rbi-campus-low/simulation/worlds/rbi_ptic_environment.sdf
# In another Terminal:
GZ_SIM_RESOURCE_PATH=/tmp/rbi-campus-low/simulation/models \
  GZ_PARTITION=rbi_campus_low GZ_IP=127.0.0.1 \
  gz sim -g --gui-config /tmp/rbi-campus-low/simulation/gui/ptic_overview.config
```

Use a fresh output directory for a different experiment. The canonical launcher
uses the project assets; a separate generated root needs the explicit paths above.
Changing canonical defaults intentionally requires editing the YAML and rerunning
`--write`. Generated data should not be edited by hand.

## Launch and static inspection

On this macOS installation, start server and GUI in separate Terminals. Baseline
commands and partition remain unchanged; the campus has its own default partition.
An explicitly exported `GZ_PARTITION` overrides both defaults, so keep matching
values in the two Terminals. Stop each owned process with Ctrl-C.

```bash
# Terminal A, from the project directory:
./scripts/launch_world.sh ptic-validate
./scripts/launch_world.sh ptic-server

# Terminal B, choose ONE view:
./scripts/launch_world.sh ptic-overview
# or: ./scripts/launch_world.sh ptic-topdown
# or: ./scripts/launch_world.sh ptic-architecture
# or: ./scripts/launch_world.sh ptic-groundlevel

# Original Phase 1B, independently runnable:
./scripts/launch_world.sh validate
./scripts/launch_world.sh server
# Separate Terminal: ./scripts/launch_world.sh gui
# Alternative baseline view: ./scripts/launch_world.sh topdown
```

The GUI configurations use Ogre2, a 1400 × 950 window, 60° horizontal field of
view, and static overview/top-down/architecture/eye-level camera positions.
The visible renderer viewport is 1400 × 870 in the captured session. Eye level
is 1.8 m. The complete-field views have mathematical frustum coverage tests.
A 3 m near clip and 3000 m far clip were chosen after testing on this Metal
installation: the earlier 0.15 m near clip at eye level yielded an almost empty
image even though the camera pose was correct. The 3 m clip worked in the same
pose. The exact upstream defect is not established. Objects within 3 m of the
camera are intentionally clipped; these presets are for static environment
inspection, not close-range sensor simulation.

## Validation and benchmark commands

```bash
python3 -m unittest discover -s tests -v
python3 scripts/validate_ptic_environment.py \
  --output-dir logs/ptic_environment/manual-overview-001 \
  --duration 10 --view overview --repetitions 2
python3 scripts/benchmark_ptic_environment.py \
  --output-dir logs/ptic_environment/comparison-001 --duration 10
```

Evidence directories must not already exist, protecting earlier runs. The
validator records raw stdout/stderr, argv, unique transport partition, world
hash, clock/stats JSON streams, camera pose, process samples and Screenshot
plugin PNGs. `SDF_PATH` is supplied for standalone `gz sdf -k`; Gazebo runtime
uses `GZ_SIM_RESOURCE_PATH`. These are different resolution contexts.

The benchmark serializes all Gazebo sessions, uses equal 10 s clock/stats
windows after the same 4 s GUI warmup, and samples owned process groups every
0.5 s. Startup means elapsed time until successful CLI clock/stats discovery.
GUI PNG receipt includes warmup/polling/service overhead and requires visual
confirmation. RTF measures physics timing, **not GUI frames per second**. macOS
`ps` CPU values are process-lifetime percentages; summed RSS is not unique
physical memory, GPU allocation or whole-system usage. No FPS, GPU power or
thermal endurance result is claimed.

ENV-001 through ENV-016 and the baseline regression are mapped to actual evidence
in `ptic_validation_report.md`. GUI review is deliberately separate from process
success: an existing PNG or live process cannot prove a correct scene.

## Remaining boundaries

The scene is a stylized engineering approximation, not photographic reconstruction.
Tree crowns remain low-poly; shadows may exhibit visible banding/aliasing on this
native Ogre2/Metal stack. Overcast or LOW provides a simple shadow-free fallback.
No advanced AA or shadow-map tuning was enabled without installed-plugin support.

ArduPilot SITL and its Gazebo plugin remain unbuilt/unexecuted. Prior verified
blockers are summarized in [the SITL compatibility report](sitl_compatibility.md):
missing OpenCV/GStreamer development packages and Python prerequisites, with
Python 3.15 integration still unverified. No system package was installed, no
software was reinstalled/upgraded and no physical aircraft hardware was contacted.
