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
- 현재 기능을 직접 확인할 때는 [수동 검증 순서와 확인 수준](docs/manual-verification.md)을 따른다.
- 서강이 로컬 화면·재시작·검사 방법은 [서강이 앱 안내](web_tool/sogangi/README.md), 원본 레이어와 동작 제작 범위는 [Live2D 제작 설계](docs/sogangi-live2d-plan.md)를 참고한다. 실제 Live2D 중립·기쁨·화남·놀람 표정, 눈·입·작은 고개 기울기·호흡·오른팔 인사를 기본 화면에서 지원한다. SVG 모션도 선택할 수 있다. 입체 회전·디포머 계층·나머지 감정 원화는 남아 있다.
- 로컬 일상 사용 기능과 출시 조건은 [서강이 제품화 기록](docs/sogangi-release.md), 반복 가능한 말투·기억·행동 주장 검증은 [페르소나 평가](docs/sogangi-persona-evaluation.md)를 참고한다.

## 팀원이 읽을 순서

1. [첫 1–2주 계획](docs/plan.md)
   - 10월 29일 결정 사항과 통합·평가 제안: [시스템 방향](docs/system-direction.md)
   - 실제 작업 순서와 완료 기준: [사전 작업 계획](docs/preparation-plan.md)
   - 소스 조사·현재 레포 피드백·공개 재사용 후보: [AIRI 포팅 검토](docs/airi-porting-review.md)
2. [다른 PC에서 첫 실행 체크리스트](docs/first-run-checklist.md)
   - Ollama 없이 시작할 때: [Windows · Gemini API 실행 안내](docs/local-gemini-setup.md)
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

팀 설계 문서와 코드 변경은 이 저장소 안에서 관리한다. Minecraft와 방송은 후속 통합 대상으로 포함하며, 산책 동반과 로컬 8개 에이전트 경기는 확장 목표다. AWS·Docker와 상용 API 사용은 팀 결정이며, 현재 AWS 배포가 완료됐다는 뜻은 아니다. 세부 코드 폴더는 기존 구조를 조사한 뒤 필요한 범위에서 결정한다.

## 공유 방식

팀 변경은 `origin`에 공유하고, 원본 `upstream`은 참조와 필요한 업데이트에 사용한다. 문서와 코드 변경을 같은 저장소에서 관리하며 작업별 브랜치에서 검토한다.

push 이후 검사와 외부 서비스 설정은 [GitHub Actions 안내](docs/ci.md)를 참고한다.
