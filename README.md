# EC Research Studio v1.6 Experiment Summary

## New
- Experiment Summary tab
- Displays the most recently updated result values
- Displays the latest DPV, SWV, EIS, or CV graph
- Displays the latest DPV/SWV ΔPeak table
- Shows raw/result/figure counts
- Shows the most recent ELN note
- Exports a self-contained HTML experiment report with the graph embedded

## Selection rules
- Latest result: newest CSV/XLSX file inside `Results`
- Graph: newest relevant PNG, preferring the same method as the latest result
- ΔPeak: newest `peak_values` or `baseline_info` table from DPV/SWV
- No analysis algorithms or native raw parsers were changed

## Apply patch
Overwrite:
- `main.py`
- `README.md`
- `summary/__init__.py`
- `summary/experiment_summary.py`

Then run:
```bat
streamlit run main.py
```

## GitHub Desktop
Summary: `Add Experiment Summary and HTML report v1.6`
