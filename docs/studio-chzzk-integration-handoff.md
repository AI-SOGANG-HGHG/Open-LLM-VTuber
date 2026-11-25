# Persona Studio 치지직 방송 연동 인수인계

`chzzk/main_integrated`의 병합 커밋 `1291112` 이후, **Studio에서 고른 캐릭터로 치지직 채팅에 답하고 그 응답을 Studio 화면에서 재생하는 방송 모드**를 구현했다. 로컬 모의 테스트와 실제 치지직 채팅 유입을 확인했다. AWS용 설정 파일도 준비했으며, AWS 배포와 공개 HTTPS 실방 검증은 남아 있다.

## 병합으로 들어온 코드와 이후 작업

| 기준                             | 들어 있는 기능                                                                                                                                                  |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `main` · `c9cefe2`               | Persona Studio, 캐릭터별 프로필과 장기 기억, 대화방별 과제·감정, 턴 단위 표정과 페르소나 평가 도구                                                              |
| `chzzk/team_develop` · `189b6cc` | 치지직 채팅·후원 수집기, `/proxy-ws`의 입력 큐, 채팅·닉네임 필터, 후원 우선 처리                                                                                |
| 병합 `1291112` 이후              | Studio 방송 화면과 치지직 수집기를 같은 방송 세션에 연결, Studio 캐릭터 적용, 시청자 입력으로 시작된 응답 재생, AWS 연결·인증 설정, 모의 스크립트와 통합 테스트 |

병합 직후 기존 Open-LLM-VTuber 웹 화면은 WebSocket URL을 `/proxy-ws`로 바꾸어 치지직 응답을 받을 수 있었다. Persona Studio는 `/client-ws` 직통으로 연결됐으므로, Studio에서 선택한 캐릭터와 기존 프록시가 연 방송 세션은 별개였다. [기존 프록시](../src/open_llm_vtuber/proxy_handler.py) · [Studio 연결 코드](../web_tool/platform/runtime/js/conversation-connection.js)

## 현재 연결 구조

```text
Studio 일반 대화 → /client-ws → 선택한 캐릭터의 일반 대화

Studio 방송 화면 → /proxy-ws?mode=studio ──┐
치지직 → 수집기 → /internal/chzzk-ws ────────┴─→ 방송용 프록시·큐
                                                   ↓
                                          내부 /client-ws 세션
                                          선택한 Studio 캐릭터
                                                   ↓
                                       대화 처리·모델·TTS
                                                   ↓
Studio 방송 화면 ← /proxy-ws ← 텍스트·음성·표정 이벤트
```

**음성·Live2D 대화**를 열면 일반 모드, **방송** 탭이나 **방송 대화실 열기**를 누르면 방송 모드다. 방송 모드에서는 Studio 입력창에 직접 보낸 텍스트와 치지직 채팅이 같은 큐를 사용한다. 두 모드는 같은 캐릭터의 장기 기억을 조회하며, 브라우저에서 마지막으로 열었던 대화방은 모드별로 복원한다. [Studio 연결 메뉴](../web_tool/platform/js/views/connections.js) · [방송 모드와 대화방 저장 범위](../web_tool/platform/runtime/js/app.js)

### 1. 연결과 입력 큐

Studio 방송 모드는 기존 `/proxy-ws`와 별도 세션·큐를 사용한다. 조작 화면 한 개가 방송 세션을 열고, 수집기는 `/internal/chzzk-ws`로 치지직 채팅과 후원만 보낸다. 수집기 연결은 루프백 주소와 `STUDIO_CHZZK_TOKEN`을 검사한다. Caddy는 공개 주소에서 내부 경로 접근을 차단한다. [라우트](../src/open_llm_vtuber/routes.py) · [방송 세션](../src/open_llm_vtuber/studio_broadcast.py) · [Caddy 설정](../deploy/Caddyfile)

기존 필터가 일반 채팅과 닉네임을 검사한다. 차단된 일반 채팅은 버리고, 통과한 본문에 부적절한 닉네임이 붙으면 `익명시청자`로 바꾼다. 차단된 후원 본문은 필터 안내문으로 대체한다. 일반 후원은 대기 중인 일반 채팅보다 먼저 처리하며, 1만 치즈 이상 후원은 진행 중인 응답을 중단할 수 있다. Studio 화면은 현재 시청자 닉네임 대신 기존 입력 말풍선의 **나** 라벨을 표시한다. [필터 및 후원 처리](../src/open_llm_vtuber/proxy_handler.py) · [닉네임 필터](../src/open_llm_vtuber/live/chat_filter.py)

### 2. 방송 세션에 캐릭터 적용

방송 화면이 연결되면 서버가 내부 `/client-ws` 연결을 열고, 팀 로그인과 작업공간 확인에 필요한 헤더를 루프백 연결에 전달한다. 기존 `apply-studio-persona` 처리기가 `workspace_id`와 `agent_id`의 접근 권한을 확인한다. **프로필 적용과 대화방 준비가 끝난 뒤** 큐가 치지직 입력을 대화 엔진에 넘긴다. 이때 수집기는 채팅 이벤트를 보내고, 대화 엔진이 선택한 캐릭터의 성격·기억을 적용한다. 화면이 끊기거나 로그아웃하면 방송용 대화 연결도 정리한다. [방송 세션 초기화](../src/open_llm_vtuber/studio_broadcast.py) · [기존 Studio 프로필 적용](../src/open_llm_vtuber/websocket_handler.py)

### 3. 시청자 입력으로 시작된 응답 재생

Studio 방송 화면은 `user-input-transcription`으로 받은 채팅을 저장하고, 서버의 `conversation-chain-start`에서 해당 `request_id`의 응답을 시작한다. 화면에서 전송 버튼을 누르지 않아도 같은 ID의 텍스트·표정 정보·음성을 처리한다. 음성 재생을 마치면 `frontend-playback-complete`를 돌려보내고, 서버가 응답 종료를 알리면 큐가 다음 입력을 처리한다. 방송 프록시는 활성 요청의 재생 완료 신호만 전달한다. [Studio 응답 처리](../web_tool/platform/runtime/js/app.js) · [메시지 큐](../src/open_llm_vtuber/proxy_message_queue.py)

## 확인한 결과

| 검증 | 확인한 내용 |
| --- | --- |
| 백엔드 회귀 테스트 | `python -m unittest discover -s tests` 총 **138개 통과**. 신규 방송 통합 테스트 2개가 포함된다. |
| 로컬 WebSocket 통합 | 수집기가 먼저 보낸 채팅을 프로필과 대화방 준비 후 처리했다. 선택한 캐릭터 지침과 관련 기억이 모델 요청에 들어갔고, 시작·표정·음성·종료 이벤트와 재생 완료가 같은 요청에 대응했다. Gemini와 TTS는 테스트용 응답을 사용했다. |
| 로컬 권한 테스트 | 로그인 세션 없음, 잘못된 `Origin`, 잘못된 수집기 토큰을 거절했다. 다른 작업공간의 캐릭터는 적용할 수 없었고 로그아웃 시 열린 방송 연결이 닫혔다. |
| Chrome 화면 확인 | 모의 채팅·응답·WAV 이벤트로 시청자 메시지와 답변이 표시됐다. 화면이 입력을 다시 보내지 않고 재생 완료를 한 번 보냈다. |
| 팀원의 로컬 실방 확인 | 실제 치지직 채팅방에 수집기가 접속하고 채팅을 전달했다. 올바른 로컬 Studio 방송 대화실로 연결한 뒤 동작을 확인했다는 팀원 보고가 있었다. AWS 공개 접속과 OBS 시청 화면에서의 음성·표정 품질은 이번 기록에 포함되지 않는다. |

[방송 통합 테스트](../tests/test_studio_broadcast.py) · [후원 필터 회귀 테스트](../tests/test_proxy_donation_filter.py)

## 팀원이 로컬에서 재현하는 순서

1. `conf.yaml`의 기존 `system_config` 아래에 `enable_proxy: true`를 설정한다. 서버용 PowerShell과 수집기용 PowerShell 모두에 같은 로컬 테스트용 `STUDIO_CHZZK_TOKEN`을 지정한다.
2. 프로젝트 루트에서 `.\.venv\Scripts\python.exe run_server.py`로 서버를 실행한다. 브라우저에서 `http://localhost:12393/web-tool/platform/`을 열고 캐릭터의 **방송** 대화실에 들어간다.
3. 모의 입력은 `.\.venv\Scripts\python.exe scripts\test_mock_chzzk.py --studio`로 보낸다. 실방에서는 기존 `live_config.chzzk_live`에 채널 ID와 `ws://127.0.0.1:12393/internal/chzzk-ws`를 설정한 뒤, PC의 OBS로 송출을 시작하고 `.\.venv\Scripts\python.exe scripts\run_chzzk_live.py`를 실행한다.
4. 수집기 로그에 `Successfully joined Chzzk live chat room!`이 나오면 시청자 채팅을 한 건 보낸다. `Forwarded chzzk_chat`은 수집기가 로컬 서버에 보냈음을 뜻한다. 화면에 응답이 없다면 Chrome 개발자도구 **Network → WS**에서 `/proxy-ws?mode=studio` 연결 상태가 `101`인지, Messages에 `user-input-transcription`과 `conversation-chain-start`가 오는지 확인한다.

[로컬 실행 안내](studio-chzzk-integration-plan.md#로컬에서-확인) · [실방 수집기](../scripts/run_chzzk_live.py) · [모의 수집 입력](../scripts/test_mock_chzzk.py)

## AWS에 반영할 항목

- 팀 `origin`의 `chzzk/main_integrated`를 AWS 배포 소스로 사용한다. 대상 커밋을 확인한 뒤 AWS에서 해당 버전을 설치한다.
- AWS의 기존 `conf.yaml`에 프록시 활성화, 치지직 채널 ID, 내부 수집기 URL을 설정한다. 서버의 `private/chzzk.env`에 AWS 전용 토큰을 두고, 백엔드와 수집기 사용자 systemd 서비스가 같은 파일을 읽도록 적용한다. 수정된 Caddy 설정도 반영한다.
- AWS의 Studio 백엔드와 수집기를 실행하고, 송출은 PC의 OBS로 한다. 배포 후 공개 HTTPS 로그인, 방송 WebSocket 연결, 내부 수집기 경로의 공개 접근 차단, 실제 채팅과 시청 화면의 음성·표정까지 확인한다.

[AWS 배포 설정](studio-chzzk-integration-plan.md#aws-배포-설정) · [백엔드 서비스](../deploy/open-llm-vtuber.service) · [수집기 서비스](../deploy/open-llm-vtuber-chzzk.service)
