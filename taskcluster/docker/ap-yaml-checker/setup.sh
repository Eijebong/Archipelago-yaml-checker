#!/bin/sh

set -ex

BASE_COMMIT=$1
FUZZER_COMMIT=$2

apt update && apt -y install git zip curl gcc python3-dev python3-tkinter

mkdir -p /ap/archipelago
cd /ap/archipelago

git init
git remote add origin https://github.com/Eijebong/Archipelago.git
git fetch origin ${BASE_COMMIT} --depth 1
git reset --hard ${BASE_COMMIT}

ls
pwd

uv venv
uv pip install -r requirements.txt
uv run cythonize -a -i _speedups.pyx
uv pip install -r WebHostLib/requirements.txt
uv pip install -r worlds/_sc2common/requirements.txt
uv pip install -r worlds/alttp/requirements.txt
uv pip install -r worlds/factorio/requirements.txt
uv pip install -r worlds/hk/requirements.txt
uv pip install -r worlds/kh2/requirements.txt
uv pip install -r worlds/minecraft/requirements.txt
uv pip install -r worlds/sc2/requirements.txt
uv pip install -r worlds/soe/requirements.txt
uv pip install -r worlds/tloz/requirements.txt
uv pip install -r worlds/zillion/requirements.txt
uv pip install python-sat==1.8.dev13 opentelemetry-api==1.26.0 opentelemetry-sdk==1.26.0 opentelemetry-exporter-otlp-proto-grpc==1.26.0 aiohttp==3.9.5 "sentry-sdk[opentelemetry]==2.19.2" dolphin-memory-engine==1.3.0
git rev-parse HEAD > /ap/archipelago/version
mkdir -p /ap/supported_worlds
chown -R worker:worker /ap/archipelago
echo "jakanddaxter_options:\n  enforce_friendly_options: false" > /ap/archipelago/host.yaml

bash /ap/archipelago/prepare_worlds.sh /ap/archipelago /ap/supported_worlds
rm /ap/archipelago/prepare_worlds.sh

curl https://raw.githubusercontent.com/Eijebong/Archipelago-fuzzer/${FUZZER_COMMIT}/fuzz.py -o /ap/archipelago/fuzz.py

apt purge -y gcc python3-dev
apt autoremove -y
rm -Rf .git
uv cache clean
rm -Rf /var/lib/apt/lists/*
