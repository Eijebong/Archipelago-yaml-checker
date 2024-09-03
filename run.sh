#!/bin/sh -x

cd /ap/archipelago
. .venv/bin/activate

python3 check.py  /ap/supported_worlds /apworlds
