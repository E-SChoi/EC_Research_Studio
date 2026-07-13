from core.voltammetry import parse_concentration, run_voltammetry_analysis

def run_dpv_analysis(
    exp_path,
    sample_table,
    use_abs_fit=True,
    baseline_mode="preceding_local_minimum",
    peak_search_min_v=0.30,
    peak_search_max_v=0.70,
    baseline_search_min_v=0.05,
    smoothing_window=11,
):
    return run_voltammetry_analysis(
        exp_path,
        sample_table,
        method="DPV",
        use_abs_fit=use_abs_fit,
        baseline_mode=baseline_mode,
        peak_search_min_v=peak_search_min_v,
        peak_search_max_v=peak_search_max_v,
        baseline_search_min_v=baseline_search_min_v,
        smoothing_window=smoothing_window,
    )
