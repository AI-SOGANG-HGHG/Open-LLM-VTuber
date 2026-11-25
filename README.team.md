# AI-SOGANG-HGHG · 팀 개발 안내

Open-LLM-VTuber를 기반으로 개인 페르소나 에이전트를 만들고, 버튜버·방송과 Minecraft에 연결한다. 공통 기반은 캐릭터 설정·대화·기억·세션이며, 페르소나에 따른 대화·행동 차이를 재현 가능하게 검증하는 것을 최우선으로 둔다.

| 항목 | 내용 |
|---|---|
| 팀원 | 5–6명 |
| 목표 마감 | 2027년 1월 8일 |
| 초기 단계 | 첫 1–2주 동안 기존 코드 분석과 공통 플랫폼 설계 |

## 현재 상태

- 팀 조직: [AI-SOGANG-HGHG](https://github.com/AI-SOGANG-HGHG)
- 팀 저장소: [AI-SOGANG-HGHG/Open-LLM-VTuber](https://github.com/AI-SOGANG-HGHG/Open-LLM-VTuber)
- 원본 코드와 Git 이력을 기반으로 팀 개발을 진행한다.
- 로컬 `origin`은 팀 저장소, `upstream`은 Open-LLM-VTuber 원본이다.
- Windows 한 대에서 의존성 설치와 서버·텍스트·합성 음성 입력 경로를 확인했다. [첫 실행 기록](docs/local-first-run.md)의 결과와 미확인 항목을 구분해 참고한다.
- 현재 Ubuntu 서버에서 HTTPS와 화면 내 팀 로그인을 제공한다. [운영 안내](docs/team-https.md)와 실제 검증 범위를 함께 참고한다.
- 현재 기능을 직접 확인할 때는 [수동 검증 순서와 확인 수준](docs/manual-verification.md)을 따른다.
- 서강이 로컬 화면·재시작·검사 방법은 [서강이 앱 안내](web_tool/sogangi/README.md), 원본 레이어와 동작 제작 범위는 [Live2D 제작 설계](docs/sogangi-live2d-plan.md)를 참고한다. 실제 Live2D 중립·기쁨·화남·놀람 표정, 눈·입·작은 고개 기울기·호흡·오른팔 인사를 기본 화면에서 지원한다. SVG 모션도 선택할 수 있다. 입체 회전·디포머 계층·나머지 감정 원화는 남아 있다.
- 플랫폼에서는 고유한 에이전트별로 프로필과 장기 기억을 이어간다. 시작 프리셋과 다섯 축의 성격 설정, 벡터 기억 검색, 행동 규칙과 대화별 감정 상태를 실제 음성·Live2D 대화에 적용한다. [Persona Studio 실행 안내](web_tool/platform/README.md) · [파이프라인과 비교 시연](docs/studio-persona-pipeline.md)
- Studio의 Persona-CAPS 한국어 규칙 데이터는 CC BY-NC 4.0을 따른다. [규칙 데이터 출처와 이용 조건](config_templates/persona-caps-ko/README.md)
- 로컬 일상 사용 기능과 출시 조건은 [서강이 제품화 기록](docs/sogangi-release.md), 반복 가능한 말투·기억·행동 주장 검증은 [페르소나 평가](docs/sogangi-persona-evaluation.md)를 참고한다.

## 팀원이 읽을 순서

1. [첫 1–2주 계획](docs/plan.md)
   - 11월 18일 논의용: [페르소나 시스템 설계](docs/persona-management-design.md) — 네 영역의 역할과 성향·목표를 반영한 기억 저장·검색·갱신 구조
   - 관련 배경: [논문·플랫폼 조사](docs/persona-agent-research-2026-11-15.md), [구현 상세 후보](docs/persona-runtime-design.md)
   - 10월 29일 결정 사항과 통합·평가 제안: [시스템 방향](docs/system-direction.md)
   - 실제 작업 순서와 완료 기준: [사전 작업 계획](docs/preparation-plan.md)
   - 소스 조사·현재 레포 피드백·공개 재사용 후보: [AIRI 포팅 검토](docs/airi-porting-review.md)
2. [다른 PC에서 첫 실행 체크리스트](docs/first-run-checklist.md)
   - Ollama 없이 시작할 때: [Windows · Gemini API 실행 안내](docs/local-gemini-setup.md)
   - Linux 서버에서 키 파일과 상시 실행 서비스 사용: [Linux 서버 안내](docs/linux-server.md)
   - 팀 로그인과 외부 HTTPS 접속: [팀용 HTTPS 안내](docs/team-https.md)
3. [기존 한국어 실행 안내](README.KR.md)
4. [AI 작업 지침](AGENTS.md)과 담당 영역의 기존 코드

## 폴더 사용

```text
persona-platform/              # 로컬 작업 폴더
└─ Open-LLM-VTuber/             # 팀 저장소와 연결한 유일한 Git 저장소
   ├─ README.team.md           # 팀 목표·준비 상태
   ├─ AGENTS.md                # 공통 AI 작업 지침
   ├─ docs/plan.md             # 첫 2주 계획
   └─ 기존 코드·설정·실행 파일
```

팀 설계 문서와 코드 변경은 이 저장소 안에서 관리한다. Minecraft와 방송은 후속 통합 대상으로 포함하며, 산책 동반과 로컬 8개 에이전트 경기는 확장 목표다. 현재 AWS의 웹 서버는 systemd로 운영하며 Docker·방송·게임 통합은 후속 작업이다. 세부 코드 폴더는 기존 구조를 조사한 뒤 필요한 범위에서 결정한다.

## 공유 방식

팀 변경은 `origin`에 공유하고, 원본 `upstream`은 참조와 필요한 업데이트에 사용한다. 문서와 코드 변경을 같은 저장소에서 관리하며 작업별 브랜치에서 검토한다.

push 이후 검사와 외부 서비스 설정은 [GitHub Actions 안내](docs/ci.md)를 참고한다.
