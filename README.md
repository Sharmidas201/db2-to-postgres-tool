# Azure Migration Assistant - Data Explorer

A lightweight, single-user Streamlit application for inspecting, searching, and exporting Excel and CSV datasets used for infrastructure and application sizing (ARM ServiceNow, BA-to-Server mapping, RV_Tools VMware exports, CMDB-CI-SERVER, and Axonius).

## Quick Start

### 1. Launch the Application
Run the launcher script:
```bash
./run.sh
```
Or directly activate the virtual environment and run Streamlit:
```bash
.venv/bin/streamlit run app.py
```

The application will open in your browser at `http://localhost:8501`.

---

## Features

1. **Multi-File Upload & Auto-Detection**:
   - Drag and drop multiple `.xlsx`, `.xls`, or `.csv` files at once.
   - Automatically detects whether the file is:
     - `ARM SERVICE NOW FILE` (Applications catalog)
     - `BA-AS-A-SERVER` (Application-to-Server mapping)
     - `RV_TOOLS` (VMware VM vCPU, RAM, and Disk storage)
     - `CMDB-CI-SERVER` (Physical/Cloud servers, CPU, RAM, Disk)
     - `AXONIUS DEVICES` (Asset reconciliation)
2. **Sheet Selector**:
   - For multi-tab Excel files (such as RV_Tools), choose between sheets (e.g. `vInfo`, `vCPU`, `vDisk`, `vMemory`).
3. **Interactive Data Table**:
   - Global keyword search across all columns.
   - Column selector to display/hide any columns.
   - Sortable columns and resizeable table view.
4. **Column & Data Type Inspector**:
   - Expandable breakdown showing data types, non-null counts, unique counts, and sample values.
5. **Downloads & Exports**:
   - Export any viewed dataset as CSV.
   - Export any viewed dataset as Excel (`.xlsx`).
   - One-click **Consolidated Excel Export** that combines all uploaded datasets into a single workbook with individual tabs.
6. **Built-in Sample Data**:
   - Click the **🧪 Sample Data** button in the sidebar to instantly populate realistic mock datasets matching the schemas in `schema.md`.

## Azure sizing rules

Recommendations follow `azure_research.md` (Canada Central, Flexible Server, D/E/B-series v5):

- **Production:** General Purpose (D-series v5, 1:4) by default. Memory Optimized (E-series, 1:8) only when source RAM:vCPU is above 4:1 or *Force Memory Optimized* is on.
- **Non-production:** Burstable (B-series), dev/test only. Stop off-hours. No zone-redundant HA.
- **Optional inputs:** peak CPU % sizes vCPUs at 65% target utilization; hot working set GB sizes RAM at 1.5x. Without them, cores map 1:1 and RAM uses 1.25x source RAM.
- **Storage:** +30% MVCC/WAL headroom on allocated disk, 32 GiB minimum.
