import sys
sys.path.append("/home/eijebong/code/archipelago")

if len(sys.argv) != 7:
    print("Usage: self_check.py worlds_dir custom_worlds_dir apworld_name world_version world_name output_folder")
    sys.exit(1)

import check
import os
from Options import get_option_groups
from Utils import __version__, local_path
from jinja2 import Template
from worlds import AutoWorldRegister

import yaml


def world_from_apworld_name(apworld_name):
    for name, world in AutoWorldRegister.world_types.items():
        if world.__module__.startswith(f"worlds.{apworld_name}"):
            return name, world

    raise Exception(f"Couldn't find loaded workd with world: {apworld_name}")

# In Options.py
def generate_template(world_name, expected_world_name):
    def dictify_range(option):
        data = {option.default: 50}
        for sub_option in ["random", "random-low", "random-high"]:
            if sub_option != option.default:
                data[sub_option] = 0

        notes = {}
        for name, number in getattr(option, "special_range_names", {}).items():
            notes[name] = f"equivalent to {number}"
            if number in data:
                data[name] = data[number]
                del data[number]
            else:
                data[name] = 0

        return data, notes

    def yaml_dump_scalar(scalar) -> str:
        # yaml dump may add end of document marker and newlines.
        return yaml.dump(scalar).replace("...\n", "").strip()

    game_name, world = world_from_apworld_name(world_name)
    if world is None:
        raise Exception(f"Failed to resolve apworld from apworld name: {apworld_name}")

    if expected_world_name != game_name:
        raise Exception(f"The given apworld doesn't match the game named passed in. Expected {game_name}, got {expected_world_name}")

    option_groups = get_option_groups(world)
    with open(local_path("data", "options.yaml")) as f:
        file_data = f.read()

    res = Template(file_data).render(
        option_groups=option_groups,
        __version__=__version__, game=game_name, yaml_dump=yaml_dump_scalar,
        dictify_range=dictify_range,
    )

    return res

if __name__ == "__main__":
    apworld = sys.argv[3]
    version = sys.argv[4]
    world_name = sys.argv[5]
    output_folder = sys.argv[6]
    check.load_apworld(apworld, version)

    yaml_content = generate_template(apworld, world_name)

    with open(os.path.join(output_folder, "template.yaml"), "w") as fd:
        fd.write(yaml_content)
    result = check.check(yaml_content)

    if 'err' in result:
        print("Error while validating the apworld: {apworld} {version}")
        print(result["err"])
        sys.exit(1)

    if result['unsupported']:
        print("Unexpected unsupported apworlds, this should not happen:", result["unsupported"])
        sys.exit(1)

    print(f"Successfully validated {apworld} {version}")

