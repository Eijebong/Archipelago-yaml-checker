#!/bin/sh -x

cd /ap/archipelago
. .venv/bin/activate

rm -Rf /ap/archipelago/custom_worlds/*
apwm install -i /index -a /apworlds -d /ap/archipelago/custom_worlds
python3 check.py
