#!/bin/sh
# Runs the lock's built-in MQTT broker (homekey_bridge.h, mode 1) on the host with socket mocks and talks to it
# with a real MQTT client that behaves like the HomeKey-ESP32 reader.
#   pip install paho-mqtt && ./run.sh
set -e
cd "$(dirname "$0")"
c++ -std=c++17 -I. -Wall -o lock_stub lock_stub.cpp
./lock_stub &
LOCK=$!
trap 'kill $LOCK 2>/dev/null; rm -f lock_stub' EXIT
sleep 0.5
python3 reader.py
