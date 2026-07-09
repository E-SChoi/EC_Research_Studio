# EC Research Studio v0.8

## 새 기능
- Statistics Engine 추가
- Replicate 자동 인식
- Mean / SD / SEM / RSD% / 95% CI 계산
- Error bar calibration plot 생성
- LOD / LOQ 자동 계산
- 기존 DPV / SWV / EIS / Figure Builder / Database 유지

## 실행 방법
```bat
python -m pip install -r requirements.txt
streamlit run main.py
```

## GitHub 업데이트 권장 명령
```bat
git add .
git commit -m "Add statistics engine v0.8"
git tag v0.8
git push
git push origin v0.8
```
