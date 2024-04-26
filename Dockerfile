FROM debian:12-slim

ARG BASE_COMMIT

RUN apt update && apt -y install python3 git python3-venv && apt clean

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
    rm -Rf worlds/* && \
    git checkout worlds/*.py && \
    rm -Rf .git && \
    pip install -r requirements.txt && \
    pip install -r WebHostLib/requirements.txt && \
    pip install maseya-z3pr>=1.0.0rc1 xxtea>=3.0.0

COPY check.py /ap/archipelago/
COPY run.sh /ap/archipelago/

ENTRYPOINT /ap/archipelago/run.sh
