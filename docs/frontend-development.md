# 프론트 원본 소스로 개발하기

`feat/frontend-source`는 프론트 원본과 Python 백엔드를 같은 팀 저장소에서 수정하는 개발 브랜치다. 기존 `main`은 빌드된 프론트를 서브모듈로 받는 방식이며, 이 변경은 아직 병합하지 않았다.

## 코드 위치

```text
Open-LLM-VTuber/                 # Git 저장소 하나
├─ run_server.py                 # Python 실행 진입점
├─ src/open_llm_vtuber/           # 백엔드
├─ frontend/
│  ├─ src/renderer/src/           # 웹 화면: React·TypeScript
│  ├─ src/renderer/WebSDK/        # Live2D SDK
│  ├─ src/main/                  # Electron 메인 프로세스
│  ├─ package.json
│  ├─ package-lock.json
│  ├─ UPSTREAM.md                # 가져온 원본·커밋·라이선스 위치
│  └─ dist/web/                  # npm 빌드 결과, Git 제외
└─ docs/
```

`frontend/`도 루트의 Git으로 관리한다. 프론트 전용 저장소를 별도로 만들거나 서브모듈 초기화를 할 필요가 없다. 프론트·백엔드 변경을 같은 작업 브랜치와 커밋에서 검토할 수 있다.

## 다른 PC에서 받기

새 폴더에서 다음과 같이 내려받는다.

```shell
git clone --branch feat/frontend-source https://github.com/AI-SOGANG-HGHG/Open-LLM-VTuber.git
cd Open-LLM-VTuber
```

기존 `main` 작업 폴더에는 프론트 서브모듈 파일이 남을 수 있으므로 처음에는 새 clone을 권장한다. 로컬의 미커밋 파일을 삭제하거나 덮어쓰면서 전환하지 않는다.

## 웹 개발 모드: 터미널 두 개

준비물은 Node.js·npm, Python 3.10–3.12, uv, FFmpeg와 사용할 모델/음성 설정이다. 이번 프론트 빌드에는 Node.js 22.18.0과 npm 10.9.3을 사용했다. Python 의존성과 모델 설정은 [기존 한국어 안내](../README.KR.md)를 함께 참고한다.

터미널 1은 저장소 루트에서 백엔드를 실행한다. Python 3.11을 쓰는 예시다.

```shell
uv sync --python 3.11
uv run --python 3.11 run_server.py --frontend-dev
```

`--frontend-dev`는 백엔드의 웹 UI 배포를 생략한다. WebSocket, 모델·배경·음성 파일 경로는 계속 백엔드가 제공한다. 모델 초기화와 LLM·STT·TTS 설정은 여전히 필요하다.

터미널 2는 `frontend/`에서 웹 개발 서버를 실행한다.

```shell
cd frontend
npm ci --ignore-scripts
npm run dev:web
```

브라우저에서 `http://localhost:3000`을 연다. 소스를 수정하면 Vite가 화면에 반영한다. 3000번 포트가 사용 중이면 다른 포트로 자동 변경하지 않고 오류를 낸다.

프론트 설정의 기본 연결 주소는 다음과 같다. 백엔드 포트를 바꾸거나 저장된 브라우저 설정이 다르면 UI의 연결 설정도 맞춘다.

| 항목 | 기본값 |
|---|---|
| WebSocket | `ws://127.0.0.1:12393/client-ws` |
| HTTP Base URL | `http://127.0.0.1:12393` |

`npm ci --ignore-scripts`는 웹 개발에 필요한 의존성을 설치하면서 Electron 설치 스크립트를 생략한다. Electron 데스크톱 실행·패키징은 별도 의존성 준비와 검증이 필요하며 이번 범위에는 포함하지 않았다.

## 빌드 후 백엔드 하나로 실행하기

```shell
cd frontend
npm ci --ignore-scripts
npm run build:web
cd ..
uv run --python 3.11 run_server.py
```

브라우저에서 `http://127.0.0.1:12393`을 연다. 백엔드는 `frontend/dist/web/`을 제공한다. 빌드가 없으면 필요한 명령을 안내하고 종료한다. 소스를 수정한 뒤 이 방식으로 확인할 때는 다시 빌드해야 한다.

`node_modules/`, `dist/`, `out/`은 공유하지 않는다. 다른 PC에서도 소스와 잠금 파일을 받아 의존성을 설치하고 빌드한다.

## 검증 범위와 남은 확인

- `npm run build:web`: 통과. 원본 Vite의 청크 크기·CJS API와 ONNX의 eval 경고가 남아 있다.
- `npm run typecheck:web`: 원본 소스에서 586건 실패(Live2D WebSDK 582건, 앱 미사용 선언 4건). 가져온 앱·SDK 파일의 원본 일치를 확인했다. 이번 브랜치는 검사 설정을 완화하거나 SDK를 일괄 수정하지 않는다.
- Python 빌드 경로 검사는 `python -m unittest discover -s tests -v`로 실행한다. 모델 의존성 없이 새 clone의 빌드 누락과 빌드 결과 탐지를 확인한다.
- Vite 개발 서버의 HTML·모듈·Live2D·VAD 파일 응답과 FastAPI의 빌드 배포 경로를 확인했다. FastAPI 검사는 모델 초기화·앱 대화 경로를 테스트 대역으로 분리해 수행했으며, 실제 대화 검증을 의미하지 않는다.
- 전체 저장소의 Ruff 검사는 기존 코드 오류로 실패한다. 새 빌드 경로 모듈·테스트와 수정한 서버 모듈은 Ruff 검사를 통과했다. 실행 진입점에는 기존의 포괄적 예외 처리 경고가 남아 있다.
- 실제 LLM 응답·음성 입력/출력·아바타 표시와 전체 백엔드 기동은 [첫 실행 체크리스트](first-run-checklist.md)에 따라 별도로 확인해야 한다.

게임·방송 기능은 추가하지 않았다. 다음 개발은 캐릭터 설정·Persona·대화·기억·세션의 공통 동작을 확인하는 데 집중한다.
