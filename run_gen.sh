#!/bin/sh -x

cd /ap/archipelago

uv run python3 -O gen_wq.py /ap/supported_worlds /apworlds
