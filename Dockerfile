FROM debian:12-slim

ARG BASE_COMMIT

RUN apt update && apt -y install python3 git python3-venv python3-tk && apt clean

USER nobody
WORKDIR /ap

RUN mkdir archipelago && \
    cd archipelago && \
    git init && \
    git remote add origin https://github.com/ArchipelagoMW/Archipelago.git && \
    git fetch origin ${BASE_COMMIT} --depth 1 && \
    git reset --hard ${BASE_COMMIT} && \
    python3 -m venv .venv && \
    . .venv/bin/activate && \
    pip install -r requirements.txt && \
    pip install -r WebHostLib/requirements.txt && \
    pip install -r worlds/_sc2common/requirements.txt && \
    pip install -r worlds/alttp/requirements.txt && \
    pip install -r worlds/factorio/requirements.txt && \
    pip install -r worlds/hk/requirements.txt && \
    pip install -r worlds/kh2/requirements.txt && \
    pip install -r worlds/minecraft/requirements.txt && \
    pip install -r worlds/sc2/requirements.txt && \
    pip install -r worlds/soe/requirements.txt && \
    pip install -r worlds/tloz/requirements.txt && \
    pip install -r worlds/zillion/requirements.txt && \
    rm -Rf worlds/* && \
    git checkout worlds/*.py && \
    rm -Rf .git

COPY check.py /ap/archipelago/
COPY run.sh /ap/archipelago/

ENTRYPOINT /ap/archipelago/run.sh
