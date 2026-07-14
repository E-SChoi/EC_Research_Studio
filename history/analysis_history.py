from pathlib import Path
from datetime import datetime
import json
import pandas as pd

METHODS=["DPV","SWV","EIS","CV"]

def _safe_json(path):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception: return {}

def _latest(paths):
    files=[p for p in paths if p.exists() and p.is_file()]
    return max(files,key=lambda p:p.stat().st_mtime) if files else None

def _key_result(path):
    if path is None or not Path(path).exists(): return ""
    try:
        df=pd.read_excel(path) if Path(path).suffix.lower()==".xlsx" else pd.read_csv(path)
    except Exception: return ""
    if df.empty: return ""
    candidates=[("DeltaPeak_max_minus_min_uA","ΔPeak"," µA"),("DeltaPeak_peak_minus_preceding_min_uA","ΔPeak"," µA"),("DeltaDeltaPeak_vs_zero_uA","ΔΔPeak"," µA"),("Rct_ohm","Rct"," Ω"),("DeltaRct_vs_zero_ohm","ΔRct"," Ω"),("DeltaEp_V","ΔEp"," V"),("LOD_pM","LOD"," pM"),("R2","R²","")]
    for col,label,unit in candidates:
        if col in df.columns:
            s=pd.to_numeric(df[col],errors="coerce").dropna()
            if len(s): return f"{label} {float(s.iloc[-1]):.4g}{unit}"
    return ""

def _eln_text(exp):
    p=Path(exp)/"Notes"/"eln_entries.json"
    if not p.exists(): return ""
    try: entries=json.loads(p.read_text(encoding="utf-8"))
    except Exception: return ""
    if not entries: return ""
    e=sorted(entries,key=lambda x:x.get("created_at",""))[-1]
    return " ".join(str(e.get(k,"")) for k in ["title","category","observation","result_summary","next_action"])

def scan_project_history(project_path):
    root=Path(project_path)/"Experiments"; rows=[]
    if not root.exists(): return pd.DataFrame()
    for exp in sorted(p for p in root.iterdir() if p.is_dir()):
        info=_safe_json(exp/"experiment.json")
        for method in METHODS:
            raw=exp/"RawData"/method; res=exp/"Results"/method; fig=exp/"Figures"/method; rep=exp/"Reports"/method
            rawf=[p for p in raw.iterdir() if p.is_file()] if raw.exists() else []
            resf=[p for p in res.rglob('*') if p.is_file()] if res.exists() else []
            figs=[p for p in fig.rglob('*.png') if p.is_file()] if fig.exists() else []
            reps=[p for p in rep.rglob('*') if p.is_file()] if rep.exists() else []
            if not any([rawf,resf,figs,reps]): continue
            latest_result=_latest([p for p in resf if p.suffix.lower() in ['.csv','.xlsx']])
            latest_figure=_latest(figs); latest_report=_latest(reps); latest=_latest(rawf+resf+figs+reps)
            dt=datetime.fromtimestamp(latest.stat().st_mtime) if latest else None
            search=' '.join([exp.name,method,str(info.get('researcher','')),str(info.get('target','')),str(info.get('sensor','')),str(info.get('comment','')),_eln_text(exp),' '.join(p.name for p in rawf+resf)]).lower()
            rows.append({
                'Latest activity':dt.strftime('%Y-%m-%d %H:%M:%S') if dt else '',
                'Date':dt.strftime('%Y-%m-%d') if dt else '',
                'Experiment':exp.name,'Method':method,'Researcher':info.get('researcher',''),'Target':info.get('target',''),'Sensor':info.get('sensor',''),
                'Raw files':len(rawf),'Result files':len(resf),'Figures':len(figs),'Reports':len(reps),'Key result':_key_result(latest_result),
                'Latest result path':str(latest_result) if latest_result else '', 'Latest figure path':str(latest_figure) if latest_figure else '', 'Latest report path':str(latest_report) if latest_report else '',
                'Experiment path':str(exp),'Search text':search,
            })
    if not rows: return pd.DataFrame()
    df=pd.DataFrame(rows); df['Latest activity dt']=pd.to_datetime(df['Latest activity'],errors='coerce')
    return df.sort_values('Latest activity dt',ascending=False).reset_index(drop=True)

def filter_history(df,keyword='',method='All',sort_order='Latest first'):
    if df is None or df.empty: return pd.DataFrame()
    out=df.copy()
    if method!='All': out=out[out['Method']==method]
    q=str(keyword).strip().lower()
    if q: out=out[out['Search text'].str.contains(q,na=False)]
    return out.sort_values('Latest activity dt',ascending=(sort_order=='Oldest first')).reset_index(drop=True)

def compact_history_table(df):
    if df is None or df.empty: return pd.DataFrame()
    cols=['Latest activity','Experiment','Method','Target','Raw files','Result files','Figures','Key result']
    return df[[c for c in cols if c in df.columns]].copy()
