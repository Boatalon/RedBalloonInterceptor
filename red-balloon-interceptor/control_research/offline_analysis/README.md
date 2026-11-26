# Offline control research scope

Use normalized recorded CSV with explicit time, coordinates, provenance and
reference position. Analyze selected steady windows using
`analysis/plot_flight_data.py --start-s ... --end-s ...`. Generated metrics include
altitude mean/std, roll/pitch RMS, 3D position RMSE where a reference exists,
reference coverage, maximum sample gap and mode/health transitions.

These are descriptive statistics, not a stability proof. Check sample rates,
mode transitions, settling periods, missing data and estimator/world origin
alignment first. Do not mix takeoff transients into a hover metric or treat
wrapped yaw discontinuities as an oscillation. The plots intentionally show
wrapped yaw and identify its units.

`check_physics.py` assesses the separate sphere fixture against analytical free
fall and settled ground contact. It requires actual Gazebo-labelled data and
adequate sample coverage. A passing sphere test does not validate motor/propeller
coefficients or the real aircraft. See `docs/test_plan.md` for acquisition steps.

Future identification of the real frame requires measured all-up mass, center
of mass, inertia, thrust/torque curves and motor time constants. The hardware
reference file deliberately contains null values for those quantities.
