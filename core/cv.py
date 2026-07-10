
from pathlib import Path
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def parse_scan_rate(filename):
    name = str(filename).lower()
    for pat in [r"(\d+\.?\d*)\s*mv\s*/?\s*s", r"(\d+\.?\d*)\s*mvps", r"(\d+\.?\d*)\s*mv_s"]:
        m = re.search(pat, name)
        if m:
            return float(m.group(1))
    return None

def load_cv_file(path):
    path = Path(path)
    raw = pd.read_csv(path, header=None, dtype=str)
    potential, current = [], []

    for line in raw.iloc[:, 0]:
        if isinstance(line, str) and ";" in line:
            left, right = line.split(";", 1)
            try:
                potential.append(float(left.replace('"', "").strip()))
                current.append(float(right.replace('"', "").strip()))
            except ValueError:
                pass

    if potential:
        return np.array(potential), np.array(current)

    df = pd.read_csv(path)
    df = df.apply(pd.to_numeric, errors="coerce").dropna()
    if df.shape[1] < 2:
        raise ValueError(f"Potential / Current columns not found: {path}")
    return df.iloc[:, 0].to_numpy(), df.iloc[:, 1].to_numpy()

def split_forward_reverse(potential, current):
    potential = np.asarray(potential, dtype=float)
    current = np.asarray(current, dtype=float)

    if len(potential) < 5:
        return potential, current, potential, current

    dp = np.diff(potential)
    change_idx = np.where(np.sign(dp[:-1]) != np.sign(dp[1:]))[0]
    idx = int(change_idx[0] + 1) if len(change_idx) else int(np.argmax(potential))

    forward_p, forward_i = potential[:idx+1], current[:idx+1]
    reverse_p, reverse_i = potential[idx+1:], current[idx+1:]

    if len(reverse_p) < 3:
        reverse_p, reverse_i = potential, current

    return forward_p, forward_i, reverse_p, reverse_i

def analyze_cv_curve(potential, current):
    f_p, f_i, r_p, r_i = split_forward_reverse(potential, current)

    ox_idx = int(np.argmax(f_i))
    red_idx = int(np.argmin(r_i))

    epa, ipa = float(f_p[ox_idx]), float(f_i[ox_idx])
    epc, ipc = float(r_p[red_idx]), float(r_i[red_idx])

    return {
        "Epa_V": epa,
        "Ipa_uA": ipa,
        "Epc_V": epc,
        "Ipc_uA": ipc,
        "DeltaEp_V": abs(epa - epc),
        "E0_formal_V": (epa + epc) / 2,
        "PeakRatio_abs_Ipa_Ipc": abs(ipa / ipc) if ipc != 0 else np.nan,
    }

def fig_to_file(fig, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")

def run_cv_analysis(exp_path, sample_table):
    exp_path = Path(exp_path)
    raw_dir = exp_path / "RawData" / "CV"
    result_dir = exp_path / "Results" / "CV"
    figure_dir = exp_path / "Figures" / "CV"
    report_dir = exp_path / "Reports" / "CV"

    for d in [result_dir, figure_dir, report_dir]:
        d.mkdir(parents=True, exist_ok=True)

    sample_table = sample_table.copy().dropna(subset=["File", "Label"])

    datasets, rows, raw_cols = [], [], {}

    for _, row in sample_table.iterrows():
        file_name = str(row["File"])
        label = str(row["Label"])
        scan_rate = row.get("ScanRate_mV_s", None)

        if pd.isna(scan_rate) or scan_rate in ["", None]:
            scan_rate = parse_scan_rate(file_name)
        else:
            scan_rate = float(scan_rate)

        potential, current = load_cv_file(raw_dir / file_name)
        result = analyze_cv_curve(potential, current)

        datasets.append({
            "file": file_name,
            "label": label,
            "scan_rate": scan_rate,
            "potential": potential,
            "current": current,
            **result
        })

        rows.append({"File": file_name, "Label": label, "ScanRate_mV_s": scan_rate, **result})

        safe = label.replace(" ", "_")
        raw_cols[f"{safe}_Potential_V"] = pd.Series(potential)
        raw_cols[f"{safe}_Current_uA"] = pd.Series(current)

    result_df = pd.DataFrame(rows)
    result_df.to_csv(result_dir / "cv_peak_values.csv", index=False)
    pd.DataFrame(raw_cols).to_csv(result_dir / "cv_raw_overlay_data.csv", index=False)

    with pd.ExcelWriter(result_dir / "cv_analysis_results.xlsx", engine="openpyxl") as writer:
        result_df.to_excel(writer, sheet_name="CV_peak_values", index=False)
        pd.DataFrame(raw_cols).to_excel(writer, sheet_name="Raw_data", index=False)

    fig, ax = plt.subplots()
    for item in datasets:
        ax.plot(item["potential"], item["current"], label=item["label"])
    ax.set_xlabel("Potential (V)")
    ax.set_ylabel("Current (µA)")
    ax.set_title("CV raw overlay")
    ax.legend()
    fig_to_file(fig, figure_dir / "1_cv_overlay.png")
    plt.close(fig)

    fig, ax = plt.subplots()
    for item in datasets:
        ax.plot(item["potential"], item["current"], label=item["label"])
        ax.scatter(item["Epa_V"], item["Ipa_uA"], marker="^", s=70)
        ax.scatter(item["Epc_V"], item["Ipc_uA"], marker="v", s=70)
        ax.annotate("Ox", (item["Epa_V"], item["Ipa_uA"]), textcoords="offset points", xytext=(5, 5))
        ax.annotate("Red", (item["Epc_V"], item["Ipc_uA"]), textcoords="offset points", xytext=(5, -12))
    ax.set_xlabel("Potential (V)")
    ax.set_ylabel("Current (µA)")
    ax.set_title("CV peak-marked overlay")
    ax.legend()
    fig_to_file(fig, figure_dir / "2_cv_peak_marked.png")
    plt.close(fig)

    scan_df = result_df.dropna(subset=["ScanRate_mV_s"]).copy()
    scan_summary = pd.DataFrame()

    if len(scan_df) >= 2:
        scan_df["sqrt_scan_rate"] = np.sqrt(scan_df["ScanRate_mV_s"].astype(float))
        x = scan_df["sqrt_scan_rate"].to_numpy(dtype=float)
        y_ox = np.abs(scan_df["Ipa_uA"].to_numpy(dtype=float))
        y_red = np.abs(scan_df["Ipc_uA"].to_numpy(dtype=float))
        fit_rows = []

        fig, ax = plt.subplots()
        for y, name in [(y_ox, "Ipa"), (y_red, "Ipc")]:
            ax.scatter(x, y, label=f"|{name}|")
            a, b = np.polyfit(x, y, 1)
            yhat = a * x + b
            r2 = 1 - np.sum((y - yhat)**2) / np.sum((y - np.mean(y))**2)
            xline = np.linspace(x.min(), x.max(), 200)
            ax.plot(xline, a*xline+b, "--", label=f"|{name}| fit R²={r2:.4f}")
            fit_rows.append({"Peak": name, "Slope": a, "Intercept": b, "R2": r2})

        ax.set_xlabel("sqrt(scan rate) (sqrt(mV/s))")
        ax.set_ylabel("|Peak current| (µA)")
        ax.set_title("CV scan-rate analysis")
        ax.legend()
        fig_to_file(fig, figure_dir / "3_scan_rate_analysis.png")
        plt.close(fig)

        scan_summary = pd.DataFrame(fit_rows)
        scan_summary.to_csv(result_dir / "cv_scan_rate_summary.csv", index=False)

    report = "CV Analysis Report\n\nPeak values:\n"
    report += result_df.to_string(index=False)
    if not scan_summary.empty:
        report += "\n\nScan-rate summary:\n"
        report += scan_summary.to_string(index=False)
    (report_dir / "analysis_summary.txt").write_text(report, encoding="utf-8")

    return {
        "cv_df": result_df,
        "scan_summary_df": scan_summary,
        "result_dir": str(result_dir),
        "figure_dir": str(figure_dir),
        "report_dir": str(report_dir),
    }
