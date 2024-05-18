from Generate import roll_settings, PlandoOptions
from Utils import parse_yamls
from worlds.AutoWorld import AutoWorldRegister
from flask import Flask, request

import copy

app = Flask(__name__)

@app.route("/check_yaml", methods=["POST"])
def check_yaml():
    yaml_content = request.form["data"]
    parsed_yamls = parse_yamls(yaml_content)
    unsupported = []

    for yaml in parsed_yamls:
        if 'game' not in yaml:
            return {"error": "This doesn't look like an archipelago YAML? Missing game"}

        game = yaml['game']
        if isinstance(game, str):
            if is_supported(game):
                result, err = check_yaml(yaml)
            else:
                result = True
                err = "Unsupported"
                unsupported = game
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

                result, err = check_yaml(yaml_for_game)
                if not result:
                    break

    if result:
        return {"unsupported": unsupported}

    return {"error": err, "unsupported": unsupported}


def check_yaml(yaml):
    plando_options = PlandoOptions.from_set(frozenset({"bosses", "items", "connections", "texts"}))
    try:
        roll_settings(yaml, plando_options)
    except Exception as e:
        if e.__cause__:
            return False, f"Validation error: {e} - {e.__cause__}"
        else:
            return False, f"Validation error: {e}"

    return True, "OK"

def is_supported(game):
    return game in AutoWorldRegister.world_types

app.run(host="0.0.0.0")
