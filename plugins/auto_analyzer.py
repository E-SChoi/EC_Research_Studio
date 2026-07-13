
from pathlib import Path
from datetime import datetime
import pandas as pd

from core.dpv import parse_concentration as parse_dpv_concentration, run_dpv_analysis
from core.swv import parse_concentration as parse_swv_concentration, run_swv_analysis
from core.eis import parse_concentration as parse_eis_concentration, run_eis_analysis
from core.cv import parse_scan_rate, run_cv_analysis


SUPPORTED_METHODS = ["DPV", "SWV", "EIS", "CV"]


def build_method_table(exp_path, method):
    exp_path = Path(exp_path)
    raw_dir = exp_path / "RawData" / method
    if not raw_dir.exists():
        return pd.DataFrame()

    extension_map = {
        "DPV": [".csv", ".mtd"],
        "SWV": [".csv", ".mts"],
        "EIS": [".csv", ".mteisp"],
        "CV": [".csv"],
    }
    allowed = extension_map.get(method, [".csv"])
    raw_files = sorted(
        p.name
        for p in raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in allowed
    )
    rows = []

    for fname in raw_files:
        if method == "DPV":
            label, conc_pm = parse_dpv_concentration(fname)
            rows.append({
                "File": fname,
                "Label": label,
                "Concentration_pM": 0.0 if conc_pm is None else conc_pm,
            })

        elif method == "SWV":
            label, conc_pm = parse_swv_concentration(fname)
            rows.append({
                "File": fname,
                "Label": label,
                "Concentration_pM": 0.0 if conc_pm is None else conc_pm,
            })

        elif method == "EIS":
            label, conc_pm = parse_eis_concentration(fname)
            rows.append({
                "File": fname,
                "Label": label,
                "Concentration_pM": 0.0 if conc_pm is None else conc_pm,
            })

        elif method == "CV":
            scan_rate = parse_scan_rate(fname)
            rows.append({
                "File": fname,
                "Label": Path(fname).stem,
                "ScanRate_mV_s": "" if scan_rate is None else scan_rate,
            })

    return pd.DataFrame(rows)


def available_methods(exp_path):
    exp_path = Path(exp_path)
    found = []
    for method in SUPPORTED_METHODS:
        table = build_method_table(exp_path, method)
        if not table.empty:
            found.append(method)
    return found


def run_selected_methods(
    exp_path,
    methods,
    use_abs_fit=True,
    dpv_baseline_mode="preceding_local_minimum",
    dpv_peak_search_min_v=0.30,
    dpv_peak_search_max_v=0.70,
    dpv_baseline_search_min_v=0.05,
    dpv_smoothing_window=11,
):
    exp_path = Path(exp_path)
    results = []
    errors = []

    for method in methods:
        table = build_method_table(exp_path, method)
        if table.empty:
            errors.append({
                "Method": method,
                "Status": "Skipped",
                "Message": "No supported raw-data files found",
            })
            continue

        try:
            if method == "DPV":
                output = run_dpv_analysis(
                    exp_path,
                    table,
                    use_abs_fit=use_abs_fit,
                    baseline_mode=dpv_baseline_mode,
                    peak_search_min_v=float(dpv_peak_search_min_v),
                    peak_search_max_v=float(dpv_peak_search_max_v),
                    baseline_search_min_v=float(dpv_baseline_search_min_v),
                    smoothing_window=int(dpv_smoothing_window),
                )

            elif method == "SWV":
                output = run_swv_analysis(
                    exp_path,
                    table,
                    use_abs_fit=use_abs_fit,
                )

            elif method == "EIS":
                output = run_eis_analysis(
                    exp_path,
                    table,
                    use_abs_fit=use_abs_fit,
                )

            elif method == "CV":
                output = run_cv_analysis(exp_path, table)

            else:
                raise ValueError(f"Unsupported method: {method}")

            results.append({
                "Method": method,
                "Status": "Completed",
                "Raw files": len(table),
                "Result directory": output.get("result_dir", ""),
                "Figure directory": output.get("figure_dir", ""),
                "Report directory": output.get("report_dir", ""),
                "Completed at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "output": output,
            })

        except Exception as exc:
            errors.append({
                "Method": method,
                "Status": "Failed",
                "Message": str(exc),
            })

    return results, errors


def summary_dataframe(results, errors):
    rows = []

    for item in results:
        rows.append({
            "Method": item["Method"],
            "Status": item["Status"],
            "Raw files": item["Raw files"],
            "Message": "",
            "Result directory": item["Result directory"],
            "Figure directory": item["Figure directory"],
        })

    for item in errors:
        rows.append({
            "Method": item["Method"],
            "Status": item["Status"],
            "Raw files": "",
            "Message": item["Message"],
            "Result directory": "",
            "Figure directory": "",
        })

    return pd.DataFrame(rows)


def save_auto_analysis_log(exp_path, summary_df):
    exp_path = Path(exp_path)
    report_dir = exp_path / "Reports" / "AutoAnalyzer"
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = report_dir / f"auto_analysis_{timestamp}.csv"
    txt_path = report_dir / f"auto_analysis_{timestamp}.txt"

    summary_df.to_csv(csv_path, index=False)
    txt_path.write_text(summary_df.to_string(index=False), encoding="utf-8")

    return csv_path, txt_path
