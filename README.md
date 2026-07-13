# EC Research Studio v1.4.1 Stable

## DPV local-minimum baseline update
- Main DPV peak is detected inside a user-defined potential window.
- The baseline point is the local minimum located before that peak.
- Each curve is vertically shifted so the detected local minimum becomes 0 µA.
- ΔPeak is calculated as `peak current − preceding local-minimum current`.
- Smoothing is used only to detect positions; exported and plotted current values remain raw.
- Detected baseline and peak potentials are saved in CSV/Excel.
- A marker figure is generated: `2b_detected_minimum_and_peak.png`.

## Recommended settings for the supplied DPV shape
- Peak search: 0.30–0.70 V
- Minimum search start: 0.05 V
- Smoothing window: 11 points

## Apply
1. Stop Streamlit.
2. Extract patch ZIP.
3. Overwrite `main.py`, `README.md`, `core/dpv.py`, and `core/voltammetry.py`.
4. Run `streamlit run main.py`.
5. In DPV Analysis, keep `Shape-based: local minimum before main peak`.

## GitHub Desktop
Summary: `Update DPV local-minimum baseline v1.4.1`
