"""Build a one-folder executable of the Azure Migration Assistant with PyInstaller.

    python packaging/build.py            # builds for the current OS into dist/
    python packaging/build.py --onefile  # single file (slower startup)

PyInstaller cannot cross-compile: run on Windows for .exe, macOS for the macOS app.
The GitHub Actions workflow does both. Real exports in samples/ are NOT bundled.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "AzureMigrationAssistant"
SEP = ";" if os.name == "nt" else ":"

# Only these are shipped alongside the code. samples/ (real-looking exports) is deliberately absent.
DATA = ["app.py", "app_pages", "core", "docs", ".streamlit"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--onefile", action="store_true")
    args = ap.parse_args()

    cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--name", NAME,
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        "--console",  # keep a console window: shows the URL and lets users stop the app
        "--collect-all", "streamlit",
        "--copy-metadata", "streamlit",
        "--collect-all", "openpyxl",
        "--collect-all", "xlsxwriter",
        "--hidden-import", "pandas",
        "--hidden-import", "core.azure_recommender",
        "--hidden-import", "core.app_lookup",
        "--hidden-import", "core.dataset_loader",
        "--hidden-import", "core.path_manager",
        "--hidden-import", "core.schemas",
        "--hidden-import", "core.sample_data",
        "--paths", str(ROOT),
    ]
    cmd.append("--onefile" if args.onefile else "--onedir")
    for item in DATA:
        src = ROOT / item
        dest = item if src.is_dir() else "."
        cmd += ["--add-data", f"{src}{SEP}{dest}"]
    cmd.append(str(ROOT / "packaging" / "launcher.py"))

    print(" ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)

    if args.onefile:
        exe = ROOT / "dist" / (NAME + (".exe" if os.name == "nt" else ""))
        print(f"\nBuilt single file: {exe}")
        return

    # Zip the folder for sharing
    label = {"Darwin": "macos", "Windows": "windows", "Linux": "linux"}.get(platform.system(), platform.system().lower())
    archive = shutil.make_archive(str(ROOT / "dist" / f"{NAME}-{label}"), "zip", ROOT / "dist", NAME)
    print(f"\nBuilt: {archive}")


if __name__ == "__main__":
    main()
