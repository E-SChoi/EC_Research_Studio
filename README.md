# EC Research Studio v0.7

## 새 기능
- SQLite 기반 Research Database 추가
- Sensor / Sample / Recognition / Reagent database
- Experiment Wizard 추가
- Database에 저장된 항목을 선택해서 실험 생성
- 기존 DPV / SWV / EIS / Figure Builder 기능 유지

## 실행 방법
```bat
python -m pip install -r requirements.txt
streamlit run main.py
```

## GitHub 업데이트 권장 명령
```bat
git add .
git commit -m "Add database and experiment wizard v0.7"
git tag v0.7
git push
git push origin v0.7
```
