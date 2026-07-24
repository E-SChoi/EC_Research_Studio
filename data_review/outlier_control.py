from pathlib import Path
from datetime import datetime
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def _latest_file(paths):
    files=[Path(p) for p in paths if Path(p).exists() and Path(p).is_file()]
    return max(files,key=lambda p:p.stat().st_mtime) if files else None

def _read_table(path):
    if path is None:return None
    try:return pd.read_excel(path) if path.suffix.lower()=='.xlsx' else pd.read_csv(path)
    except Exception:return None

def list_experiments(project_path):
    root=Path(project_path)/'Experiments'
    return sorted([p.name for p in root.iterdir() if p.is_dir()]) if root.exists() else []

def find_calibration_table(exp_path,method):
    root=Path(exp_path)/'Results'/method
    if not root.exists():return None,None
    preferred={'DPV':['peak_values.csv','peak_values.xlsx'],'SWV':['peak_values.csv','peak_values.xlsx'],'EIS':['rct_values.csv','rct_values.xlsx','eis_fit_summary.csv']}
    candidates=[]
    for name in preferred.get(method,[]): candidates.extend(root.rglob(name))
    selected=_latest_file(candidates) or _latest_file([p for p in root.rglob('*') if p.suffix.lower() in ['.csv','.xlsx']])
    return selected,_read_table(selected)

def infer_columns(df,method):
    x=next((c for c in ['Concentration_pM','Concentration'] if c in df.columns),None)
    if method in ['DPV','SWV']:
        y=next((c for c in ['DeltaPeak_peak_minus_preceding_min_uA','DeltaPeak_max_minus_min_uA','DeltaDeltaPeak_vs_zero_uA','Abs_DeltaDeltaPeak_vs_zero_uA'] if c in df.columns),None)
    else:
        y=next((c for c in ['Rct_ohm','DeltaRct_vs_zero_ohm','Delta_Rct_ohm','DeltaRct_ohm'] if c in df.columns),None)
    label=next((c for c in ['Label','File','Sample'] if c in df.columns),None)
    return x,y,label

def calculate_outlier_diagnostics(df):
    out=df.copy(); n=len(out)
    for c in ['Residual','Studentized residual',"Cook's distance",'MAD robust z-score']: out[c]=np.nan
    out['Recommendation']='Normal'
    if n<3:return out
    x=out['Concentration_pM'].to_numpy(float); y=out['Signal'].to_numpy(float)
    X=np.column_stack([np.ones(n),x]); beta,*_=np.linalg.lstsq(X,y,rcond=None); pred=X@beta; res=y-pred
    hat=np.diag(X@np.linalg.pinv(X.T@X)@X.T); p=X.shape[1]; mse=np.sum(res**2)/max(n-p,1)
    if mse>0:
        stud=res/np.sqrt(mse*np.maximum(1-hat,1e-12)); cooks=(res**2/(p*mse))*(hat/np.maximum((1-hat)**2,1e-12))
    else: stud=np.zeros(n); cooks=np.zeros(n)
    med=np.median(res); mad=np.median(np.abs(res-med)); rz=0.6745*(res-med)/mad if mad>0 else np.zeros(n)
    out['Residual']=res; out['Studentized residual']=stud; out["Cook's distance"]=cooks; out['MAD robust z-score']=rz
    flags=(np.abs(stud)>2).astype(int)+(cooks>4/n).astype(int)+(np.abs(rz)>3.5).astype(int)
    out['Recommendation']=np.where(flags>=2,'Strong candidate',np.where(flags==1,'Review','Normal'))
    return out

def prepare_review_table(df,method):
    x,y,label=infer_columns(df,method)
    if x is None or y is None: raise ValueError('Concentration and signal columns could not be identified.')
    work=pd.DataFrame({'Point ID':np.arange(len(df)),'Label':df[label].astype(str) if label else [f'Point {i+1}' for i in range(len(df))],'Concentration_pM':pd.to_numeric(df[x],errors='coerce'),'Signal':pd.to_numeric(df[y],errors='coerce'),'Decision':'Keep','Exclusion reason':''}).dropna(subset=['Concentration_pM','Signal']).reset_index(drop=True)
    work['Point ID']=np.arange(len(work)); return calculate_outlier_diagnostics(work)

def _fit(df):
    if len(df)<2:return {'slope':np.nan,'intercept':np.nan,'r2':np.nan,'n':len(df)}
    x=df['Concentration_pM'].to_numpy(float); y=df['Signal'].to_numpy(float)
    if len(np.unique(x))<2:return {'slope':np.nan,'intercept':np.nan,'r2':np.nan,'n':len(df)}
    slope,intercept=np.polyfit(x,y,1); pred=slope*x+intercept; ssr=np.sum((y-pred)**2); sst=np.sum((y-y.mean())**2); r2=np.nan if sst==0 else 1-ssr/sst
    return {'slope':float(slope),'intercept':float(intercept),'r2':float(r2),'n':len(df)}

def recalculate_review(df):
    visible=df[df['Decision']!='Exclude entirely'].copy(); fit_df=visible[visible['Decision']!='Exclude from fitting'].copy(); orig=_fit(df); rev=_fit(fit_df)
    metrics=pd.DataFrame([{'Metric':'Included points','Original':orig['n'],'Reviewed':rev['n']},{'Metric':'Slope','Original':orig['slope'],'Reviewed':rev['slope']},{'Metric':'Intercept','Original':orig['intercept'],'Reviewed':rev['intercept']},{'Metric':'R²','Original':orig['r2'],'Reviewed':rev['r2']}])
    return {'all_visible_df':visible,'fit_df':fit_df,'original_fit':orig,'reviewed_fit':rev,'metrics_df':metrics}

def create_review_figure(df,output_path,title='Reviewed calibration'):
    r=recalculate_review(df); vis=r['all_visible_df']; fit_df=r['fit_df']; fit=r['reviewed_fit']; fig,ax=plt.subplots()
    kept=vis[vis['Decision']=='Keep']; ex=vis[vis['Decision']=='Exclude from fitting']
    if not kept.empty: ax.scatter(kept['Concentration_pM'],kept['Signal'],label='Included')
    if not ex.empty: ax.scatter(ex['Concentration_pM'],ex['Signal'],facecolors='none',edgecolors='black',label='Excluded from fitting')
    if len(fit_df)>=2 and np.isfinite(fit['slope']):
        xl=np.linspace(fit_df['Concentration_pM'].min(),fit_df['Concentration_pM'].max(),200); ax.plot(xl,fit['slope']*xl+fit['intercept'],label=f"Reviewed fit (R²={fit['r2']:.4f})")
    ax.set_xlabel('Concentration (pM)'); ax.set_ylabel('Signal'); ax.set_title(title); ax.legend(); fig.tight_layout(); output_path=Path(output_path); output_path.parent.mkdir(parents=True,exist_ok=True); fig.savefig(output_path,dpi=300,bbox_inches='tight'); plt.close(fig); return output_path

def save_review_outputs(exp_path,method,source_path,reviewed_df,metrics_df,figure_path):
    exp_path=Path(exp_path); stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); result_dir=exp_path/'Results'/method/'Reviewed'; report_dir=exp_path/'Reports'/method/'Reviewed'; result_dir.mkdir(parents=True,exist_ok=True); report_dir.mkdir(parents=True,exist_ok=True)
    reviewed_csv=result_dir/f'reviewed_points_{stamp}.csv'; metrics_csv=result_dir/f'reviewed_fit_metrics_{stamp}.csv'; log_json=report_dir/f'exclusion_log_{stamp}.json'; reviewed_df.to_csv(reviewed_csv,index=False,encoding='utf-8-sig'); metrics_df.to_csv(metrics_csv,index=False,encoding='utf-8-sig')
    excluded=reviewed_df[reviewed_df['Decision']!='Keep']; log={'created_at':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'method':method,'source_result':str(source_path),'reviewed_points_file':str(reviewed_csv.relative_to(exp_path)),'reviewed_metrics_file':str(metrics_csv.relative_to(exp_path)),'reviewed_figure':str(Path(figure_path).relative_to(exp_path)),'excluded_points':excluded[['Point ID','Label','Concentration_pM','Signal','Decision','Exclusion reason','Recommendation','Studentized residual',"Cook's distance",'MAD robust z-score']].to_dict('records')}
    log_json.write_text(json.dumps(log,ensure_ascii=False,indent=2),encoding='utf-8'); return {'reviewed_csv':reviewed_csv,'metrics_csv':metrics_csv,'log_json':log_json,'figure_path':Path(figure_path)}
