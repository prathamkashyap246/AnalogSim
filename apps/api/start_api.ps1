$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = $scriptDir
$pythonExe = Join-Path $scriptDir "app\.venv\Scripts\python.exe"

& $pythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
