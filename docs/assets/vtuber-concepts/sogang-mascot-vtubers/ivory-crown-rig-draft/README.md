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

Persona Studio에서 기본 캐릭터 **강이서**를 열거나 다른 캐릭터에 강이서 외형을 적용하면 같은 Canvas 리깅이 실행된다. 움직임 줄이기는 깜빡임을 멈추고 대화 음성의 립싱크를 유지한다.

Cubism Editor 가져오기, `.cmo3` 저장, `.moc3` 내보내기는 후속 작업이다. 기존 [서강이 최소 모델](../../../../../live2d-models/sogangi-minimum/README.md)의 파일 구성과 검수 흐름을 참고한다.

PSD를 다시 만들 때는 Python의 `playwright`, `psd-tools==1.26.0`과 Chromium이 필요한 [export_psd.py](export_psd.py)를 실행한다. 기존 PSD가 있으면 `--output`으로 새 경로를 지정한다.
