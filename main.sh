#!/bin/bash
set -e

playwright install
datasets=("1MB-chunks" "5MB-chunks" "10MB-chunks" "25MB-chunks")
versions=("v2" "v3")
timeout="60000"
action="--action zoom_in --zoom-level 3"

for version in "${versions[@]}"
do
  for dataset in "${datasets[@]}"
  do
    python main.py --dataset ${dataset} --zarr-version ${version} --timeout ${timeout} --detect-provider ${action}
  done
done
