# Studio 치지직 방송 연동 구현 계획

`chzzk/main_integrated`의 `1291112`를 기준으로 한 구현 초안이다. AWS에서 상시 운영 중인 Persona Studio에서 캐릭터를 고르고 방송 모드에 들어가면, 그 캐릭터가 치지직 채팅에 답하고 같은 화면에서 텍스트·음성·표정을 재생한다. 방송 한 세션과 조작 화면 한 개를 기준으로 한다.

브라우저는 기존 Caddy 공개 HTTPS 주소를 사용하고, 대화 백엔드는 AWS 서버의 `127.0.0.1:12393`에 둔다. 이 계획에서는 치지직 수집기도 같은 AWS 서버에서 별도 프로세스로 실행한다. 배포 기준은 [팀 HTTPS 운영 안내](team-https.md)와 [현재 배포 설정](../deploy/Caddyfile)이다.

```text
Studio 브라우저 → Caddy HTTPS → /proxy-ws?mode=studio ─┐
치지직 → AWS 수집기 → 내부 수집기 WebSocket ───────────┤
                                                       ▼
                                         방송용 ProxyHandler
                                                       ↓
                                     내부 /client-ws 대화 세션
                                     선택한 Studio 캐릭터·기억
                                                       ↓
                                         기존 대화 처리·LLM·TTS
                                                       ↓
Studio 브라우저 ← Caddy ← /proxy-ws ← 텍스트·음성·표정
```

## 1. Studio 방송 화면을 `/proxy-ws`에 연결

- Studio의 **방송 스튜디오** 카드에 선택한 캐릭터로 방송 대화실을 여는 동작을 추가한다. 기존 연결 생성 함수에 서버 경로를 넘겨 일반 대화는 `/client-ws`, 방송 모드는 같은 HTTPS 호스트의 `wss://…/proxy-ws?mode=studio`로 연결한다. 브라우저 연결은 기존 팀 로그인 세션과 `Origin` 검사를 거친다.
- AWS에서 수집기는 `live_config.chzzk_live.proxy_url`로 같은 서버의 내부 수집기 WebSocket에 연결한다. 내부 경로는 Caddy에서 차단하고, 백엔드에서 수집기 전용 자격 증명을 서버 환경변수로 검증한다. 브라우저의 로그인 쿠키를 수집기에 제공할 필요가 없다. 수집기 연결에는 치지직 채팅과 후원만 허용하고 기존 필터, 후원 우선순위, 긴급 후원 처리 규칙을 적용한다.
- Studio 방송용 `ProxyHandler`와 기존 기본 프록시의 연결·큐를 구분한다. 새 기능은 기존 Studio 백엔드에 추가하고, 수집기의 시작·재시작은 별도 systemd 서비스로 관리한다. 공개 접속 포트는 기존 HTTPS 443을 사용한다.
- 조작 화면이 연결을 끊으면 방송용 `/client-ws` 연결과 진행 중인 턴을 정리한다. 재접속 시 선택한 캐릭터와 대화방을 다시 적용한 뒤 방송 입력 처리를 재개한다.

관련 코드 · [Studio 대화 연결](../web_tool/platform/runtime/js/conversation-connection.js) · [연결 화면](../web_tool/platform/js/views/connections.js) · [WebSocket 라우트](../src/open_llm_vtuber/routes.py) · [치지직 설정](../src/open_llm_vtuber/config_manager/live.py)

## 2. 방송용 `/client-ws` 세션에 Studio 캐릭터 적용

- Studio 방송 화면에 연결된 `ProxyHandler`가 백엔드 `/client-ws` 연결을 연다. AWS 설정은 루프백에서도 인증이 필요하므로, 이미 검증된 조작 화면의 `Origin`, `__Host-studio_session`과 `studio_workspace`만 등록된 루프백 주소로 전달한다. 기존 인증 미들웨어가 팀 세션을 확인하고, 기존 `apply-studio-persona` 처리기가 `workspace_id`와 `agent_id`의 접근 권한을 확인한다. 쿠키는 URL·채팅 데이터·로그 대신 WebSocket 핸드셰이크 헤더에만 사용한다.
- Studio는 기존 순서대로 `apply-studio-persona`를 보내고, 프로필 적용 응답과 대화방 생성 또는 복원을 마친 뒤 방송 입력을 받기 시작한다. 수집기가 먼저 연결되면 초기화가 끝날 때까지 방송 입력을 보류한다. 프로필 적용에 실패하면 화면에 오류를 알리고 해당 방송 입력을 기본 캐릭터로 처리하지 않는다.
- 치지직 메시지는 기존과 같이 `text-input`으로 보낸다. 대화 서버는 방송 세션에 적용된 캐릭터의 설정을 사용하고, 관련 기억을 그 캐릭터의 저장 범위에서 조회한다. 조작 화면이 로그아웃하거나 로그인 세션이 만료되면 방송 대화 연결을 정리하고, 다시 인증된 화면이 준비되면 채팅 처리를 재개한다.

관련 코드 · [프록시 내부 연결](../src/open_llm_vtuber/proxy_handler.py) · [캐릭터 적용 요청](../web_tool/platform/runtime/js/app.js#L577) · [서버의 프로필 조회](../src/open_llm_vtuber/websocket_handler.py#L633)

## 3. 치지직이 시작한 턴을 Studio에서 재생

- `app.js`에서 화면이 응답을 받을 상태로 전환하는 부분과, 입력을 `text-input`으로 보내는 부분을 나눈다. Studio에서 직접 보낼 때는 기존 전송 경로를 쓰고, 치지직 요청은 서버의 `conversation-chain-start` 신호를 받아 같은 화면 초기화 절차를 실행한다. 이때 치지직 메시지에 대한 `text-input`을 화면에서 다시 보내지 않는다.
- 프록시가 전달하는 `user-input-transcription`에서 시청자 메시지를 받고, 서버의 시작 신호와 `request_id`로 연결한다. 현재 Studio는 자기 요청 ID와 다른 이벤트를 초기에 버린다. 방송 모드에서는 치지직 요청의 시작 신호에 붙은 ID를 먼저 활성 턴으로 등록한 후, 그 ID의 텍스트·음성·종료 이벤트를 기존 재생 경로로 처리한다. Studio에서 보낸 입력은 기존 ID로 한 번만 시작한다.
- `frontend-playback-complete`는 현재 방송 턴의 재생을 담당하는 Studio 화면에서만 전달한다. 긴급 후원이나 연결 종료로 턴이 중단되면 이전 재생과 표정 예약을 정리한다. 이전 턴의 늦은 이벤트가 새 턴을 바꾸지 않는지 확인한다.
- 기존 큐의 30초 대기 제한과 Studio의 재생 완료 대기 시간을 함께 확인한다. 정상 재생이 30초를 넘었을 때 일반 채팅이 끼어들지 않도록 방송 모드의 종료 기준을 맞추고, 완료 신호를 받지 못한 경우에는 유한한 시간 안에 큐를 복구한다.

관련 코드 · [Studio의 턴 시작과 응답 처리](../web_tool/platform/runtime/js/app.js#L469) · [대화 시작 및 재생 완료 신호](../src/open_llm_vtuber/conversations/conversation_utils.py#L153) · [프록시 요청 ID](../src/open_llm_vtuber/proxy_message_queue.py#L108)

## 검증 순서와 완료 기준

| 검증 | 확인할 결과 |
| --- | --- |
| 기존 화면과 일반 Studio 대화 | 기존 화면의 `/proxy-ws` 경로와 Studio의 일반 `/client-ws` 대화가 각각 동작한다. |
| 로컬 모의 치지직 입력 | 방송 화면에서 전송 버튼을 누르지 않고도 `안녕!` 한 건에 답변이 한 번 생성된다. 텍스트·음성·표정이 표시되고 다음 채팅도 처리된다. |
| 캐릭터와 기억 범위 | Studio 캐릭터 두 개에 서로 다른 합성 기억 노트를 넣고, 같은 질문을 각각 방송 모드로 보낸다. 선택한 캐릭터의 프로필과 그 캐릭터의 기억 범위가 적용된다. 다른 작업공간의 `agent_id`로는 시작할 수 없다. |
| 연결 순서와 재접속 | 수집기가 먼저 접속한 경우, 화면이 재접속한 경우, 캐릭터 적용이 실패한 경우를 확인한다. 프로필과 대화방 준비가 끝난 세션에서만 방송 답변을 생성한다. |
| 후원과 재생 중단 | 일반 채팅 뒤에 긴급 후원을 보내 이전 재생이 중단되고 새 답변이 재생되는지 확인한다. 음소거 시에도 완료 신호가 돌아오고 큐가 진행된다. |
| AWS 인증과 공개 접속 | 공개 HTTPS에서 팀 로그인과 방송 모드 연결을 확인한다. Caddy를 통한 수집기 경로 접근, 미인증 브라우저, 잘못된 `Origin`, 수집기 자격 증명 오류를 각각 확인한다. 방송 중 로그아웃하면 기존 방송 연결로 답변을 계속 생성하지 않는다. |
| 실제 치지직 방송 | 모의 검증 뒤 AWS에서 수집기를 실행하고 실제 방송의 채팅 한 건이 공개 Studio 화면까지 도달하는지 확인한다. 실제 모델 응답, 음성 재생, 아바타 반응을 각각 기록한다. |

### 로컬에서 확인

1. `conf.yaml`의 `system_config`에 `enable_proxy: true`를 설정한다. 서버와 모의 수집기를 같은 PowerShell 세션에서 실행할 경우, 먼저 `$env:STUDIO_CHZZK_TOKEN = [guid]::NewGuid().ToString('N')`으로 테스트용 토큰을 만든다. 별도 터미널을 사용하면 같은 값을 두 프로세스에 전달한다.
2. `python run_server.py`로 백엔드를 실행하고 `http://localhost:12393/web-tool/platform/`의 캐릭터에서 **방송** 탭을 연다. 두 프로세스가 같은 포트·토큰을 사용하도록 설정한다.
3. `python scripts/test_mock_chzzk.py --studio`로 합성 채팅과 후원을 보낸다. 12393 이외의 포트라면 `--port`를 지정한다. 직접 메시지를 쓰지 않고도 답변이 표시되는지, 이어지는 채팅이 순서대로 처리되는지 확인한다. 자동 테스트만 실행하려면 `python -m unittest discover -s tests -p test_studio_broadcast.py`를 사용한다. 자동 테스트는 실제 Gemini나 TTS 공급자를 호출하지 않는다.

### AWS 배포 설정

- 기존 `conf.yaml`의 `system_config.enable_proxy`를 켜고, `live_config.chzzk_live.channel_id`와 `proxy_url: "ws://127.0.0.1:12393/internal/chzzk-ws"`를 설정한다. 백엔드의 루프백 포트가 다르면 해당 주소를 맞춘다.
- AWS 서버의 `private/chzzk.env`에 충분히 긴 무작위 `STUDIO_CHZZK_TOKEN`을 넣고 읽기 권한을 제한한다. 백엔드와 수집기 systemd 서비스는 같은 파일을 읽는다.
- 저장소의 [Caddyfile](../deploy/Caddyfile)을 반영해 외부에서 수집기 내부 경로에 접근할 수 없는지 확인한다. [백엔드 서비스](../deploy/open-llm-vtuber.service)와 [수집기 서비스](../deploy/open-llm-vtuber-chzzk.service)를 사용자 systemd에 반영하고 백엔드를 먼저 실행한다. 수집기는 실제 방송에 연결하고, 연결이 끊기면 systemd가 재시작한다.
