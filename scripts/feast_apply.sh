#!/usr/bin/env bash
set -euo pipefail

echo "Running 'feast apply' for feature_repo/ ..."
feast -c feature_repo apply