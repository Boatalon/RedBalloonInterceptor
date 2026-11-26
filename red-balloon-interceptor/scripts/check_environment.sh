#!/usr/bin/env bash
# Read-only inspection: never installs or changes shell/system configuration.
set -uo pipefail
export HOMEBREW_NO_AUTO_UPDATE=1
printf 'Inspection UTC: '; date -u '+%Y-%m-%dT%H:%M:%SZ'
sw_vers
uname -m
for tool in gz brew python3 git cmake clang pkg-config sim_vehicle.py arducopter mavproxy.py; do
  command -v "$tool" || printf 'MISSING: %s\n' "$tool"
done
if command -v gz >/dev/null; then
  printf '\nGazebo Sim versions:\n'; gz sim --versions
  printf '\nSDFormat versions:\n'; gz sdf --versions
fi
for tool in python3 git cmake clang; do
  if command -v "$tool" >/dev/null; then "$tool" --version; fi
done
xcode-select -p
if command -v brew >/dev/null; then
  brew --version
  brew list --versions | awk '/^(gz-|sdformat|rapidjson|opencv|gstreamer|python|numpy|cmake|dartsim)/'
fi
python3 - <<'PY'
import importlib.util, platform, socket, sys
print('Python executable:', sys.executable)
print('Python machine:', platform.machine())
for name in ('numpy', 'pandas', 'matplotlib', 'pymavlink'):
    print(name, 'PRESENT' if importlib.util.find_spec(name) else 'MISSING')
try:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(('127.0.0.1', 0))
    print('Loopback UDP bind: PASS')
except OSError as exc:
    print('Loopback UDP bind: BLOCKED:', exc)
PY
for package in opencv4 gstreamer-1.0 gstreamer-app-1.0; do
  if pkg-config --exists "$package"; then pkg-config --modversion "$package";
  else printf 'MISSING pkg-config dependency: %s\n' "$package"; fi
done
