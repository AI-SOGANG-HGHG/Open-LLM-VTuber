# Windows에서 Gemini API로 첫 실행

Ollama 설치 없이 Gemini API로 대화를 생성한다. 음성 인식은 기본 SenseVoice를 CPU에서 실행하고, 음성 출력은 한국어 Edge TTS를 사용한다. 이 PC의 실제 준비 상태와 관찰한 결과는 [첫 실행 기록](local-first-run.md)을 참고한다. 다른 PC의 설치·실행 성공까지 보장하는 기록은 아니다.

## 1. 실행 도구와 의존성

PowerShell에서 uv와 FFmpeg를 설치한 뒤 터미널을 새로 연다.

```powershell
winget install --id astral-sh.uv -e
winget install --id Gyan.FFmpeg -e
```

저장소 루트에서 실행한다. `.python-version`에 맞춰 Python 3.10을 준비하고, `uv.lock` 기준으로 `.venv`에 의존성을 설치한다. 별도의 가상환경 활성화는 필요하지 않다.

```powershell
uv --version
ffmpeg -version
uv python install 3.10
uv sync --locked
```

프론트엔드 서브모듈이 없다면 `git submodule update --init --recursive`를 실행한다. 현재 프론트엔드는 빌드된 파일이므로 브라우저 실행을 위해 Node.js를 설치할 필요는 없다.

## 2. 로컬 설정과 API 키

[Google AI Studio](https://aistudio.google.com/apikey)에서 API 키를 발급한다. 무료 등급을 사용하려면 프로젝트의 등급과 모델별 할당량을 확인한다. 예시 모델은 `gemini-3.5-flash-lite`이며, 가용성과 무료 제공 조건은 [공식 요금표](https://ai.google.dev/gemini-api/docs/pricing)와 [사용량 제한](https://ai.google.dev/gemini-api/docs/rate-limits)을 확인한다.

처음 설정할 때 공유용 예시를 복사한다. 아래 명령은 기존 `conf.yaml`을 덮어쓰지 않는다. 이미 설정이 있으면 필요한 항목만 비교해 수정한다.

```powershell
if (-not (Test-Path -LiteralPath conf.yaml)) {
    Copy-Item -LiteralPath config_templates/conf.gemini.example.yaml -Destination conf.yaml
}
```

예시에는 다음 값이 설정돼 있다.

| 위치 | 값 |
|---|---|
| `character_config.agent_config.agent_settings.basic_memory_agent.llm_provider` | `gemini_llm` |
| 같은 블록의 `use_mcpp` | `false` |
| `character_config.agent_config.llm_configs.gemini_llm.llm_api_key` | `${GEMINI_API_KEY}` |
| 같은 블록의 `model` | `gemini-3.5-flash-lite` |
| 같은 블록의 `temperature` | `0.7` |
| `character_config.asr_config.asr_model` | `sherpa_onnx_asr` |
| `character_config.asr_config.sherpa_onnx_asr.provider` | `cpu` |
| `character_config.tts_config.tts_model` | `edge_tts` |
| `character_config.tts_config.edge_tts.voice` | `ko-KR-SunHiNeural` |

서버를 실행할 PowerShell 창에서 키를 입력한다. 입력한 키가 화면이나 명령 기록에 직접 남지 않도록 프롬프트로 받는다. 환경 변수는 현재 터미널과 여기서 시작한 프로세스에만 적용된다.

```powershell
$geminiKey = Read-Host 'Gemini API key' -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $geminiKey).Password
Remove-Variable geminiKey
```

기존 설정 로더가 `${GEMINI_API_KEY}`를 환경 변수 값으로 치환한다. 서버 실행 시 이 변수가 반드시 설정돼 있어야 한다. `.env` 파일은 자동으로 읽지 않는다. `conf.yaml`은 Git 제외 대상으로 유지하고 실제 키를 공유용 템플릿·문서·커밋에 넣지 않는다.

## 3. 서버와 브라우저

같은 PowerShell 창의 저장소 루트에서 실행한다.

```powershell
uv run --locked run_server.py
```

이 PC에는 Python과 FFmpeg를 프로젝트 안에 준비했다. 여기서는 `start-local.ps1`이 `.venv`의 Python과 `tmp/tools/ffmpeg/bin`을 사용한다. 전역 PATH 변경이나 가상환경 활성화 없이 다음 명령으로 실행할 수 있다.

```powershell
powershell -ExecutionPolicy Bypass -File .\start-local.ps1
```

이 명령으로 실행한 서버는 해당 터미널에서 `Ctrl+C`로 종료한다. 최초 점검을 위해 백그라운드에서 켠 서버는 `stop-local.ps1`로 종료한 후 위 명령을 사용한다.

처음에는 음성 인식 모델을 자동 다운로드하므로 초기화가 오래 걸릴 수 있다. 서버 초기화가 끝나면 브라우저에서 <http://localhost:12393>에 접속한다. 종료는 `Ctrl+C`다. Edge TTS와 Gemini API를 사용하므로 실행 중 인터넷 연결이 필요하다.

캐릭터 표시 → 한국어 텍스트 대화 → 음성 출력 → 마이크 입력 → 대화 중단 순으로 확인하고 [첫 실행 체크리스트](first-run-checklist.md)에 실제 결과를 기록한다. `429` 오류는 AI Studio의 요청·토큰·일일 한도를 확인한다. 무료 Gemini API의 대화 내용은 제품 개선에 사용될 수 있으므로 테스트용 내용을 사용한다.

## 4. 로컬 작업 브랜치

공유 설정이 `main`에 반영된 뒤 로컬 작업은 별도 브랜치에서 진행한다. 아래 이름은 예시이며 목적에 맞게 정한다.

```powershell
git switch main
git pull --ff-only
git switch -c work/local-experiments
```

공식 참고: [프로젝트 설치 안내](https://docs.llmvtuber.com/en/docs/quick-start/), [Gemini OpenAI 호환 API](https://ai.google.dev/gemini-api/docs/openai).
