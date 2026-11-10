"""Dataset loading helpers shared by all pages."""

import io
import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from core.schemas import detect_schema
from core.path_manager import find_local_system_path, save_persistent_path
from core.sample_data import generate_sample_datasets
from core.source_adapters import normalize_frame, validate_source


def _read_dataset(file_ref, file_name, in_memory=False):
    """Read a supported file and select the worksheet with the strongest schema match."""
    if file_name.lower().endswith((".xlsx", ".xls")):
        workbook = pd.ExcelFile(file_ref)
        sheet_names = workbook.sheet_names
        candidates = []
        for index, sheet in enumerate(sheet_names):
            header = pd.read_excel(workbook, sheet_name=sheet, nrows=0)
            schema = detect_schema(header.columns)
            candidates.append((schema != "Custom / Unknown", index, sheet, schema))
        recognized = [candidate for candidate in candidates if candidate[0]]
        if recognized:
            _, _, selected_sheet, schema = recognized[0]
        else:
            selected_sheet = sheet_names[0]
            schema = "Custom / Unknown"
        return pd.read_excel(workbook, sheet_name=selected_sheet), sheet_names, selected_sheet, True, schema

    df = pd.read_csv(file_ref)
    return df, ["default"], "default", False, detect_schema(df.columns)


def _file_digest(path=None, file_bytes=None):
    digest = hashlib.sha256()
    if path is not None:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    else:
        digest.update(file_bytes or b"")
    return digest.hexdigest()


def load_dataset_from_source(source, expected_schema=None, slot_key=None):
    """
    Loads dataset from a local file path (str or Path) or uploaded file object.
    If the file exists on the local filesystem, saves the path, avoids holding large
    file_bytes in memory, and persists the path across app restarts.
    """
    file_path = None
    file_name = ""
    file_bytes = None

    if isinstance(source, (str, Path)):
        resolved = Path(source).expanduser().resolve()
        if resolved.exists() and resolved.is_file():
            file_path = resolved
            file_name = resolved.name
        else:
            st.error(f"File not found on system: {source}")
            return False
    elif hasattr(source, "name"):
        file_name = source.name
        # Check if this uploaded file exists on the local system
        local_match = find_local_system_path(file_name)
        if local_match:
            file_path = local_match
        else:
            file_bytes = source.getvalue()
    else:
        return False

    try:
        source_hash = _file_digest(file_path, file_bytes) if file_path else _file_digest(file_bytes=file_bytes)
        duplicate = next((name for name, meta in st.session_state.datasets.items() if meta.get("source_hash") == source_hash), None)
        if duplicate and duplicate != file_name:
            st.warning(f"This file matches already loaded dataset `{duplicate}`. Skipped duplicate import.")
            return True

        schema = detect_schema(file_name)
        if schema == "Custom / Unknown" and expected_schema:
            schema = expected_schema

        if file_path:
            df, sheet_names, pref_sheet, is_excel, sheet_schema = _read_dataset(file_path, file_name)
            if sheet_schema != "Custom / Unknown":
                schema = sheet_schema
            normalized_df, lineage = normalize_frame(df, schema, file_name)
            validation = validate_source(df, schema)

            # Persist path if slot_key provided or derivable
            derived_slot = slot_key
            if not derived_slot:
                if schema == "ARM SERVICE NOW FILE":
                    derived_slot = "arm"
                elif schema == "BA-AS-A-SERVER":
                    derived_slot = "ba"
                elif schema == "CMDB-CI-SERVER":
                    derived_slot = "cmdb"
            if derived_slot:
                save_persistent_path(derived_slot, str(file_path))

            st.session_state.datasets[file_name] = {
                "file_path": str(file_path),
                "file_bytes": None,
                "df": df,
                "detected_schema": schema,
                "source_hash": source_hash,
                "normalized_df": normalized_df,
                "source_lineage": lineage,
                "validation": validation,
                "sheets": sheet_names,
                "active_sheet": pref_sheet,
                "is_excel": is_excel,
                "is_local": True
            }
            return True
        else:
            # In-memory uploaded bytes fallback
            df, sheet_names, pref_sheet, is_excel, sheet_schema = _read_dataset(io.BytesIO(file_bytes), file_name, in_memory=True)
            if sheet_schema != "Custom / Unknown":
                schema = sheet_schema
            normalized_df, lineage = normalize_frame(df, schema, file_name)
            validation = validate_source(df, schema)

            st.session_state.datasets[file_name] = {
                "file_path": None,
                "file_bytes": file_bytes,
                "df": df,
                "detected_schema": schema,
                "source_hash": source_hash,
                "normalized_df": normalized_df,
                "source_lineage": lineage,
                "validation": validation,
                "sheets": sheet_names,
                "active_sheet": pref_sheet,
                "is_excel": is_excel,
                "is_local": False
            }
            return True
    except Exception as e:
        st.error(f"Error loading {file_name}: {e}")
        return False


def load_file_into_state(file_name, file_bytes, expected_schema=None):
    """Compatibility wrapper calling load_dataset_from_source."""
    class DummyUpload:
        def __init__(self, name, bytes_val):
            self.name = name
            self._bytes = bytes_val
        def getvalue(self):
            return self._bytes
    return load_dataset_from_source(DummyUpload(file_name, file_bytes), expected_schema=expected_schema)


def load_sample_data():
    """Populates session state with mock datasets for testing."""
    samples = generate_sample_datasets()
    st.session_state.datasets.clear()
    for name, df in samples.items():
        schema = detect_schema(name)
        st.session_state.datasets[name] = {
            "df": df,
            "detected_schema": schema,
            "sheets": ["Sheet1"],
            "active_sheet": "Sheet1",
            "is_excel": True,
            "file_bytes": None
        }


def convert_df_to_excel_bytes(dfs_dict):
    """Converts a dict of {sheet_name: df} into an in-memory Excel workbook."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in dfs_dict.items():
            safe_name = str(sheet_name)[:31].replace(":", "_").replace("/", "_").replace("\\", "_")
            df.to_excel(writer, sheet_name=safe_name, index=False)
    output.seek(0)
    return output.getvalue()
