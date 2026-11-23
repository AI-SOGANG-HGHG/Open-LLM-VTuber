# 강이서 눈·입 리깅 초안

작업명은 Ivory Crown이었다. [정면 원화](../ivory-crown-front-base.png)를 기준으로 만든 상반신 움직임 시안이다.

## 움직임 확인

[index.html](index.html)을 브라우저에서 연다. 자동 깜빡임, 한 번 깜빡이기, 좌우 눈과 입 수동 조작을 확인할 수 있다. WAV나 MP3 파일을 선택하고 재생하면 브라우저가 음량에 맞춰 입을 움직인다. 오디오는 브라우저에서 읽는다. 중립으로 복귀하면 오디오와 자동 깜빡임을 멈추고 기본 자세를 표시한다.

Chromium에서 수동 조작의 눈·입 픽셀 변화와 중립 복귀, 자동 깜빡임, 합성 WAV의 재생·음소거·일시정지·종료, 모바일 너비를 확인했다. Canvas에서 눈은 속눈썹을 기준으로 열린 눈 폭을 세로로 좁힌 뒤 감은 눈으로 전환하고, 입은 음량에 따라 벌림 모양을 확대한다.

## Cubism용 PSD

[ivory-crown-facial-draft.psd](ivory-crown-facial-draft.psd)는 1024×1536 RGB 8비트 투명 캔버스에 픽셀 레이어 7개를 담는다. 화면 왼쪽을 L, 오른쪽을 R로 표기했다. 기본 상태에서는 열린 눈과 닫힌 입이 보인다. 내보낸 PSD를 다시 읽어 레이어 그룹, 좌표, 가시성, 픽셀, 배경 투명도를 확인했다.

| 매개변수 후보 | PSD 레이어 | 첫 키폼 |
| --- | --- | --- |
| `ParamEyeLOpen` | `Eye L/EyeL_Open`, `Eye L/EyeL_Closed` | 0 감음, 1 뜸 |
| `ParamEyeROpen` | `Eye R/EyeR_Open`, `Eye R/EyeR_Closed` | 0 감음, 1 뜸 |
| `ParamMouthOpenY` | `Mouth/Mouth_Closed`, `Mouth/Mouth_Open` | 0 닫힘, 0.25 약간 벌림, 1 벌림 |

`Base_HeadBody`에는 눈과 입을 가리는 피부색 보완을 넣었다. 눈·입 패치에도 가장자리 피부가 포함돼 있어 Cubism에서 패치의 불투명도를 바꿔 초기 키폼을 시험할 수 있다. 벌린 입을 변형하기 전에는 입술·입 안쪽·치아와 주변 피부를 더 세밀하게 분리하고, 눈의 중간 감김 모양과 앞머리가 겹치는 경계를 보완한다. 머리와 몸통은 한 레이어여서 고개 회전이나 머리카락 물리는 별도 원화 작업이 필요하다.

## Persona Studio 연결

저장된 아바타 키는 `ivory-crown`이다. 대화실에서 `/live2d-models/kang-iseo/runtime/kang-iseo.model3.json`을 먼저 확인한다. 모델이나 필수 표정 파일을 읽을 수 없거나 WebGL 컨텍스트가 사라지면 기존 Canvas로 돌아간다. Canvas 초기화까지 실패하면 같은 정면 이미지를 표시한다. **Live2D 다시 불러오기**는 해당 모델을 다시 확인한다. 렌더러를 바꿀 때 현재 표정과 음성의 입 벌림 값을 넘긴다.

`main`의 턴 단위 동작을 따라 Studio는 첫 응답에서 서버가 보낸 표정을 정하고 그 턴 동안 유지한다. 강이서가 지원하는 표정은 중립·기쁨·놀람이다. 지원 범위 밖 표정은 중립으로 표시한다. Canvas에서는 두 눈의 기본 열림을 각각 1.00, 0.72, 1.10으로 바꾸고 깜빡임을 곱한다. 입 벌림은 오디오 큐가 계속 제어한다. 움직임 줄이기와 OS 동작 감소 설정은 깜빡임·기울기·호흡을 멈추고 표정과 립싱크를 유지한다.

## Cubism 제작 인계

정면 원화와 Studio WebP는 각각 1024×1536이다. PSD를 다시 읽어 아래 픽셀 레이어 7개, 기본 가시성, 좌표, 모서리 알파 0을 확인했다. 좌표는 캔버스 좌상단을 기준으로 한다.

| PSD 파츠와 영역 | Cubism에 연결할 파라미터 | 키폼과 레이어 보완 |
| --- | --- | --- |
| `EyeL_Open` / `EyeL_Closed` · (384, 433)–(497, 502) | `ParamEyeLOpen` · 0–1 | 감은 눈과 뜬 눈 사이에 중간 감김을 추가한다. 눈꺼풀·홍채·하이라이트를 분리하고 앞머리 아래를 채운다. |
| `EyeR_Open` / `EyeR_Closed` · (540, 433)–(653, 502) | `ParamEyeROpen` · 0–1 | 반대쪽과 독립적으로 움직이게 한다. 두 눈을 `EyeBlink` 그룹에 넣는다. |
| `Mouth_Closed` / `Mouth_Open` · (474, 550)–(561, 590) | `ParamMouthOpenY` · 0–1 | 닫힘 0, 약간 벌림 0.25, 벌림 1. 입술·구강·치아를 분리하고 `LipSync` 그룹에 넣는다. |
| 두 눈 주변과 추가 눈썹 파츠 | `ParamFaceMood` · 0, 1, 2 | 중립·기쁨·놀람 키폼을 각각 연결한다. `neutral`, `joy`, `surprise` 이름으로 `.exp3.json`을 등록하고 눈·입 벌림 파라미터는 표정 파일에서 제외한다. |
| `Base_HeadBody` · (0, 0)–(1024, 1536) | `ParamAngleZ` · 약 −3°~3°, `ParamBreath` · 0–1 | 오늘의 Canvas 구현은 한 장의 초상을 ±2.5° 기울이고 최대 약 1% 확대한다. Cubism에서 고개만 기울이려면 머리·목·몸통, 앞/뒷머리와 후드의 가림 영역을 분리한다. 호흡은 상체에 작은 변형으로 연결한다. |

PSD의 피부 패치와 바깥쪽 알파 경계는 에디터에서 밝고 어두운 배경에 각각 합성해 점검한다. 모서리 쪽에 남은 작은 픽셀과 머리카락·후드 가장자리를 정리한 뒤 텍스처를 만든다. `ParamFaceMood` 키폼은 눈 감김과 입 벌림의 조합에서도 각각의 변형을 유지하게 만든다.

Windows 로컬과 Ubuntu 작업 서버에서 Cubism Editor 실행 환경을 찾지 못해 강이서의 `.cmo3`, `.moc3`, 텍스처와 표정 파일을 내보내지 못했다. 내보낸 뒤에는 `live2d-models/kang-iseo/runtime/`에 모델 묶음을 두고 `python tools/check_live2d_bundle.py live2d-models/kang-iseo/runtime/kang-iseo.model3.json`을 실행한다. [Live2D 검수실](../../../../../web_tool/sogangi/live2d-preview.html)에 같은 경로를 입력해 실제 Core에서 눈·입 슬라이더와 세 표정을 조작한다. [서강이 표정 모델](../../../../../live2d-models/sogangi-expressions/README.md)의 모델·표정 파일 구성을 참고한다.

## Chromium에서 확인한 동작

- 강이서 원화 기반 Canvas에서 자동 깜빡임과 눈 뜸 복귀, 포인터 기울기와 호흡, 움직임 줄이기 적용을 확인했다.
- 대화실에서 테스트 WAV를 재생하며 `joy` 표정과 열린 입 픽셀을 확인했다. 같은 턴의 표현 태그와 중복 표정 이벤트는 초기 표정을 바꾸지 않았다. 중단하면 입 부분 픽셀이 중립과 일치했다. 다음 턴은 음소거 상태에서 `surprise`를 적용했고 입은 닫혀 있었다.
- 강이서 모델 응답을 404로 두어 Canvas로 내려가는지 확인했다. Canvas 스크립트까지 차단하면 정적 이미지가 표시됐고, 차단 해제 후 재시도하면 Canvas가 다시 활성화됐다. 기본 프로필과 추가한 캐릭터에서 저장된 `ivory-crown` 키를 확인했다.
- 서강이의 기존 `.moc3`와 표정 파일을 강이서 로더 경로에 테스트 응답으로 제공했다. 실제 Cubism Core에서 눈·입 파라미터와 놀람 표정 동시 적용을 확인했다. WebGL 컨텍스트 손실 이벤트를 발생시키면 현재 표정과 열린 입 값을 Canvas가 이어 받았고 이후 입 닫기 값이 적용됐다. 강이서 자체 MOC의 변형 검수는 내보내기 뒤에 진행한다.

[브라우저 회귀 테스트](../../../../../tests/browser/ivory_crown.py)는 스튜디오의 HTTP 등록 경로, 테스트 WebSocket 메시지, 브라우저 오디오 재생을 사용한다.

PSD를 다시 만들 때는 Python의 `playwright`, `psd-tools==1.26.0`과 Chromium이 필요한 [export_psd.py](export_psd.py)를 실행한다. 기존 PSD가 있으면 `--output`으로 새 경로를 지정한다.
