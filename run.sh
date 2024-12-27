#!/bin/sh -x

cd /ap/archipelago
. .venv/bin/activate

python3 -O wq.py  /ap/supported_worlds /apworlds
