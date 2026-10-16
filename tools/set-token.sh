#!/bin/sh
# Replace the Canvas token in every MCP client config. See set_token.py.
# Prefers the project venv, but the script is standard-library only, so any
# python3 will do -- it has to run before the venv exists too.
here=$(cd "$(dirname "$0")" && pwd)
if [ -x "$here/../.venv/bin/python" ]; then
    py="$here/../.venv/bin/python"
else
    py=python3
fi
exec "$py" -I "$here/set_token.py" "$@"
