import os
import sentry_sdk

if "SENTRY_DSN" in os.environ:
    try:
        with open("version") as fd:
            version = fd.read().strip()
    except FileNotFoundError:
        version = None

    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        instrumenter="otel",
        traces_sample_rate=1.0,
        environment=os.environ.get("ENVIRONMENT", "dev"),
        release=version
    )

from wq import LobbyQueue, JobStatus
import asyncio
import multiprocessing
import sys
import uuid
import handler
import checker


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

    ap_handler = handler.ApHandler(apworlds_dir, custom_apworlds_dir)
    ap_checker = checker.YamlChecker(ap_handler, otlp_endpoint)

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
                await do_a_check(ap_checker, job)
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


async def do_a_check(ap_checker, job):
    result = ap_checker.run_check_for_job(job)
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

