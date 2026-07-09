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
    value = float(match.group(1)); unit = match.group(2)
    factors = {"pm":1, "nm":1e3, "um":1e6, "µm":1e6, "mm":1e9, "m":1e12}
    return f"{value:g} {unit}", value * factors[unit]

def fig_to_file(fig, path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")

def load_eis_file(path):
    path = Path(path)
    try:
        df = pd.read_csv(path)
    except Exception:
        df = pd.read_csv(path, header=None)
    if df.shape[1] == 1:
        raw = pd.read_csv(path, header=None, dtype=str)
        rows = []
        for line in raw.iloc[:, 0]:
            if not isinstance(line, str) or ";" not in line:
                continue
            nums = []
            for p in [x.replace('"', "").strip() for x in line.split(";")]:
                try: nums.append(float(p))
                except ValueError: pass
            if len(nums) >= 3: rows.append(nums[:3])
        if rows:
            arr = np.array(rows, dtype=float)
            return arr[:,0], arr[:,1], arr[:,2]
    df_num = df.apply(pd.to_numeric, errors="coerce").dropna(how="all")
    if df_num.shape[1] < 3 or df_num.dropna().shape[0] < 5:
        df = pd.read_csv(path, skiprows=2)
        df_num = df.apply(pd.to_numeric, errors="coerce").dropna(how="all")
    if df_num.shape[1] < 3:
        raise ValueError(f"EIS file needs at least 3 numeric columns: {path}")
    df3 = df_num.iloc[:, :3].copy()
    df3.columns = ["Z", "Zi", "Freq"]
    df3 = df3.apply(pd.to_numeric, errors="coerce").dropna()
    return df3["Z"].to_numpy(), df3["Zi"].to_numpy(), df3["Freq"].to_numpy()

def fit_circle_algebraic(x, y):
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float)
    x_m, y_m = np.mean(x), np.mean(y)
    u, v = x-x_m, y-y_m
    A = np.column_stack([u, v, np.ones_like(u)])
    B = u**2 + v**2
    C, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
    uc, vc = C[0]/2, C[1]/2
    R2 = C[2] + uc**2 + vc**2
    return uc+x_m, vc+y_m, np.sqrt(max(R2, 0))

def get_rct_from_circle(xc, yc, r):
    return 2 * np.sqrt(max(0, r**2 - yc**2))

def extract_arc(zre, zim, freq):
    order = np.argsort(freq)[::-1]
    zre_s = np.asarray(zre)[order]; zim_s = np.asarray(zim)[order]
    if len(zre_s) < 6: return zre_s, zim_s
    peak_idx = int(np.argmax(zim_s))
    valley_idx = peak_idx + int(np.argmin(zim_s[peak_idx:]))
    if valley_idx + 1 < 6: return zre_s, zim_s
    return zre_s[:valley_idx+1], zim_s[:valley_idx+1]

def r2_score(y, yhat):
    ss_res = np.sum((y-yhat)**2); ss_tot = np.sum((y-np.mean(y))**2)
    return 1 - ss_res/ss_tot if ss_tot != 0 else np.nan

def langmuir(C, y0, A, Kd):
    return y0 + A*C/(Kd+C)

def hill(C, y0, A, Kd, n):
    return y0 + A*(C**n/(Kd**n+C**n))

def run_eis_analysis(exp_path, sample_table, use_abs_fit=True):
    exp_path = Path(exp_path); method = "EIS"
    raw_dir = exp_path/"RawData"/method
    result_dir = exp_path/"Results"/method
    figure_dir = exp_path/"Figures"/method
    report_dir = exp_path/"Reports"/method
    for d in [result_dir, figure_dir, report_dir]: d.mkdir(parents=True, exist_ok=True)

    sample_table = sample_table.copy()
    sample_table["Concentration_pM"] = pd.to_numeric(sample_table["Concentration_pM"], errors="coerce")
    sample_table = sample_table.dropna(subset=["File","Label","Concentration_pM"]).sort_values("Concentration_pM")

    datasets, rows = [], []
    for _, row in sample_table.iterrows():
        zre, zim, freq = load_eis_file(raw_dir/str(row["File"]))
        order = np.argsort(freq)[::-1]
        zre = np.asarray(zre, dtype=float)[order]; zim = np.asarray(zim, dtype=float)[order]; freq = np.asarray(freq, dtype=float)[order]
        arc_x, arc_y = extract_arc(zre, zim, freq)
        xc, yc, r = fit_circle_algebraic(arc_x, arc_y)
        rct = float(get_rct_from_circle(xc, yc, r))
        item = {"file":str(row["File"]), "label":str(row["Label"]), "conc_pM":float(row["Concentration_pM"]), "conc_M":float(row["Concentration_pM"])*1e-12, "zre":zre, "zim":zim, "freq":freq, "xc":xc, "yc":yc, "r":r, "Rct_ohm":rct}
        datasets.append(item)
        rows.append({"File":item["file"],"Label":item["label"],"Concentration_pM":item["conc_pM"],"Concentration_M":item["conc_M"],"Rct_ohm":rct,"Circle_xc":xc,"Circle_yc":yc,"Circle_r":r})

    rct_df = pd.DataFrame(rows).sort_values("Concentration_pM")
    if (rct_df["Concentration_pM"] == 0).sum() == 0:
        raise RuntimeError("A zero sample with Concentration_pM = 0 is required.")
    rct_zero = rct_df.loc[rct_df["Concentration_pM"]==0,"Rct_ohm"].iloc[0]
    rct_df["DeltaRct_vs_zero_ohm"] = rct_df["Rct_ohm"] - rct_zero
    rct_df["Abs_DeltaRct_vs_zero_ohm"] = np.abs(rct_df["DeltaRct_vs_zero_ohm"])
    rct_df.to_csv(result_dir/"rct_values.csv", index=False)
    with pd.ExcelWriter(result_dir/"rct_values.xlsx", engine="openpyxl") as writer:
        rct_df.to_excel(writer, sheet_name="Rct_values", index=False)

    fig, ax = plt.subplots()
    for item in datasets: ax.scatter(item["zre"], item["zim"], s=18, label=item["label"])
    ax.set_xlabel("Z' (Ω)"); ax.set_ylabel("-Z'' (Ω)"); ax.set_title("EIS Nyquist scatter only"); ax.legend(); ax.set_aspect("equal", adjustable="datalim")
    fig_to_file(fig, figure_dir/"1a_nyquist_scatter_only.png"); plt.close(fig)

    fig, ax = plt.subplots()
    for item in datasets:
        ax.scatter(item["zre"], item["zim"], s=18, label=f"{item['label']} (Rct={item['Rct_ohm']:.1f} Ω)")
        theta = np.linspace(0, np.pi, 300)
        ax.plot(item["xc"]+item["r"]*np.cos(theta), item["yc"]+item["r"]*np.sin(theta), "--", linewidth=1.3)
    ax.set_xlabel("Z' (Ω)"); ax.set_ylabel("-Z'' (Ω)"); ax.set_title("EIS Nyquist + semicircle fit"); ax.legend(); ax.set_aspect("equal", adjustable="datalim")
    fig_to_file(fig, figure_dir/"1b_nyquist_semicircle_fit.png"); plt.close(fig)

    fig, ax = plt.subplots()
    ax.scatter(rct_df["Concentration_pM"], rct_df["DeltaRct_vs_zero_ohm"]); ax.axhline(0, linewidth=0.5)
    ax.set_xlabel("Concentration (pM)"); ax.set_ylabel("ΔRct vs zero (Ω)"); ax.set_title("ΔRct vs concentration")
    fig_to_file(fig, figure_dir/"2_deltaRct_scatter.png"); plt.close(fig)

    fit_df = rct_df[rct_df["Concentration_M"] > 0].copy(); fit_summary = []
    if len(fit_df) >= 2:
        x = fit_df["Concentration_M"].to_numpy()
        y_raw = fit_df["DeltaRct_vs_zero_ohm"].to_numpy()
        y = np.abs(y_raw) if use_abs_fit else y_raw
        lnx = np.log(x); a,b = np.polyfit(lnx,y,1); r2_log = r2_score(y, a*lnx+b)
        x_line = np.logspace(np.log10(x.min()), np.log10(x.max()), 300)
        fig, ax = plt.subplots(); ax.scatter(x,y,label="data"); ax.plot(x_line,a*np.log(x_line)+b,"--",label="log fit")
        fit_summary.append({"Model":"LogTrend(ln)","a":a,"b":b,"R2":r2_log})
        if len(fit_df) >= 3:
            try:
                y0_0,A_0,Kd_0 = float(np.min(y)),float(np.max(y)-np.min(y)),float(np.median(x))
                popt_L,_ = curve_fit(langmuir,x,y,p0=[y0_0,A_0,Kd_0],bounds=([-np.inf,0,0],[np.inf,np.inf,np.inf]),maxfev=30000)
                r2_L = r2_score(y, langmuir(x,*popt_L)); ax.plot(x_line,langmuir(x_line,*popt_L),"--",label="Langmuir")
                popt_H,_ = curve_fit(hill,x,y,p0=[y0_0,A_0,Kd_0,1.0],bounds=([-np.inf,0,0,0],[np.inf,np.inf,np.inf,10]),maxfev=60000)
                r2_H = r2_score(y, hill(x,*popt_H)); ax.plot(x_line,hill(x_line,*popt_H),"--",label="Hill")
                fit_summary.append({"Model":"Langmuir","y0":popt_L[0],"A":popt_L[1],"Kd_M":popt_L[2],"Kd_pM":popt_L[2]/1e-12,"R2":r2_L})
                fit_summary.append({"Model":"Hill","y0":popt_H[0],"A":popt_H[1],"Kd_M":popt_H[2],"Kd_pM":popt_H[2]/1e-12,"n":popt_H[3],"R2":r2_H})
            except Exception as e:
                fit_summary.append({"Model":"Langmuir/Hill failed","Error":str(e)})
        ax.set_xlabel("Concentration (M)"); ax.set_ylabel("|ΔRct| (Ω)" if use_abs_fit else "ΔRct (Ω)")
        ax.set_title("EIS fitting: log / Langmuir / Hill"); ax.text(0.02,0.98,f"log: y={a:.4g} ln(x)+{b:.4g}\\nR²={r2_log:.4f}",transform=ax.transAxes,va="top"); ax.legend()
        fig_to_file(fig, figure_dir/"3_fit_compare.png"); plt.close(fig)

    fit_summary_df = pd.DataFrame(fit_summary)
    fit_summary_df.to_csv(result_dir/"fit_summary.csv", index=False)
    with pd.ExcelWriter(result_dir/"fit_summary.xlsx", engine="openpyxl") as writer:
        fit_summary_df.to_excel(writer, sheet_name="Fit_summary", index=False)
    report = "EIS Analysis Report\\n\\nRct values:\\n" + rct_df.to_string(index=False) + "\\n\\nFit summary:\\n" + fit_summary_df.to_string(index=False)
    (report_dir/"analysis_summary.txt").write_text(report, encoding="utf-8")
    return {"rct_df": rct_df, "fit_summary_df": fit_summary_df, "result_dir": str(result_dir), "figure_dir": str(figure_dir), "report_dir": str(report_dir)}
