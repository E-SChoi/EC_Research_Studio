# EC Research Studio v1.8.0 Smart Experiment

## New workflow
1. Upload one concentration-series folder or ZIP.
2. Use the folder name as the suggested Experiment name.
3. Automatically classify `.mtd`, `.mts`, and `.mteisp`.
4. Detect concentrations from filenames.
5. Normalize all concentrations to pM.
6. Create a new Experiment automatically.
7. Import raw files.
8. Optionally run Auto Analyze.
9. Display generated figures and concentration tables.

## Concentration examples
- `3-pbs.mtd` → 0 pM
- `4-10pM.mtd` → 10 pM
- `5-50pM.mts` → 50 pM
- `sample_1nM.mteisp` → 1000 pM
- `blank.mtd` → 0 pM

## Safety
- The suggested Experiment name can be edited.
- Existing Experiment collision options:
  - Create new with timestamp
  - Use existing
  - Cancel
- Unrecognized concentrations must be reviewed before Auto Analyze.
- Existing analysis engines and native raw parsers remain unchanged.

## Apply patch
Overwrite:
- `main.py`
- `README.md`
- `CHANGELOG.md`
- `USER_GUIDE.md`
- `RELEASE_NOTE.md`
- `VALIDATION_REPORT.md`
- `smart_experiment/__init__.py`
- `smart_experiment/manager.py`

Then run:
```bat
streamlit run main.py
```

## GitHub Desktop
Summary:
```text
Add Smart Experiment v1.8.0
```
