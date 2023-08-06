#!/bin/bash
set -e

playwright install
versions=("v2" "v3")
action="--action zoom_in --zoom-level 3"

for version in "${versions[@]}"
do
  for chunk in 1 5 10 25
  do
    timeout=$((c=5000, chunk, y=2000, c+chunk*y))
    dataset="${chunk}MB-chunks"
    echo ${dataset}
    python main.py --dataset ${dataset} --zarr-version ${version} --timeout ${timeout} --detect-provider ${action}
  done
done
