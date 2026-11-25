# 서강이 로컬 앱

기존 Open-LLM-VTuber 서버의 대화·ASR·TTS 경로를 쓰는 별도 화면이다. 실제 Cubism 중립·기쁨·화남·놀람 표정, 눈·입·작은 정면 기울기·호흡·오른팔 인사를 지원하며 SVG 파츠도 선택할 수 있다. 입체 회전·디포머 계층·나머지 감정 원화는 남아 있다.

11월 2일에는 대화 이어가기·설정 저장·연결 복구·기록 내려받기 등 일상 사용 기능을 강화했다. [제품화 기록과 남은 완제품 조건](../../docs/sogangi-release.md)을 참고한다.

## 열기

저장소 루트에서 기존 가상환경과 로컬 `conf.yaml`을 준비한 뒤 실행한다. 키는 이 문서나 캐릭터 프리셋에 넣지 않는다.

```powershell
powershell -ExecutionPolicy Bypass -File .\restart-local.ps1 -OpenBrowser
```

- 화면: <http://localhost:12393/web-tool/sogangi/>
- 실제 Live2D 대화: <http://localhost:12393/web-tool/sogangi/?avatar=live2d> (설정에서 선택·저장 가능, 눈·입·기울기·호흡 연동)
- 고개·호흡 수동 검수: <http://localhost:12393/web-tool/sogangi/live2d-preview.html?model=sogangi-motion>
- 팔 인사 수동 검수: <http://localhost:12393/web-tool/sogangi/live2d-preview.html?model=sogangi-greeting>
- 현재 표정 모델 검수: <http://localhost:12393/web-tool/sogangi/live2d-preview.html?model=sogangi-expressions> (수동 슬라이더 또는 표정 파일 재생)
- 일반 주소도 저장된 선택이 없으면 Live2D로 열린다. 명시적 URL 선택도 저장하므로 이전 SVG 설정을 위 링크로 전환할 수 있다. 로드 실패 시 SVG로 자동 복구한다.
- 레이어·움직임 설계와 파츠 다운로드: <http://localhost:12393/web-tool/sogangi/live2d-plan.html>
- Cubism 가져오기 준비: 위 설계 화면에서 9개 그룹·24개 파츠의 여백 정리 PSD와 눈/입 연결표를 받을 수 있다. 실제 Editor 가져오기를 확인했으며 [재현·검수 안내](../../docs/sogangi-rigging-integration.md)를 따른다.
- 기존 Live2D 화면: <http://localhost:12393/>
- 실제 Cubism 모델 검수실: <http://localhost:12393/web-tool/sogangi/live2d-preview.html> (Mao 기준 모델, 대화 API 미사용)
- 첫 실제 서강이 모델: <http://localhost:12393/web-tool/sogangi/live2d-preview.html?model=sogangi-minimum> (눈·입 3개 연결, 수동 검수실)
- PSD 피벗·원화 보완 좌표도: <http://localhost:12393/web-tool/sogangi/rigging-map.html>
- 자세별 원본·어깨 후보 비교: <http://localhost:12393/web-tool/sogangi/art-review.html> (7개 자세, 어깨/얼굴 확대, 별도 후보 PSD)

현재 로컬 포트 기준 주소다. 캐릭터 설정은 `characters/ko_sogangi.yaml`이며 서버 연결 시 이 프리셋을 선택한다. 설정에 있는 `mao_pro`는 기존 서버가 요구하는 fallback 모델이다. 이 화면은 별도 어댑터로 SVG 또는 실제 최소 MOC3를 표시한다. backend fallback/model_dict 등록은 변경하지 않았다.

## 화면과 움직임

- `index.html`, `../platform/runtime/css/style.css`, `../platform/runtime/css/lounge.css`, `../platform/runtime/css/history.css`: 화면과 반응형 구성.
- `assets/campus-lounge.svg`: 가상의 캠퍼스 라운지. 공식 캐릭터와 어울리는 단순한 벡터 배경으로 교체했다.
- `../platform/runtime/js/avatars/mascot-renderer.js`: 공식 파츠를 이용한 눈 깜빡임, 음성 크기 기반 입 움직임, 고개 기울기, 작은 시선 이동과 인사 동작. 눈·입의 작은 입력에서는 원화 모양을 연속 전환한다.
- `../platform/runtime/js/avatars/sogangi-renderer.js`: SVG/실제 Cubism 전환과 수명 관리. Live2D는 실제 Core의 눈·입 값을 구동하며 실패 시 SVG로 복귀한다. 재생 중 전환·지연 로드·컨텍스트 복구가 음성을 다시 재생하지 않는다.
- `../platform/runtime/js/expressions.js`: 문장의 완전한 감정 태그에서 중립·기쁨·화남·놀람을 선택한다. SVG에서는 중립/기쁨으로 제한한다. 실제 재생 문장과 표정을 맞추고, 미지원 표정은 중립으로 대체한다. 상세 구현·검수 범위는 [리깅 연결 안내](../../docs/sogangi-rigging-integration.md)를 참고한다.
- `../platform/runtime/js/app.js`: 설정 선택·대화·음성 큐·중단·음소거·기록 복원·녹음과 전사.
- 손 흔들기 버튼은 SVG/Live2D에서 로컬 동작만 재생하며 대화 API를 호출하지 않는다. Live2D 인사는 1.6초 후 복귀하고 재생 중 중복 클릭을 쌓지 않는다. 중단·새 대화·모드 전환과 앱/OS 동작 줄이기는 인사를 취소하며 다시 켜도 이전 동작을 재생하지 않는다. 음성에 필요한 입 움직임은 유지한다.
- 설정에서 음량·재생 속도·배경·큰 글씨·음소거·움직임을 바꾸고 저장할 수 있다. 대화 초안과 마지막 기록은 같은 탭에서 새로고침 후 이어진다. 재연결은 최대 5회 자동 시도하며 질문을 자동으로 재전송하지 않는다.
- 기록 목록의 검색은 최근 메시지 내용 기준이다. 현재 대화는 한글 텍스트 파일로 내려받을 수 있다. `../platform/runtime/js/local-state.js`는 설정과 탭 상태 저장, `../platform/runtime/css/product.css`는 추가 화면 스타일을 담당한다.

데스크톱에서는 캐릭터 무대와 대화를 나란히, 모바일에서는 작은 무대와 대화를 위아래로 표시한다. 모바일 메시지만 내부 스크롤하고 입력창은 첫 화면 안에 둔다. 아주 낮은 화면이나 키보드·확대 설정은 기기에서 추가 확인이 필요하다.

## 검증

서버를 실행한 상태에서 [브라우저 검사 안내](../../tests/browser/README.md)를 따른다. 일반 브라우저 검사와 화면 캡처는 대화 WebSocket만 fixture로 바꾸며 LLM API를 호출하지 않는다.

```powershell
$env:PYTHONUTF8='1'
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_smoke.py
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_product.py
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_art_review.py
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_visual.py
# 선택: 실제 LLM 요청 한 번과 TTS/브라우저 재생 검사. API 할당량을 사용한다.
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_live.py --live
# 선택: 실제 대화 두 번으로 새로고침 후 취향 기억까지 검사
.\tmp\browser-tools\Scripts\python.exe tests/browser/sogangi_live.py --live --memory
```

검사 결과와 캡처는 Git 제외 폴더 `tmp/sogangi-browser/redesign/`에 저장한다. API 지연은 서비스 상태와 요청에 따라 달라지므로 단일 측정을 성능 보장으로 해석하지 않는다.

## 남은 제작 범위

보이는 파츠의 [제작 준비 PSD/PNG](../../docs/sogangi-art-handoff.md), [눈·입 기준 모델](../../live2d-models/sogangi-minimum/README.md), [고개·호흡 기준 모델](../../live2d-models/sogangi-motion/README.md)과 [인사 모델](../../live2d-models/sogangi-greeting/README.md)을 만들고 실제 Cubism 음성·문장 표정·중단을 연결했다. 디포머 계층과 입체 회전, 팔꿈치/손가락 분할과 확장 표정/모션 파일은 남아 있다. 세션 Agent 기억은 분리했지만 디스크 기록은 같은 캐릭터 폴더에서 공유하며 로그인·사용자 권한 분리는 아직 없다. 실제 마이크 하드웨어와 스피커 청취는 사용자 기기에서 확인한다.

출처는 [assets/README.md](assets/README.md), 제작 순서와 검수 조건은 [Live2D 제작 설계](../../docs/sogangi-live2d-plan.md)를 참고한다.
