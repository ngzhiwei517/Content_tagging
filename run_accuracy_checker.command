#!/bin/bash
set -e

cd "$(dirname "$0")"

if [ ! -x ".venv/bin/python" ]; then
  echo "The local environment is not installed yet."
  echo "Run: bash setup_mac.command"
  exit 1
fi

exec .venv/bin/python -m streamlit run creative_type_accuracy_checker_v7_alias_normalized.py
