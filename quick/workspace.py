from pathlib import Path
from datetime import datetime
import zipfile
import pandas as pd

METHODS = ["DPV", "SWV", "EIS", "CV", "Images", "Other"]

def ensure_experiment_structure(exp_path):
    exp_path = Path(exp_path)
    for rel in [
        "RawData/DPV", "RawData/SWV", "RawData/EIS", "RawData/CV",
        "Attachments/Images", "Attachments/Other",
        "Results", "Figures", "Reports", "Notes", "Exports"
    ]:
        (exp_path / rel).mkdir(parents=True, exist_ok=True)

def save_uploaded_files(exp_path, method, uploaded_files):
    exp_path = Path(exp_path)
    ensure_experiment_structure(exp_path)
    if method in ["DPV", "SWV", "EIS", "CV"]:
        target_dir = exp_path / "RawData" / method
    elif method == "Images":
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
            "Category": method,
            "Relative path": str(target.relative_to(exp_path)),
            "Size (KB)": round(target.stat().st_size / 1024, 2),
            "Imported at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    return saved

def build_inventory(exp_path):
    exp_path = Path(exp_path)
    ensure_experiment_structure(exp_path)
    rows = []
    category_map = {
        "RawData/DPV": "DPV raw", "RawData/SWV": "SWV raw",
        "RawData/EIS": "EIS raw", "RawData/CV": "CV raw",
        "Attachments/Images": "Image", "Attachments/Other": "Attachment",
        "Results": "Result", "Figures": "Figure", "Reports": "Report", "Notes": "Note"
    }
    for rel, category in category_map.items():
        folder = exp_path / rel
        if not folder.exists():
            continue
        for p in folder.rglob('*'):
            if p.is_file():
                rows.append({
                    "Category": category,
                    "File": p.name,
                    "Relative path": str(p.relative_to(exp_path)),
                    "Size (KB)": round(p.stat().st_size / 1024, 2),
                    "Modified": datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                })
    if not rows:
        return pd.DataFrame(columns=["Category", "File", "Relative path", "Size (KB)", "Modified"])
    return pd.DataFrame(rows).sort_values(["Category", "File"])

def save_quick_note(exp_path, title, note, tags=""):
    exp_path = Path(exp_path)
    ensure_experiment_structure(exp_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_title = title.strip().replace(' ', '_') or 'note'
    note_path = exp_path / "Notes" / f"{timestamp}_{safe_title}.txt"
    note_path.write_text("\n".join([
        f"Title: {title}",
        f"Created at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Tags: {tags}", "", note
    ]), encoding="utf-8")
    return note_path

def export_experiment_zip(exp_path):
    exp_path = Path(exp_path)
    ensure_experiment_structure(exp_path)
    export_dir = exp_path / "Exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = export_dir / f"{exp_path.name}_export_{timestamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for p in exp_path.rglob('*'):
            if p.is_file() and "Exports" not in p.parts:
                z.write(p, p.relative_to(exp_path))
    return zip_path
