# Mem0 · 대량 대화 · 페르소나 실험

설계와 적용 범위: [기억/RAG 계획](../../docs/memory-rag-plan.md).

공식 LongMemEval-S, MemOps, 공개 한국어 자료를 사용하는 후속 평가는 [BENCHMARKS.md](BENCHMARKS.md)에 분리했다. 아래 5,009개 합성 이벤트 실험과 점수를 섞지 않는다.

기존 웹/음성 앱과 독립적인 text replay다. 공개 `mem0ai` SDK가 기억을 추출하고 로컬 Qdrant에 저장한다. 이후 구현한 선택형 앱 연결은 [RAG 실행 안내](../../docs/rag-runtime.md)에 분리했다. 기존 `mem0_llm.py` 대신 `basic_memory_agent`에 연결한다.

## API 없는 기준선

저장소 루트 PowerShell:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_memory_experiment.py -v
.\.venv\Scripts\python.exe scripts/evaluate_memory.py --output tmp/memory-offline
```

5,009개 이벤트를 SQLite에 저장하고 최근 8개/어휘 검색 조건의 프롬프트 30개를 만든다. API를 호출하거나 응답을 생성하지 않는다. 기본 잡음은 5,000개다.

## 실제 Mem0 + 모델 응답

메인 앱 의존성을 변경하지 않는 별도 환경:

```powershell
uv venv --python 3.10 tmp/mem0-study-env
uv pip install --python tmp/mem0-study-env/Scripts/python.exe -r experiments/memory/requirements-lock.txt
.\tmp\mem0-study-env\Scripts\python.exe scripts/evaluate_memory.py --backend mem0 --generate --key-file private/gemini-api-key.txt --output tmp/memory-mem0
```

기본 생성 호출 간격은 5초다. 호출량 제한 등으로 실패하면 전체 실험을 다시 수집하지 않고 실패한 응답만 재시도한다. 최초 응답 파일도 별도로 보존한다.

```powershell
.\tmp\mem0-study-env\Scripts\python.exe scripts/retry_memory_generation.py --key-file private/gemini-api-key.txt --output tmp/memory-mem0 --interval 5
```

완료한 합성 실험 저장소의 격리·삭제는 다음으로 확인한다. **다른 방(room-b)의 시험용 기억과 원문을 삭제**하며 주 실험 범위의 결과는 보존한다. 삭제 확인을 이미 수행한 저장소에서 반복 실행하면 초기 fixture 존재 검사가 실패할 수 있다.

```powershell
.\tmp\mem0-study-env\Scripts\python.exe scripts/check_memory_lifecycle.py --key-file private/gemini-api-key.txt --output tmp/memory-mem0
```

키가 이미 `GEMINI_API_KEY`에 있으면 `--key-file`을 생략한다. 키는 결과 파일에 기록하지 않는다. `gemini.example.json`의 모델/임베딩 가용성은 계정별로 확인해야 하며, `--settings`로 다른 JSON을 지정할 수 있다. Gemini API의 [호환 API](https://ai.google.dev/gemini-api/docs/openai)와 [텍스트 임베딩](https://ai.google.dev/gemini-api/docs/embeddings)을 사용한다. 실제 호출은 API 사용량을 발생시킨다.

첫 설치와 실제 검증 버전은 `mem0ai==2.2.1`. `requirements-lock.txt`는 실험 환경의 의존성 버전을 고정하며 기본 앱의 `uv.lock`과 별개다. 선택 설치 가능한 spaCy/fastembed는 포함하지 않았으므로 Mem0 자체의 BM25/개체명 기능은 비활성 상태다. SQLite 어휘 검색과 Mem0 벡터 검색을 각각 비교한다.

`--generate` 없이 Mem0 backend를 사용해도 **기억 추출·임베딩·검색 API 호출**이 발생한다. `--noise`, `--repeats`로 실험 크기를 조절한다. 반복 1회 결과는 파일럿이며 통계적 효과 추정으로 해석하지 않는다.

## 결과 파일

`--output`은 기존 데이터와 섞이지 않도록 새 디렉터리만 받는다. 출력은 기본적으로 Git 제외 `tmp/`에 둔다.

| 파일 | 용도 |
|---|---|
| `transcripts.db` | 소유 범위를 가진 원문과 FTS5 인덱스 |
| `mem0/qdrant/` | Mem0 로컬 벡터 기억 |
| `mem0/mem0_history.db` | Mem0 기억 변경 이력; 전체 대화 원문과 다름 |
| `ingestion.json` | 각 입력의 Mem0 추출·변경 결과 |
| `retrievals.json` | 질문/모드별 실제 검색 결과와 전달한 근거 |
| `responses.jsonl` | 페르소나별 실제 프롬프트, 응답, 토큰 사용량, 실패 유형 |
| `summary.json` | 설정·데이터 해시·오류 수·키워드 포함률·응답 길이 |
| `lifecycle.json` | 별도 실행한 저장소 재열기·격리·논리 삭제 검사 |
| `blind-review.csv` | 페르소나/모드명을 숨긴 사람 평가용 CSV; 매핑은 responses에 있음 |

공유할 수 있는 합성 결과만 요약 문서에 옮긴다. 실제 개인정보/대화로 바꿔 실험할 경우 결과 전체를 커밋하지 않는다. `forget`은 논리 삭제이며 디스크 잔존, 백업, SQLite WAL까지 제거하는 완전 삭제 보장은 아니다.
