__import__("sys").path.append("/home/eijebong/code/ap0.5")

import os
import sentry_sdk

if "SENTRY_DSN" in os.environ:
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        instrumenter="otel",
        traces_sample_rate=1.0,
        environment=os.environ.get("ENVIRONMENT", "dev")
    )

import aiohttp
import asyncio
import enum
import multiprocessing
import sys
import uuid

from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

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

    worker_name = str(uuid.uuid4())
    otlp_endpoint = os.environ.get("OTLP_ENDPOINT")

    checker = check.YamlChecker(apworlds_dir, custom_apworlds_dir, otlp_endpoint)

    q = LobbyQueue(root_url, "yaml_validation", worker_name, token, loop)

    while True:
        try:
            job = await q.claim_job()
        except Exception as e:
            print(f"Error while claiming job from lobby: {e}. Retrying in 1s...")
            await asyncio.sleep(1)
            continue

        try:
            if job is not None:
                print(f"Claimed job: {job.job_id}")
                await do_a_check(checker, job)
            continue
        except Exception as e:
            print(e)
            sentry_sdk.capture_exception(e)

            try:
                await job.resolve(JobStatus.InternalError, {"error": str(e)})
            except Exception as e:
                print(e)
                sentry_sdk.capture_exception(e)
                continue

    await q.close()


async def do_a_check(checker, job):
    result = checker.run_check_for_job(job)
    status = JobStatus.Failure if 'error' in result else JobStatus.Success
    await job.resolve(status, result)
    print(f"Resolved job {job.job_id} with status {status}")


if __name__ == "__main__":
    multiprocessing.set_start_method('fork')
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(main(loop))
    except KeyboardInterrupt:
        pass
