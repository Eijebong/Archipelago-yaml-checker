#!/bin/sh

BASE_COMMIT=daccb30e3d08a39729403e3b4f2da26a638b481a
docker build -t ap-yaml-checker --build-arg=BASE_COMMIT=${BASE_COMMIT} .
