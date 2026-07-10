# EC Research Studio v0.9

## 새 기능
- CV Analysis Engine 추가
- CV raw overlay
- Oxidation peak / reduction peak 자동 검출
- Epa / Epc / ΔEp / E0' / Ipa / Ipc / peak ratio 계산
- Peak marker figure 생성
- Scan-rate 분석: Ipa/Ipc vs sqrt(scan rate)
- 기존 DPV / SWV / EIS / Statistics / Figure Builder / Database 유지

## 실행 방법
```bat
python -m pip install -r requirements.txt
streamlit run main.py
```

## GitHub 업데이트 권장 명령
```bat
git add .
git commit -m "Add CV engine v0.9"
git tag v0.9
git push
git push origin v0.9
```
