FROM ghcr.io/eijebong/apwm:latest

ARG BASE_COMMIT

RUN apt update && apt -y install python3 git python3-venv python3-tk zip && apt clean

# %include wq.py
# %include check.py
# %include self_check.py
# %include run.sh

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
    pip install python-sat==1.8.dev13 opentelemetry-api==1.26.0 opentelemetry-sdk==1.26.0 opentelemetry-exporter-otlp-proto-grpc==1.26.0 aiohttp==3.9.5 "sentry-sdk[opentelemetry]==2.19.2" && \
    git rev-parse HEAD > /ap/archipelago/version && \
    mkdir -p /ap/supported_worlds && \
    chown -R worker:worker /ap/archipelago && \
    rm -Rf .git

# %include prepare_worlds.sh
COPY /topsrcdir/prepare_worlds.sh /ap/archipelago/
RUN bash /ap/archipelago/prepare_worlds.sh /ap/archipelago /ap/supported_worlds

COPY /topsrcdir/wq.py /ap/archipelago/
COPY /topsrcdir/check.py /ap/archipelago/
COPY /topsrcdir/self_check.py /ap/archipelago/
COPY /topsrcdir/run.sh /ap/archipelago/

CMD /ap/archipelago/run.sh
