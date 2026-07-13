
from pathlib import Path
from datetime import datetime
import zipfile
import pandas as pd

def ensure_structure(exp_path):
    exp_path = Path(exp_path)
    folders = [
        "RawData/DPV", "RawData/SWV", "RawData/EIS", "RawData/CV",
        "Attachments/Images", "Attachments/Other",
        "Results", "Figures", "Reports", "Notes", "Exports"
    ]
    for rel in folders:
        (exp_path / rel).mkdir(parents=True, exist_ok=True)

def save_uploaded_files(exp_path, category, uploaded_files):
    exp_path = Path(exp_path)
    ensure_structure(exp_path)

    if category in ["DPV", "SWV", "EIS", "CV"]:
        target_dir = exp_path / "RawData" / category
    elif category == "Images":
        target_dir = exp_path / "Attachments" / "Images"
    else:
        target_dir = exp_path / "Attachments" / "Other"

    saved = []
    for uploaded in uploaded_files or []:
        target = target_dir / uploaded.name
        with open(target, "wb") as f:
            f.write(uploaded.getbuffer())

        saved.append({
            "File": uploaded.name,
            "Category": category,
            "Relative path": str(target.relative_to(exp_path)),
            "Size (KB)": round(target.stat().st_size / 1024, 2),
            "Imported at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    return saved

def save_quick_note(exp_path, observation, result, next_action):
    exp_path = Path(exp_path)
    ensure_structure(exp_path)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    note_path = exp_path / "Notes" / f"{timestamp}_quick_note.txt"

    content = [
        f"Created at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "[Observation]",
        observation,
        "",
        "[Result]",
        result,
        "",
        "[Next action]",
        next_action,
    ]
    note_path.write_text("\n".join(content), encoding="utf-8")
    return note_path

def build_inventory(exp_path):
    exp_path = Path(exp_path)
    ensure_structure(exp_path)

    mapping = {
        "RawData/DPV": "DPV raw",
        "RawData/SWV": "SWV raw",
        "RawData/EIS": "EIS raw",
        "RawData/CV": "CV raw",
        "Attachments/Images": "Image",
        "Attachments/Other": "Attachment",
        "Results": "Result",
        "Figures": "Figure",
        "Reports": "Report",
        "Notes": "Note",
    }

    rows = []
    for rel, category in mapping.items():
        folder = exp_path / rel
        if not folder.exists():
            continue
        for p in folder.rglob("*"):
            if p.is_file():
                rows.append({
                    "Category": category,
                    "File": p.name,
                    "Relative path": str(p.relative_to(exp_path)),
                    "Size (KB)": round(p.stat().st_size / 1024, 2),
                    "Modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                })

    if not rows:
        return pd.DataFrame(columns=["Category", "File", "Relative path", "Size (KB)", "Modified"])

    return pd.DataFrame(rows).sort_values(["Category", "File"])

def get_analysis_status(exp_path):
    exp_path = Path(exp_path)
    status = {}

    for method in ["DPV", "SWV", "EIS", "CV"]:
        raw_dir = exp_path / "RawData" / method
        result_dir = exp_path / "Results" / method

        raw_count = len(list(raw_dir.glob("*"))) if raw_dir.exists() else 0
        result_count = len(list(result_dir.rglob("*"))) if result_dir.exists() else 0

        if result_count > 0:
            state = "Done"
        elif raw_count > 0:
            state = "Ready"
        else:
            state = "No data"

        status[method] = {
            "raw_count": raw_count,
            "result_count": result_count,
            "state": state
        }

    return status

def recent_figures(exp_path, limit=6):
    exp_path = Path(exp_path)
    fig_root = exp_path / "Figures"
    if not fig_root.exists():
        return []

    figures = [p for p in fig_root.rglob("*.png") if p.is_file()]
    figures.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return figures[:limit]

def export_experiment_zip(exp_path):
    exp_path = Path(exp_path)
    ensure_structure(exp_path)

    export_dir = exp_path / "Exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = export_dir / f"{exp_path.name}_export_{timestamp}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in exp_path.rglob("*"):
            if not p.is_file():
                continue
            if "Exports" in p.parts:
                continue
            z.write(p, p.relative_to(exp_path))

    return zip_path
