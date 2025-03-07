FROM ghcr.io/eijebong/apwm:latest

ARG BASE_COMMIT
ARG FUZZER_COMMIT


# %include wq.py
# %include check.py
# %include self_check.py
# %include ap_tests.py
# %include run.sh
# %include prepare_worlds.sh

COPY /topsrcdir/* /ap/archipelago/
COPY setup.sh /ap/setup.sh

WORKDIR /ap
RUN bash /ap/setup.sh ${BASE_COMMIT} ${FUZZER_COMMIT} && rm /ap/setup.sh

CMD /ap/archipelago/run.sh
