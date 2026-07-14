# EC Research Studio v1.7.1 Sidebar UI

## UI change
- Replaced the long top tab bar with sidebar navigation.
- Only the selected page is rendered.
- Other pages are not displayed below the active page.
- Existing analysis functions and project data are unchanged.

## Navigation pages
- Today
- Analysis History
- Experiment Summary
- Auto Analyze
- Results
- Dashboard
- Experiments
- Experiment Wizard
- Database
- Raw Data Import
- DPV / SWV / EIS / CV Analysis
- Statistics
- Figure Builder
- ELN
- Project Info

## Apply patch
1. Stop Streamlit.
2. Extract the patch ZIP.
3. Overwrite:
   - `main.py`
   - `README.md`
   - `CHANGELOG.md`
   - `USER_GUIDE.md`
   - `RELEASE_NOTE.md`
   - `VALIDATION_REPORT.md`
4. Run:

```bat
streamlit run main.py
```

## GitHub Desktop
Summary:

```text
Add sidebar page isolation v1.7.1
```
