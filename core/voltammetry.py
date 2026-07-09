from pathlib import Path
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

def parse_concentration(filename):
    name = filename.lower()
    if "zero" in name or "blank" in name:
        return "zero", 0.0
    match = re.search(r"(\d+\.?\d*)\s*(pm|nm|um|µm|mm|m)", name)
    if match is None:
        return filename, None
    value = float(match.group(1))
    unit = match.group(2)
    factors = {"pm": 1, "nm": 1e3, "um": 1e6, "µm": 1e6, "mm": 1e9, "m": 1e12}
    return f"{value:g} {unit}", value * factors[unit]

def load_voltammetry_file(path):
    path = Path(path)
    raw = pd.read_csv(path, header=None, dtype=str)
    potential, current = [], []
    for line in raw.iloc[:, 0]:
        if not isinstance(line, str) or ";" not in line:
            continue
        left, right = line.split(";", 1)
        left = left.replace('"', "").strip()
        right = right.replace('"', "").strip()
        try:
            potential.append(float(left))
            current.append(float(right))
        except ValueError:
            continue
    if len(potential) > 0:
        return np.array(potential), np.array(current)
    df = pd.read_csv(path)
    df = df.apply(pd.to_numeric, errors="coerce").dropna()
    if df.shape[1] < 2:
        raise ValueError(f"Potential / Current columns not found: {path}")
    return df.iloc[:, 0].to_numpy(), df.iloc[:, 1].to_numpy()

def r2_score(y, yhat):
    ss_res = np.sum((y - yhat) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    return 1 - ss_res / ss_tot if ss_tot != 0 else np.nan

def langmuir(C, y0, A, Kd):
    return y0 + A * C / (Kd + C)

def hill(C, y0, A, Kd, n):
    return y0 + A * (C**n / (Kd**n + C**n))

def fig_to_file(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")

def run_voltammetry_analysis(exp_path, sample_table, method="DPV", use_abs_fit=True):
    exp_path = Path(exp_path)
    method = method.upper()
    raw_dir = exp_path / "RawData" / method
    result_dir = exp_path / "Results" / method
    figure_dir = exp_path / "Figures" / method
    report_dir = exp_path / "Reports" / method
    for d in [result_dir, figure_dir, report_dir]:
        d.mkdir(parents=True, exist_ok=True)

    sample_table = sample_table.copy()
    sample_table["Concentration_pM"] = pd.to_numeric(sample_table["Concentration_pM"], errors="coerce")
    sample_table = sample_table.dropna(subset=["File", "Label", "Concentration_pM"])
    sample_table = sample_table.sort_values("Concentration_pM")

    data = {}
    for _, row in sample_table.iterrows():
        potential, current = load_voltammetry_file(raw_dir / str(row["File"]))
        data[str(row["File"])] = {
            "file": str(row["File"]),
            "label": str(row["Label"]),
            "conc_pM": float(row["Concentration_pM"]),
            "conc_M": float(row["Concentration_pM"]) * 1e-12,
            "potential": potential,
            "current": current,
        }

    fig, ax = plt.subplots()
    for item in data.values():
        ax.plot(item["potential"], item["current"], label=item["label"])
    ax.set_xlabel("Potential (V)")
    ax.set_ylabel("Current (µA)")
    ax.set_title(f"{method} raw overlay")
    ax.legend()
    fig_to_file(fig, figure_dir / "1_raw_overlay.png")
    plt.close(fig)

    baseline_cols, baseline_info = {}, []
    fig, ax = plt.subplots()
    for item in data.values():
        potential, current = item["potential"], item["current"]
        mask = potential <= 0
        if not mask.any():
            raise ValueError(f"{item['label']}: No potential region <= 0 V.")
        baseline = np.min(current[mask])
        shifted = current - baseline
        ax.plot(potential, shifted, label=item["label"])
        safe = item["label"].replace(" ", "_")
        baseline_cols[f"{safe}_Potential_V"] = pd.Series(potential)
        baseline_cols[f"{safe}_Current_raw_uA"] = pd.Series(current)
        baseline_cols[f"{safe}_Current_shift_uA"] = pd.Series(shifted)
        baseline_info.append({
            "File": item["file"], "Label": item["label"],
            "Concentration_pM": item["conc_pM"], "Concentration_M": item["conc_M"],
            "Baseline_min_current_at_V<=0_uA": baseline
        })
    ax.set_xlabel("Potential (V)")
    ax.set_ylabel("Current (µA, baseline-shifted)")
    ax.set_title(f"{method} baseline-shift overlay")
    ax.legend()
    fig_to_file(fig, figure_dir / "2_baseline_shift_overlay.png")
    plt.close(fig)

    baseline_df = pd.DataFrame(baseline_cols)
    baseline_info_df = pd.DataFrame(baseline_info)
    with pd.ExcelWriter(result_dir / "raw_and_baseline_data.xlsx", engine="openpyxl") as writer:
        baseline_df.to_excel(writer, sheet_name="Raw_and_shifted", index=False)
        baseline_info_df.to_excel(writer, sheet_name="Baseline_info", index=False)
    baseline_df.to_csv(result_dir / "raw_and_baseline_data.csv", index=False)
    baseline_info_df.to_csv(result_dir / "baseline_info.csv", index=False)

    peak_rows = []
    for item in data.values():
        delta_peak = float(np.max(item["current"]) - np.min(item["current"]))
        peak_rows.append({
            "File": item["file"], "Label": item["label"],
            "Concentration_pM": item["conc_pM"], "Concentration_M": item["conc_M"],
            "DeltaPeak_max_minus_min_uA": delta_peak
        })
    peak_df = pd.DataFrame(peak_rows).sort_values("Concentration_pM")
    if (peak_df["Concentration_pM"] == 0).sum() == 0:
        raise RuntimeError("A zero sample with Concentration_pM = 0 is required.")
    zero_delta = peak_df.loc[peak_df["Concentration_pM"] == 0, "DeltaPeak_max_minus_min_uA"].iloc[0]
    peak_df["DeltaDeltaPeak_vs_zero_uA"] = peak_df["DeltaPeak_max_minus_min_uA"] - zero_delta
    peak_df["Abs_DeltaDeltaPeak_vs_zero_uA"] = np.abs(peak_df["DeltaDeltaPeak_vs_zero_uA"])
    peak_df.to_csv(result_dir / "peak_values.csv", index=False)
    with pd.ExcelWriter(result_dir / "peak_values.xlsx", engine="openpyxl") as writer:
        peak_df.to_excel(writer, sheet_name="Peak_values", index=False)

    fig, ax = plt.subplots()
    ax.scatter(peak_df["Concentration_pM"], peak_df["DeltaDeltaPeak_vs_zero_uA"])
    ax.axhline(0, linewidth=0.5)
    ax.set_xlabel("Concentration (pM)")
    ax.set_ylabel("ΔΔPeak (µA)")
    ax.set_title(f"{method} ΔΔPeak vs concentration")
    fig_to_file(fig, figure_dir / "3_delta_delta_peak_scatter.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(peak_df["Label"], peak_df["DeltaPeak_max_minus_min_uA"])
    ax.set_xlabel("Concentration")
    ax.set_ylabel("ΔPeak = max − min (µA)")
    ax.set_title(f"{method} ΔPeak by concentration")
    fig.tight_layout()
    fig_to_file(fig, figure_dir / "4_delta_peak_bar.png")
    plt.close(fig)

    fit_summary = []
    fit_df = peak_df[peak_df["Concentration_M"] > 0].copy()
    if len(fit_df) >= 2:
        x = fit_df["Concentration_M"].to_numpy()
        y_raw = fit_df["DeltaDeltaPeak_vs_zero_uA"].to_numpy()
        y = np.abs(y_raw) if use_abs_fit else y_raw
        lnx = np.log(x)
        a, b = np.polyfit(lnx, y, 1)
        r2_log = r2_score(y, a * lnx + b)
        x_line = np.logspace(np.log10(x.min()), np.log10(x.max()), 300)

        fig, ax = plt.subplots()
        ax.scatter(x, y, label="data")
        ax.plot(x_line, a * np.log(x_line) + b, "--", label="log fit")
        ax.set_xlabel("Concentration (M)")
        ax.set_ylabel("|ΔΔPeak| (µA)" if use_abs_fit else "ΔΔPeak (µA)")
        ax.set_title(f"{method} log trendline")
        ax.text(0.55, 0.25, f"y = {a:.4f} ln(x) + {b:.4f}\\nR² = {r2_log:.4f}", transform=ax.transAxes)
        ax.legend()
        fig_to_file(fig, figure_dir / "5_log_fit.png")
        plt.close(fig)
        fit_summary.append({"Model": "LogTrend(ln)", "a": a, "b": b, "R2": r2_log})

        if len(fit_df) >= 3:
            try:
                y0_0, A_0, Kd_0 = float(np.min(y)), float(np.max(y) - np.min(y)), float(np.median(x))
                popt_L, _ = curve_fit(langmuir, x, y, p0=[y0_0, A_0, Kd_0], bounds=([-np.inf, 0, 0], [np.inf, np.inf, np.inf]), maxfev=30000)
                r2_L = r2_score(y, langmuir(x, *popt_L))
                popt_H, _ = curve_fit(hill, x, y, p0=[y0_0, A_0, Kd_0, 1.0], bounds=([-np.inf, 0, 0, 0], [np.inf, np.inf, np.inf, 10]), maxfev=60000)
                r2_H = r2_score(y, hill(x, *popt_H))
                fig, ax = plt.subplots()
                ax.scatter(x, y, label="data")
                ax.plot(x_line, langmuir(x_line, *popt_L), "--", label="Langmuir")
                ax.plot(x_line, hill(x_line, *popt_H), "--", label="Hill")
                ax.set_xlabel("Concentration (M)")
                ax.set_ylabel("|ΔΔPeak| (µA)" if use_abs_fit else "ΔΔPeak (µA)")
                ax.set_title(f"{method} Langmuir / Hill fitting")
                ax.legend()
                fig_to_file(fig, figure_dir / "6_langmuir_hill_fit.png")
                plt.close(fig)
                fit_summary.append({"Model": "Langmuir", "y0": popt_L[0], "A": popt_L[1], "Kd_M": popt_L[2], "Kd_pM": popt_L[2]/1e-12, "R2": r2_L})
                fit_summary.append({"Model": "Hill", "y0": popt_H[0], "A": popt_H[1], "Kd_M": popt_H[2], "Kd_pM": popt_H[2]/1e-12, "n": popt_H[3], "R2": r2_H})
            except Exception as e:
                fit_summary.append({"Model": "Langmuir/Hill failed", "Error": str(e)})

    fit_summary_df = pd.DataFrame(fit_summary)
    fit_summary_df.to_csv(result_dir / "fit_summary.csv", index=False)
    with pd.ExcelWriter(result_dir / "fit_summary.xlsx", engine="openpyxl") as writer:
        fit_summary_df.to_excel(writer, sheet_name="Fit_summary", index=False)
    report = f"{method} Analysis Report\\n\\nPeak values:\\n{peak_df.to_string(index=False)}\\n\\nFit summary:\\n{fit_summary_df.to_string(index=False)}"
    (report_dir / "analysis_summary.txt").write_text(report, encoding="utf-8")
    return {"peak_df": peak_df, "fit_summary_df": fit_summary_df, "result_dir": str(result_dir), "figure_dir": str(figure_dir), "report_dir": str(report_dir)}
