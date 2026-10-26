# AI-SOGANG-HGHG — 팀 개발 안내

Open-LLM-VTuber를 기반으로 캐릭터 설정·Persona·대화·기억·세션을 갖춘 공통 AI 캐릭터 플랫폼을 설계한다.

팀 5~6명 · 목표 마감 2027-01-08 · 첫 1~2주는 기존 코드 분석과 기본 플랫폼 설계

## 현재 상태

- 팀 조직: [AI-SOGANG-HGHG](https://github.com/AI-SOGANG-HGHG).
- 팀 저장소: [AI-SOGANG-HGHG/Open-LLM-VTuber](https://github.com/AI-SOGANG-HGHG/Open-LLM-VTuber).
- GitHub에서 새로 만든 팀 저장소에 원본 코드와 main의 Git 이력을 가져와 시작한다. GitHub의 Fork 관계로 생성한 저장소는 아니다.
- 로컬 origin은 팀 저장소, upstream은 Open-LLM-VTuber 원본으로 구분한다.
- 이 안내문·AGENTS.md·docs/plan.md를 시작점으로 팀의 첫 2주 설계를 진행한다.
- 기존 앱의 의존성 설치와 모델·음성 실행은 아직 확인하지 않았다.

## 팀원이 읽을 순서

1. [첫 2주 계획](docs/plan.md).
2. [기존 한국어 실행 안내](README.KR.md).
3. 담당 영역의 기존 코드와 [AI 작업 지침](AGENTS.md).

## 폴더 사용

```text
persona-platform/              # 로컬 작업 폴더
└─ Open-LLM-VTuber/             # 팀 저장소와 연결한 유일한 Git 저장소
   ├─ README.team.md           # 팀 목표·준비 상태
   ├─ AGENTS.md                # 공통 AI 작업 지침
   ├─ docs/plan.md             # 첫 2주 계획
   └─ 기존 코드·설정·실행 파일
```

팀 설계 문서와 코드 변경은 이 저장소 안에서 관리한다. 게임·방송은 현재 범위에 포함하지 않는다. 세부 코드 폴더는 기존 구조를 조사한 뒤 필요한 범위에서 결정한다.

## 공유 방식

팀 변경은 origin에 공유하고, 원본 upstream은 참조와 필요한 업데이트에 사용한다. 문서와 코드 변경을 같은 저장소에서 관리하며 작업별 브랜치에서 검토한다.
