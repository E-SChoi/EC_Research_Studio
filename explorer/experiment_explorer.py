
from pathlib import Path
from datetime import datetime
import base64
import html
import pandas as pd
import numpy as np


METHODS = ["DPV", "SWV", "EIS", "CV"]


def _latest_file(paths):
    files = [Path(p) for p in paths if Path(p).exists() and Path(p).is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def _read_table(path):
    if path is None:
        return None
    try:
        return pd.read_excel(path) if path.suffix.lower() == ".xlsx" else pd.read_csv(path)
    except Exception:
        return None


def list_experiments(project_path):
    root = Path(project_path) / "Experiments"
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()])


def find_result_table(exp_path, method):
    exp_path = Path(exp_path)
    root = exp_path / "Results" / method
    if not root.exists():
        return None, None

    preferred = {
        "DPV": ["peak_values.csv", "peak_values.xlsx", "baseline_info.csv"],
        "SWV": ["peak_values.csv", "peak_values.xlsx", "baseline_info.csv"],
        "EIS": ["rct_values.csv", "rct_values.xlsx", "eis_fit_summary.csv", "fit_summary.csv"],
        "CV": ["cv_peak_values.csv", "cv_results.csv", "analysis_results.xlsx"],
    }

    candidates = []
    for name in preferred.get(method, []):
        candidates.extend(root.rglob(name))

    selected = _latest_file(candidates)
    if selected is None:
        selected = _latest_file(
            [p for p in root.rglob("*") if p.suffix.lower() in [".csv", ".xlsx"]]
        )

    return selected, _read_table(selected)


def find_latest_figure(exp_path, method):
    root = Path(exp_path) / "Figures" / method
    if not root.exists():
        return None

    preferred = {
        "DPV": ["2_baseline_shift_overlay.png", "1_raw_overlay.png", "3_delta_delta_peak_scatter.png"],
        "SWV": ["2_baseline_shift_overlay.png", "1_raw_overlay.png", "3_delta_delta_peak_scatter.png"],
        "EIS": ["1_nyquist_overlay.png", "1_eis_overlay.png", "1a_eis_scatter.png"],
        "CV": ["2_cv_peak_marked.png", "1_cv_overlay.png"],
    }

    for name in preferred.get(method, []):
        selected = _latest_file(root.rglob(name))
        if selected is not None:
            return selected

    return _latest_file(root.rglob("*.png"))


def _numeric_series(df, names):
    if df is None or df.empty:
        return None, None
    for name in names:
        if name in df.columns:
            series = pd.to_numeric(df[name], errors="coerce")
            if series.notna().any():
                return name, series
    return None, None


def summarize_experiment(exp_path, experiment_name, method):
    result_path, df = find_result_table(exp_path, method)
    figure_path = find_latest_figure(exp_path, method)

    summary = {
        "Experiment": experiment_name,
        "Method": method,
        "Result file": str(result_path) if result_path else "",
        "Figure file": str(figure_path) if figure_path else "",
        "Rows": int(len(df)) if df is not None else 0,
    }

    if method in ["DPV", "SWV"]:
        delta_col, delta = _numeric_series(df, [
            "DeltaPeak_peak_minus_preceding_min_uA",
            "DeltaPeak_max_minus_min_uA",
        ])
        dd_col, dd = _numeric_series(df, [
            "DeltaDeltaPeak_vs_zero_uA",
            "Abs_DeltaDeltaPeak_vs_zero_uA",
        ])
        peak_col, peak = _numeric_series(df, ["Peak_potential_V"])
        base_col, baseline = _numeric_series(df, ["Baseline_potential_V"])
        r2_col, r2 = _numeric_series(df, ["R2"])

        summary.update({
            "Mean ΔPeak (µA)": float(delta.mean()) if delta is not None else np.nan,
            "Max ΔPeak (µA)": float(delta.max()) if delta is not None else np.nan,
            "Max |ΔΔPeak| (µA)": float(dd.abs().max()) if dd is not None else np.nan,
            "Mean peak potential (V)": float(peak.mean()) if peak is not None else np.nan,
            "Mean baseline potential (V)": float(baseline.mean()) if baseline is not None else np.nan,
            "Best R²": float(r2.max()) if r2 is not None else np.nan,
        })

    elif method == "EIS":
        rct_col, rct = _numeric_series(df, ["Rct_ohm", "Rct", "Rct_Ohm"])
        drct_col, drct = _numeric_series(df, [
            "DeltaRct_vs_zero_ohm",
            "Delta_Rct_ohm",
            "DeltaRct_ohm",
        ])
        r2_col, r2 = _numeric_series(df, ["R2", "R_squared"])

        summary.update({
            "Mean Rct (Ω)": float(rct.mean()) if rct is not None else np.nan,
            "Max Rct (Ω)": float(rct.max()) if rct is not None else np.nan,
            "Max ΔRct (Ω)": float(drct.max()) if drct is not None else np.nan,
            "Best R²": float(r2.max()) if r2 is not None else np.nan,
        })

    elif method == "CV":
        dep_col, dep = _numeric_series(df, ["DeltaEp_V"])
        ratio_col, ratio = _numeric_series(df, ["PeakRatio_abs_Ipa_Ipc"])
        summary.update({
            "Mean ΔEp (V)": float(dep.mean()) if dep is not None else np.nan,
            "Mean |Ipa/Ipc|": float(ratio.mean()) if ratio is not None else np.nan,
        })

    return summary, df, figure_path


def compare_experiments(project_path, experiment_names, method):
    rows = []
    details = {}

    for name in experiment_names:
        exp_path = Path(project_path) / "Experiments" / name
        summary, df, figure = summarize_experiment(exp_path, name, method)
        rows.append(summary)
        details[name] = {
            "table": df,
            "figure": figure,
            "summary": summary,
        }

    return pd.DataFrame(rows), details


def build_comparison_series(details, method):
    """
    Return a tidy concentration/value table for charting across Experiments.
    """
    rows = []

    for experiment, item in details.items():
        df = item.get("table")
        if df is None or df.empty:
            continue

        conc_col = next(
            (c for c in ["Concentration_pM", "Concentration"] if c in df.columns),
            None,
        )
        if conc_col is None:
            continue

        if method in ["DPV", "SWV"]:
            value_col = next(
                (
                    c for c in [
                        "DeltaPeak_peak_minus_preceding_min_uA",
                        "DeltaPeak_max_minus_min_uA",
                        "DeltaDeltaPeak_vs_zero_uA",
                    ]
                    if c in df.columns
                ),
                None,
            )
        elif method == "EIS":
            value_col = next(
                (
                    c for c in [
                        "Rct_ohm",
                        "DeltaRct_vs_zero_ohm",
                        "Delta_Rct_ohm",
                    ]
                    if c in df.columns
                ),
                None,
            )
        else:
            value_col = next(
                (c for c in ["DeltaEp_V", "PeakRatio_abs_Ipa_Ipc"] if c in df.columns),
                None,
            )

        if value_col is None:
            continue

        work = pd.DataFrame({
            "Experiment": experiment,
            "Concentration_pM": pd.to_numeric(df[conc_col], errors="coerce"),
            "Value": pd.to_numeric(df[value_col], errors="coerce"),
            "Metric": value_col,
        }).dropna(subset=["Concentration_pM", "Value"])

        rows.extend(work.to_dict("records"))

    return pd.DataFrame(rows)


def calculated_comparison_text(summary_df, method):
    if summary_df is None or len(summary_df) < 2:
        return "두 개 이상의 Experiment가 필요합니다."

    lines = []
    clean = summary_df.copy()

    if method in ["DPV", "SWV"] and "Max ΔPeak (µA)" in clean.columns:
        values = clean.dropna(subset=["Max ΔPeak (µA)"])
        if len(values) >= 2:
            best = values.loc[values["Max ΔPeak (µA)"].idxmax()]
            worst = values.loc[values["Max ΔPeak (µA)"].idxmin()]
            if worst["Max ΔPeak (µA)"] != 0:
                pct = (
                    (best["Max ΔPeak (µA)"] - worst["Max ΔPeak (µA)"])
                    / abs(worst["Max ΔPeak (µA)"])
                    * 100
                )
                lines.append(
                    f"{best['Experiment']}의 최대 ΔPeak가 "
                    f"{worst['Experiment']}보다 {pct:.1f}% 높습니다."
                )

    if method == "EIS" and "Max ΔRct (Ω)" in clean.columns:
        values = clean.dropna(subset=["Max ΔRct (Ω)"])
        if len(values) >= 2:
            best = values.loc[values["Max ΔRct (Ω)"].idxmax()]
            worst = values.loc[values["Max ΔRct (Ω)"].idxmin()]
            lines.append(
                f"가장 큰 ΔRct는 {best['Experiment']}에서 "
                f"{best['Max ΔRct (Ω)']:.4g} Ω로 나타났습니다."
            )

    if "Best R²" in clean.columns:
        values = clean.dropna(subset=["Best R²"])
        if len(values):
            best = values.loc[values["Best R²"].idxmax()]
            lines.append(
                f"가장 높은 R²는 {best['Experiment']}의 "
                f"{best['Best R²']:.4f}입니다."
            )

    if not lines:
        lines.append("비교 가능한 공통 정량 항목이 제한적입니다.")

    return "\n\n".join(lines)


def _image_uri(path):
    if path is None or not Path(path).exists():
        return ""
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def create_comparison_html(project_path, experiment_names, method, summary_df, details, comparison_text):
    report_dir = Path(project_path) / "Reports" / "ExperimentExplorer"
    report_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = report_dir / f"{method}_comparison_{stamp}.html"

    figure_blocks = []
    for name in experiment_names:
        figure = details.get(name, {}).get("figure")
        if figure is None:
            continue
        figure_blocks.append(
            f"""
            <div class="figure-card">
              <h3>{html.escape(name)}</h3>
              <img src="{_image_uri(figure)}" alt="{html.escape(Path(figure).name)}">
              <p>{html.escape(str(figure))}</p>
            </div>
            """
        )

    body = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Experiment Explorer</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 34px; color: #1f2937; }}
h1, h2 {{ color: #0f3d5e; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border-bottom: 1px solid #ddd; padding: 8px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
.figure-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; }}
.figure-card {{ border: 1px solid #ddd; border-radius: 8px; padding: 12px; }}
.figure-card img {{ max-width: 100%; }}
.figure-card p {{ word-break: break-all; font-size: 11px; color: #64748b; }}
.summary {{ white-space: pre-wrap; background: #f8fafc; padding: 16px; border-radius: 8px; }}
</style>
</head>
<body>
<h1>EC Research Studio — Experiment Explorer</h1>
<p>Method: <strong>{html.escape(method)}</strong></p>
<p>Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
<h2>Key result comparison</h2>
{summary_df.to_html(index=False, border=0)}
<h2>Calculated comparison</h2>
<div class="summary">{html.escape(comparison_text)}</div>
<h2>Latest figures</h2>
<div class="figure-grid">{''.join(figure_blocks)}</div>
</body>
</html>
"""
    output.write_text(body, encoding="utf-8")
    return output
