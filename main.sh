#!/bin/bash
set -e


playwright install
datasets=("25MB-chunks")
versions=("v2" "v3")

for version in "${versions[@]}"
do
  for dataset in "${datasets[@]}"
  do
    python main.py --dataset ${dataset} --zarr-version ${version} --action zoom_in --zoom-level 3 --detect-provider --s3-bucket s3://carbonplan-benchmarks
  done
done
