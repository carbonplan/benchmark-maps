#!/bin/bash
set -e

playwright install
versions=("v3")
action=""
runs=50

for version in "${versions[@]}"
do
  for chunk in 1 5 10 25
  do
    timeout=$((c=5000, chunk, y=2000, c+chunk*y))
    dataset="${chunk}MB-chunks"
    echo ${dataset}
    python main.py --dataset ${dataset} --zarr-version ${version} --timeout ${timeout} --detect-provider ${action} --runs ${runs}
  done
done
