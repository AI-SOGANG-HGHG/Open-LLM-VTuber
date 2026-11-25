// Our team's message contract. These are NOT built-in MCPFabric message types.
const readonly = new Set([
  'get_status', 'get_self', 'get_inventory', 'describe_scene',
  'navigation_status', 'poll_events',
])
const writes = new Map([['move_to', 'navigate_to'], ['stop', 'stop_navigation']])

export function normalizeCommand(message, allowMovement = false) {
  if (!message || typeof message !== 'object' || message.type !== 'game.command') {
    throw Object.assign(new Error('Expected game.command'), { code: 'INVALID_TYPE' })
  }
  if (!/^[A-Za-z0-9_.-]{1,96}$/.test(message.id || '')) {
    throw Object.assign(new Error('Invalid command ID'), { code: 'INVALID_ID' })
  }
  const action = message.action
  if (!readonly.has(action) && !writes.has(action)) {
    throw Object.assign(new Error('Action not allowed'), { code: 'ACTION_NOT_ALLOWED' })
  }
  if (action === 'move_to' && !allowMovement) {
    throw Object.assign(new Error('Movement disabled in .env'), { code: 'MOVEMENT_DISABLED' })
  }
  const params = message.params ?? {}
  if (params === null || Array.isArray(params) || typeof params !== 'object') {
    throw Object.assign(new Error('params must be an object'), { code: 'INVALID_PARAMS' })
  }
  if (action === 'move_to') {
    const keys = Object.keys(params).sort().join(',')
    if (keys !== 'x,y,z' || !['x', 'y', 'z'].every(k => Number.isSafeInteger(params[k]) && Math.abs(params[k]) <= 30_000_000)) {
      throw Object.assign(new Error('move_to requires safe integer x, y, z'), { code: 'INVALID_PARAMS' })
    }
  } else if (Object.keys(params).length !== 0) {
    throw Object.assign(new Error('This action does not take params'), { code: 'INVALID_PARAMS' })
  }
  return { id: message.id, action, tool: writes.get(action) || action,
    arguments: action === 'move_to' ? params : {} }
}

export function toolPayload(toolResult) {
  // Screenshot may contain base64. NEVER forward image binary to the broadcast proxy.
  if (toolResult.structuredContent !== undefined) {
    const json = JSON.stringify(toolResult.structuredContent)
    return json.length <= 8000 ? toolResult.structuredContent : { truncated: true, preview: json.slice(0, 8000) }
  }
  const text = (toolResult.content || []).filter(x => x.type === 'text').map(x => x.text).join('\n')
  if (!text) return { note: 'No text response; binary content omitted' }
  try {
    const parsed = JSON.parse(text)
    return text.length <= 8000 ? parsed : { truncated: true, preview: text.slice(0, 8000) }
  } catch {
    return { text: text.slice(0, 8000), truncated: text.length > 8000 }
  }
}
