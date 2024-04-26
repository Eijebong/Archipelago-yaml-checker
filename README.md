Archipelago YAML checker
========================

This project is a helper to build a docker container containing an "empty"
archipelago installation and a very simple web server with a single route.

To build the container, simply run `./build.sh`, it'll clone the archipelago
repository and install all necessary dependencies. It'll build a container
named `ap-yaml-checker`.

To run it, `docker run -p 5000:5000 --mount type=bind,source=$(pwd)/worlds,target=/ap/archipelago/worlds -it ap-yaml-checker`
Not that the provided worlds folder requires a few things apart from the usual
apworlds. Because of how docker handles bind mounts and how archipelago doesn't
want worlds to be in a different folder, the container can't provide those
mandatory files. The list of files to provide in addition to your apworlds in the world directory is as follows:

- AutoSNIClient.py
- AutoWorld.py
- Files.py
- generic/
- __init__.py
- LauncherComponents.py

As of archipelago 0.4.6 you also need to provide a world for alttp.

### Routes

#### `/check_yaml`

Provide it a file as a multipart upload `data`. It'll return `{}` if the file
is OK, and `{"error": "..."}` if it isn't with `"..."` being the error message
from archipelago.
