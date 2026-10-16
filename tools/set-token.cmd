@echo off
REM Replace the Canvas token in every MCP client config. See set_token.py.
REM Prefers the project venv; falls back to the py launcher, since the script
REM is standard-library only and has to run before the venv exists too.
set "PY=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
"%PY%" -I "%~dp0set_token.py" %*
