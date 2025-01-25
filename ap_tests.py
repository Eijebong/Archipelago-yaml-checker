import sys

if len(sys.argv) != 7:
    print("Usage: self_check.py worlds_dir custom_worlds_dir apworld_name world_version world_name output_folder")
    sys.exit(1)

import check
import json
import os
import unittest
from test.bases import WorldTestBase
import test.general.test_fill
import test.general.test_ids



if __name__ == "__main__":
    apworlds_dir = sys.argv[1]
    custom_apworlds_dir = sys.argv[2]
    apworld = sys.argv[3]
    version = sys.argv[4]
    world_name = sys.argv[5]
    output_folder = sys.argv[6]

    os.makedirs(output_folder, exist_ok=True)
    checker = check.YamlChecker(apworlds_dir, custom_apworlds_dir, None)
    checker.load_apworld(apworld, version)

    class WorldTest(WorldTestBase):
        game = world_name

    runner = unittest.TextTestRunner(verbosity=2)

    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(WorldTest))
    suite.addTests(unittest.defaultTestLoader.discover("test/general", top_level_dir="."))
    results = runner.run(suite)

    if results.failures or results.errors:
        output = {
            "failures": {fail.id(): {"traceback": tb, "description": fail.shortDescription() } for fail, tb in results.failures},
            "errors": {error.id(): {"traceback": tb, "description": error.shortDescription()} for error, tb in results.errors},
            "apworld": apworld,
            "version": version,
            "world_name": world_name
        }

        with open(os.path.join(output_folder, f"{apworld}.aptest"), "w") as fd:
            fd.write(json.dumps(output))

    if not results.wasSuccessful():
        sys.exit(1)

    print(f"Successfully validated {apworld} {version}")
