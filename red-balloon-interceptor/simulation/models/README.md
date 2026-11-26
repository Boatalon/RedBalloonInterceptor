# Standard models only

No custom aircraft has been created. The first integration target is the official
`ArduPilot/ardupilot_gazebo` Iris model. `scripts/prepare_iris_world.py` references
an existing checkout without editing its model parameters, meshes, or licenses.
Its generated world is an optional, currently unverified integration artifact.
The baseline world never depends on this directory containing downloaded assets.

Do not infer HAOYERC mass, inertia, thrust, drag, or performance from the reference
BOM. Obtain measurements before building a separate hardware model.
