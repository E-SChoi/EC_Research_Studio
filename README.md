# EC Research Studio v1.5.1 Native Raw Import

## New native instrument formats
- DPV: `.mtd`
- SWV: `.mts`
- EIS: `.mteisp`
- Existing CSV files remain supported.

## Curve selection rule
- DPV/SWV: the last stored curve in the file is used.
- Differential current is reconstructed as `i1 - i2`, matching the instrument CSV export.
- EIS: the last stored `NYQUIST` curve is used.
- EIS fields are read as:
  - `potential` → Z′
  - `i1` → −Z″
  - `time` → frequency

## Workflow
1. Upload the original instrument file without CSV conversion.
2. Select the correct category: DPV, SWV, or EIS.
3. Save it to the Experiment.
4. Run the individual analysis tab or Auto Analyze.
5. The original raw file remains unchanged.

## Compatibility
- CSV workflows still work.
- Existing Projects and Experiments remain compatible.
- DPV shape-based local-minimum baseline settings remain available.

## Apply patch
Overwrite:
- `main.py`
- `README.md`
- `core/voltammetry.py`
- `core/eis.py`
- `plugins/auto_analyzer.py`
- `quick/workspace.py`
- `rawio/__init__.py`
- `rawio/instrument_xml.py`

Then run:
```bat
streamlit run main.py
```

## GitHub Desktop
Summary: `Add native instrument raw import v1.5.1`
