#!/bin/bash
set -e


playwright install
python main.py --dataset 1MB-chunks --zarr-version v2 --action zoom_in --zoom-level 4 --s3-bucket s3://carbonplan-benchmarks
python main.py --dataset 5MB-chunks --zarr-version v2 --action zoom_in --zoom-level 4 --s3-bucket s3://carbonplan-benchmarks
python main.py --dataset 10MB-chunks --zarr-version v2 --action zoom_in --zoom-level 4 --s3-bucket s3://carbonplan-benchmarks
python main.py --dataset 25MB-chunks --zarr-version v2 --action zoom_in --zoom-level 4 --s3-bucket s3://carbonplan-benchmarks
python main.py --dataset 1MB-chunks --zarr-version v3 --action zoom_in --zoom-level 4 --s3-bucket s3://carbonplan-benchmarks
python main.py --dataset 5MB-chunks --zarr-version v3 --action zoom_in --zoom-level 4 --s3-bucket s3://carbonplan-benchmarks
python main.py --dataset 10MB-chunks --zarr-version v3 --action zoom_in --zoom-level 4 --s3-bucket s3://carbonplan-benchmarks
python main.py --dataset 25MB-chunks --zarr-version v3 --action zoom_in --zoom-level 4 --s3-bucket s3://carbonplan-benchmarks
