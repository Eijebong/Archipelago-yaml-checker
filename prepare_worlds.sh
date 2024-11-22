set -ex

if [ "$1" == ""  ] || [ "$2" == "" ]; then
    echo "Usage: prepare_worlds.sh ap_root dest"
    exit 1
fi

DEST=$2

for f in $1/worlds/*; do
    if [[ -f $f ]]; then
        continue
    fi

    if [[ "$(basename $f)" == _* ]]; then
        continue;
    fi

    if [[ "$(basename $f)" == "generic" ]]; then
        continue
    fi

    # Until this gets fixed, alttp is essential for most things to work...
    # Yes it makes no sense, no I can't do anything about it.
    if [[ "$(basename $f)" == "alttp" ]]; then
        continue
    fi

    # FF1 throws errors when loaded as a .apworld
    if [[ "$(basename $f)" == "ff1" ]]; then
        continue
    fi

    # OoT throws errors when loaded as a .apworld
    if [[ "$(basename $f)" == "oot" ]]; then
        continue
    fi

    # Raft throws errors when loaded as a .apworld
    if [[ "$(basename $f)" == "raft" ]]; then
        continue
    fi

    (cd $(dirname $f) && zip -r ${DEST}/$(basename $f)-0.5.0.apworld $(basename $f))
    rm -Rf "$f"
done