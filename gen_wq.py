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
        release=version,
    )

from wq import LobbyQueue, JobStatus
import asyncio
import multiprocessing
import sys
import uuid
import handler
import tempfile
import traceback
import aiohttp
import zipfile
import io
import random
from io import StringIO
from contextlib import redirect_stderr, redirect_stdout
from multiprocessing import Process, Pipe
from Generate import main as GenMain, PlandoOptions
from Main import main as ERmain
import Main
from argparse import Namespace
import Utils

ORIG_USER_PATH = Utils.user_path

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

    token = os.environ.get("GENERATION_QUEUE_TOKEN")
    if token is None:
        print("Please provide a token in `GENERATION_QUEUE_TOKEN`")
        sys.exit(1)

    api_key = os.environ.get("LOBBY_API_KEY")
    if api_key is None:
        print("Please provide an API key in `LOBBY_API_KEY`")
        sys.exit(1)

    output_dir = os.environ.get("GENERATOR_OUTPUT_DIR")
    if output_dir is None:
        print("Please provide an output dir in `GENERATOR_OUTPUT_DIR`")
        sys.exit(1)

    worker_name = str(uuid.uuid4())
    otlp_endpoint = os.environ.get("OTLP_ENDPOINT")

    ap_handler = handler.ApHandler(apworlds_dir, custom_apworlds_dir)
    async with LobbyQueue(root_url, "generation", worker_name, token, loop) as q:
        while True:
            try:
                job = await q.claim_job()
            except RuntimeError:
                break
            except Exception as e:
                print(f"Error while claiming job from lobby: {e}. Retrying in 1s...")
                await asyncio.sleep(1)
                continue

            try:
                if job is not None:
                    print(f"Claimed job: {job.job_id}")
                    await do_a_gen(ap_handler, job, root_url, output_dir)
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


async def gather_resources(root_url, room_id, players_dir):
    async with aiohttp.ClientSession(root_url) as client:
        yamls_url = f"/room/{room_id}/yamls"
        response = await client.get(yamls_url, headers = { "X-Api-Key": os.environ["LOBBY_API_KEY"] })
        response.raise_for_status()

        body = io.BytesIO(await response.read())
        z = zipfile.ZipFile(body)
        z.extractall(players_dir)

def _inner_run_gen_for_job(job, ctx, ap_handler, root_url, output_dir, wpipe):
    output_path = os.path.join(output_dir, job.job_id)
    os.makedirs(output_path, exist_ok=True)
    out_file = open(os.path.join(output_path, "output.log"), "w")
    with redirect_stdout(out_file), redirect_stderr(out_file):
        # TODO: ctx should setup otlp + sentry
        loop = asyncio.new_event_loop()

        # Override Utils.user path so we can customize the logs folder
        def my_user_path(name):
            if name == "logs":
                return output_path
            return ORIG_USER_PATH(name)


        Utils.user_path = my_user_path

        try:
            room_id = job.params["room_id"]

            players_dir = tempfile.mkdtemp(prefix="apgen")
            loop.run_until_complete(gather_resources(root_url, room_id, players_dir))
            # TODO: Get meta file
            for apworld, version in job.params["apworlds"]:
                ap_handler.load_apworld(apworld, version)

            from settings import get_settings

            settings = get_settings()

            args = Namespace(
                **{
                    "weights_file_path": settings.generator.weights_file_path,
                    "sameoptions": False,
                    "player_files_path": players_dir,
                    "seed": random.randint(10000, 10000000),
                    "multi": 1,
                    "spoiler": 1,
                    "outputpath": output_path,
                    "race": False,
                    "meta_file_path": "meta-doesnt-exist.yaml", # TODO
                    "log_level": "info",
                    "yaml_output": 1,
                    "plando": PlandoOptions.from_set(frozenset({"bosses", "items", "connections", "texts"})),
                    "skip_prog_balancing": False,
                    "skip_output": False,
                    "csv_output": False,
                    "log_time": False,
                }
            )
            erargs, seed = GenMain(args)
            ERmain(erargs, seed)
        except Exception as e:
            error = traceback.format_exc()
            traceback.print_exc()
            sentry_sdk.capture_exception(e)

            wpipe.send({"error": error})
            return

        result = {}
        wpipe.send(result)

async def run_gen_for_job(job, ap_handler, root_url, output_dir):
    rpipe, wpipe = Pipe()
    data_available = asyncio.Event()
    asyncio.get_event_loop().add_reader(rpipe.fileno(), data_available.set)


    async def reclaim_loop():
        while True:
            await job.reclaim()
            await asyncio.sleep(7)

    task = loop.create_task(reclaim_loop())

    p = Process(target=_inner_run_gen_for_job, args=(job, job.ctx, ap_handler, root_url, output_dir, wpipe))
    p.start()

    while not rpipe.poll():
        await data_available.wait()
        data_available.clear()

    asyncio.get_event_loop().remove_reader(rpipe.fileno())
    ret = rpipe.recv()
    task.cancel()

    return ret


async def do_a_gen(ap_handler, job, root_url, output_dir):
    result = await run_gen_for_job(job, ap_handler, root_url, output_dir)

    status = JobStatus.Failure if "error" in result else JobStatus.Success
    await job.resolve(status, result)
    print(f"Resolved job {job.job_id} with status {status}")


if __name__ == "__main__":
    multiprocessing.set_start_method("fork")
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(main(loop))
    except KeyboardInterrupt:
        pass
