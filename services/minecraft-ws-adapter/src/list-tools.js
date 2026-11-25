// Inspect actual MCPFabric tool input schemas before enabling movement.
import { config } from './config.js'
import { McpFabricClient } from './mcp.js'
const client = new McpFabricClient(config.mcpUrl)
try {
  const tools = await client.listTools()
  for (const tool of tools) {
    if (['get_status', 'get_self', 'navigate_to', 'stop_navigation'].includes(tool.name)) {
      console.log(JSON.stringify(tool, null, 2))
    }
  }
} catch (err) {
  console.error('MCP connection failed:', err.message)
  process.exitCode = 1
} finally {
  await client.close()
}
