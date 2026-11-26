# Campus material library

`ptic_materials.json` is generated from `config/ptic_environment.yaml`.
The generator inlines standard SDF ambient/diffuse and optional PBR metal workflow
values. Local procedural PNG maps are under `simulation/models/ptic_materials/`.
No Gazebo Classic `.material` script dependency or photographic texture is used.
See `docs/ptic_environment.md` for profiles and native-rendering limitations.
