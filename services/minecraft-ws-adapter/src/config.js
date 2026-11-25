// Values from .env are loaded by Node.js --env-file=.env (Node 22+).
export const config = {
  wsUrl: process.env.PROXY_WS_URL || 'ws://127.0.0.1:12393/proxy-ws?mode=game',
  token: process.env.MINECRAFT_WS_TOKEN || '',
  mcpUrl: process.env.MCP_URL || 'http://127.0.0.1:25600/mcp',
  allowMovement: process.env.ALLOW_MOVEMENT === 'true',
  stateIntervalMs: Number(process.env.STATE_INTERVAL_MS || 0),
}

export function validateConfig() {
  const ws = new URL(config.wsUrl)
  const mcp = new URL(config.mcpUrl)
  if (!['ws:', 'wss:'].includes(ws.protocol)) throw Error('PROXY_WS_URL must start with ws:// or wss://')
  if (!['http:', 'https:'].includes(mcp.protocol)) throw Error('MCP_URL must be http(s)://')
  if (!config.token || config.token.length < 20 || config.token.startsWith('REPLACE_')) {
    throw Error('Set MINECRAFT_WS_TOKEN in .env to the SAME random token as the Python server (20+ chars)')
  }
  if (!Number.isSafeInteger(config.stateIntervalMs) || config.stateIntervalMs < 0) {
    throw Error('STATE_INTERVAL_MS must be a nonnegative integer')
  }
}
