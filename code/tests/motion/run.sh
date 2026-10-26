#!/bin/sh
# Simulates a door lock (end stops, clutch backlash, reed magnet, key turns, jams) against motion.h
set -e
cd "$(dirname "$0")"
c++ -std=c++17 -Wall -Wextra -o sim sim.cpp
trap 'rm -f sim' EXIT
./sim
