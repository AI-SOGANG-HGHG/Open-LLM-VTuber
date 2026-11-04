# Windows 로컬 첫 실행 기록

확인 날짜: 2026년 10월 28일. 기준 코드는 `648f8bf`이며, 아래 실행 수정은 `work/local-experiments`의 미커밋 변경으로 적용했다. 실제 API 키와 대화 원본은 이 문서에 포함하지 않는다.

## 환경과 설정

| 항목 | 값 |
|---|---|
| OS | Windows 10 Pro 22H2 |
| GPU | NVIDIA GeForce RTX 3050 8GB. LLM은 외부 API, 음성 인식은 CPU 사용 |
| Python | 프로젝트 내부 CPython 3.10.22, `.venv` |
| 의존성 | `uv.lock` 기준. Edge TTS만 7.3.1로 갱신 |
| FFmpeg | 9.0.2 essentials. 배포자 GitHub 미러에서 받고 SHA-256 검증 |
| Agent / LLM | `basic_memory_agent` / Gemini `gemini-3.5-flash-lite` |
| 음성 인식 | `sherpa_onnx_asr`, SenseVoice int8, CPU |
| 음성 출력 | Edge TTS, `ko-KR-SunHiNeural` |
| 도구 호출 | MCP 비활성화 |
| 접속 주소 | <http://localhost:12393> |

## 관찰한 결과

| 검사 | 결과와 한계 |
|---|---|
| 의존성·설정 검증 | 가상환경 설치와 프로젝트 설정 스키마 검증 통과 |
| 서버 시작 | ASR·TTS·Gemini Agent 초기화 후 HTTP 서버 시작 |
| 프론트엔드 | HTML과 정적 자산, Live2D 모델 설명 파일 접근 확인. 실제 브라우저의 캐릭터 렌더링은 사용자 확인 필요 |
| 한국어 텍스트 대화 | 실제 `/client-ws` 경로로 Gemini 응답과 음성 데이터 수신. 약 14.4초에 전체 턴 완료 |
| 한국어 음성 입력 | 합성한 한국어 시험 음성을 16kHz mono로 변환해 서버에 전달. 한국어 전사와 응답·음성 데이터 수신. 약 10.5초에 전체 턴 완료 |
| 음성 생성·전송 | 한국어 MP3 생성 및 WebSocket WAV 오디오 데이터 전달 확인. 실제 스피커 청취는 사용자 확인 필요 |
| 실제 마이크·중단·장시간 대화 | 아직 미확인 |

측정 시간은 시험 요청 시작부터 대화 종료 신호까지의 전체 시간이다. 첫 글자·첫 음성 지연이나 실제 오디오 재생 시간의 측정값은 아니다. 시험 클라이언트는 오디오를 받은 뒤 재생 완료 신호를 보냈으며 실제로 소리를 재생하지 않았다.

## 실행 중 발견해 수정한 문제

- Edge TTS 7.2.7에서 Microsoft 음성 서비스가 `403`을 반환했다. 7.3.1로 업데이트한 뒤 한국어·영어 음성 생성이 성공했다. 소스 요구 버전, 잠금 파일, requirements의 해당 버전을 함께 맞췄다.
- Uvicorn의 레거시 WebSocket 구현에서 음성 데이터를 전송하며 `AssertionError`가 발생했다. `websockets-sansio`로 전환한 뒤 텍스트·음성 입력 두 경로의 대화가 완료됐다. 해당 구현이 도입된 Uvicorn 0.35.0 이상을 요구한다.
- 새 Gemini 프로젝트용 설정 예시를 실제로 응답한 `gemini-3.5-flash-lite`에 맞췄다.

## 현재 PC에서 사용

서버가 켜져 있으면 브라우저에서 <http://localhost:12393>에 접속해 마이크 권한을 허용하고, 짧은 텍스트 대화부터 확인한다.

처음 점검한 백그라운드 서버를 종료하려면 저장소 루트에서 실행한다.

```powershell
powershell -ExecutionPolicy Bypass -File .\stop-local.ps1
```

다시 실행할 때는 다음 명령을 사용하고, 종료할 때 해당 터미널에서 `Ctrl+C`를 누른다.

```powershell
powershell -ExecutionPolicy Bypass -File .\start-local.ps1
```

Python과 도구는 `.venv`, `tmp`, 모델은 `models`에 있다. 이 폴더들과 개인 `conf.yaml`은 Git 제외 대상이다. 다른 PC에 도구가 준비됐다는 의미는 아니므로 [설치 안내](local-gemini-setup.md)를 따른다.
