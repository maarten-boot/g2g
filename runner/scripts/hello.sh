#!/usr/bin/env bash
# Example script: shows what the runner provides.
set -euo pipefail
echo "hello ${RUNNER_USER} (script: ${RUNNER_SCRIPT})"
for i in 1 2 3; do
    echo "step $i"
    sleep 1
done
echo "done"
