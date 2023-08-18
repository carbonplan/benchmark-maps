#!/bin/bash
set -e


playwright install

carbonplan_benchmarks --dataset pyramids-v3-sharded-4326-1MB
