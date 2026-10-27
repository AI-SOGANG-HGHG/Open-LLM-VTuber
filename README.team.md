# AI-SOGANG-HGHG · 팀 개발 안내

Open-LLM-VTuber를 기반으로 캐릭터 설정·Persona·대화·기억·세션을 갖춘 공통 AI 캐릭터 플랫폼을 설계한다.

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
- `feat/frontend-source` 개발 브랜치에는 프론트 원본을 포함했다. 프론트·백엔드를 같은 저장소에서 수정한다. `main`에는 아직 병합하지 않았다.
- 웹 빌드는 확인했다. 원본 TypeScript 검사는 오류가 남아 있으며, 전체 백엔드·모델·음성 실행은 아직 확인하지 않았다.

## 팀원이 읽을 순서

1. [첫 1–2주 계획](docs/plan.md)
2. [프론트 원본 개발·빌드 안내](docs/frontend-development.md)
3. [다른 PC에서 첫 실행 체크리스트](docs/first-run-checklist.md)
4. [기존 한국어 실행 안내](README.KR.md)
5. [AI 작업 지침](AGENTS.md)과 담당 영역의 기존 코드

## 폴더 사용

```text
persona-platform/              # 로컬 작업 폴더
└─ Open-LLM-VTuber/             # 팀 저장소와 연결한 유일한 Git 저장소
   ├─ README.team.md           # 팀 목표·준비 상태
   ├─ AGENTS.md                # 공통 AI 작업 지침
   ├─ docs/plan.md             # 첫 2주 계획
   ├─ frontend/                # React·TypeScript 원본 소스
   ├─ src/open_llm_vtuber/      # Python 백엔드
   └─ 기존 코드·설정·실행 파일
```

팀 설계 문서와 코드 변경은 이 저장소 안에서 관리한다. 게임·방송은 현재 범위에 포함하지 않는다. 세부 코드 폴더는 기존 구조를 조사한 뒤 필요한 범위에서 결정한다.

## 공유 방식

팀 변경은 `origin`에 공유하고, 원본 `upstream`은 참조와 필요한 업데이트에 사용한다. 문서와 코드 변경을 같은 저장소에서 관리하며 작업별 브랜치에서 검토한다.
