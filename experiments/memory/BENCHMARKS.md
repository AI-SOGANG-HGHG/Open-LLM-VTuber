# 공개 벤치마크 재현

규약: [평가 프로토콜](../../docs/memory-benchmark-protocol.md).

아래 명령은 저장소 루트 PowerShell 기준이다. API 키 값은 명령에 직접 쓰지 않고 환경변수 또는 기존 로컬 키 파일을 사용한다. 실행은 기본 앱과 분리된 `tmp/mem0-study-env` 환경을 사용한다.

## 준비와 API 없는 전체 검색 검사

```powershell
.\.venv\Scripts\python.exe scripts/prepare_memory_benchmarks.py
.\.venv\Scripts\python.exe scripts/benchmark_memory.py audit --output tmp/benchmark-audit
.\.venv\Scripts\python.exe scripts/benchmark_memory.py retrieve --per-category 0 --output tmp/longmemeval-retrieval
.\.venv\Scripts\python.exe scripts/benchmark_memory_supplement.py heard-ko --per-category 0 --output tmp/heard-ko-retrieval
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_memory*.py' -v
```

`--per-category 0`는 전체 선택이다. LongMemEval은 500문항, heard는 REFL을 제외한 사실 문항 64개다. 데이터 다운로드는 네트워크를 사용하지만 이 단계는 LLM API를 호출하지 않는다.

## 고정 표본의 응답·보조 채점

```powershell
.\tmp\mem0-study-env\Scripts\python.exe scripts/benchmark_memory_live.py --retrieval-dir tmp/longmemeval-retrieval --output tmp/lme-live7 --methods recent lexical --key-file private/gemini-api-key.txt
.\tmp\mem0-study-env\Scripts\python.exe scripts/benchmark_memory_live.py --retrieval-dir tmp/longmemeval-retrieval --output tmp/lme-mem0-update1 --methods mem0 --question-ids 42ec0761 --key-file private/gemini-api-key.txt
.\tmp\mem0-study-env\Scripts\python.exe scripts/benchmark_memory_supplement.py heard-ko --generate --output tmp/heard-live5 --key-file private/gemini-api-key.txt
.\tmp\mem0-study-env\Scripts\python.exe scripts/benchmark_memory_supplement.py memops-adjacent --generate --mem0 --output tmp/memops-live5 --key-file private/gemini-api-key.txt
```

`benchmark_memory_live.py`의 기본 표본은 7유형 각 1문항이다. `--question-ids`로 그 고정 표본 안의 특정 문항만 처리할 수 있다. 같은 출력 경로와 설정으로 재실행하면 완료한 블록·응답·채점을 건너뛴다. 중간에 끝난 작업을 새 출력 경로에서 시작하면 이전 API 작업을 재사용하지 못한다.

Mem0는 검색만이 아니라 원문 추출·임베딩·기억 저장 호출을 한다. API 제한이 발생할 수 있으므로 대량 응답 전에 표본의 실제 실행량을 확인한다. 임베딩/모델 호출을 여러 프로세스에서 병렬 실행하면 계정의 같은 할당량을 공유한다.

## 독립 심사 모델의 대조 검사와 재채점

```powershell
.\tmp\mem0-study-env\Scripts\python.exe scripts/judge_memory_benchmarks.py --output tmp/independent-judge --key-file private/gemini-api-key.txt --runs tmp/lme-live7 tmp/heard-live5 tmp/memops-live5
```

기본 보조 심사 모델은 `gemini-3.5-flash`다. 대조 문항 16개가 모두 통과해야 재채점하며, 최초 판정과 별도 파일에 저장한다. GPT-4o 자격증명이 환경에 있으면 다음 설정으로 모델을 변경할 수 있다.

```powershell
.\tmp\mem0-study-env\Scripts\python.exe scripts/judge_memory_benchmarks.py --settings experiments/memory/longmemeval-judge.example.json --output tmp/gpt4o-judge --runs tmp/lme-live7
```

공식 원본 CLI도 다운로드되어 있다. `hypotheses-recent.jsonl`, `hypotheses-lexical.jsonl`, `hypotheses-mem0.jsonl`은 그 CLI가 받는 두 필드 형식이다. 공식 CLI의 추가 의존성은 원본 requirements를 확인한다. 현재 실행한 것은 원본 프롬프트를 사용하는 별도 기록·재개 가능한 평가기다.

## 주요 산출물

- `manifest.json`: 데이터·원본 코드 고정 버전과 파일 해시.
- `run.json`: 선택한 질문 ID·설정·검색 조건.
- `retrievals.jsonl`: 실제 검색 결과. 정답 메타데이터 매핑이 있으므로 모델 입력으로 파일 전체를 사용하지 않는다.
- `responses.jsonl` / `hypotheses-*.jsonl`: 실제 답변과 공식 CLI용 출력.
- `mem0-ingestion.jsonl`: 추출 블록별 상태와 기억 결과. 추출 내부 호출 비용은 SDK 전체 usage를 제공하지 않아 완전히 집계되지 않는다.
- `judgments.jsonl`, `api-usage.jsonl`: 모델 판정·API 사용량과 오류.
- `controls.jsonl`, `control-summary.json`: 보조 judge의 대조 검사.
- `*.summary.json`: 데이터셋·심사 모델·표본 수별 집계. 데이터셋 간 점수를 합산하지 않는다.

데이터와 실제 모델 출력은 Git 제외 `tmp/`에 두고, 공유 문서에는 출처와 필요한 집계만 기록한다.
