from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from Generate import roll_settings, PlandoOptions
from Utils import parse_yamls
from worlds.AutoWorld import AutoWorldRegister, call_all, World
from argparse import Namespace
from Options import VerifyKeys
from BaseClasses import CollectionState, MultiWorld
from worlds import WorldSource
from flask import Flask, request

import copy
import json
import os
import tempfile
import shutil
import sys


try:
    APWORLDS_DIR = sys.argv[1]
    CUSTOM_APWORLDS_DIR = sys.argv[2]
except:
    print("Usage check.py worlds_dir custom_worlds_dir")
    sys.exit(1)

tracer = trace.get_tracer("yaml-validator")
resource = Resource(attributes={
    SERVICE_NAME: "yaml-checker"
})

otlp_endpoint = os.environ.get("OTLP_ENDPOINT")
if otlp_endpoint:
    traceProvider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
    traceProvider.add_span_processor(processor)
    trace.set_tracer_provider(traceProvider)
else:
    print("OTLP_ENDPOINT not provided, not enabling otlp exporter")


app = Flask(__name__)

@app.route("/healthz", methods=["GET"])
def healthz():
    return "OK"

@tracer.start_as_current_span("load_apworld")
def load_apworld(apworld_name, apworld_version):
    span = trace.get_current_span()
    span.set_attribute("apworld_name", apworld_name)
    span.set_attribute("apworld_version", apworld_version)

    if '/' in apworld_name:
        raise Exception("Invalid apworld name")

    if '/' in apworld_version:
        raise Exception("Invalid apworld version")

    tempdir = tempfile.mkdtemp()
    apworld_path = f"{CUSTOM_APWORLDS_DIR}/{apworld_name}-{apworld_version}.apworld"
    supported_apworld_path = f"{APWORLDS_DIR}/{apworld_name}-{apworld_version}.apworld"
    dest_path = f"{tempdir}/{apworld_name}.apworld"

    if os.path.isfile(apworld_path):
        shutil.copy(apworld_path, dest_path)
    elif os.path.isfile(supported_apworld_path):
        shutil.copy(supported_apworld_path, dest_path)
    else:
        if "worlds." + apworld_name in sys.modules:
            return
        raise Exception("Invalid apworld: {}, version {}".format(apworld_name, apworld_version))

    WorldSource(dest_path, is_zip=True, relative=False).load()

@app.route("/check_yaml", methods=["POST"])
def check_yaml_route():
    ctx = TraceContextTextMapPropagator().extract(carrier=request.headers)
    data = request.form["data"]
    apworlds = request.form["apworlds"]

    rpipe, wpipe = os.pipe()
    pid = os.fork()
    if pid == 0:
        with tracer.start_as_current_span("check_yamls", context=ctx) as span:
            try:
                for (apworld, version) in json.loads(apworlds):
                    load_apworld(apworld, version)
            except Exception as e:
                os.write(wpipe, json.dumps({"error": f"Failed to load apworld: {e}"}).encode())
                os.close(wpipe)
                span.__exit__(None, None, None)
                processor.force_flush()
                os._exit(0)

            try:
                value = check_request(ctx, data)
                os.write(wpipe, json.dumps(value).encode())
            except Exception as e:
                if e.__cause__:
                    os.write(wpipe, json.dumps({"error": f"{e} - {e.__cause__}"}).encode())
                else:
                    os.write(wpipe, json.dumps({"error": f"{e}"}).encode())
            finally:
                os.close(wpipe)
                span.__exit__(None, None, None)
                processor.force_flush()
                os._exit(0)
    else:
        os.close(wpipe)
        response = b""
        while True:
            partial = os.read(rpipe, 1024)
            if not partial:
                break
            response += partial

        return response.decode()


def check_request(ctx, data):
    yaml_content = data
    parsed_yamls = parse_yamls(yaml_content)
    unsupported = []

    for yaml in parsed_yamls:
        if 'game' not in yaml:
            return {"error": "This doesn't look like an archipelago YAML? Missing game"}
        if 'name' not in yaml:
            return {"error": "This doesn't look like an archipelago YAML? Missing player"}

        game = yaml['game']
        name = yaml['name']
        if isinstance(game, str):
            if is_supported(game):
                result, err = check_yaml(game, name, yaml)
            else:
                result = True
                err = "Unsupported"
                unsupported = [game,]
        else:
            for game, weight in game.items():
                if weight == 0:
                    continue

                if not is_supported(game):
                    result = True
                    err = "Unsupported"
                    unsupported.append(game)
                    continue

                yaml_for_game = copy.deepcopy(yaml);
                for yaml_game in yaml_for_game['game']:
                    yaml_for_game['game'][yaml_game] = 1 if yaml_game == game else 0

                result, err = check_yaml(game, name, yaml_for_game)
                if not result:
                    break

    if result:
        return {"unsupported": unsupported}

    return {"error": err, "unsupported": unsupported}

class DummyWorld(World):
    game = "Dummy World"
    item_name_to_id = {}
    location_name_to_id = {}

@tracer.start_as_current_span("check_yaml")
def check_yaml(game, name, yaml):
    span = trace.get_current_span()
    span.set_attribute("game", game)
    plando_options = PlandoOptions.from_set(frozenset({"bosses", "items", "connections", "texts"}))
    try:
        world_type = AutoWorldRegister.world_types[game]
        multiworld = MultiWorld(2)
        multiworld.game = {1: world_type.game, 2: "Dummy World"}
        multiworld.player_name = {1: f"YAMLChecker", 2: f"YAMLChecker2"}
        multiworld.set_seed(0)
        multiworld.state = CollectionState(multiworld)

        span.add_event("Rolling settings")
        yaml_args = vars(roll_settings(yaml, plando_options))
        span.add_event("Settings rolled")

        span.add_event("Verifying keys")
        args = Namespace()
        for name, option in world_type.options_dataclass.type_hints.items():
            value = yaml_args.get(name, option.default)

            setattr(args, name, {1: value, 2: {}})
        span.add_event("Keys verified")

        # Skip generate_early for Zillion as it generates the level layout which is way too slow
        if game in ["Zillion"]:
            return True, "OK"

        with tracer.start_span("generate_early"):
            multiworld.set_options(args)
            call_all(multiworld, "generate_early")
    except Exception as e:
        if e.__cause__:
            return False, f"Validation error for {name}: {e} - {e.__cause__}"
        else:
            return False, f"Validation error {name}: {e}"

    return True, "OK"

def is_supported(game):
    return game in AutoWorldRegister.world_types

app.run(host="0.0.0.0")
