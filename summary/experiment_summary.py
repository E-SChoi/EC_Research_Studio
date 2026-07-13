
from pathlib import Path
from datetime import datetime
import base64
import html
import pandas as pd


METHODS = ["DPV", "SWV", "EIS", "CV"]


def _latest_file(paths):
    paths = [p for p in paths if p.exists() and p.is_file()]
    return max(paths, key=lambda p: p.stat().st_mtime) if paths else None


def _read_table(path):
    if path is None:
        return None
    try:
        if path.suffix.lower() == ".xlsx":
            return pd.read_excel(path)
        return pd.read_csv(path)
    except Exception:
        return None


def _method_from_path(path):
    for method in METHODS:
        if method in Path(path).parts:
            return method
    return "Other"


def latest_result_table(exp_path):
    exp_path = Path(exp_path)
    result_root = exp_path / "Results"
    if not result_root.exists():
        return None, None, None

    candidates = []
    for p in result_root.rglob("*"):
        if p.is_file() and p.suffix.lower() in [".csv", ".xlsx"]:
            candidates.append(p)

    latest = _latest_file(candidates)
    if latest is None:
        return None, None, None

    return _method_from_path(latest), latest, _read_table(latest)


def latest_method_figure(exp_path, preferred_method=None):
    exp_path = Path(exp_path)
    fig_root = exp_path / "Figures"
    if not fig_root.exists():
        return None, None

    preferred_names = [
        "2_baseline_shift_overlay.png",
        "1_raw_overlay.png",
        "2_cv_peak_marked.png",
        "1_nyquist_overlay.png",
        "1_eis_overlay.png",
    ]

    methods = [preferred_method] if preferred_method in METHODS else METHODS

    for method in methods:
        method_root = fig_root / method
        if not method_root.exists():
            continue

        for name in preferred_names:
            hits = list(method_root.rglob(name))
            latest = _latest_file(hits)
            if latest:
                return method, latest

        latest = _latest_file(list(method_root.rglob("*.png")))
        if latest:
            return method, latest

    latest = _latest_file(list(fig_root.rglob("*.png")))
    if latest:
        return _method_from_path(latest), latest

    return None, None


def latest_delta_peak_table(exp_path, preferred_method=None):
    exp_path = Path(exp_path)
    result_root = exp_path / "Results"

    if not result_root.exists():
        return None, None, None

    methods = [preferred_method] if preferred_method in ["DPV", "SWV"] else ["DPV", "SWV"]

    filename_candidates = [
        "peak_values.csv",
        "peak_values.xlsx",
        "baseline_info.csv",
        "baseline_info.xlsx",
    ]

    for method in methods:
        method_root = result_root / method
        if not method_root.exists():
            continue

        candidates = []
        for name in filename_candidates:
            candidates.extend(method_root.rglob(name))

        latest = _latest_file(candidates)
        df = _read_table(latest)
        if latest is not None and df is not None and not df.empty:
            return method, latest, df

    return None, None, None


def compact_latest_values(df, max_rows=8):
    if df is None or df.empty:
        return pd.DataFrame()

    preferred = [
        "Label",
        "Concentration_pM",
        "Baseline_potential_V",
        "Peak_potential_V",
        "DeltaPeak_max_minus_min_uA",
        "DeltaPeak_peak_minus_preceding_min_uA",
        "DeltaDeltaPeak_vs_zero_uA",
        "Abs_DeltaDeltaPeak_vs_zero_uA",
        "Rct_ohm",
        "DeltaRct_vs_zero_ohm",
        "R2",
        "LOD_pM",
        "LOQ_pM",
    ]

    cols = [c for c in preferred if c in df.columns]
    if not cols:
        cols = df.columns[: min(6, len(df.columns))].tolist()

    return df.loc[:, cols].tail(max_rows).reset_index(drop=True)


def experiment_counts(exp_path):
    exp_path = Path(exp_path)
    rows = []

    for method in METHODS:
        raw_dir = exp_path / "RawData" / method
        result_dir = exp_path / "Results" / method
        figure_dir = exp_path / "Figures" / method

        rows.append({
            "Method": method,
            "Raw files": len([p for p in raw_dir.iterdir() if p.is_file()]) if raw_dir.exists() else 0,
            "Result files": len([p for p in result_dir.rglob("*") if p.is_file()]) if result_dir.exists() else 0,
            "Figures": len([p for p in figure_dir.rglob("*.png") if p.is_file()]) if figure_dir.exists() else 0,
        })

    return pd.DataFrame(rows)


def latest_eln_entry(exp_path):
    exp_path = Path(exp_path)
    eln_path = exp_path / "Notes" / "eln_entries.json"
    if not eln_path.exists():
        return None

    try:
        import json
        entries = json.loads(eln_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    if not entries:
        return None

    return sorted(entries, key=lambda x: x.get("created_at", ""))[-1]


def _image_data_uri(path):
    path = Path(path)
    if not path.exists():
        return ""

    mime = "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def create_html_report(
    exp_path,
    experiment_name,
    latest_method,
    latest_result_path,
    latest_result_df,
    graph_method,
    graph_path,
    delta_method,
    delta_path,
    delta_df,
):
    exp_path = Path(exp_path)
    report_dir = exp_path / "Reports" / "ExperimentSummary"
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = report_dir / f"{experiment_name}_summary_{timestamp}.html"

    counts_df = experiment_counts(exp_path)
    latest_values = compact_latest_values(latest_result_df)
    delta_values = compact_latest_values(delta_df)
    eln = latest_eln_entry(exp_path)

    graph_html = ""
    if graph_path is not None:
        graph_html = (
            f'<img class="main-figure" src="{_image_data_uri(graph_path)}" '
            f'alt="{html.escape(graph_path.name)}">'
        )

    eln_html = "<p>No ELN entry available.</p>"
    if eln:
        eln_html = f"""
        <p><strong>{html.escape(str(eln.get("title", "")))}</strong></p>
        <p>{html.escape(str(eln.get("created_at", "")))}</p>
        <p>{html.escape(str(eln.get("result_summary", "")))}</p>
        """

    latest_table_html = (
        latest_values.to_html(index=False, border=0, classes="data-table")
        if not latest_values.empty
        else "<p>No latest result values available.</p>"
    )

    delta_table_html = (
        delta_values.to_html(index=False, border=0, classes="data-table")
        if not delta_values.empty
        else "<p>No ΔPeak table available.</p>"
    )

    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(experiment_name)} summary</title>
<style>
body {{
    font-family: Arial, Helvetica, sans-serif;
    margin: 36px;
    color: #1f2937;
    line-height: 1.5;
}}
h1, h2 {{ color: #0f3d5e; }}
.meta {{
    color: #64748b;
    margin-bottom: 24px;
}}
.cards {{
    display: grid;
    grid-template-columns: repeat(4, minmax(120px, 1fr));
    gap: 12px;
    margin: 16px 0 28px 0;
}}
.card {{
    border: 1px solid #dbe4ea;
    border-radius: 10px;
    padding: 14px;
    background: #f8fafc;
}}
.card strong {{
    display: block;
    font-size: 20px;
    margin-top: 4px;
}}
.main-figure {{
    max-width: 100%;
    border: 1px solid #dbe4ea;
    border-radius: 8px;
}}
.data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}}
.data-table th, .data-table td {{
    padding: 7px 9px;
    border-bottom: 1px solid #e5e7eb;
    text-align: right;
}}
.data-table th:first-child, .data-table td:first-child {{
    text-align: left;
}}
.section {{
    margin-top: 30px;
}}
.path {{
    font-family: Consolas, monospace;
    font-size: 12px;
    color: #475569;
    word-break: break-all;
}}
</style>
</head>
<body>
<h1>EC Research Studio — Experiment Summary</h1>
<div class="meta">
Experiment: <strong>{html.escape(experiment_name)}</strong><br>
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
</div>

<h2>Data status</h2>
{counts_df.to_html(index=False, border=0, classes="data-table")}

<div class="section">
<h2>Latest updated result</h2>
<p>Method: <strong>{html.escape(str(latest_method or ""))}</strong></p>
<p class="path">{html.escape(str(latest_result_path or ""))}</p>
{latest_table_html}
</div>

<div class="section">
<h2>Latest electrochemical graph</h2>
<p>Method: <strong>{html.escape(str(graph_method or ""))}</strong></p>
<p class="path">{html.escape(str(graph_path or ""))}</p>
{graph_html}
</div>

<div class="section">
<h2>Latest ΔPeak values</h2>
<p>Method: <strong>{html.escape(str(delta_method or ""))}</strong></p>
<p class="path">{html.escape(str(delta_path or ""))}</p>
{delta_table_html}
</div>

<div class="section">
<h2>Latest ELN note</h2>
{eln_html}
</div>
</body>
</html>
"""

    output.write_text(html_text, encoding="utf-8")
    return output
