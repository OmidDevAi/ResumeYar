#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ -x ".venv/Scripts/python.exe" ]; then
  PY=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  python -m venv .venv
  if [ -x ".venv/Scripts/python.exe" ]; then PY=".venv/Scripts/python.exe"; else PY=".venv/bin/python"; fi
  "$PY" -m pip install --upgrade pip
  "$PY" -m pip install -r requirements.txt
fi
exec "$PY" app.py
