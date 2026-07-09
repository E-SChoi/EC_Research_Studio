from core.voltammetry import parse_concentration, run_voltammetry_analysis

def run_swv_analysis(exp_path, sample_table, use_abs_fit=True):
    return run_voltammetry_analysis(exp_path, sample_table, method="SWV", use_abs_fit=use_abs_fit)
