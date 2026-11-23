# 서강이 원화·리깅 연결과 실제 모델 검수

2026-11-03 후속. 앞선 기준 모델을 보존하고 [표정 모델](../live2d-models/sogangi-expressions/README.md)을 기본 대화 화면에 연결했다. 실제 Core에서 눈·입·작은 기울기·호흡·팔·표정 7개 키폼의 조합과 정확한 중립 복귀, 대화 오디오/중단을 확인했다. ArtMesh의 합성 변형이며 디포머 계층·입체 회전·팔꿈치/손가락 분할과 확장 표정/모션은 후속 단계다. 아래 최소 모델 기록은 확장 전의 기준 검수다.

현재 모델: <http://localhost:12393/web-tool/sogangi/live2d-preview.html?model=sogangi-minimum>. 눈·입 슬라이더와 입 왕복 시험을 사용할 수 있다. 27개 표준 파라미터 중 연결한 것은 눈 2개·입 1개다. 미연결 기울기는 조작을 비활성화했다. 파일과 정확한 검증 범위는 `live2d-models/sogangi-minimum/`에 있다.

대화 연결: <http://localhost:12393/web-tool/sogangi/?avatar=live2d>, 또는 설정에서 Live2D를 선택한다. `web_tool/platform/runtime/js/avatars/sogangi-renderer.js`가 실제 Core의 눈/입에 깜빡임·짧은 기쁨 반응·오디오 크기를 적용한다. 음소거·중단·새 대화는 입을 닫고, 늦은 로드가 끝난 발화를 다시 재생하지 않는다. 모드 전환은 현재 오디오 시계와 요청 ID를 유지하며 실패/컨텍스트 상실은 SVG로 복구한다. 8개 실제 Core 브라우저 회귀와 실제 Gemini/TTS 요청 한 번을 확인했다. 기존 backend fallback은 유지한다.

## 원화 좌표도

<http://localhost:12393/web-tool/sogangi/rigging-map.html>

- 실제 준비 PSD와 같은 2048×2048 좌표를 사용한다. 24개 레이어의 경계는 각 PNG의 알파 영역을 측정했다.
- 피벗/계층 9개, 보완 검토 영역 6개, 파라미터 연결 10개를 선택해 볼 수 있다.
- 계층은 발 기준 Root → 상체 호흡/기울기 → 머리·팔 → 눈·입이다. 계층의 영향 범위는 중첩될 수 있다.
- 피벗과 보완 영역은 제작자 검토용 제안이다. 원화를 이어 그리거나 실제 디포머를 배치한 결과로 해석하지 않는다.
- 준비 PSD SHA-256, 파츠 ID, 좌표와 파라미터 범위를 검사한다. PSD를 새로 내보내면 좌표도도 재생성한다.

```powershell
.\tmp\art-tools\Scripts\python.exe tools/prepare_sogangi_rigging.py
```

`web_tool/sogangi/workshop/rigging-map/rigging-map.json`에서 좌상단이 (0,0)이고 L/R은 화면 기준이다. 현재 SVG 인사와 맞춰 커스텀 인사 파라미터는 **ParamArmRWave**로 정리했다. 기존 초안의 ParamArmLWave 이름을 그대로 혼용하지 않는다. 실제 모델에서 캐릭터 기준 좌우로 바꾸려면 PSD·명세·동작 파일의 대응표도 함께 변경한다.

## 실제 Cubism 모델 검수실

11월 3일 추가한 [원화 동작 비교](http://localhost:12393/web-tool/sogangi/art-review.html)는 기존 파츠와 어깨 캡 후보를 7개 자세에서 비교한다. 첫 범위의 고정 회전에서는 후보 추가로 보이는 결과가 달라지지 않아, 실제 리깅의 시작 자료는 기존 24개 레이어 PSD로 유지한다. 26개 후보 PSD는 검토 실험 자료다. 각 레이어 픽셀은 보존했고 정면 PSD 합성의 작은 오차도 [인계 기록](sogangi-art-handoff.md)에 남겼다. 실제 메시 변형의 가림은 별도로 검사한다.

<http://localhost:12393/web-tool/sogangi/live2d-preview.html>

기존 Mao를 기준으로 실제 MOC3·텍스처를 불러와 WebGL 표시와 눈·입·기울기 파라미터를 검사했다. 기존 프론트엔드의 Cubism Core를 사용하며 대화 설정·API 키·메모리를 변경하지 않는다. LLM/TTS나 대화 WebSocket을 호출하지 않는다.

검수실에서 가능한 것:

1. `/live2d-models/` 아래 model3.json을 입력해 표시한다. 모델 폴더 밖이나 외부 서버를 참조하는 파일은 거부한다.
2. 실제 Core에 있는 파라미터의 최소/기본/최대값으로 슬라이더를 만든다. 입은 model3의 LipSync 그룹을 먼저 사용한다. Mao의 ParamA를 서강이의 표준 ParamMouthOpenY로 가정하지 않는다.
3. 실제 눈·입·기울기를 조작하고 입 왕복 검사를 실행한다. 수동값 우선 적용을 끄면 표정/모션 자체의 변화를 볼 수 있다.
4. 내보낸 표정, 모션 그룹과 파일을 선택해 검사한다. 모션 반복은 원본 파일 설정을 따르며, 연결된 소리는 검사 화면에서 재생하지 않는다.
5. 같은 모델을 다시 읽을 때 참조 파일에 검사 세대별 URL을 부여한다. 이전 모델의 텍스처 해제나 브라우저 캐시가 새 내보내기와 충돌하지 않게 한다. 불러오기 실패 시 기존 모델을 유지한다.

검수실은 편집기나 업로더가 아니다. 모델 파일은 서버의 `live2d-models/`에 먼저 배치한다. 이 검사에 성공해도 최신 Cubism Editor의 모든 내보내기와 호환된다는 보장은 없다. 실제 서강이 모델은 같은 Core에서 다시 검사해야 한다.

## 파일 검사와 등록 순서

```powershell
# 기존 기준 모델: 참조와 등록 인덱스를 확인
.\.venv\Scripts\python.exe tools/check_live2d_bundle.py live2d-models/mao_pro/runtime/mao_pro.model3.json --model-dict model_dict.json --name mao_pro
# 현재 눈·입 최소 모델. 전체 표정 규격은 아직 적용하지 않았다.
.\.venv\Scripts\python.exe tools/check_live2d_bundle.py live2d-models/sogangi-minimum/runtime/sogangi.model3.json
# 향후 전체 모델이 준비된 뒤 실행. 아래 전체 모델 경로는 아직 없다.
.\.venv\Scripts\python.exe tools/check_live2d_bundle.py live2d-models/sogangi/runtime/sogangi.model3.json --sogangi
```

정적 검사는 경로·누락 파일·파일 시그니처·표정 순서·그룹/인덱스를 확인한다. MOC 내부나 렌더 품질을 해석하지 않는다. `--sogangi`는 전체 설계의 5개 표정 순서(neutral/joy/sadness/surprise/anger)와 눈·입·Idle 그룹을 요구한다. 최소 리깅을 시험하는 단계는 일반 파일 검사와 검수실로 먼저 확인한다.

기존 기본 프론트엔드까지 서강이로 바꾸려면 실제 모델의 제작 검수를 마친 뒤 `model_dict.json`에 등록하고 캐릭터 설정의 fallback `mao_pro`를 바꾼다. 별도 서강이 대화 화면은 이미 직접 Cubism을 탑재하므로 이 등록을 요구하지 않는다. 파일 검사 통과나 Mao 표시를 서강이 모델 제작 완료로 기록하지 않는다.

## 현재 대화 표정 연결

문장에 포함된 완전한 태그의 의미를 사용하고 fallback Mao의 숫자 인덱스와 분리했다. 현재 Native 모델은 중립·기쁨·화남·놀람을 지원하며 나머지는 중립으로 대체한다. SVG는 중립/기쁨으로 제한한다. 한 문장에 여러 태그가 있으면 마지막 완전한 태그를 사용한다. 표정 가시성과 깜빡임/입 벌림을 곱해 음소거 중 입을 닫고 표정과 립싱크를 독립적으로 유지한다.

음성이 켜져 있으면 실제 재생하는 문장의 표정을 적용한다. 다음 문장이 먼저 도착해도 재생 중인 표정을 덮지 않는다. 음소거 중에는 글에 맞춰 표정을 적용하고 입은 닫는다. 중단·새 대화·연결 끊김에서는 중립으로 복귀하며 이전 요청의 오디오/태그를 재적용하지 않는다. 기쁨은 기존 감은 눈 후보를 짧게 사용하며 동작 줄이기 설정에서는 부차 동작을 생략한다.

렌더링 라이브러리는 버전을 고정해 로컬에 보관했고 무결성과 고지를 기록했다. [의존성 출처](../web_tool/shared/vendor/README.md)를 참고한다. SVG 모드만 사용하면 이 의존성을 읽지 않으며 Live2D 선택 시 지연 로드한다.

## 자동 변환 도구의 소스 검토

2026-11-03에 공개 [autoLive2d](https://github.com/KonshinHaoshin/autoLive2d)의 `4fcdf472d21488c8e8258fd05a601b2822855705`를 저장소 밖의 로컬 `reference-sources/autoLive2d`에 참고용으로 받았다. 도구 소스는 MIT이며, [README](https://github.com/KonshinHaoshin/autoLive2d/blob/4fcdf472d21488c8e8258fd05a601b2822855705/README.md)와 Java bridge의 PSD 가져오기·텍스처·MOC 출력 호출을 읽었다. 아래는 이후 실제로 실행한 범위다.

도구는 설치된 Cubism Editor 5.1의 JAR/DLL과 JDK 17 이상에 의존한다. Java/Javac 23과 Node 24.22.1을 확인했다. pnpm 10.12.4를 프로젝트 임시 폴더에 두고 배포 무결성을 확인한 뒤, 참고 도구의 lockfile 그대로 설치 스크립트를 끄고 의존성을 준비했다. TypeScript 타입 검사는 통과했다. 제공 테스트 6개 중 3개는 통과했고, 나머지는 저장소에 없는 `dataset/anon.psd` 관련 두 실패와 MCP 변환 오류 한 실패였다. 전체 변환 도구가 검증됐다고 표현하지 않는다.

우리 PSD는 도구의 실제 TypeScript/ag-psd 판독기로 별도 확인했다. 기본 PSD는 24개 파츠의 픽셀을 보존해 읽었지만 자동 파라미터를 하나도 만들지 못했다. 아래의 그룹·여백 정리본은 9개 그룹·24개 파츠의 픽셀과 좌표를 정확히 읽었다. 이 경우에도 자동 추론 결과는 AngleX/BodyAngleX뿐이었고 눈·입을 건너뛰었다. 따라서 자동 추론을 적용하지 않고 눈·입 3개의 명시적 연결표를 준비했다. 숨김 여부는 도구의 중간 표현에서 생략되므로 원본 manifest와 Editor에서 별도 확인한다.

이후 설치된 Editor의 라이브러리를 프로젝트 `tmp/cubism-bridge`에 캐시해 실제 MOC 내보내기를 실행했다. Native 일관성 검사와 24개 Drawable·27개 표준 파라미터를 확인했고, 그중 3개만 명시적으로 연결했다. Codex MCP 등록은 하지 않았다. 공식 Editor 내부 클래스에 의존하므로 다른 버전에서 바로 동작한다고 가정하지 않는다. 도구의 MIT가 Editor·Core·학교 원화의 사용 조건을 대신하지 않는다.

원래 아틀라스 배치에서 파츠 사이 여백이 없어 실제 웹 렌더에 가는 선이 나타났다. 공개 도구의 배치 함수를 2048 한 장·여유 4픽셀로 수정해 재출력하니 선이 사라졌다. 패치와 출처는 [재현 안내](../tools/patches/README.md), 실행 도구는 `tools/build_sogangi_minimum.mjs`다. Editor 프로그램이나 인증 파일은 수정하지 않았다. Windows 한글 경로가 Java 출력에서 깨지는 문제도 subprocess UTF-8 설정과 참조 경로 검증으로 보완했다.

눈은 열린/감은 공식 후보의 불투명도를 교차하고, 입은 불투명도와 크기를 조절하는 키폼이다. 기본 PSD-import ArtMesh를 사용하며 아직 고개/몸 디포머가 없다. 후속 확장 모델은 원본 폼을 보존해 눈·입·작은 정면 고개 기울기·호흡을 한 다차원 키폼 격자로 조합했다. 별도로 GUI 자동 메시 생성도 확인하고 로컬 참고 cmo3를 보존했지만, 그 메시를 현재 자동 빌드의 입력으로 쓰지는 않는다. 다음 작업은 메시/디포머 품질 개선과 입체 회전·팔 인사·확장 표정이다.

## 공식 Editor 설치와 첫 가져오기

[공식 다운로드 페이지](https://www.live2d.com/en/cubism/download/editor/)와 그 배포 스크립트에서 제공하는 5.1.03 Windows 설치 파일을 `tmp/cubism-setup/`에 받았다. 크기 242,640,032바이트, SHA-256 `65dc89790e81366ba6dac13960bacea45dc9f5bd27cebb6a367e210fff799da8`, 서명은 `Live2D Inc.`의 Valid였다. 첫 UAC 확인은 취소됐지만, 설치창을 보이게 다시 실행한 뒤 설치·실행을 완료했다. GUI에 평가판 42일 모드가 표시됐다. 실제 PSD를 가져오고, 기본/자동 메시 cmo3 저장과 최종 최소 cmo3 재열기를 확인했다. GUI 안에서 모든 키폼을 직접 편집한 검수와 FREE 모드 내보내기는 별도 미검증이다.

다음 명령은 먼저 해시/서명을 확인하고 공식 설치창을 연다. Windows 관리자 권한 확인과 설치 마법사는 사용자가 직접 처리한다. 확인이 취소되면 설치를 반복하지 않고 상태를 기록한다. 유료 라이선스를 구매하거나 라이선스키를 입력하지 않는다.

아래는 첫 설치를 재현하는 순서다. 현재 로컬 설치는 이미 완료돼 다시 설치할 필요가 없다. 준비 PSD/독립 판독기의 `editor_import_verified: false`는 해당 생성/판독 도구가 수행한 검사 범위를 뜻한다. 현재 실제 모델의 Editor/웹 검수는 `live2d-models/sogangi-minimum/verification.json`에 파일 해시와 함께 기록했다.

```powershell
# 파일/설치 여부만 확인: 설치나 관리자 권한 요청 없음
powershell -ExecutionPolicy Bypass -File tools/setup_cubism_editor.ps1
# 사용자가 설치창을 처리할 수 있을 때 실행
powershell -ExecutionPolicy Bypass -File tools/setup_cubism_editor.ps1 -Install -OpenEditor
```

1. Editor에서 `web_tool/sogangi/assets/cubism-import/sogangi-cubism-import.psd`를 연다. 2048 캔버스, 그룹 9개·파츠 24개, 기본 숨김 후보 3개와 정면 합성을 확인한다. 그룹 이름 L/R은 화면 기준이다.
2. 숨긴 눈/입도 편집 가능한 ArtMesh로 들어왔는지 확인한다. 모든 ArtMesh를 선택해 필요 시 공식 자동 메시 생성(Ctrl+Shift+A)을 사용하고, 먼저 중립 cmo3를 저장한다. [공식 메시 생성 안내](https://docs.live2d.com/en/cubism-editor-manual/mesh-edit/)를 따른다.
3. `keyform-plan.json`의 눈 2개·입 1개를 연결한다. 스케일 피벗은 PSD 좌상단 픽셀 좌표이므로 Editor의 좌표/디포머에 맞춰 확인한다. 기본값 복귀 시 숨김·실루엣이 유지돼야 한다.
4. 첫 텍스처는 2048×2048 한 장으로 계획했다. `atlas-layout-proposal.json`은 겹치지 않는 배치 검토안이며, 실제 텍스처/UV 파일이 아니다. 반드시 Editor에서 텍스처 아틀라스를 만들고 대응하는 MOC와 함께 내보낸다. [공식 FREE/PRO 비교](https://www.live2d.com/en/cubism/comparison/)의 현재 FREE 제한(텍스처 한 장·최대 2048, ArtMesh 100, 파라미터 30, 폴더 30)을 참고했으며 실제 5.1의 저장/내보내기는 별도 검증한다.
5. 현재 Core가 읽을 수 있는 버전으로 내보내 정적 파일 검사와 실제 검수실의 표시·눈·입 검사를 수행한다. 이 확인 전에는 main 앱 fallback이나 모델 등록을 변경하지 않는다.
