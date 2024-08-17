from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from Generate import roll_settings, PlandoOptions
from Utils import parse_yamls
from worlds.AutoWorld import AutoWorldRegister, call_all
from argparse import Namespace
from Options import VerifyKeys
from BaseClasses import CollectionState, MultiWorld
from flask import Flask, request
import os

import copy


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

@app.route("/restart", methods=["GET"])
def restart():
    os._exit(0)

@app.route("/check_yaml", methods=["POST"])
def check_yaml():
    ctx = TraceContextTextMapPropagator().extract(carrier=request.headers)
    with tracer.start_as_current_span("check_yamls", context=ctx) as span:
        yaml_content = request.form["data"]
        parsed_yamls = parse_yamls(yaml_content)
        unsupported = []

        for yaml in parsed_yamls:
            if 'game' not in yaml:
                return {"error": "This doesn't look like an archipelago YAML? Missing game"}

            game = yaml['game']
            if isinstance(game, str):
                if is_supported(game):
                    result, err = check_yaml(game, yaml)
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

                    result, err = check_yaml(game, yaml_for_game)
                    if not result:
                        break

        if result:
            return {"unsupported": unsupported}

        return {"error": err, "unsupported": unsupported}


@tracer.start_as_current_span("check_yaml")
def check_yaml(game, yaml):
    span = trace.get_current_span()
    span.set_attribute("game", game)
    plando_options = PlandoOptions.from_set(frozenset({"bosses", "items", "connections", "texts"}))
    try:
        world_type = AutoWorldRegister.world_types[game]
        multiworld = MultiWorld(1)
        multiworld.game = {1: world_type.game}
        multiworld.player_name = {1: f"YAMLChecker"}
        multiworld.set_seed(0)
        multiworld.state = CollectionState(multiworld)

        span.add_event("Rolling settings")
        yaml_args = vars(roll_settings(yaml, plando_options))
        span.add_event("Settings rolled")

        span.add_event("Verifying keys")
        args = Namespace()
        for name, option in world_type.options_dataclass.type_hints.items():
            value = yaml_args.get(name, option.default)

            if issubclass(option, VerifyKeys):
                option.verify_keys(value.value)

            setattr(args, name, {1: value})
        span.add_event("Keys verified")

        # Skip generate_early for Zillion as it generates the level layout which is way too slow
        if game in ["Zillion"]:
            return True, "OK"

        with tracer.start_span("generate_early"):
            multiworld.set_options(args)
            call_all(multiworld, "generate_early")
    except Exception as e:
        if e.__cause__:
            return False, f"Validation error: {e} - {e.__cause__}"
        else:
            return False, f"Validation error: {e}"

    return True, "OK"

def is_supported(game):
    return game in AutoWorldRegister.world_types

app.run(host="0.0.0.0")
