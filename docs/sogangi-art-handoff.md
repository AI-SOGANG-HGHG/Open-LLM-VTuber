# 서강이 원화 제작 인계 자료

2026-11-02, 공식 PDF에서 추출한 SVG 파츠를 **24개 레이어 PSD와 같은 캔버스 PNG**로 변환했다. 실제 파일은 `web_tool/sogangi/assets/production/`에 있고 [제작 설계 화면](http://localhost:12393/web-tool/sogangi/live2d-plan.html)에서 내려받을 수 있다.

## 포함한 것

- `sogangi-visible-parts.psd`: 2048×2048, RGB 8bit, 투명 레이어. 모든 레이어는 같은 전체 캔버스와 좌표를 사용한다.
- 기본형 21개 레이어는 보이고, 공식 기쁨형에서 정렬한 감은 눈 2개와 열린 입 1개는 기본적으로 숨겨져 있다.
- `layers/*.png`: 같은 캔버스/투명도를 가진 24개 파츠. 원본 SVG의 선·채우기·클리핑을 Chrome에서 렌더링했다. 새 캐릭터 원화를 그리거나 가려진 부분을 보완한 자료는 아니다.
- `neutral-preview.png`, `handoff-manifest.json`, `README.txt`: 기본 합성 미리보기, 원본 PDF와 각 SVG/레이어/PSD 해시, 좌표·가시성·검증 결과.
- `sogangi-art-handoff.zip`: 위의 제작 자료 묶음.

이 PSD는 팀이 변환한 **보이는 파츠 준비 파일**이다. 학교가 배포한 공식 레이어 PSD 원본이나 Cubism에 바로 납품할 완성 원화라고 부르지 않는다. 원본 캐릭터 권리와 사용 조건은 변하지 않는다.

## 검증과 제한

PSD를 다시 열어 24개 이름·순서·좌표·기본 가시성·각 레이어 RGBA 픽셀의 왕복 일치를 확인했다. 호환용 합성 미리보기의 투명도도 확인했다. PSD 레이어 합성과 같은 캔버스의 원본 SVG를 비교해 알파/색 오차를 측정했고, 시각적으로 얼굴·의상 문양·팔다리를 확인했다. 문양 클리핑을 반영하지 못한 중간 변환 결과는 사용하지 않았다.

기록된 합성 오차는 0–255 척도에서 채널 평균 약 0.0012이며, 최대 채널 차이가 16을 넘는 픽셀 비율은 0이다. 개별 PNG→PSD 레이어 픽셀은 정확히 일치한다. 합성 경계의 안티앨리어싱 차이까지 전체 픽셀이 동일하다고 주장하지 않는다.

이 보이는 파츠 변환의 검증 도구는 psd-tools 1.26.0과 설치된 Chrome이다. 원래 평면 준비 PSD를 Photoshop에서 직접 가져오기는 미확인이다. 이후 아래의 그룹/여백 정리본은 실제 Cubism Editor에서 가져왔고, 별도의 눈·입 최소 cmo3·moc3도 생성·검수했다. 전체 각도/몸 리깅까지 검증한 것은 아니다.

## 제작자가 이어 할 일

1. 화면 기준 L/R 이름과 실제 모델의 좌우 기준을 정한다. 필요하면 일괄 변경하고 대응표를 남긴다.
2. 회전 시 드러나는 부분을 먼저 점검하고 필요한 곳을 이어 그린다. 분리된 도형에도 이미 가림 부분이 있다. 아래의 고정 회전 비교를 실제 Cubism 메시 변형에 대한 보증으로 사용하지 않는다.
3. 입의 중간 형태, 눈 닫힘 전환, 후드와 부리의 각도별 모양을 검토/보완한다.
4. Cubism에서 눈·입·호흡·고개 기울기부터 리깅하고, 접지와 팔 연결을 검수한다.
5. 편집용 cmo3와 실행용 moc3/model3/텍스처를 분리해 내보내고 앱에서 음성·중단·표정·모바일을 검사한다. 상세 기준은 [Live2D 제작 설계](sogangi-live2d-plan.md)를 따른다.

## 재현

앱 Python은 기존 버전으로 유지한다. psd-tools의 버전 요구 때문에 변환 도구는 별도의 Python >=3.11 환경에서 실행한다. 확인한 환경은 Python 3.13과 설치된 Chrome이다.

```powershell
# uv가 설치돼 있다면 같은 명령에서 uv.exe 경로를 조정할 수 있다.
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) 'tmp/python'
.\tmp\tools\uv.exe venv --no-project tmp/art-tools --python 3.13
.\tmp\tools\uv.exe pip install --python tmp/art-tools/Scripts/python.exe -r tools/requirements-art.txt
.\tmp\art-tools\Scripts\python.exe tools/export_sogangi_psd.py --overwrite
```

`SOGANGI_BROWSER`로 다른 Chromium 실행 파일을 지정할 수 있다. 변환은 LLM/TTS API를 호출하지 않는다. 원본 SVG 파츠 추출은 기존 `tools/prepare_sogangi_layers.py`와 고정 PDF 해시를 사용한다.

도구의 PSD 쓰기/레이어 API는 [psd-tools 공식 사용 안내](https://psd-tools.readthedocs.io/en/latest/usage.html)를 참고했다. 일반 편집 도구의 합성/표시 차이는 실제 제작 환경에서 다시 확인한다.

## 11월 3일 겹침·자세 비교

[원화 동작 비교 화면](http://localhost:12393/web-tool/sogangi/art-review.html)에서 정면, 고개 ±3°, 팔 인사 18°/36°, 동시 극값, 범위 밖 8°/60°의 7개 자세를 볼 수 있다. 어깨·얼굴 확대와 피벗 표시, 별도 후보 PSD 다운로드를 제공한다. 비교는 실제 벡터를 고정 회전한 결과다.

기존 팔의 불투명 픽셀 중 화면 왼팔 약 60.0%, 오른팔 약 59.9%가 앞쪽 레이어에 완전히 가려져 있었다. 후드 약 62.8%, 얼굴 약 11.0%도 가려져 있다. 즉, 분리 파일이 보이는 실루엣만 잘라 놓은 자료는 아니었다. 이 수치는 검수 영역을 정하는 근거이며 변형 안전성을 판정한 값은 아니다.

별도의 `assets/overlap-candidates/`에 직접 작성한 어깨 캡 두 개와 **26개 레이어 후보 PSD**를 만들었다. 학교 원본과 기존 24개 레이어는 바꾸지 않았다. 후보는 두 어깨 디포머에 각각 같이 연결하는 검토안이다.

- 정면 2048×2048 Chrome 합성: 기존 대비 RGBA 픽셀 완전 일치.
- 각 레이어의 PNG→PSD 왕복: 픽셀 완전 일치. 기존 24개 레이어도 동일.
- PSD 합성: 4,194,304픽셀 중 151픽셀에서 최대 채널 차이 1/255. psd-tools 합성 오차 허용 범위로 기록하며 완전 일치라고 표현하지 않는다.
- 1024×1024 자세 비교: 7개 모두 후보 추가 전후의 보이는 픽셀 차이 0.

따라서 **현재 동작 범위에는 어깨 후보를 채택하지 않고 기본 24개 자료를 유지한다.** 추가 원화로 품질이 좋아졌다는 근거가 없기 때문이다. 후보 ZIP은 비교 실험의 인계 자료다. 실제 리깅에는 기본 PSD부터 가져오고, 메시 변형에서 드러나는 곳을 다시 판단한다. 얼굴 좌우 회전·뒤통수·입 메시의 중간 형태와 Cubism 가져오기는 아직 확인하지 않았다.

범위 밖 60° 팔 자세에서는 팔이 큰 머리 뒤로 가려지는 한계도 보였다. 어깨 캡 추가로 해결되는 문제가 아니므로, 머리 위로 드는 큰 인사를 추가하려면 팔의 앞뒤 그리기 순서·메시 연결을 함께 설계해야 한다. 현재 앱의 작은 옆 인사 범위와 구분한다.

재생성은 기존 원본을 보존하는 별도 명령이다. 기본 제작 PSD 출력 폴더를 대상으로 지정하면 거부한다.

```powershell
.\tmp\art-tools\Scripts\python.exe tools/prepare_sogangi_overlap.py --overwrite
```

`review.json`에는 기준/후보 PSD 해시, 원화 출처 구분, 레이어별 픽셀 해시, 측정 결과와 미검증 항목이 있다. 검사에는 모델·음성 API를 쓰지 않는다.

## Cubism 가져오기용 그룹·여백 정리본

`assets/cubism-import/sogangi-cubism-import.psd`는 기존 원화를 복원 좌표 그대로 보존하면서 9개 그룹으로 정리한 별도 준비 파일이다. 각 파츠의 투명 여백만 잘라 PSD 오프셋을 유지했다. 캔버스는 같은 2048×2048, 그림 레이어는 같은 24개, 기본 숨김 후보도 같은 3개다. 원화 추가나 기존 준비 파일 교체는 하지 않았다. [제작 설계 화면](http://localhost:12393/web-tool/sogangi/live2d-plan.html)에서 묶음을 받을 수 있다.

- PSD를 다시 열어 24개 레이어를 전체 캔버스로 복원했을 때 원본 PNG의 픽셀과 정확히 일치했다.
- 그룹 정리 후 정면 PSD 합성은 275픽셀에서 최대 채널 차이 1/255였다. 기존 합성과 완전 일치라고 부르지 않는다.
- 다른 구현인 TypeScript/ag-psd 판독기로도 9개 그룹 경로, 24개 파츠의 잘린 픽셀과 오프셋을 정확히 읽었다. 결과는 `independent-reader-report.json`이다.
- 파일 크기는 17,360,770바이트다. 잘린 PNG를 쓸 때는 반드시 manifest의 좌표를 적용해야 하며 개별 PNG를 다시 가운데 정렬하면 안 된다.

`keyform-plan.json`은 화면 좌우 기준으로 `ParamEyeLOpen`, `ParamEyeROpen`, `ParamMouthOpenY`의 두 끝값·기본 가시성·PSD 피벗을 명시한다. 기본값은 원래 눈/입 표시와 일치한다. 실제 모델에 적용한 결과는 아니다.

`atlas-layout-proposal.json`은 모든 파츠를 원본 크기 100%, 여유 4픽셀로 2048×2048 한 장에 겹치지 않게 배치한 계산 결과다. PNG 아틀라스나 모델 UV를 생성한 자료는 아니다. 실제 Editor에서 같은 해상도의 아틀라스를 만들고 대응하는 MOC와 함께 내보내야 한다.

독립 PSD 판독은 **그 자체로 Editor/모델 검증을 대신하지 않는다.** 이후 공식 Editor 설치를 완료하고 이 정리본을 가져왔으며 눈·입 최소 cmo3/moc3도 별도로 검사했다. 생성/판독 manifest의 미검증 표시는 각 도구의 검사 범위다. 현재 실제 모델의 파일 해시와 검증 여부는 `live2d-models/sogangi-minimum/verification.json`, 실행 순서는 [원화·리깅 연결](sogangi-rigging-integration.md)에 있다.

```powershell
.\tmp\art-tools\Scripts\python.exe tools/prepare_sogangi_import.py --overwrite
.\tmp\browser-tools\Lib\site-packages\playwright\driver\node.exe tools/check_sogangi_psd_interop.mjs --converter ../reference-sources/autoLive2d --psd web_tool/sogangi/assets/cubism-import/sogangi-cubism-import.psd --manifest web_tool/sogangi/assets/cubism-import/import-manifest.json --output web_tool/sogangi/assets/cubism-import/independent-reader-report.json
```

독립 판독 검사에는 별도 참고 도구의 고정 의존성이 필요하다. 첫 명령은 원본 준비 PSD와 파츠 폴더를 대상으로 출력하면 거부한다. 독립 판독 결과는 ZIP과 별도 제공하며, 재생성 후 두 번째 명령으로 다시 확인한다.
