# 팀 저장소의 GitHub Actions

원본에서 가져온 워크플로 중 외부 서비스·유료 기능·전용 실행기가 필요한 작업은 팀 저장소에서도 해당 준비가 돼 있어야 실행할 수 있다. 작업을 건너뛴 결과는 해당 검사에 통과했다는 의미가 아니다.

| 워크플로 | 실행 조건과 설정 |
|---|---|
| Ruff | Python 코드·검사 설정 변경 시 실행한다. CI, `uv.lock`, pre-commit은 Ruff `0.14.14`를 사용한다. 검사 규칙을 추가하거나 오류를 무시하지 않고 기존 잠금 버전으로 검사한다. |
| Studio Authentication | 로그인·서버 연결·의존성 변경 시 실제 HTTP·쿠키·WebSocket 계약을 검사한다. 잠금 파일의 최소 의존성만 설치하며 모델·음성 엔진이나 실제 키를 사용하지 않는다. |
| Sync Requirements | 의존성·잠금 파일·해당 워크플로 변경 시 실행한다. `uv.lock`을 버전 제약으로 내보내고 `--python-version 3.10 --universal`로 최소 지원 Python을 명시한다. 실행기 기본 버전이 지원 범위를 벗어나도 잠금 버전에서 requirements를 생성한다. |
| CodeQL Advanced | 비공개 저장소에서는 먼저 code scanning API 접근을 확인한다. GitHub Code Security 미활성화 오류일 때만 안내와 함께 분석을 건너뛴다. 기능을 활성화하면 자동으로 분석한다. 다른 API 오류나 실제 분석 오류는 실패로 처리한다. |
| Fossa Scan | `fossaApiKey` Actions secret이 있으면 실행한다. 키가 없으면 안내를 기록하고 건너뛴다. Gemini API 키와는 별개다. |
| Docker Build & Push (Blacksmith) | 원본 저장소에서는 기존대로 실행한다. 팀 저장소에서는 전용 Blacksmith 실행기와 레지스트리 인증을 준비하고 Actions variable `ENABLE_BLACKSMITH_BUILDS=true`를 설정해야 실행한다. |

Ruff·CodeQL·FOSSA는 문서만 바뀐 push에서 실행하지 않는다. 필요하면 각 워크플로의 **Run workflow**로 수동 실행할 수 있다. Docker 배포를 켜는 것은 별도의 작업이며 이 설정 수정으로 이미지가 발행되지는 않는다.

Ruff 버전은 개발 환경과 함께 갱신한다. `uv.lock`의 Ruff 버전을 변경할 때 `.github/workflows/ruff.yml`의 `version`과 `.pre-commit-config.yaml`의 `rev`도 맞춘다. 예전 `ruff>=0.8.6` 범위를 CI에서 직접 해석하면 새 버전과 새 기본 검사 규칙이 예고 없이 적용될 수 있다.

로컬에서 프로젝트 의존성을 설치했다면 `uv run --locked ruff check .`로 같은 검사를 실행한다. 앱 실행을 검증한 결과와 CI 검사 결과는 별도로 기록한다.

설정 위치는 GitHub 저장소의 **Settings → Secrets and variables → Actions**다. 비공개 저장소의 CodeQL에는 [GitHub Code Security 활성화](https://docs.github.com/en/code-security/reference/code-scanning/troubleshoot-analysis-errors/private-repository-enablement)가 필요하다. 서비스 키를 소스·문서·`conf.yaml` 공유본에 넣지 않는다.
