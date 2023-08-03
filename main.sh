#!/bin/bash
set -e


playwright install
pytest -v -s
