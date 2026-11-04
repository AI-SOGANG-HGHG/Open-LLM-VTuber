import asyncio
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from src.open_llm_vtuber.service_context import ServiceContext
from src.open_llm_vtuber.websocket_handler import WebSocketHandler
from src.open_llm_vtuber.message_handler import MessageHandler


class ConnectionCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_turn_is_cancelled_before_its_context_closes_and_other_clients_survive(
        self,
    ):
        handler = WebSocketHandler(ServiceContext())
        handler.chat_group_manager = SimpleNamespace(get_client_group=lambda uid: None)
        order = []
        started = asyncio.Event()

        async def conversation():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                order.append("cancelled")

        first = SimpleNamespace(
            close=AsyncMock(side_effect=lambda: order.append("closed"))
        )
        second = SimpleNamespace(close=AsyncMock())
        handler.client_contexts.update(first=first, second=second)
        handler.current_conversation_tasks["first"] = asyncio.create_task(
            conversation()
        )
        await started.wait()
        with patch(
            "src.open_llm_vtuber.websocket_handler.handle_client_disconnect",
            new_callable=AsyncMock,
        ):
            await handler.handle_disconnect("first")
            await handler.handle_disconnect("first")
        self.assertEqual(order, ["cancelled", "closed"])
        first.close.assert_awaited_once()
        second.close.assert_not_awaited()
        self.assertIs(handler.client_contexts["second"], second)

    async def test_disconnected_playback_waiter_does_not_recreate_client_caches(self):
        handler = MessageHandler()
        waiter = asyncio.create_task(handler.wait_for_response("client", "playback"))
        await asyncio.sleep(0)
        handler.cleanup_client("client")
        self.assertIsNone(await asyncio.wait_for(waiter, timeout=1))
        self.assertNotIn("client", handler._response_events)
        self.assertNotIn("client", handler._response_data)

    async def test_agent_closes_even_when_mcp_cleanup_fails(self):
        context = ServiceContext()
        agent = SimpleNamespace(close=AsyncMock())
        context.agent_engine = agent
        context.mcp_client = SimpleNamespace(
            aclose=AsyncMock(side_effect=RuntimeError("fixture MCP failure"))
        )
        with self.assertRaisesRegex(RuntimeError, "fixture MCP failure"):
            await context.close()
        agent.close.assert_awaited_once()
        await context.close()
        agent.close.assert_awaited_once()

    async def test_timed_out_waiter_does_not_leave_an_empty_cache(self):
        handler = MessageHandler()
        self.assertIsNone(
            await handler.wait_for_response("client", "playback", timeout=0.001)
        )
        self.assertNotIn("client", handler._response_events)
        self.assertNotIn("client", handler._response_data)
