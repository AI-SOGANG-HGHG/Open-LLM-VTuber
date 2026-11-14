# 다른 PC에서 확인하는 순서

아래는 확인 절차다. 해당 PC에서 설치·실행 성공을 확인한 기록이 아니다. PowerShell 기준이며 Git·uv·FFmpeg를 먼저 준비한다.

## 1. 이 문서가 있는 브랜치 받기

이미 팀 저장소가 있다면 해당 저장소에서 실행한다. 로컬 변경이 있으면 먼저 보관하고 브랜치를 전환한다.

```powershell
git fetch origin
git switch work/local-experiments
git pull --ff-only origin work/local-experiments
```

처음 받는 경우 원하는 작업 폴더에서 실행한다.

```powershell
git clone --branch work/local-experiments https://github.com/AI-SOGANG-HGHG/Open-LLM-VTuber.git
cd Open-LLM-VTuber
```

`docs/week1-original-system/README.md`부터 읽는다. 이 단계는 문서를 받는 과정이므로 서강이 서버를 먼저 실행할 필요는 없다.

## 2. 원본을 별도 폴더에 준비

팀 저장소 루트에서 실행한다. 형제 폴더 `Open-LLM-VTuber-original`이 아직 없을 때 사용하는 명령이다. 이미 있다면 새로 덮어쓰지 않고 현재 커밋과 로컬 변경부터 확인한다.

```powershell
git clone --no-checkout https://github.com/Open-LLM-VTuber/Open-LLM-VTuber.git ../Open-LLM-VTuber-original
cd ../Open-LLM-VTuber-original
git checkout --detach 992309c0aa19845960228f880013d4685fde93b5
git submodule update --init --recursive
git rev-parse HEAD
git submodule status
```

기대하는 HEAD는 `992309c0aa19845960228f880013d4685fde93b5`, 프론트 서브모듈은 `06a659b114fff788cf0daaa86e484576db4975bf`다. 분석 기준을 고정한 detached HEAD이며, 원본 수정 실험을 저장할 때는 별도 브랜치를 만든다. `git submodule update --remote`는 고정된 프론트 버전을 바꿀 수 있으므로 이 확인 절차에서 사용하지 않는다.

현재 팀 브랜치에서 `start-local.ps1`을 실행하거나 원본 UI `/`만 여는 방법은 원본 백엔드 확인을 대신하지 않는다. 원본 폴더에는 팀의 실행 스크립트·Gemini 설정 예시가 없을 수 있다.

## 3. 의존성과 로컬 설정 준비

원본 폴더에서 진행한다. 원본의 Python 요구 범위는 `>=3.10,<3.13`이다. 다음은 Python 3.10으로 맞추는 절차다.

```powershell
uv --version
ffmpeg -version
uv python install 3.10
uv sync --locked --python 3.10
if (-not (Test-Path -LiteralPath conf.yaml)) {
    Copy-Item -LiteralPath config_templates/conf.default.yaml -Destination conf.yaml
}
```

`conf.yaml`에서 다음 항목을 확인·수정한다. 기존 YAML의 해당 필드를 편집하며 파일 전체를 아래 표로 대체하지 않는다.

| 위치 | 첫 확인 기준 |
|---|---|
| `system_config.host` | `localhost` |
| `system_config.port` | 기본 `12393`; 다른 서버가 쓰면 포트를 바꾸고 접속 주소도 맞춤 |
| `character_config.agent_config.conversation_agent_choice` | `basic_memory_agent` |
| `character_config.agent_config.agent_settings.basic_memory_agent.use_mcpp` | `false`로 두고 일반 대화부터 확인 |
| 같은 블록의 `llm_provider` | 사용할 공급자 설정과 일치시킴. 원본 기본은 `ollama_llm` |
| `character_config.agent_config.llm_configs`의 선택한 공급자 | 실제 사용 가능한 모델 ID, API 키 또는 서버 주소 |
| `character_config.persona_prompt` | 테스트할 언어·말투를 명시 |
| `character_config.asr_config` | 사용할 음성 인식 엔진과 장치 설정 |
| `character_config.tts_config` | 사용할 음성 합성 엔진과 음성 설정 |

템플릿의 오래된 모델 ID가 지금도 제공되는지 별도 확인한다. API 사용 시 공급자 문서와 계정에서 사용 가능한 모델을 선택하고 결과 양식에 ID를 적는다. 이 자료는 현재 모델 가용성·요금·무료 할당량을 검증하지 않았다.

원본 설정 로더도 `${환경변수명}` 치환을 지원한다. 예를 들어 Gemini를 선택했다면 원본 `llm_configs.gemini_llm.llm_api_key`를 `${GEMINI_API_KEY}`로 설정하고, 서버를 실행할 같은 PowerShell 창에서 입력할 수 있다.

```powershell
$week1GeminiKey = Read-Host 'Gemini API key' -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $week1GeminiKey).Password
Remove-Variable week1GeminiKey
```

이 예시는 키 주입 방법이다. 원본 Gemini 어댑터와 현재 서비스의 호환성을 실행 검증한 예시는 아니다. 팀 작업본의 공급자 설정·어댑터 수정이 원본에도 들어 있다고 가정하지 않는다.

실제 키와 개인 대화는 결과에 적지 않는다. 원본은 로그에 설정·프롬프트·입력을 출력하는 경로가 있으므로 공유할 캡처·로그에서 키와 개인 내용을 가린다.

## 4. 서버와 기본 화면 확인

```powershell
uv run --locked --python 3.10 run_server.py
```

초기 엔진 준비가 끝나면 `http://localhost:12393/`를 연다. 포트를 바꿨다면 바꾼 주소를 사용한다. 종료는 실행 창에서 `Ctrl+C`다. 초기화 중 음성 인식 모델 다운로드나 외부 서비스 접근이 필요할 수 있다.

원본 폴더에서는 `uv run upgrade.py`, 최신 커밋으로의 pull 등 기준을 바꾸는 작업을 분석 도중 섞지 않는다. 해결을 위해 변경이 필요하면 원본 결과를 먼저 기록하고 별도 실험 브랜치에서 변경한다.

## 5. 기능을 순서대로 관찰

| 순서 | 행동 | 적을 내용 |
|---|---|---|
| 1 | “자기소개를 한국어 두 문장으로 해줘.” | 연결·응답·음성·아바타 표시 |
| 2 | “방금 답을 한 문장으로 줄여줘.” | 앞 대화 문맥 반영 |
| 3 | 마이크로 짧은 질문 | 전사 정확도, 첫 텍스트·첫 음성까지 시간 |
| 4 | 긴 답변을 요청하고 중단 | 음성 정지, 새 요청 처리, 저장된 기록 |
| 5 | “시험용 별명은 구름연필7429야.” → 다른 주제 3턴 → 별명 질문 | 같은 대화의 문맥 |
| 6 | 새로고침 후 기존 기록 선택 → 별명 질문 | 기록 복원 |
| 7 | 서버 재시작 후 기존 기록 선택 → 별명 질문 | 디스크 기록 복원 |
| 8 | 완전히 새 대화 → 별명 질문 | 세션 간 기억과 구분. 모른다고 해도 실패로 단정하지 않음 |

성격 비교는 차분한 존댓말 / 활발한 반말 두 설정으로 같은 질문을 사용한다. “과제가 밀려서 시작하기가 싫어.”와 “처음 배우는 사람에게 머신러닝을 설명해줘.”를 각각 새 대화에서 묻는다. 설정을 다시 읽는 방법을 기록하고 모델·음성·외형은 고정한다.

추가로 시간이 있으면 두 브라우저 창에서 서로 다른 시험용 사실을 입력해 연결별 문맥이 섞이는지 본다. 원본에 Agent 공유 경로가 있다는 소스 근거와 실제 관찰 결과를 구분해서 적는다.

## 6. 코드 확인과 회의 자료

읽는 순서는 `websocket_handler.py` → `conversation_handler.py` → `single_conversation.py` → `service_context.py` → `basic_memory_agent.py` → `chat_history_manager.py`다. 출력은 `conversation_utils.py`와 `tts_manager.py`까지 연결한다.

- 실제 파일·함수 이름을 붙인 구조도 한 장.
- 성공·부분 성공·실패·미확인 표와 재현 순서.
- 같은 질문에 대한 성격 A/B 응답.
- 세 팀이 함께 결정할 질문 세 개.
- 가능하면 입력→응답→음성·아바타를 담은 짧은 영상.

설치나 API 연결에서 막혔어도 오류와 재현 순서를 기록하면 분석 결과다. 코드 분석 결과와 실행으로 관찰한 결과를 분리한다.
