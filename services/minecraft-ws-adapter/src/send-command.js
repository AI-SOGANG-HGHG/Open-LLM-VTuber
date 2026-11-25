// Manual stand-in for the future VTuber Agent. Run: npm.cmd run send -- get_self
import WebSocket from 'ws'
import { randomUUID } from 'node:crypto'
import { config, validateConfig } from './config.js'

validateConfig()
const action = process.argv[2] || 'get_status'
let params = {}
if (action === 'move_to') {
  const [x, y, z] = process.argv.slice(3).map(Number)
  if (![x, y, z].every(Number.isSafeInteger)) {
    console.error('Usage: npm.cmd run send -- move_to X Y Z')
    process.exit(1)
  }
  params = { x, y, z }
}
const id = randomUUID()
const socket = new WebSocket(config.wsUrl)
const timer = setTimeout(() => {
  console.error('[Test] No game.result within 40 seconds')
  process.exitCode = 1
  socket.close()
}, 40_000)

socket.on('open', () => socket.send(JSON.stringify({
  type: 'game.register', role: 'controller', token: config.token,
})))
socket.on('message', raw => {
  let msg
  try { msg = JSON.parse(raw.toString()) } catch { return }
  if (msg.type === 'game.registered' && msg.role === 'controller') {
    socket.send(JSON.stringify({ type: 'game.command', id, action, params }))
    console.log(`[Test] Sent ${action} to proxy-ws`)
    return
  }
  if (msg.type === 'game.result' && msg.id === id) {
    console.log(JSON.stringify(msg, null, 2))
    if (!msg.ok) process.exitCode = 1
    clearTimeout(timer)
    socket.close()
  }
})
socket.on('close', () => clearTimeout(timer))
socket.on('error', err => {
  console.error('[Test] WebSocket error:', err.message)
  process.exitCode = 1
  clearTimeout(timer)
})
