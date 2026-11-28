import asyncio
import unittest
from unittest.mock import AsyncMock, call, patch

from src.open_llm_vtuber.live import chzzk_live


class ChzzkRoomRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_follows_replacement_without_interrupting_an_unchanged_room(self):
        platform = chzzk_live.ChzzkLivePlatform("channel")
        platform._running = True
        events = []
        wait_for_close = asyncio.Event()

        async def listen(room, token):
            events.append(("join", room, token))
            try:
                if room == "old":
                    await wait_for_close.wait()
            finally:
                events.append(("leave", room))

        with (
            patch.object(chzzk_live, "ROOM_CHECK_INTERVAL", 0.01),
            patch.object(
                platform,
                "_fetch_chat_channel_id",
                side_effect=["old", "old", TimeoutError(), "new"],
            ),
            patch.object(
                platform, "_fetch_chat_access_token", side_effect=["first", "second"]
            ) as tokens,
            patch.object(platform, "_listen_chzzk_chat", side_effect=listen),
        ):
            await asyncio.wait_for(platform._follow_live_chat(), timeout=2)

        self.assertEqual(tokens.await_args_list, [call("old"), call("new")])
        self.assertEqual(
            events,
            [
                ("join", "old", "first"),
                ("leave", "old"),
                ("join", "new", "second"),
                ("leave", "new"),
            ],
        )

    async def test_shutdown_cancels_active_listener(self):
        platform = chzzk_live.ChzzkLivePlatform("channel")
        platform._running = True
        joined = asyncio.Event()
        left = asyncio.Event()

        async def listen(room, token):
            joined.set()
            try:
                await asyncio.Event().wait()
            finally:
                left.set()

        with (
            patch.object(
                platform, "_fetch_chat_channel_id", new=AsyncMock(return_value="room")
            ),
            patch.object(
                platform,
                "_fetch_chat_access_token",
                new=AsyncMock(return_value="token"),
            ),
            patch.object(platform, "_listen_chzzk_chat", side_effect=listen),
        ):
            task = asyncio.create_task(platform._follow_live_chat())
            try:
                await asyncio.wait_for(joined.wait(), timeout=2)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(left.is_set())
