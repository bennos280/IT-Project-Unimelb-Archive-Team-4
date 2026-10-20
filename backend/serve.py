"""`uv run app`: the API and the worker, until Ctrl+C. `uv run api`: just the API, reloading on code changes. `uv run prestcribe`:
the installed app, the built frontend with the API and the worker, opened in the browser."""
import subprocess
import sys
import threading
import webbrowser

from backend.common import ROOT
from backend.db import database

ADDRESS = "http://127.0.0.1:8000"


def main(app="backend.api.main:app", open_browser=False):
    database.migrate()
    #no reloading: on Windows, uvicorn reloads by sending Ctrl+C to the whole terminal, which would stop the worker too
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", app])
    worker = subprocess.Popen([sys.executable, "-m", "backend.worker"])
    if open_browser:
        threading.Timer(3, webbrowser.open, [ADDRESS]).start()  #once the API is listening
    try:
        api.wait()
    except KeyboardInterrupt:  #both got the Ctrl+C: let each stop itself
        api.wait()
        worker.wait()
    else:  #the API stopped by itself
        worker.terminate()


def installed():
    print(f"PrestCribe is running at {ADDRESS}. Close this window to stop it.")
    main("backend.site:site", open_browser=True)


def api():
    import uvicorn
    database.migrate()
    uvicorn.run("backend.api.main:app", reload=True, reload_dirs=[str(ROOT / "backend")])
