# Minecraft MCPFabric × Open-LLM-VTuber proxy-ws 연결 실습

> **범위:** VLM/LLM/방송 자동 대사 제외. 기존 방송팀의 `/proxy-ws`에 게임 명령 경로를 추가하고 Minecraft 상태 조회까지 수행하는 MVP.
> **출발점:** `Open-LLM-VTuber-chzzk-team_develop.zip`에 있는 `src/open_llm_vtuber/routes.py`와 `proxy_handler.py`.

## 0. 오늘 만들 구조

```text
Agent 대신 테스트 명령 프로그램 (Node.js)
  → WebSocket(ws://127.0.0.1:12393/proxy-ws?mode=game)
  → Python GameWsRelay (권한 검사·전달·응답 라우팅)
  → Node.js Minecraft Adapter (명령 → MCP 도구 호출)
  → MCPFabric MCP HTTP (http://127.0.0.1:25600/mcp)
  → Minecraft MCPFabric Mod (http://127.0.0.1:25599)
  → 게임 데이터가 같은 경로로 돌아옴
```

**핵심 개념**

- `WebSocket`: 연결을 유지하면서 명령/결과를 양방향으로 전달하는 통신.
- `MCP`: LLM 등이 게임 도구의 목록과 입력 형식을 읽고 호출할 수 있는 프로토콜.
- `Adapter`: WebSocket `game.command`를 MCP `callTool`로 바꾸는 번역기.
- `Relay`: 게임 명령을 방송팀 대화 큐가 아닌 Minecraft Adapter로 전달하는 중계기.
- `id`: 요청과 응답을 짝지어 주는 고유 번호. 여러 요청이 섞여도 결과가 정확한 요청자에게 돌아오게 함.

**MVP와 최종 Agent의 차이:** 현재 명령 발신자는 `send-command.js` 테스트 프로그램. 나중에 VTuber Agent가 `controller` 역할로 접속해 `game.command`를 보내도록 바꾸면 된다. **현재 코드가 방송 LLM의 판단/대사까지 자동 구현한 것은 아니다.**

## 1. 팀 GitHub 저장소를 복제하고 브랜치 만들기

PowerShell 터미널: VS Code 상단 **터미널 → 새 터미널**. 먼저 저장할 폴더로 이동한다.

```powershell
cd "$env:USERPROFILE\Desktop\dev\vtuber"
git clone --recurse-submodules https://github.com/AI-SOGANG-HGHG/Open-LLM-VTuber.git
cd .\Open-LLM-VTuber
git remote -v
git fetch origin
git branch -r
git status
```

- `git clone`: GitHub 저장소 전체를 내려받고 커밋 기록을 연결한다. ZIP 파일과 달리 Git으로 push 가능.
- `--recurse-submodules`: 방송팀 저장소가 사용하는 별도 프론트엔드 Git 하위 모듈까지 받는다.
- `git remote -v`: 업로드 대상이 **팀 저장소**인지 확인. 원본 저장소에 실수로 올리지 않기 위해 필요.
- `git fetch`: 원격 브랜치 정보를 갱신하되 현재 작업 파일을 변경하지 않는다.
- `git branch -r`: `origin/team_develop` 등 실제 사용할 브랜치가 있는지 확인.
- `git status`: 현재 작업 파일 변경사항을 확인.

**`origin/team_develop`이 목록에 있다면**, 다음을 실행한다.

```powershell
git switch -c feature/mcpfabric-websocket origin/team_develop
```

`origin/team_develop`이 없다면 실제 목록을 확인해 팀원과 기준 브랜치를 합의한다. 임의로 없는 브랜치를 사용하지 않는다. 이미 같은 로컬 브랜치가 있으면 `git switch feature/mcpfabric-websocket`으로 전환한다.

`git switch -c`: 기존 브랜치 대신 **새로운 개발 브랜치**를 만들어 여기서만 변경한다.

## 2. 이 실습 코드 적용하기

받은 ZIP에는 `minecraft-websocket-mvp.patch`가 있다. ZIP 압축을 풀고 **그 파일을 Git 저장소 루트**(위 `Open-LLM-VTuber` 폴더)에 복사한다.

VS Code에서 해당 루트의 터미널에서:

```powershell
git apply --check .\minecraft-websocket-mvp.patch
```

- `git apply --check`: 실제 파일을 수정하지 않고 패치가 현재 코드에 맞는지 검사한다. **이 단계에서 오류가 나면 적용을 중단**한다. 팀 저장소 파일이 업로드된 ZIP과 달라졌을 수 있다.

검사가 성공하면:

```powershell
git apply .\minecraft-websocket-mvp.patch
Remove-Item .\minecraft-websocket-mvp.patch
git status
```

- `git apply`: 패치를 실제 소스코드에 적용한다.
- `Remove-Item`: 임시 패치 파일만 삭제한다(변경된 소스코드는 그대로 유지).

변경된 파일은 다음과 같다.

```text
src/open_llm_vtuber/routes.py              # 기존 /proxy-ws에 게임 경로 분기만 추가
src/open_llm_vtuber/game_ws_relay.py       # 새 인증/중계/결과 매칭
services/minecraft-ws-adapter/             # 새 Node.js MCPFabric 어댑터
services/minecraft-ws-adapter/src/main.js  # WebSocket 수신 + MCP 호출
services/minecraft-ws-adapter/src/mcp.js   # MCP HTTP 연결 및 callTool
services/minecraft-ws-adapter/src/send-command.js  # 가상 Agent
services/minecraft-ws-adapter/.env.example # 로컬 설정 예시
services/minecraft-ws-adapter/tests/       # 자바스크립트 단위 테스트
tests/test_game_ws_relay.py               # Python 중계 단위 테스트
docs/minecraft-websocket-mvp.md           # 이 실습 안내
```

**왜 `proxy_handler.py`를 고치지 않았나?** 기존 치지직 채팅/후원 메시지 큐와 방송 음성 흐름을 건드리지 않기 위해서다. `/proxy-ws`로 접속한 클라이언트는 원래대로 동작하고, `?mode=game` 클라이언트만 별도 라우터로 간다.

## 3. 게임팀 준비: Minecraft와 MCPFabric

1. Minecraft를 MCPFabric 모드가 설치된 Fabric/NeoForge 프로필로 실행한다.
2. 실제 싱글플레이 월드에 입장한다(LAN 열기 불필요).
3. 별도 PowerShell 터미널을 열어 Node.js가 보이는지 확인한다.

```powershell
node -v
```

전에 `fnm` 설치 이후 새 터미널에서 Node.js를 찾지 못했다면 **그 터미널에서**:

```powershell
fnm env --use-on-cd --shell powershell | Out-String | Invoke-Expression
fnm use 22
```

이제 MCPFabric 서버를 시작한다.

```powershell
$env:MCPFABRIC_TRANSPORT = 'http'
$env:MCPFABRIC_HTTP_PORT = '25600'
$env:MCPFABRIC_TOOLSETS = 'readonly'
$env:MCPFABRIC_SCRIPTS = '0'
npx.cmd -y mcpfabric-mcp-server
```

- `$env:...`: **현재 PowerShell 프로세스**와 그 자식 프로그램에 환경변수를 설정한다. 다른 터미널에는 자동으로 복사되지 않는다.
- `TRANSPORT=http`: MCP 서버를 Streamable HTTP 모드로 연다.
- `HTTP_PORT=25600`: Node 어댑터가 붙을 MCP 포트를 지정한다.
- `TOOLSETS=readonly`: 첫 테스트에서는 좌표·상태 조회만 허용한다.
- `SCRIPTS=0`: 임의 스크립트 실행 도구를 숨긴다.
- `npx.cmd`: 필요한 npm 패키지에서 MCPFabric 서버를 실행한다.

콘솔에 `streamable-HTTP transport ready on http://127.0.0.1:25600/mcp`와 같은 메시지가 보여야 한다. **이 터미널은 계속 켜 둔다.**

`25599`는 게임 모드 브리지, `25600`은 MCP 서버, `12393`은 방송팀 WebSocket이다. 서로 다른 포트다.

포트 점검(새 PowerShell):

```powershell
Test-NetConnection 127.0.0.1 -Port 25599
Test-NetConnection 127.0.0.1 -Port 25600
```

둘 다 `TcpTestSucceeded : True`라면 TCP 연결 가능. **실제 MCP 도구 성공 여부는 6단계에서 확인한다.**

## 4. 방송팀 준비: 안전한 게임 채널 토큰

**새 PowerShell 터미널**을 열고 `Open-LLM-VTuber` 팀 저장소 루트에서 작업한다. 아래 코드는 보안용 랜덤 토큰을 생성한다.

```powershell
$bytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$token = -join ($bytes | ForEach-Object { $_.ToString('x2') })
$env:MINECRAFT_WS_TOKEN = $token
$token
```

- `$bytes`: 32바이트 임시 배열.
- `RandomNumberGenerator`: 예측하기 어려운 무작위 값을 생성.
- `$token`: Python 중계기와 Node 어댑터가 **같은 비밀 값**으로 서로를 인증하기 위한 문자열.
- `$env:MINECRAFT_WS_TOKEN`: 현재 PowerShell에서 시작할 방송팀 Python 서버로 토큰을 전달.

토큰이 터미널에 출력되면 **외부에 공유하지 않는다.** Node.js 설정에 복사할 때만 사용한다. 원격 배포 시에는 별도 서비스 인증, TLS, 서버 측 네트워크 제한이 필요하다.

팀 저장소 루트에 있는 로컬 `conf.yaml`을 VS Code로 열어 `system_config:` 아래에 아래 줄을 추가하거나 기존 항목을 `true`로 바꾼다(같은 항목을 중복해서 두지 않는다).

```yaml
system_config:
  host: localhost
  port: 12393
  enable_proxy: true
```

**주의:** 위 YAML은 추가할 설정을 설명하는 발췌 예시다. 원래 `conf.yaml`의 나머지 설정(모델, TTS, 캐릭터 등)은 **절대 지우지 않는다**. `conf.yaml`은 개인 설정이라 GitHub에 커밋하지 않는다.

기존에 방송팀 개발 서버가 정상 실행되던 명령을 그대로 이용한다. 팀 Windows 환경에서 `.venv`, FFmpeg, `conf.yaml`이 갖춰져 있다면:

```powershell
.\start-local.ps1
```

`uv` 환경에서 이미 실행해 왔다면 `uv run run_server.py` 같은 팀의 기존 실행 방식도 사용 가능하다. `Proxy mode enabled - /proxy-ws endpoint will be available` 로그를 확인한다.

**중요:** 실행 파일 `start-local.ps1`을 다른 PowerShell 창에서 실행하면 `$env:MINECRAFT_WS_TOKEN`이 전달되지 않을 수 있다. **토큰을 지정한 바로 그 터미널에서 서버를 실행**한다.

## 5. Node.js Minecraft Adapter 설치 및 실행

VS Code에서 새 PowerShell을 열고 팀 저장소의 다음 폴더로 이동한다.

```powershell
cd .\services\minecraft-ws-adapter
npm.cmd install
Copy-Item .env.example .env
notepad .env
```

- `cd`: 작업 폴더를 바꾼다. npm이 올바른 `package.json`을 읽게 하려는 것.
- `npm.cmd install`: Node.js 의존성 2종(`ws`, `@modelcontextprotocol/sdk`)을 설치.
- `Copy-Item`: 비밀 값이 없는 설정 예시에서 로컬 `.env`를 만든다. **이미 파일이 있으면 다시 복사하지 말 것**.
- `notepad .env`: 메모장으로 편집. 아래 설정을 확인한다.

```dotenv
PROXY_WS_URL=ws://127.0.0.1:12393/proxy-ws?mode=game
MINECRAFT_WS_TOKEN=4단계에서_출력된_실제_토큰으로_교체
MCP_URL=http://127.0.0.1:25600/mcp
STATE_INTERVAL_MS=0
ALLOW_MOVEMENT=false
```

이 값은 예시다. `MINECRAFT_WS_TOKEN`을 실제 난수로 바꿔 `Ctrl+S`로 저장한다. `.env`는 Git에서 자동 제외된다.

이제 어댑터 실행:

```powershell
npm.cmd start
```

- `npm start`는 `package.json`의 `start` 명령을 실행한다.
- 안에서는 `node --env-file=.env src/main.js`가 실행되어 `.env` 설정을 읽고 WebSocket을 연다.
- 접속 후 `{type:'game.register',role:'minecraft',token:...}`을 보내 인증한다.
- 인증되면 `[WS] Authenticated as Minecraft adapter`가 표시된다.

Node adapter 실행 터미널도 **계속 켜 둔다**.

## 6. 상태 조회 왕복 테스트 (VLM/LLM 필요 없음)

**또 다른 터미널**을 열고 `services/minecraft-ws-adapter` 폴더로 이동한다.

```powershell
cd .\services\minecraft-ws-adapter
npm.cmd run send -- get_status
npm.cmd run send -- get_self
```

`npm.cmd run send -- get_self`를 해석하면:

- `npm.cmd run`: `package.json`에 있는 스크립트 실행.
- `send`: `src/send-command.js` 실행.
- `--`: 뒤의 `get_self`를 npm 옵션이 아니라 프로그램 인자로 전달.
- `get_self`: MCPFabric의 플레이어 체력·좌표 등을 조회하는 명령 이름.

정상 예시(실제 값은 게임에 따라 다름):

```json
{
  "type": "game.result",
  "id": "요청-고유-ID",
  "action": "get_self",
  "ok": true,
  "data": {"...": "MCPFabric에서 받은 상태 정보"}
}
```

**주의:** `game.registered`는 WebSocket 인증 성공만 의미한다. 실제 게임 연결까지 성공하려면 최종 `game.result.ok=true`와 게임 데이터가 확인되어야 한다.

같은 방식으로:

```powershell
npm.cmd run send -- get_inventory
npm.cmd run send -- describe_scene
```

## 7. 코드 이해하기

**Python `src/open_llm_vtuber/routes.py`:**

```python
if websocket.query_params.get("mode") == "game":
    await game_relay.handle_connection(websocket)
else:
    await proxy_handler.handle_client_connection(websocket)
```

- `if`: 접속 주소에 `?mode=game`이 있으면 기존 대화 기능이 아닌 게임 전용 경로로 분리한다.
- `await`: 비동기 작업이 완료되기를 기다리는 동안 다른 WebSocket 처리도 할 수 있도록 한다.

**Python `game_ws_relay.py`:**

- `game.register`의 토큰과 역할(`minecraft` 또는 `controller`)을 검사한다.
- 인증된 `controller`에서만 `game.command`를 받는다.
- 허용된 `action`만 Minecraft 어댑터에 전송한다.
- `id`별로 요청자를 기억했다가 `game.result`를 **해당 요청자에게만** 돌려준다.
- 중복 ID, 허용되지 않은 명령, 타임아웃, 어댑터 연결 종료를 처리한다.
- 기존 `text-input` 대기열과 독립적으로 동작한다.

**Node.js `src/main.js`:**

- `new WebSocket(PROXY_WS_URL)`: 방송팀 서버에 네트워크 연결.
- `ws.on('message', ...)`: 서버에서 새로운 명령이 도착할 때 실행.
- `normalizeCommand`: 명령 형식을 검사하고 게임 MCP 도구 이름으로 변환.
- `mcp.call(...)`: MCPFabric HTTP 서버에 `callTool` 실행.
- 결과를 `{type:'game.result',id,ok,data}`로 반환.

**Node.js `src/mcp.js`:**

- `StreamableHTTPClientTransport`: MCP HTTP 접속 방식을 구현한 SDK 클래스.
- `client.connect(...)`: MCP 초기화/핸드셰이크.
- `client.listTools()`: 실제 서버에서 제공하는 도구 이름을 얻음.
- `client.callTool({name,arguments})`: Minecraft 작업 실행.

## 8. 단위 테스트

두 터미널 중 어느 쪽이든 작업 중인 저장소에서 실행할 수 있다.

**Python (팀 저장소 루트):**

```powershell
uv run python -m unittest tests.test_game_ws_relay -v
```

`uv`가 없지만 Python 가상환경이 있다면 `.\.venv\Scripts\python.exe -m unittest tests.test_game_ws_relay -v`를 사용한다.

**Node.js (`services/minecraft-ws-adapter`):**

```powershell
npm.cmd test
```

테스트가 확인하는 것: 인증, 역할별 전달, 요청 ID 대응, 허용 도구 제한, 타임아웃, 게임 상태 구분. **단위 테스트 통과가 Minecraft 실물 연결 성공을 증명하지는 않는다.**

## 9. 이동 기능은 별도 테스트

기본은 조회 전용. 실제 Minecraft에서 안전한 개인 월드에 들어가서 이동 테스트를 원하는 경우에만 세 설정을 변경한다.

1. MCP 서버 실행 터미널에서 `$env:MCPFABRIC_TOOLSETS='play'`로 바꾸고 서버를 재실행한다(`MCPFABRIC_SCRIPTS='0'` 유지).
2. 방송팀 서버 실행 터미널에서 `$env:MINECRAFT_WS_ALLOW_MOVEMENT='true'`를 설정하고 서버를 재실행한다.
3. 어댑터의 `.env`에서 `ALLOW_MOVEMENT=true`로 바꾸고 `npm.cmd start`로 재실행한다.

**먼저 도구 입력 형식을 직접 확인한다.**

```powershell
npm.cmd run tools
```

MCPFabric 버전별 `navigate_to`의 `inputSchema`를 확인한 뒤 가까운 안전한 좌표를 선택한다. `move_to`는 현재 구현에서 `{x,y,z}` 정수를 MCPFabric `navigate_to`로 전달한다. 도구 스키마가 다르면 `src/protocol.js`의 변환기를 수정해야 한다.

```powershell
npm.cmd run send -- move_to 100 70 100
npm.cmd run send -- navigation_status
npm.cmd run send -- stop
```

**좌표는 예시이며 실제 게임 위치 주변 안전한 좌표로 바꿔야 한다.** `move_to` 응답 성공이 도착 완료를 의미하지 않을 수 있으므로 `navigation_status`로 추적한다. 초기 테스트에서는 게임 모드의 세계 변경·관리자 명령을 허용하지 않는다.

## 10. GitHub 브랜치에 올리기

팀 저장소 루트 PowerShell에서:

```powershell
git status
git diff --check
git add src/open_llm_vtuber/routes.py src/open_llm_vtuber/game_ws_relay.py tests/test_game_ws_relay.py services/minecraft-ws-adapter docs/minecraft-websocket-mvp.md
git status
git commit -m "feat: connect Minecraft MCPFabric through proxy websocket"
git push -u origin feature/mcpfabric-websocket
```

- `git diff --check`: 잘못된 공백/충돌 표시 등을 검사.
- `git add`: GitHub에 올릴 변경 파일을 선택. `node_modules`, `.env`, `conf.yaml`, 토큰 등은 올리지 않는다.
- `git status`: 실제로 무엇이 업로드될지 다시 확인.
- `git commit`: 현재 변경사항을 하나의 추적 가능한 작업 단위로 기록.
- `git push`: 팀 저장소 `origin`에 해당 브랜치를 업로드.
- 팀의 리뷰를 위해 GitHub에서 Pull Request를 만든다. **바로 main에 합치지 않는다.**

**실제 GitHub push는 사용자의 Windows PC에서 실행해야 한다.** 여기에 포함된 파일만으로 자동으로 GitHub 계정에 업로드되는 것은 아니다.

## 11. 오류가 나면 어디부터 볼까?

| 오류 | 뜻 | 확인 |
|---|---|---|
| `MINECRAFT_WS_TOKEN missing` / WebSocket 1008 | 토큰 없음 또는 불일치 | 서버와 Node `.env`의 동일 토큰 확인 |
| `ECONNREFUSED :12393` | 방송팀 서버에 연결하지 못함 | `enable_proxy: true`, 방송팀 서버 실행 여부 확인 |
| `ADAPTER_OFFLINE` | MCPFabric Adapter가 WebSocket에 미접속 | `npm.cmd start` 터미널 로그 확인 |
| `TIMEOUT` | 명령을 보냈지만 결과를 받지 못함 | MCP 서버 실행 여부와 도구 실행 시간 확인 |
| `ECONNREFUSED :25600` | MCPFabric MCP HTTP 서버 미실행 | `npx.cmd -y mcpfabric-mcp-server` 콘솔 확인 |
| `bridge not reachable :25599` | MCP 서버가 게임 모드에 접근하지 못함 | Minecraft 모드/월드 접속, `bridge.json` 확인 |
| `TOOL_UNAVAILABLE` | 도구가 숨겨졌거나 버전 불일치 | MCP toolsets와 `npm.cmd run tools` 확인 |
| `npm` 명령 인식 실패 | 새 PowerShell에서 fnm 미활성화 | `fnm env ...` → `fnm use 22`; `npm.cmd` 사용 |
| `git apply --check` 실패 | ZIP 시점과 실제 브랜치 코드가 다름 | 패치를 억지로 적용하지 말고 변경 내용 비교 |

## 12. 이번 버전에서 하지 않는 것

- VLM/스크린샷 전송, 게임 공간 맵 생성.
- Agent가 자율적으로 다음 행동을 결정하는 로직.
- 장시간 채굴 작업 큐, 재시작 후 작업 복구, 정확한 동작 완료 확인.
- 치지직 채팅을 게임 명령으로 자동 전환하는 기능(안전한 명령 승인 흐름 필요).
- 외부 클라우드의 방송 서버 접속. 현재는 같은 Windows PC의 `localhost` 테스트 기준.

## 참고

- [MCPFabric 원본](https://github.com/denfry/mcpfabric)
- [Open-LLM-VTuber 방송 개발 문서](https://docs.llmvtuber.com/en/docs/development-guide/live-dev/)
- [MCP TypeScript SDK](https://ts.sdk.modelcontextprotocol.io/client)
