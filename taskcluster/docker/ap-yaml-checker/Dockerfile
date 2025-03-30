FROM alpine:latest AS enemizer

ADD --checksum=sha256:efab6784cbfe4189a01e0e25226943afd7f71e7c2f10f74b88bfa34fdac972ab https://github.com/Ijwu/Enemizer/releases/latest/download/ubuntu.16.04-x64.zip Enemizer.zip
RUN apk update && apk add unzip && unzip Enemizer.zip -d /Enemizer

FROM ghcr.io/eijebong/apwm:latest

ARG BASE_COMMIT
ARG FUZZER_COMMIT


# %include checker.py
# %include handler.py
# %include wq.py

# %include ap_tests.py
# %include check_wq.py
# %include gen_wq.py
# %include self_check.py

# %include run.sh
# %include run_gen.sh
# %include prepare_worlds.sh

COPY /topsrcdir/* /ap/archipelago/
COPY --from=enemizer /Enemizer /ap/enemizer
COPY setup.sh /ap/setup.sh

WORKDIR /ap
RUN bash /ap/setup.sh ${BASE_COMMIT} ${FUZZER_COMMIT} && rm /ap/setup.sh

CMD /ap/archipelago/run.sh
