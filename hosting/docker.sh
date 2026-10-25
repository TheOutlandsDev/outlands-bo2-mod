#!/usr/bin/env bash
set -euo pipefail
export DOCKER_HOST=unix:///var/run/docker.sock
if docker info >/dev/null 2>&1; then
    exec docker "$@"
fi
if id -nG "$(id -un)" | tr ' ' '\n' | grep -qx docker; then
    docker_command="$(python3 - "$@" <<'PY'
import shlex
import sys
print(shlex.join(['docker', *sys.argv[1:]]))
PY
)"
    exec sg docker -c "$docker_command"
fi
printf '%s\n' 'The current account needs Docker access.' >&2
exit 1
