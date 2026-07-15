# EC Research Studio v1.7.2 Smart Folder Import

## New
- Upload one complete experiment folder or ZIP file.
- Automatically classify native electrochemical files:
  - `.mtd` → DPV
  - `.mts` → SWV
  - `.mteisp` → EIS
- Automatically classify images and documents.
- Preview and edit classification before import.
- CSV files are marked `Review required`.
- Duplicate handling:
  - Rename with timestamp
  - Skip
  - Overwrite
- Save import logs as CSV.
- Save import metadata as JSON.
- Optional Auto Analyze after import.

## Safety
- Original uploaded files are never modified.
- Existing analysis engines and native raw parsers are unchanged.
- The default duplicate policy preserves both files by renaming the new one.
- Unknown CSV files are not guessed automatically.

## Apply patch
Overwrite:
- `main.py`
- `README.md`
- `CHANGELOG.md`
- `USER_GUIDE.md`
- `RELEASE_NOTE.md`
- `VALIDATION_REPORT.md`
- `smart_import/__init__.py`
- `smart_import/folder_import.py`

Then run:
```bat
streamlit run main.py
```

## GitHub Desktop
Summary:
```text
Add Smart Folder Import v1.7.2
```
