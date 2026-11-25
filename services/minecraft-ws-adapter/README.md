# Minecraft WebSocket Adapter

이 폴더는 방송팀 저장소의 `proxy-ws` ↔ MCPFabric 사이에서 명령을 변환하는 Node.js 프로그램이다.

**처음 실행한다면:** [전체 실습 안내](../../docs/minecraft-websocket-mvp.md)를 처음부터 따라 할 것.

## 빠른 실행

```powershell
npm.cmd install
Copy-Item .env.example .env
notepad .env
npm.cmd start
```

또 다른 터미널에서:

```powershell
npm.cmd run send -- get_status
npm.cmd run send -- get_self
```

**주의:** 먼저 Minecraft 모드, MCP HTTP 서버(25600), 팀 방송 서버(12393), 동일 토큰 설정이 완료되어야 한다. VLM이나 LLM은 필요 없다. `.env`는 절대 Git에 올리지 않는다.
