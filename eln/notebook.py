from pathlib import Path
from datetime import datetime
import json
import shutil
import pandas as pd

def notes_dir(exp_path):
    p = Path(exp_path) / "Notes"
    p.mkdir(parents=True, exist_ok=True)
    return p

def eln_file(exp_path):
    return notes_dir(exp_path) / "eln_entries.json"

def load_entries(exp_path):
    p = eln_file(exp_path)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

def save_entries(exp_path, entries):
    eln_file(exp_path).write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")

def add_entry(exp_path, entry, uploaded_files=None):
    exp_path = Path(exp_path)
    entries = load_entries(exp_path)
    entry_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    attachments = []

    if uploaded_files:
        adir = notes_dir(exp_path) / "Attachments" / entry_id
        adir.mkdir(parents=True, exist_ok=True)
        for uploaded in uploaded_files:
            target = adir / uploaded.name
            with open(target, "wb") as f:
                f.write(uploaded.getbuffer())
            attachments.append({
                "name": uploaded.name,
                "relative_path": str(target.relative_to(exp_path)),
                "size_bytes": target.stat().st_size
            })

    item = dict(entry)
    item.update({
        "entry_id": entry_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "attachments": attachments
    })
    entries.append(item)
    save_entries(exp_path, entries)
    export_markdown(exp_path, entries)
    return item

def delete_entry(exp_path, entry_id):
    exp_path = Path(exp_path)
    entries = [e for e in load_entries(exp_path) if e.get("entry_id") != entry_id]
    shutil.rmtree(notes_dir(exp_path) / "Attachments" / entry_id, ignore_errors=True)
    save_entries(exp_path, entries)
    export_markdown(exp_path, entries)

def entries_dataframe(entries):
    return pd.DataFrame([{
        "Date": e.get("created_at", ""),
        "Title": e.get("title", ""),
        "Researcher": e.get("researcher", ""),
        "Category": e.get("category", ""),
        "Measurement": e.get("measurement", ""),
        "Result summary": e.get("result_summary", ""),
        "Attachments": len(e.get("attachments", [])),
        "Entry ID": e.get("entry_id", "")
    } for e in entries])

def export_markdown(exp_path, entries=None):
    entries = load_entries(exp_path) if entries is None else entries
    lines = ["# Electronic Lab Notebook", ""]
    for e in sorted(entries, key=lambda x: x.get("created_at", ""), reverse=True):
        lines += [
            f"## {e.get('title','Untitled entry')}", "",
            f"- Date: {e.get('created_at','')}",
            f"- Researcher: {e.get('researcher','')}",
            f"- Category: {e.get('category','')}",
            f"- Electrode: {e.get('electrode','')}",
            f"- Surface modification: {e.get('surface_modification','')}",
            f"- Recognition element: {e.get('recognition_element','')}",
            f"- Target: {e.get('target','')}",
            f"- Measurement: {e.get('measurement','')}", "",
            "### Protocol / Procedure", e.get("protocol",""), "",
            "### Observation", e.get("observation",""), "",
            "### Result summary", e.get("result_summary",""), "",
            "### Next action", e.get("next_action",""), ""
        ]
        if e.get("attachments"):
            lines.append("### Attachments")
            for a in e["attachments"]:
                lines.append(f"- {a.get('name','')}: `{a.get('relative_path','')}`")
            lines.append("")
        lines += ["---", ""]
    out = notes_dir(exp_path) / "ELN_export.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out
