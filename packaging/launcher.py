"""Entry point for the packaged executable (PyInstaller).

Starts the bundled Streamlit app on a free local port and opens the browser.
Also works from source: `python packaging/launcher.py`.
"""

import multiprocessing
import os
import socket
import sys
from pathlib import Path


def app_root() -> Path:
    """Folder holding app.py: the PyInstaller bundle when frozen, else the repo root."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parents[1]


def free_port(start: int = 8501, tries: int = 50) -> int:
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free port found between %d and %d" % (start, start + tries))


def main() -> None:
    root = app_root()
    # Remember where the user started us, so dataset search still looks in their folder.
    os.environ.setdefault("AMA_LAUNCH_DIR", str(Path.cwd()))
    # Streamlit finds .streamlit/config.toml (theme) relative to the working directory.
    os.chdir(root)
    sys.path.insert(0, str(root))

    port = free_port()
    sys.argv = [
        "streamlit", "run", str(root / "app.py"),
        "--global.developmentMode=false",   # required when bundled
        "--server.fileWatcherType=none",
        "--server.port", str(port),
        "--server.address=127.0.0.1",
        "--browser.gatherUsageStats=false",
    ]
    print(f"Azure Migration Assistant starting at http://localhost:{port}  (close this window to stop)")

    from streamlit.web import cli as stcli

    sys.exit(stcli.main())


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
