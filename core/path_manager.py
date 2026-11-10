"""
Path Manager for Local Dataset File Persistence & Resolution.
Enables saving and resolving local file paths so datasets persist across app restarts
without storing large file byte buffers in memory.
"""

import json
import os
import re
from pathlib import Path
from core.schemas import check_filename_includes, normalize_name

# Saved paths live in the user's home so they work for a packaged executable too (the bundle is read-only
# and shared, and must never ship one person's file paths).
CONFIG_DIR = Path.home() / ".azure_migration_assistant"
CONFIG_FILE = CONFIG_DIR / "saved_dataset_paths.json"
# Where the user launched the app from (the packaged launcher changes the working directory).
LAUNCH_DIR = Path(os.environ.get("AMA_LAUNCH_DIR", Path.cwd()))
DEFAULT_SEARCH_DIRS = [LAUNCH_DIR / "samples", LAUNCH_DIR, Path.home() / "Downloads"]


def load_persistent_paths() -> dict:
    """Reads saved dataset paths from the user config file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                valid = {}
                for k, v in data.items():
                    if isinstance(v, str) and Path(v).exists():
                        valid[k] = str(Path(v).resolve())
                return valid
        except Exception:
            return {}
    return {}


def save_persistent_path(slot_key: str, file_path: str):
    """Saves or updates a file path in the user config file."""
    paths = load_persistent_paths()
    if file_path and Path(file_path).exists():
        paths[slot_key] = str(Path(file_path).resolve())
    else:
        paths.pop(slot_key, None)
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(paths, f, indent=2)
    except Exception:
        pass


def clear_persistent_paths():
    """Removes all saved paths from the config file."""
    if CONFIG_FILE.exists():
        try:
            CONFIG_FILE.unlink()
        except Exception:
            pass


def find_local_system_path(filename_or_keyword: str, custom_dirs=None):
    """
    Checks whether a file exists on the local filesystem by exact path, filename,
    or keyword matching (lowercase, special characters removed).
    Returns resolved Path if found on disk, otherwise None.
    """
    if not filename_or_keyword:
        return None

    # 1. Exact path or relative path
    p = Path(filename_or_keyword).expanduser()
    if p.exists() and p.is_file():
        return p.resolve()

    target_clean = normalize_name(filename_or_keyword)
    dirs = (custom_dirs or []) + DEFAULT_SEARCH_DIRS

    # 2. Search candidate directories
    for d in dirs:
        dir_path = Path(d).expanduser().resolve()
        if not dir_path.is_dir():
            continue
        for f in dir_path.iterdir():
            if f.is_file() and f.suffix.lower() in [".xlsx", ".xls", ".csv"]:
                # Exact name match
                if f.name.lower() == str(filename_or_keyword).lower() or normalize_name(f.name) == target_clean:
                    return f.resolve()
                # Keyword containment match
                if target_clean in normalize_name(f.name):
                    return f.resolve()

    return None


def scan_default_local_files():
    """
    Scans ./samples and ./ for the 3 required dataset files.
    Returns dict mapping slot keys ('arm', 'ba', 'cmdb') to resolved Path or None.
    """
    found = {"arm": None, "ba": None, "cmdb": None, "axonius": None, "rvtools": None, "visual_group": None, "sizing_report": None}
    saved = load_persistent_paths()

    # Pre-populate from saved config if valid
    for slot in ["arm", "ba", "cmdb", "axonius", "rvtools", "visual_group", "sizing_report"]:
        if slot in saved and Path(saved[slot]).exists():
            found[slot] = Path(saved[slot]).resolve()

    # If any slot is missing, auto-discover from local directories
    if not found["arm"]:
        found["arm"] = find_local_system_path("ARM Service now")
    if not found["ba"]:
        found["ba"] = find_local_system_path("ba_as_server") or find_local_system_path("ba_as_a_server")
    if not found["cmdb"]:
        found["cmdb"] = find_local_system_path("cmdb_ci_server")
    if not found["axonius"]:
        found["axonius"] = find_local_system_path("axonius")
    if not found["rvtools"]:
        found["rvtools"] = find_local_system_path("rvtools")
    if not found["visual_group"]:
        found["visual_group"] = find_local_system_path("visual_group")
    if not found["sizing_report"]:
        found["sizing_report"] = find_local_system_path("sizing_report")

    return found
