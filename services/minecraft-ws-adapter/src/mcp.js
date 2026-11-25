import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'
import { toolPayload } from './protocol.js'

export class McpFabricClient {
  constructor(url) {
    this.url = url
    this.client = null
    this.connecting = null
    this.tools = new Map()
  }

  async connect() {
    if (this.client) return
    if (this.connecting) return this.connecting
    this.connecting = (async () => {
      const c = new Client({ name: 'minecraft-ws-adapter', version: '0.1.0' })
      try {
        await c.connect(new StreamableHTTPClientTransport(new URL(this.url)))
        const list = await c.listTools()
        this.tools = new Map(list.tools.map(t => [t.name, t]))
        this.client = c
        console.log(`[MCP] Connected; available tools: ${this.tools.size}`)
      } catch (err) {
        await c.close().catch(() => {})
        throw err
      }
    })()
    try { await this.connecting } finally { this.connecting = null }
  }

  async call(name, arguments_ = {}) {
    await this.connect()
    if (!this.tools.has(name)) {
      throw Object.assign(new Error(`MCP tool ${name} unavailable (check toolsets)`), { code: 'TOOL_UNAVAILABLE' })
    }
    let result
    try {
      result = await this.client.callTool({ name, arguments: arguments_ })
    } catch (err) {
      await this.close()  // Transport may have gone away; reconnect next request.
      throw err
    }
    const data = toolPayload(result)
    if (result.isError) {
      throw Object.assign(new Error(`MCP tool error: ${JSON.stringify(data).slice(0, 350)}`), { code: 'MCP_TOOL_ERROR' })
    }
    return data
  }

  async listTools() {
    await this.connect()
    return [...this.tools.values()].map(tool => ({ name: tool.name, inputSchema: tool.inputSchema }))
  }

  async close() {
    const existing = this.client
    this.client = null
    this.tools = new Map()
    if (existing) await existing.close().catch(() => {})
  }
}
