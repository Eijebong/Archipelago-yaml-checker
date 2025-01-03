from opentelemetry import trace
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sentry_sdk.integrations.opentelemetry import SentryPropagator, SentrySpanProcessor
import sentry_sdk

from Generate import roll_settings, PlandoOptions
from Utils import parse_yamls
from worlds.AutoWorld import AutoWorldRegister, call_all, World
from worlds.generic.Rules import exclusion_rules, locality_rules
from argparse import Namespace
from Options import VerifyKeys, PerGameCommonOptions, StartInventoryPool
from BaseClasses import CollectionState, MultiWorld, LocationProgressType
from worlds import WorldSource

import copy
import os
import requests
import shutil
import sys
import tempfile
from multiprocessing import Process, Pipe


resource = Resource(attributes={
    SERVICE_NAME: "yaml-validation-worker"
})


# Some **supported** apworlds try to get stuff from external APIs. We do not want that as it currently times out in prod
# Until I have a better solution, just return an error immediately when someone tries to use requests
def no_internet(*args, **kwargs):
    raise RuntimeError("The apworld tried to contact the internet which isn't supported with YAML validation.")

requests.get = no_internet
requests.post = no_internet
requests.put = no_internet
requests.head = no_internet
requests.options = no_internet
requests.delete = no_internet

tracer = trace.get_tracer("yaml-validation-worker")

class YamlChecker:
    def __init__(self, apworlds_dir, custom_apworlds_dir, otlp_endpoint):
        self.apworlds_dir = apworlds_dir
        self.custom_apworlds_dir = custom_apworlds_dir
        self.otlp_endpoint = otlp_endpoint

    @tracer.start_as_current_span("load_apworld")
    def load_apworld(self, apworld_name, apworld_version):
        span = trace.get_current_span()
        span.set_attribute("apworld_name", apworld_name)
        span.set_attribute("apworld_version", apworld_version)

        if '/' in apworld_name:
            raise Exception("Invalid apworld name")

        if '/' in apworld_version:
            raise Exception("Invalid apworld version")

        tempdir = tempfile.mkdtemp()
        apworld_path = f"{self.custom_apworlds_dir}/{apworld_name}-{apworld_version}.apworld"
        supported_apworld_path = f"{self.apworlds_dir}/{apworld_name}-{apworld_version}.apworld"
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

    def check(self, yaml_content):
        parsed_yamls = parse_yamls(yaml_content)
        result = False
        err = "No game verified, check your yaml"

        for yaml in parsed_yamls:
            if 'game' not in yaml:
                return {"error": "This doesn't look like an archipelago YAML? Missing game"}
            if 'name' not in yaml:
                return {"error": "This doesn't look like an archipelago YAML? Missing player"}

            game = yaml['game']
            name = yaml['name']
            if isinstance(game, str):
                result, err = check_yaml(game, name, yaml)
            else:
                for game, weight in game.items():
                    if weight == 0:
                        continue

                    yaml_for_game = copy.deepcopy(yaml);
                    for yaml_game in yaml_for_game['game']:
                        yaml_for_game['game'][yaml_game] = 1 if yaml_game == game else 0

                    result, err = check_yaml(game, name, yaml_for_game)
                    if not result:
                        break

        if result:
            return {}

        return {"error": err}

    def _load_apworlds_and_check(self, apworlds, data):
        # Some apworlds (project diva for example) require read access to the player YAMLs at load time to create their world
        # They do so in order to load custom DLC data because archipelago doesn't provide an API for dynamic worlds.
        # To be able to use those apworlds, write the yaml in a tmpdir and then fake out the `--players_files_path` argument
        yamldir = tempfile.mkdtemp()
        with open(f"{yamldir}/Player.yaml", "w") as fd:
            fd.write(data)

        sys.argv.append("--player_files_path")
        sys.argv.append(yamldir)

        try:
            for (apworld, version) in apworlds:
                self.load_apworld(apworld, version)
        except Exception as e:
            # This shouldn't happen ever. If an apworld fails to load, report it to sentry so it raises an alert on top of failing validation
            sentry_sdk.record_exception(e)
            raise e

        return self.check(data)

    def _inner_run_check_for_job(self, params, ctx, wpipe):
        traceProvider = TracerProvider(resource=resource)
        if self.otlp_endpoint:
            processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=self.otlp_endpoint))
            traceProvider.add_span_processor(processor)
        else:
            print("OTLP_ENDPOINT not provided, not enabling otlp exporter")

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
            sentry_processor = SentrySpanProcessor()
            traceProvider.add_span_processor(sentry_processor)
            set_global_textmap(SentryPropagator())

        trace.set_tracer_provider(traceProvider)


        with tracer.start_as_current_span("check_yamls", context=ctx) as span:
            try:
                result = self._load_apworlds_and_check(params['apworlds'], params['yaml'])
                wpipe.send(result)
            except Exception as e:
                span.record_exception(e)
                wpipe.send({"error": f"{e}"})

        traceProvider.force_flush()
        sentry_sdk.flush()

    def run_check_for_job(self, job):
        rpipe, wpipe = Pipe()
        p = Process(target=self._inner_run_check_for_job, args=(job.params, job.ctx, wpipe))
        p.start()

        return rpipe.recv()


class DummyWorld(World):
    game = "Dummy World"
    item_name_to_id = {}
    location_name_to_id = {}
    options_dataclass = PerGameCommonOptions

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
        erargs = Namespace()
        settings = roll_settings(yaml, plando_options)
        span.add_event("Settings rolled")

        for k, v in vars(settings).items():
            if v is not None:
                try:
                    getattr(erargs, k)[1] = v
                except AttributeError:
                    setattr(erargs, k, {1: v})
                except Exception as e:
                    raise Exception(f"Error setting {k} to {v} for player") from e

        for option_name, option in DummyWorld.options_dataclass.type_hints.items():
            getattr(erargs, option_name)[2] = option(option.default)

        # Skip generate_early for Zillion as it generates the level layout which is way too slow
        if game in ["Zillion"]:
            return True, "OK"

        multiworld.set_options(erargs)
        multiworld.set_item_links()

        with tracer.start_span("generate_early"):
            call_all(multiworld, "generate_early")

        # this whole block is basically https://github.com/ArchipelagoMW/Archipelago/blob/7ff201e32c859eeb1b3e07ee087f11da3249f833/Generate.py#L68
        # except it's adapted to generation with 2 YAMLs only, with one being a dummy one using `DummyWorld` above

        for player in multiworld.player_ids:
            for item_name, count in multiworld.worlds[player].options.start_inventory.value.items():
                for _ in range(count):
                    multiworld.push_precollected(multiworld.create_item(item_name, player))

            for item_name, count in getattr(multiworld.worlds[player].options,
                                            "start_inventory_from_pool",
                                            StartInventoryPool({})).value.items():
                for _ in range(count):
                    multiworld.push_precollected(multiworld.create_item(item_name, player))
                # remove from_pool items also from early items handling, as starting is plenty early.
                early = multiworld.early_items[player].get(item_name, 0)
                if early:
                    multiworld.early_items[player][item_name] = max(0, early-count)
                    remaining_count = count-early
                    if remaining_count > 0:
                        local_early = multiworld.local_early_items[player].get(item_name, 0)
                        if local_early:
                            multiworld.early_items[player][item_name] = max(0, local_early - remaining_count)
                        del local_early
                del early

        with tracer.start_span("create_regions"):
            call_all(multiworld, "create_regions")

        with tracer.start_span("create_items"):
            call_all(multiworld, "create_items")

        for player in multiworld.player_ids:
            # items can't be both local and non-local, prefer local
            multiworld.worlds[player].options.non_local_items.value -= multiworld.worlds[player].options.local_items.value
            multiworld.worlds[player].options.non_local_items.value -= set(multiworld.local_early_items[player])

        with tracer.start_span("set_rules"):
            call_all(multiworld, "set_rules")

        for player in multiworld.player_ids:
            exclusion_rules(multiworld, player, multiworld.worlds[player].options.exclude_locations.value)
            multiworld.worlds[player].options.priority_locations.value -= multiworld.worlds[player].options.exclude_locations.value
            world_excluded_locations = set()
            for location_name in multiworld.worlds[player].options.priority_locations.value:
                try:
                    location = multiworld.get_location(location_name, player)
                except KeyError:
                    continue

                if location.progress_type != LocationProgressType.EXCLUDED:
                    location.progress_type = LocationProgressType.PRIORITY
                else:
                    world_excluded_locations.add(location_name)
            multiworld.worlds[player].options.priority_locations.value -= world_excluded_locations

        locality_rules(multiworld)

        with tracer.start_span("generate_basic"):
            call_all(multiworld, "generate_basic")

        # remove starting inventory from pool items.
        # Because some worlds don't actually create items during create_items this has to be as late as possible.
        if any(getattr(multiworld.worlds[player].options, "start_inventory_from_pool", None) for player in multiworld.player_ids):
            new_items: List[Item] = []
            old_items: List[Item] = []
            depletion_pool: Dict[int, Dict[str, int]] = {
                player: getattr(multiworld.worlds[player].options,
                                "start_inventory_from_pool",
                                StartInventoryPool({})).value.copy()
                for player in multiworld.player_ids
            }
            for player, items in depletion_pool.items():
                player_world = multiworld.worlds[player]
                for count in items.values():
                    for _ in range(count):
                        new_items.append(player_world.create_filler())
            target: int = sum(sum(items.values()) for items in depletion_pool.values())
            for i, item in enumerate(multiworld.itempool):
                if depletion_pool[item.player].get(item.name, 0):
                    target -= 1
                    depletion_pool[item.player][item.name] -= 1
                    # quick abort if we have found all items
                    if not target:
                        old_items.extend(multiworld.itempool[i+1:])
                        break
                else:
                    old_items.append(item)

            # leftovers?
            if target:
                for player, remaining_items in depletion_pool.items():
                    remaining_items = {name: count for name, count in remaining_items.items() if count}
                    if remaining_items:
                        # find all filler we generated for the current player and remove until it matches 
                        removables = [item for item in new_items if item.player == player]
                        for _ in range(sum(remaining_items.values())):
                            new_items.remove(removables.pop())
            assert len(multiworld.itempool) == len(new_items + old_items), "Item Pool amounts should not change."
            multiworld.itempool[:] = new_items + old_items

        multiworld.link_items()
    except Exception as e:
        span = trace.get_current_span()
        span.record_exception(e)

        if e.__cause__:
            return False, f"Validation error for {name}: {e} - {e.__cause__}"
        else:
            return False, f"Validation error {name}: {e}"

    return True, "OK"

