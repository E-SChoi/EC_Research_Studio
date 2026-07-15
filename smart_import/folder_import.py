
from pathlib import Path, PurePosixPath
from datetime import datetime
import io
import json
import zipfile
import pandas as pd


CATEGORY_DESTINATIONS = {
    "DPV": Path("RawData") / "DPV",
    "SWV": Path("RawData") / "SWV",
    "EIS": Path("RawData") / "EIS",
    "CV": Path("RawData") / "CV",
    "Images": Path("Attachments") / "Images",
    "Other": Path("Attachments") / "Other",
    "Review required": Path("Attachments") / "ReviewRequired",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
OTHER_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".txt", ".json", ".md"}
NATIVE_MAP = {
    ".mtd": "DPV",
    ".mts": "SWV",
    ".mteisp": "EIS",
}


def classify_filename(filename):
    suffix = Path(filename).suffix.lower()

    if suffix in NATIVE_MAP:
        return NATIVE_MAP[suffix]
    if suffix in IMAGE_EXTENSIONS:
        return "Images"
    if suffix in OTHER_EXTENSIONS:
        return "Other"
    if suffix == ".csv":
        return "Review required"
    return "Other"


def _safe_relative_name(name):
    """
    Preserve a useful folder-relative name while preventing path traversal.
    """
    pure = PurePosixPath(str(name).replace("\\", "/"))
    safe_parts = [
        part for part in pure.parts
        if part not in ("", ".", "..") and not part.endswith(":")
    ]
    return "/".join(safe_parts) if safe_parts else Path(str(name)).name


def uploaded_files_to_records(uploaded_files):
    records = []

    for uploaded in uploaded_files or []:
        relative_name = _safe_relative_name(uploaded.name)
        records.append({
            "Original path": relative_name,
            "File": Path(relative_name).name,
            "Detected type": classify_filename(relative_name),
            "Selected type": classify_filename(relative_name),
            "Size (KB)": round(uploaded.size / 1024, 2),
            "Source": "Folder upload",
            "_bytes": uploaded.getvalue(),
        })

    return records


def zip_upload_to_records(uploaded_zip):
    if uploaded_zip is None:
        return []

    data = uploaded_zip.getvalue()
    records = []

    with zipfile.ZipFile(io.BytesIO(data), "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue

            relative_name = _safe_relative_name(info.filename)
            if not relative_name:
                continue

            file_bytes = z.read(info.filename)
            records.append({
                "Original path": relative_name,
                "File": Path(relative_name).name,
                "Detected type": classify_filename(relative_name),
                "Selected type": classify_filename(relative_name),
                "Size (KB)": round(len(file_bytes) / 1024, 2),
                "Source": uploaded_zip.name,
                "_bytes": file_bytes,
            })

    return records


def records_preview_dataframe(records):
    rows = []
    for index, record in enumerate(records):
        category = record.get("Selected type", record.get("Detected type", "Other"))
        destination = CATEGORY_DESTINATIONS.get(category, CATEGORY_DESTINATIONS["Other"])
        rows.append({
            "Record ID": index,
            "Original path": record["Original path"],
            "File": record["File"],
            "Detected type": record["Detected type"],
            "Selected type": category,
            "Destination": destination.as_posix(),
            "Size (KB)": record["Size (KB)"],
            "Source": record["Source"],
        })

    return pd.DataFrame(rows)


def update_records_from_preview(records, preview_df):
    updated = []

    if preview_df is None or preview_df.empty:
        return updated

    by_id = {index: dict(record) for index, record in enumerate(records)}

    for _, row in preview_df.iterrows():
        record_id = int(row["Record ID"])
        if record_id not in by_id:
            continue

        record = by_id[record_id]
        category = str(row["Selected type"])
        if category not in CATEGORY_DESTINATIONS:
            category = "Review required"

        record["Selected type"] = category
        updated.append(record)

    return updated


def _timestamped_name(path, timestamp):
    return path.with_name(f"{path.stem}_{timestamp}{path.suffix}")


def _resolve_destination(target, duplicate_policy, timestamp):
    if not target.exists():
        return target, "Imported"

    if duplicate_policy == "Skip":
        return None, "Skipped duplicate"

    if duplicate_policy == "Overwrite":
        return target, "Overwritten"

    candidate = _timestamped_name(target, timestamp)
    counter = 2
    while candidate.exists():
        candidate = target.with_name(
            f"{target.stem}_{timestamp}_{counter}{target.suffix}"
        )
        counter += 1

    return candidate, "Renamed duplicate"


def import_records(exp_path, records, duplicate_policy="Rename with timestamp"):
    exp_path = Path(exp_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    imported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_rows = []

    for category, destination in CATEGORY_DESTINATIONS.items():
        (exp_path / destination).mkdir(parents=True, exist_ok=True)

    log_dir = exp_path / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    for record in records:
        category = record.get("Selected type", record.get("Detected type", "Other"))
        destination_rel = CATEGORY_DESTINATIONS.get(
            category,
            CATEGORY_DESTINATIONS["Other"],
        )

        # Store by base name. The original folder path remains in the import log.
        requested_target = exp_path / destination_rel / record["File"]
        final_target, status = _resolve_destination(
            requested_target,
            duplicate_policy,
            timestamp,
        )

        if final_target is not None:
            final_target.parent.mkdir(parents=True, exist_ok=True)
            final_target.write_bytes(record["_bytes"])
            final_rel = str(final_target.relative_to(exp_path))
        else:
            final_rel = str(requested_target.relative_to(exp_path))

        log_rows.append({
            "Imported at": imported_at,
            "Source": record.get("Source", ""),
            "Original path": record["Original path"],
            "Original filename": record["File"],
            "Detected type": record["Detected type"],
            "Selected type": category,
            "Destination": final_rel,
            "Duplicate policy": duplicate_policy,
            "Status": status,
            "Size (KB)": record["Size (KB)"],
        })

    log_df = pd.DataFrame(log_rows)
    log_csv = log_dir / f"smart_import_{timestamp}.csv"
    log_df.to_csv(log_csv, index=False, encoding="utf-8-sig")

    counts = (
        log_df.groupby(["Selected type", "Status"])
        .size()
        .reset_index(name="Count")
    )

    metadata = {
        "import_time": imported_at,
        "source_files": sorted(set(log_df["Source"].astype(str))),
        "total_records": int(len(log_df)),
        "duplicate_policy": duplicate_policy,
        "counts_by_type": {
            key: int(value)
            for key, value in log_df["Selected type"].value_counts().to_dict().items()
        },
        "status_counts": {
            key: int(value)
            for key, value in log_df["Status"].value_counts().to_dict().items()
        },
        "log_file": str(log_csv.relative_to(exp_path)),
    }

    metadata_path = log_dir / f"experiment_import_{timestamp}.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "log_df": log_df,
        "counts_df": counts,
        "log_csv": log_csv,
        "metadata_path": metadata_path,
        "metadata": metadata,
    }
