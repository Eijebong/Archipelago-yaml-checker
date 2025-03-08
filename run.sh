#!/bin/sh -x

cd /ap/archipelago

uv run python3 -O check_wq.py /ap/supported_worlds /apworlds
