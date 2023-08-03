#!/bin/bash
set -e
playwright install
python main.py --dataset 1MB-chunks --zarr-version v2 --action zoom_in --zoom-level 4
