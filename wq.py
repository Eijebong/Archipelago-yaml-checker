import aiohttp
import asyncio
import uuid
import enum
import os
import sys
import multiprocessing

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

import check

class JobStatus(enum.Enum):
    Success = "Success"
    Failure = "Failure"
    InternalError = "InternalError"

class LobbyQueue:
    def __init__(self, root_url, queue_name, worker_id, token, loop):
        self.queue_name = queue_name
        self.worker_id = worker_id
        self.client = aiohttp.ClientSession(root_url, loop=loop)
        self.token = token

    async def claim_job(self):
        resp = await self.post("claim_job", json={"worker_id": self.worker_id})
        resp.raise_for_status()

        job_raw = await resp.json()
        if job_raw is None:
            return None

        return Job(self, **job_raw)

    async def post(self, route, *args, **kwargs):
        route = "/queues/{}/{}".format(self.queue_name, route)
        if 'headers' not in kwargs:
            kwargs['headers'] = {}

        if 'otlp_context' in kwargs:
            W3CBaggagePropagator().inject(kwargs['headers'], kwargs['otlp_context'])
            TraceContextTextMapPropagator().inject(kwargs['headers'], kwargs['otlp_context'])
            del kwargs['otlp_context']

        kwargs['headers']['X-Worker-Auth'] = self.token
        result = await self.client.post(route, *args, **kwargs)
        result.raise_for_status()
        return result

    async def close(self):
        await self.client.close()


class Job:
    def __init__(self, queue, job_id, params):
        self._queue = queue
        self.job_id = job_id
        self.params = params
        self.ctx = TraceContextTextMapPropagator().extract(carrier=params['otlp_context'])

    async def resolve(self, status, result):
        await self._queue.post("resolve_job", json={"worker_id": self._queue.worker_id, "job_id": self.job_id, "status": status.value, "result": result})

    async def reclaim_job(self):
        await self._queue.post("reclaim_job", json={"worker_id": self._queue.worker_id, "job_id": self.job_id})


async def main(loop):
    try:
        apworlds_dir = sys.argv[1]
        custom_apworlds_dir = sys.argv[2]
    except:
        print("Usage wq.py worlds_dir custom_worlds_dir")
        sys.exit(1)

    root_url = os.environ.get("LOBBY_ROOT_URL")
    if root_url is None:
        print("Please provide the lobby root url in `LOBBY_ROOT_URL`")
        sys.exit(1)

    token = os.environ.get("YAML_VALIDATION_QUEUE_TOKEN")
    if token is None:
        print("Please provide a token in `YAML_VALIDATION_QUEUE_TOKEN`")
        sys.exit(1)

    otlp_endpoint = os.environ.get("OTLP_ENDPOINT")

    checker = check.YamlChecker(apworlds_dir, custom_apworlds_dir, otlp_endpoint)
    worker_name = str(uuid.uuid4())
    q = LobbyQueue(root_url, "yaml_validation", worker_name, token, loop)

    while True:
        job = await q.claim_job()

        try:
            if job is not None:
                print(f"Claimed job: {job.job_id}")
                await do_a_check(checker, job)
        except Exception as e:
            print(e)
            # TODO: Light the beacon, gondor's calling for help
            await job.resolve(JobStatus.InternalError, {"error": str(e)})

    await q.close()


async def do_a_check(checker, job):
    result = checker.run_check_for_job(job)
    status = JobStatus.Failure if 'error' in result else JobStatus.Success
    await job.resolve(status, result)
    print(f"Resolved job {job.job_id} with status {status}")


if __name__ == "__main__":
    multiprocessing.set_start_method('fork')
    loop = asyncio.new_event_loop()
    loop.run_until_complete(main(loop))
