import WebSocket from 'ws'
import { config, validateConfig } from './config.js'
import { McpFabricClient } from './mcp.js'
import { normalizeCommand } from './protocol.js'

validateConfig()
const mcp = new McpFabricClient(config.mcpUrl)
let socket = null
let registered = false
let stopping = false
let busy = false
let reconnectTimer = null
let pollTimer = null

function send(message) {
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(message))
}

async function runCommand(message) {
  // Exactly one MCP call at a time in this introductory MVP.
  if (busy) {
    send({ type: 'game.result', id: message.id, ok: false,
      error: { code: 'BUSY', message: 'Another MCP call is running' } })
    return
  }
  busy = true
  try {
    const cmd = normalizeCommand(message, config.allowMovement)
    const data = await mcp.call(cmd.tool, cmd.arguments)
    send({ type: 'game.result', id: cmd.id, action: cmd.action, ok: true, data })
    console.log(`[Game] ${cmd.action}: success`)
  } catch (err) {
    send({ type: 'game.result', id: message.id, action: message.action, ok: false,
      error: { code: err.code || 'MCP_ERROR', message: err.message.slice(0, 450) } })
    console.error('[Game] Error:', err.message)
  } finally {
    busy = false
  }
}

function connect() {
  if (stopping) return
  registered = false
  socket = new WebSocket(config.wsUrl, { maxPayload: 128 * 1024 })
  socket.on('open', () => {
    // First packet identifies THIS connection as the game adapter.
    send({ type: 'game.register', role: 'minecraft', token: config.token })
  })
  socket.on('message', raw => {
    let data
    try { data = JSON.parse(raw.toString()) } catch { return }
    if (data.type === 'game.registered' && data.role === 'minecraft') {
      registered = true
      console.log('[WS] Authenticated as Minecraft adapter')
      return
    }
    if (registered && data.type === 'game.command') void runCommand(data)
  })
  socket.on('error', err => console.error('[WS] Error:', err.message))
  socket.on('close', () => {
    registered = false
    if (!stopping) {
      console.log('[WS] Disconnected; reconnecting in 3 seconds')
      reconnectTimer = setTimeout(connect, 3000)
    }
  })
}

// Optional low-frequency push; default is OFF to reduce needless MCP calls.
async function broadcastState() {
  if (!registered || busy) return
  busy = true
  try {
    const data = await mcp.call('get_self', {})
    send({ type: 'game.state', timestamp: new Date().toISOString(), data })
  } catch (err) { console.warn('[Game] State poll error:', err.message) }
  finally { busy = false }
}

console.log(`[Adapter] WebSocket: ${config.wsUrl}`)
console.log(`[Adapter] MCP server: ${config.mcpUrl}`)
console.log(`[Adapter] Movement enabled: ${config.allowMovement}`)
connect()
if (config.stateIntervalMs > 0) pollTimer = setInterval(() => void broadcastState(), config.stateIntervalMs)

async function shutdown() {
  stopping = true
  clearTimeout(reconnectTimer)
  clearInterval(pollTimer)
  socket?.close()
  await mcp.close()
}
process.once('SIGINT', () => void shutdown())
process.once('SIGTERM', () => void shutdown())
