#!/usr/bin/env bash
# Separate server/client processes are required by the macOS Gazebo packaging.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-server}"
if [ "$#" -gt 0 ]; then shift; fi
DEFAULT_PARTITION=rbi_phase1
case "$MODE" in ptic-*) DEFAULT_PARTITION=rbi_ptic_environment ;; esac
export GZ_PARTITION="${GZ_PARTITION:-$DEFAULT_PARTITION}"
export GZ_IP="${GZ_IP:-127.0.0.1}"
export GZ_SIM_RESOURCE_PATH="$ROOT/simulation/models:$ROOT/simulation/worlds${GZ_SIM_RESOURCE_PATH:+:$GZ_SIM_RESOURCE_PATH}"
command -v gz >/dev/null || { echo 'gz is missing from PATH' >&2; exit 2; }
case "$MODE" in
  ptic-validate)
    export SDF_PATH="$ROOT/simulation/models${SDF_PATH:+:$SDF_PATH}"
    exec gz sdf -k "$ROOT/simulation/worlds/rbi_ptic_environment.sdf" ;;
  ptic-server|ptic-overview|ptic-topdown|ptic-architecture|ptic-groundlevel)
    mkdir -p "$ROOT/logs/ptic_environment"
    RUN_DIR="$(mktemp -d "$ROOT/logs/ptic_environment/${MODE}-XXXXXXXX")"
    export GZ_LOG_PATH="$RUN_DIR"
    exec > >(tee "$RUN_DIR/stdout.log") 2> >(tee "$RUN_DIR/stderr.log" >&2)
    echo "Gazebo logs: $RUN_DIR; partition: $GZ_PARTITION"
    if [ "$MODE" = ptic-server ]; then
      SEED="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["seed"])' "$ROOT/config/ptic_environment.yaml")"
      exec gz sim -s -r -v 3 --seed "$SEED" --record-path "$RUN_DIR/state" "$ROOT/simulation/worlds/rbi_ptic_environment.sdf" "$@"
    else
      VIEW="${MODE#ptic-}"
      exec gz sim -g -v 3 --gui-config "$ROOT/simulation/gui/ptic_${VIEW}.config" "$@"
    fi ;;
  validate) exec gz sdf -k "$ROOT/simulation/worlds/rbi_phase1.sdf" ;;
  server|gui|topdown)
    mkdir -p "$ROOT/logs"
    RUN_DIR="$(mktemp -d "$ROOT/logs/${MODE}-XXXXXXXX")"
    export GZ_LOG_PATH="$RUN_DIR"
    exec > >(tee "$RUN_DIR/stdout.log") 2> >(tee "$RUN_DIR/stderr.log" >&2)
    echo "Gazebo logs: $RUN_DIR; partition: $GZ_PARTITION"
    if [ "$MODE" = server ]; then
      SEED="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["physics"]["seed"])' "$ROOT/config/world_config.yaml")"
      exec gz sim -s -r -v 3 --seed "$SEED" --record-path "$RUN_DIR/state" "$ROOT/simulation/worlds/rbi_phase1.sdf" "$@"
    else
      VIEW=perspective
      if [ "$MODE" = topdown ]; then VIEW=topdown; fi
      exec gz sim -g -v 3 --gui-config "$ROOT/simulation/gui/$VIEW.config" "$@"
    fi ;;
  *) echo 'Usage: scripts/launch_world.sh {validate|server|gui|topdown|ptic-validate|ptic-server|ptic-overview|ptic-topdown|ptic-architecture|ptic-groundlevel} [gz sim options]' >&2; exit 2 ;;
esac
