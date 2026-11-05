#!/usr/bin/env bash
# No fallback to the host network, no real credentials or home writes.
set +x
set -euo pipefail
here=$(builtin cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
command -v unshare >/dev/null || { echo 'unshare required; refusing unisolated tests.' >&2; exit 1; }
host_net=$(readlink /proc/self/ns/net)
exec env -i PATH=/usr/bin:/bin PYTHONDONTWRITEBYTECODE=1 BRIDGE_TEST_HOST_NET="$host_net" \
  unshare --user --map-root-user --net -- /usr/bin/python3 -I -B "$here/test_bridge.py"
