
from pathlib import Path
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats

def detect_concentration_from_text(text):
    text = str(text).lower()
    if "zero" in text or "blank" in text or "control" in text:
        return 0.0, "zero"
    match = re.search(r"(\d+\.?\d*)\s*(pm|nm|um|µm|mm|m)", text)
    if not match:
        return None, None
    value = float(match.group(1))
    unit = match.group(2)
    factors = {"pm": 1.0, "nm": 1e3, "um": 1e6, "µm": 1e6, "mm": 1e9, "m": 1e12}
    return value * factors[unit], f"{value:g} {unit}"

def detect_replicate_from_text(text):
    text = str(text).lower()
    for pat in [r"rep[\s_-]*(\d+)", r"repeat[\s_-]*(\d+)", r"r[\s_-]*(\d+)", r"[_-](\d+)(?=\.csv$|\.xlsx$|\.txt$|$)"]:
        m = re.search(pat, text)
        if m:
            return int(m.group(1))
    return 1

def load_signal_table(file_path):
    path = Path(file_path)
    if path.suffix.lower() in [".xlsx", ".xls"]:
        return pd.read_excel(path)
    return pd.read_csv(path)

def prepare_statistics_input(file_path, signal_column=None):
    df = load_signal_table(file_path)

    if signal_column is None:
        for col in [
            "DeltaDeltaPeak_vs_zero_uA",
            "Abs_DeltaDeltaPeak_vs_zero_uA",
            "DeltaPeak_max_minus_min_uA",
            "DeltaRct_vs_zero_ohm",
            "Abs_DeltaRct_vs_zero_ohm",
            "Rct_ohm",
            "Signal",
            "signal",
            "Value",
            "value",
        ]:
            if col in df.columns:
                signal_column = col
                break

    if signal_column is None or signal_column not in df.columns:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        numeric_cols = [c for c in numeric_cols if c not in {"Concentration_pM", "Concentration_M"}]
        if not numeric_cols:
            raise ValueError("No numeric signal column was found.")
        signal_column = numeric_cols[-1]

    if "Concentration_pM" not in df.columns:
        source_col = "File" if "File" in df.columns else ("Label" if "Label" in df.columns else df.columns[0])
        concs, labels = [], []
        for text in df[source_col]:
            conc_pm, label = detect_concentration_from_text(text)
            concs.append(conc_pm)
            labels.append(label)
        df["Concentration_pM"] = concs
        df["Concentration_label"] = labels
    else:
        df["Concentration_pM"] = pd.to_numeric(df["Concentration_pM"], errors="coerce")
        df["Concentration_label"] = df["Concentration_pM"].apply(lambda x: "zero" if x == 0 else f"{x:g} pM")

    if "Replicate" not in df.columns:
        source_col = "File" if "File" in df.columns else ("Label" if "Label" in df.columns else df.columns[0])
        df["Replicate"] = [detect_replicate_from_text(x) for x in df[source_col]]

    df["Signal"] = pd.to_numeric(df[signal_column], errors="coerce")
    df = df.dropna(subset=["Concentration_pM", "Signal"])
    return df.sort_values(["Concentration_pM", "Replicate"]), signal_column

def summarize_replicates(df):
    rows = []
    for conc, g in df.groupby("Concentration_pM"):
        values = g["Signal"].dropna().to_numpy(dtype=float)
        n = len(values)
        mean = float(np.mean(values)) if n else np.nan
        sd = float(np.std(values, ddof=1)) if n > 1 else 0.0
        sem = float(sd / np.sqrt(n)) if n > 1 else 0.0
        rsd = float((sd / mean) * 100) if mean != 0 and n > 1 else np.nan
        ci95 = float(stats.t.ppf(0.975, n - 1) * sem) if n > 1 else 0.0
        rows.append({
            "Concentration_pM": conc,
            "Concentration_M": conc * 1e-12,
            "n": n,
            "Mean": mean,
            "SD": sd,
            "SEM": sem,
            "RSD_percent": rsd,
            "CI95": ci95,
        })
    return pd.DataFrame(rows).sort_values("Concentration_pM")

def calculate_lod_loq(summary_df, error_source="SD"):
    blank = summary_df[summary_df["Concentration_pM"] == 0]
    if len(blank):
        sigma = float(blank[error_source].iloc[0])
        sigma_source = "blank"
    else:
        sigma = float(summary_df[error_source].iloc[0])
        sigma_source = "first concentration"

    fit_df = summary_df[summary_df["Concentration_pM"] > 0].dropna(subset=["Mean"])
    if len(fit_df) < 2:
        return {"slope_per_pM": np.nan, "intercept": np.nan, "r2": np.nan, "sigma": sigma, "sigma_source": sigma_source, "LOD_pM": np.nan, "LOQ_pM": np.nan}

    x = fit_df["Concentration_pM"].to_numpy(dtype=float)
    y = fit_df["Mean"].to_numpy(dtype=float)
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
    lod = abs(3.3 * sigma / slope) if slope != 0 else np.nan
    loq = abs(10.0 * sigma / slope) if slope != 0 else np.nan

    return {
        "slope_per_pM": float(slope),
        "intercept": float(intercept),
        "r2": float(r_value ** 2),
        "p_value": float(p_value),
        "std_err": float(std_err),
        "sigma": sigma,
        "sigma_source": sigma_source,
        "LOD_pM": float(lod) if not np.isnan(lod) else np.nan,
        "LOQ_pM": float(loq) if not np.isnan(loq) else np.nan,
    }

def save_statistics_outputs(exp_path, method, replicate_df, summary_df, lod_info, error_bar="SD"):
    exp_path = Path(exp_path)
    method = method.upper()
    result_dir = exp_path / "Results" / method / "Statistics"
    figure_dir = exp_path / "Figures" / method / "Statistics"
    report_dir = exp_path / "Reports" / method / "Statistics"
    for d in [result_dir, figure_dir, report_dir]:
        d.mkdir(parents=True, exist_ok=True)

    replicate_df.to_csv(result_dir / "replicate_values.csv", index=False)
    summary_df.to_csv(result_dir / "statistics_summary.csv", index=False)
    pd.DataFrame([lod_info]).to_csv(result_dir / "lod_loq.csv", index=False)

    with pd.ExcelWriter(result_dir / "statistics_results.xlsx", engine="openpyxl") as writer:
        replicate_df.to_excel(writer, sheet_name="Replicate_values", index=False)
        summary_df.to_excel(writer, sheet_name="Statistics_summary", index=False)
        pd.DataFrame([lod_info]).to_excel(writer, sheet_name="LOD_LOQ", index=False)

    yerr = summary_df[error_bar].to_numpy(dtype=float) if error_bar in summary_df.columns else summary_df["SD"].to_numpy(dtype=float)

    fig, ax = plt.subplots()
    ax.scatter(replicate_df["Concentration_pM"], replicate_df["Signal"], alpha=0.65, label="Replicates")
    ax.errorbar(summary_df["Concentration_pM"], summary_df["Mean"], yerr=yerr, fmt="o", capsize=4, label=f"Mean ± {error_bar}")
    ax.set_xlabel("Concentration (pM)")
    ax.set_ylabel("Signal")
    ax.set_title(f"{method} replicate statistics")
    ax.legend()
    fig.savefig(figure_dir / "1_replicate_errorbar.png", dpi=300, bbox_inches="tight")
    fig.savefig(figure_dir / "1_replicate_errorbar.svg", bbox_inches="tight")
    plt.close(fig)

    fit_df = summary_df[summary_df["Concentration_pM"] > 0].dropna(subset=["Mean"])
    fig, ax = plt.subplots()
    ax.errorbar(summary_df["Concentration_pM"], summary_df["Mean"], yerr=yerr, fmt="o", capsize=4, label=f"Mean ± {error_bar}")
    if len(fit_df) >= 2 and not np.isnan(lod_info.get("slope_per_pM", np.nan)):
        xline = np.linspace(fit_df["Concentration_pM"].min(), fit_df["Concentration_pM"].max(), 200)
        yline = lod_info["slope_per_pM"] * xline + lod_info["intercept"]
        ax.plot(xline, yline, "--", label="Linear fit")
        ax.text(0.05, 0.95, f"R² = {lod_info['r2']:.4f}\nLOD = {lod_info['LOD_pM']:.3g} pM\nLOQ = {lod_info['LOQ_pM']:.3g} pM", transform=ax.transAxes, va="top")
    ax.set_xlabel("Concentration (pM)")
    ax.set_ylabel("Mean signal")
    ax.set_title(f"{method} calibration with error bars")
    ax.legend()
    fig.savefig(figure_dir / "2_calibration_lod_loq.png", dpi=300, bbox_inches="tight")
    fig.savefig(figure_dir / "2_calibration_lod_loq.svg", bbox_inches="tight")
    plt.close(fig)

    report = f"{method} Statistics Report\n\nStatistics summary:\n"
    report += summary_df.to_string(index=False)
    report += "\n\nLOD / LOQ:\n"
    report += pd.DataFrame([lod_info]).to_string(index=False)
    (report_dir / "statistics_report.txt").write_text(report, encoding="utf-8")

    return {"replicate_df": replicate_df, "summary_df": summary_df, "lod_info": lod_info, "result_dir": str(result_dir), "figure_dir": str(figure_dir), "report_dir": str(report_dir)}

def run_statistics_analysis(exp_path, method, input_file, signal_column=None, error_bar="SD", lod_error_source="SD"):
    replicate_df, detected_signal_column = prepare_statistics_input(input_file, signal_column=signal_column)
    summary_df = summarize_replicates(replicate_df)
    lod_info = calculate_lod_loq(summary_df, error_source=lod_error_source)
    lod_info["Detected_signal_column"] = detected_signal_column
    return save_statistics_outputs(exp_path, method, replicate_df, summary_df, lod_info, error_bar=error_bar)
