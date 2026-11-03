#!/usr/bin/env bash
# Fail closed: tests require an isolated network namespace, never real API access.
set +x
set -euo pipefail
unset LUMA_API_KEY
here=$(builtin cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
command -v unshare >/dev/null || { echo 'unshare is required; refusing unisolated tests.' >&2; exit 1; }
host_net=$(readlink /proc/self/ns/net)
exec env -i PATH=/usr/bin:/bin LUMA_TEST_HOST_NET="$host_net" \
  unshare --user --map-root-user --net -- /usr/bin/python3 "$here/test_luma.py"
