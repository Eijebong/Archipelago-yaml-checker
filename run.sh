#!/bin/sh -x

cd /ap/archipelago
. .venv/bin/activate

while true; do
    apwm install -i /index -a /apworlds -d /ap/archipelago/worlds
    python3 check.py
done
