from pathlib import Path
import pandas as pd
import numpy as np

def collect_result_files(exp_path):
    root = Path(exp_path) / "Results"
    items = []
    if not root.exists():
        return items
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in [".csv", ".xlsx"]:
            method = next((m for m in ["DPV","SWV","EIS","CV"] if m in p.parts), "Other")
            items.append({"method": method, "label": str(p.relative_to(root)).replace("\\","/"), "path": str(p)})
    return sorted(items, key=lambda x: (x["method"], x["label"]))

def read_result_table(path):
    path = Path(path)
    return pd.read_excel(path) if path.suffix.lower() == ".xlsx" else pd.read_csv(path)

def collect_figures(exp_path):
    root = Path(exp_path) / "Figures"
    items = []
    if not root.exists():
        return items
    for p in root.rglob("*.png"):
        method = next((m for m in ["DPV","SWV","EIS","CV"] if m in p.parts), "Other")
        items.append({"method": method, "path": str(p), "mtime": p.stat().st_mtime})
    return sorted(items, key=lambda x: x["mtime"], reverse=True)

def batch_summary(exp_path):
    exp_path = Path(exp_path)
    rows = []
    for method in ["DPV","SWV","EIS","CV"]:
        raw = exp_path / "RawData" / method
        res = exp_path / "Results" / method
        fig = exp_path / "Figures" / method
        rows.append({
            "Method": method,
            "Raw files": len([p for p in raw.glob("*") if p.is_file()]) if raw.exists() else 0,
            "Result files": len([p for p in res.rglob("*") if p.is_file()]) if res.exists() else 0,
            "Figures": len([p for p in fig.rglob("*.png") if p.is_file()]) if fig.exists() else 0
        })
    return pd.DataFrame(rows)

def generate_discussion(method, df):
    if df is None or df.empty:
        return "분석 가능한 결과가 없습니다."
    method = method.upper()
    lines = [f"{method} 결과 자동 해석 초안입니다."]

    if method in ["DPV","SWV"] and "Concentration_pM" in df.columns:
        signal = next((c for c in ["DeltaDeltaPeak_vs_zero_uA","Abs_DeltaDeltaPeak_vs_zero_uA","DeltaPeak_max_minus_min_uA"] if c in df.columns), None)
        if signal:
            work = df.dropna(subset=["Concentration_pM", signal]).sort_values("Concentration_pM")
            if len(work) >= 2:
                corr = work["Concentration_pM"].corr(work[signal])
                lines.append(f"농도 증가에 따라 {signal}은 전반적으로 {'증가' if corr > 0 else '감소'}하는 경향을 보입니다.")
                lines.append("이는 타겟 결합에 따른 전극 계면의 전하 전달 또는 확산 특성 변화와 관련될 수 있습니다.")

    elif method == "EIS" and {"Concentration_pM","Rct_ohm"}.issubset(df.columns):
        work = df.dropna(subset=["Concentration_pM","Rct_ohm"]).sort_values("Concentration_pM")
        if len(work) >= 2:
            corr = work["Concentration_pM"].corr(work["Rct_ohm"])
            lines.append("농도 증가에 따라 Rct가 " + ("증가" if corr > 0 else "감소") + "하는 경향을 보입니다.")
            lines.append("Nyquist 반원 크기와 semicircle fitting 품질을 함께 확인해야 합니다.")

    elif method == "CV":
        if "DeltaEp_V" in df.columns:
            vals = pd.to_numeric(df["DeltaEp_V"], errors="coerce").dropna()
            if len(vals):
                lines.append(f"평균 ΔEp는 {vals.mean():.4f} V입니다.")
                lines.append("ΔEp 변화는 전자전달 속도와 계면 저항 변화를 반영할 수 있습니다.")

    if "R2" in df.columns:
        vals = pd.to_numeric(df["R2"], errors="coerce").dropna()
        if len(vals):
            lines.append(f"가장 높은 R²는 {vals.max():.4f}입니다.")

    lines.append("최종 Discussion에서는 반복실험, 대조군, 표면화학, 세척조건을 함께 반영해야 합니다.")
    return "\n\n".join(lines)
