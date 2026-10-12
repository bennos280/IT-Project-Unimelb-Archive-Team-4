"""`uv run app`: the API and the worker, until Ctrl+C. `uv run api`: just the API, reloading on code changes."""
import subprocess
import sys

from backend.common import ROOT
from backend.db import database


def main():
    database.migrate()
    #no reloading: on Windows, uvicorn reloads by sending Ctrl+C to the whole terminal, which would stop the worker too
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "backend.api.main:app"])
    worker = subprocess.Popen([sys.executable, "-m", "backend.worker"])
    try:
        api.wait()
    except KeyboardInterrupt:  #both got the Ctrl+C: let each stop itself
        api.wait()
        worker.wait()
    else:  #the API stopped by itself
        worker.terminate()


def api():
    import uvicorn
    database.migrate()
    uvicorn.run("backend.api.main:app", reload=True, reload_dirs=[str(ROOT / "backend")])
