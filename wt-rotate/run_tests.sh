#!/usr/bin/env bash
# Suite de tests wt-rotate — zéro dépendance externe.
#   Serveur Python : unittest (stdlib) + aiohttp.test_utils
#   Extension      : runner natif `node --test`
# Lancer depuis n'importe où : ./run_tests.sh
set -e
cd "$(dirname "$0")"

echo "── Tests serveur (Python / unittest) ──────────────────────────"
python3 -m unittest discover -s tests -t . -v

echo
echo "── Tests extension (Node / node:test) ─────────────────────────"
node --test tests/*.test.js

echo
echo "✓ Toute la suite est verte."
