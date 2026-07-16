
from pathlib import Path, PurePosixPath
from datetime import datetime
import json
import re
import pandas as pd

from project.manager import safe_name, create_experiment


ZERO_TERMS = {
    "pbs",
    "zero",
    "blank",
    "control",
    "negativecontrol",
    "negative_control",
    "negative-control",
}

UNIT_TO_PM = {
    "pm": 1.0,
    "nm": 1.0e3,
    "um": 1.0e6,
    "µm": 1.0e6,
    "μm": 1.0e6,
    "mm": 1.0e9,
    "m": 1.0e12,
}


def infer_source_folder_name(records, fallback="Smart_Experiment"):
    """
    Infer the uploaded folder name.

    Folder upload:
      root_folder/file.mtd -> root_folder

    ZIP upload:
      Prefer the common top-level folder.
      If unavailable, use the ZIP filename without .zip.
    """
    if not records:
        return fallback

    paths = [
        PurePosixPath(str(record.get("Original path", "")).replace("\\", "/"))
        for record in records
    ]
    first_parts = [
        path.parts[0]
        for path in paths
        if len(path.parts) >= 2 and path.parts[0] not in ("", ".", "..")
    ]

    if first_parts and len(set(first_parts)) == 1:
        return first_parts[0]

    sources = [
        str(record.get("Source", "")).strip()
        for record in records
        if str(record.get("Source", "")).strip()
    ]
    zip_sources = [Path(source).stem for source in sources if source.lower().endswith(".zip")]
    if zip_sources:
        return zip_sources[0]

    return fallback


def sanitize_experiment_name(name):
    cleaned = safe_name(str(name))
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "Smart_Experiment"


def resolve_experiment_name(project_path, suggested_name, collision_policy):
    project_path = Path(project_path)
    experiments_root = project_path / "Experiments"
    experiments_root.mkdir(parents=True, exist_ok=True)

    base_name = sanitize_experiment_name(suggested_name)
    candidate = experiments_root / base_name

    if not candidate.exists():
        return base_name, "Create new"

    if collision_policy == "Use existing":
        return base_name, "Use existing"

    if collision_policy == "Cancel":
        return None, "Cancelled"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    renamed = f"{base_name}_{timestamp}"
    counter = 2
    while (experiments_root / renamed).exists():
        renamed = f"{base_name}_{timestamp}_{counter}"
        counter += 1

    return renamed, "Create new with timestamp"


def parse_concentration_from_filename(filename):
    """
    Parse concentration and normalize it to pM.

    Examples:
      3-pbs.mtd       -> 0 pM
      4-10pM.mtd      -> 10 pM
      sample_1nM.mts  -> 1000 pM
      blank.mteisp    -> 0 pM
    """
    stem = Path(filename).stem
    normalized = stem.lower().replace(" ", "")
    tokens = re.split(r"[^a-z0-9µμ]+", normalized)
    token_set = {token for token in tokens if token}

    if token_set.intersection(ZERO_TERMS):
        return {
            "Label": "Zero",
            "Concentration_pM": 0.0,
            "Detected unit": "zero",
            "Detection status": "Detected",
        }

    match = re.search(
        r"(?<![a-z0-9])(\d+(?:\.\d+)?)\s*(pm|nm|um|µm|μm|mm|m)(?![a-z])",
        stem,
        flags=re.IGNORECASE,
    )

    if match is None:
        # Handles compact names such as 10pM after separators were removed by Path stem.
        match = re.search(
            r"(\d+(?:\.\d+)?)(pm|nm|um|µm|μm|mm|m)",
            normalized,
            flags=re.IGNORECASE,
        )

    if match is not None:
        value = float(match.group(1))
        unit = match.group(2).lower()
        concentration_pm = value * UNIT_TO_PM[unit]
        return {
            "Label": f"{value:g} {unit}",
            "Concentration_pM": float(concentration_pm),
            "Detected unit": unit,
            "Detection status": "Detected",
        }

    # Treat a filename made only from 0 / zero-like separators as the zero sample.
    if re.fullmatch(r"(?:0+|0+[-_ ]*(?:pbs|zero|blank|control))", normalized):
        return {
            "Label": "Zero",
            "Concentration_pM": 0.0,
            "Detected unit": "zero",
            "Detection status": "Detected",
        }

    return {
        "Label": stem,
        "Concentration_pM": None,
        "Detected unit": "",
        "Detection status": "Review required",
    }


def build_concentration_preview(records):
    rows = []

    for index, record in enumerate(records):
        category = record.get("Selected type", record.get("Detected type", "Other"))
        if category not in ["DPV", "SWV", "EIS"]:
            continue

        parsed = parse_concentration_from_filename(record["File"])
        rows.append({
            "Record ID": index,
            "Method": category,
            "File": record["File"],
            "Original path": record.get("Original path", record["File"]),
            "Label": parsed["Label"],
            "Concentration_pM": parsed["Concentration_pM"],
            "Detected unit": parsed["Detected unit"],
            "Detection status": parsed["Detection status"],
        })

    if not rows:
        return pd.DataFrame(columns=[
            "Record ID",
            "Method",
            "File",
            "Original path",
            "Label",
            "Concentration_pM",
            "Detected unit",
            "Detection status",
        ])

    df = pd.DataFrame(rows)
    return df.sort_values(
        ["Method", "Concentration_pM", "File"],
        na_position="last",
    ).reset_index(drop=True)


def update_records_and_concentrations(records, concentration_df):
    updated = [dict(record) for record in records]

    if concentration_df is None or concentration_df.empty:
        return updated

    for _, row in concentration_df.iterrows():
        record_id = int(row["Record ID"])
        if not (0 <= record_id < len(updated)):
            continue

        concentration = pd.to_numeric(
            pd.Series([row.get("Concentration_pM")]),
            errors="coerce",
        ).iloc[0]

        updated[record_id]["Smart label"] = str(row.get("Label", "")).strip()
        updated[record_id]["Concentration_pM"] = (
            None if pd.isna(concentration) else float(concentration)
        )
        updated[record_id]["Concentration status"] = (
            "Review required"
            if pd.isna(concentration)
            else "Confirmed"
        )

    return updated


def create_or_open_smart_experiment(
    project_path,
    project_info,
    experiment_name,
    collision_policy,
    metadata=None,
):
    resolved_name, action = resolve_experiment_name(
        project_path,
        experiment_name,
        collision_policy,
    )

    if resolved_name is None:
        return None, action

    exp_path = Path(project_path) / "Experiments" / resolved_name

    if action == "Use existing":
        return exp_path, action

    exp_info = {
        "experiment_name": resolved_name,
        "researcher": "",
        "target": "",
        "sensor": "",
        "recognition": "",
        "technique": [],
        "temperature": "",
        "reaction_time": "",
        "comment": "Created by Smart Experiment",
        "smart_experiment": metadata or {},
    }

    exp_path = create_experiment(
        Path(project_path),
        project_info,
        exp_info,
    )
    return exp_path, action


def save_concentration_tables(exp_path, records):
    exp_path = Path(exp_path)
    table_root = exp_path / "Notes" / "SmartExperiment"
    table_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_rows = []

    for record in records:
        method = record.get("Selected type", record.get("Detected type", "Other"))
        if method not in ["DPV", "SWV", "EIS"]:
            continue

        concentration = record.get("Concentration_pM")
        all_rows.append({
            "Method": method,
            "File": record["File"],
            "Label": record.get("Smart label", Path(record["File"]).stem),
            "Concentration_pM": concentration,
            "Concentration_M": (
                None if concentration is None else float(concentration) * 1.0e-12
            ),
            "Detection status": record.get("Concentration status", "Review required"),
        })

    all_df = pd.DataFrame(all_rows)
    csv_paths = {}

    if all_df.empty:
        return {
            "all_table": all_df,
            "all_csv": None,
            "method_csvs": {},
        }

    all_df = all_df.sort_values(
        ["Method", "Concentration_pM", "File"],
        na_position="last",
    ).reset_index(drop=True)

    all_csv = table_root / f"all_concentrations_{timestamp}.csv"
    all_df.to_csv(all_csv, index=False, encoding="utf-8-sig")

    for method in ["DPV", "SWV", "EIS"]:
        method_df = all_df[all_df["Method"] == method].copy()
        if method_df.empty:
            continue

        method_csv = table_root / f"{method.lower()}_concentrations_{timestamp}.csv"
        method_df.to_csv(method_csv, index=False, encoding="utf-8-sig")
        csv_paths[method] = method_csv

    return {
        "all_table": all_df,
        "all_csv": all_csv,
        "method_csvs": csv_paths,
    }


def update_experiment_smart_metadata(
    exp_path,
    source_name,
    concentration_table_info,
    import_result,
    auto_analysis_summary=None,
):
    exp_path = Path(exp_path)
    exp_json = exp_path / "experiment.json"

    try:
        info = json.loads(exp_json.read_text(encoding="utf-8"))
    except Exception:
        info = {}

    info["smart_experiment"] = {
        "source_name": source_name,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "concentration_table": (
            str(concentration_table_info["all_csv"].relative_to(exp_path))
            if concentration_table_info.get("all_csv")
            else ""
        ),
        "import_log": (
            str(import_result["log_csv"].relative_to(exp_path))
            if import_result and import_result.get("log_csv")
            else ""
        ),
        "auto_analysis_completed": bool(auto_analysis_summary is not None),
    }

    exp_json.write_text(
        json.dumps(info, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
