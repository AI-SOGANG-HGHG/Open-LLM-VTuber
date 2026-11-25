import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeCommand, toolPayload } from '../src/protocol.js'

test('get_self allowed without arguments', () => {
  assert.deepEqual(normalizeCommand({ type: 'game.command', id: 'abc', action: 'get_self', params: {} }).tool, 'get_self')
})
test('arbitrary tool is blocked', () => {
  assert.throws(() => normalizeCommand({ type: 'game.command', id: 'x', action: 'run_command' }), /not allowed/)
})
test('movement is disabled by default', () => {
  assert.throws(() => normalizeCommand({ type: 'game.command', id: 'x', action: 'move_to', params: {x:0,y:64,z:0} }), /disabled/)
})
test('move_to maps to navigate_to if enabled', () => {
  assert.equal(normalizeCommand({ type: 'game.command', id: 'x', action: 'move_to', params: {x:0,y:64,z:0} }, true).tool, 'navigate_to')
})
test('screenshot image data omitted from results', () => {
  assert.deepEqual(toolPayload({ content: [{ type:'image',data:'secretBase64',mimeType:'image/png' }] }), { note: 'No text response; binary content omitted' })
})
