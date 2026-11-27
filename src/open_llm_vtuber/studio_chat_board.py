"""Bounded, short-lived Chzzk chat candidates for a Studio broadcast."""

import asyncio
from dataclasses import dataclass
import re
import unicodedata

from .proxy_message_queue import ProxyMessageQueue

MAX_CANDIDATES = 5
CANDIDATE_TTL = 15
WORDS = re.compile(r"[^\W_]+", re.UNICODE)
REQUEST = re.compile(
    r"[?？]|(?:인가요|나요|할까|할래|거야|해\s*줘|주세요|부탁|알려|궁금)[.!\s]*$|(?:^|\s)(?:뭐|무슨|언제|어떤|어떻게|왜|몇)(?=\s|$)"
)


def _words(text: str) -> list[str]:
    return WORDS.findall(unicodedata.normalize("NFKC", text).casefold())


@dataclass(frozen=True)
class ChatCandidate:
    author: str
    text: str
    received: float
    words: tuple[str, ...]
    request: bool

    def payload(self) -> dict[str, str]:
        return {"author": self.author, "text": self.text}


class StudioChatBoard(ProxyMessageQueue):
    def __init__(self, *, turn_timeout: float, max_pending: int) -> None:
        super().__init__(turn_timeout=turn_timeout, max_pending=max_pending)
        self.candidates: list[ChatCandidate] = []
        self.topic: set[str] = set()
        self.board_changed = asyncio.Event()

    def set_topic(self, text: str) -> None:
        self.topic = set(_words(text))
        self.candidates.sort(key=self._rank, reverse=True)
        self.board_changed.set()

    def _rank(self, candidate: ChatCandidate) -> tuple[bool, int, float]:
        return (
            candidate.request,
            len(self.topic.intersection(candidate.words)),
            candidate.received,
        )

    def prune(self) -> None:
        cutoff = asyncio.get_running_loop().time() - CANDIDATE_TTL
        fresh = [item for item in self.candidates if item.received > cutoff]
        if fresh != self.candidates:
            self.candidates = fresh
            self.board_changed.set()

    def offer(self, author: str, text: str, received: float) -> None:
        self.prune()
        words = tuple(_words(text))
        if (
            not words
            or not any(char.isalnum() for char in text)
            or received <= asyncio.get_running_loop().time() - CANDIDATE_TTL
            or (len(words) >= 3 and len(set(words)) == 1)
            or (len(words) == 1 and len(words[0]) >= 3 and len(set(words[0])) == 1)
        ):
            return

        candidate = ChatCandidate(
            author, text, received, words, bool(REQUEST.search(text))
        )
        # Ignore punctuation and spacing when identifying repeated copies.
        key = "".join(words)
        duplicate = next(
            (item for item in self.candidates if "".join(item.words) == key), None
        )
        if duplicate and self._rank(duplicate) >= self._rank(candidate):
            return
        ranked = [item for item in self.candidates if item is not duplicate]
        ranked.append(candidate)
        ranked.sort(key=self._rank, reverse=True)
        ranked = ranked[:MAX_CANDIDATES]
        if ranked != self.candidates:
            self.candidates = ranked
            self.board_changed.set()
            self.notify_pending()

    def has_pending_messages(self) -> bool:
        self.prune()
        return super().has_pending_messages() or bool(self.candidates)

    def _take_next(self) -> tuple[dict, str | None] | None:
        if queued := super()._take_next():
            return queued
        self.prune()
        if not self.candidates:
            return None

        candidates, self.candidates = self.candidates, []
        self.board_changed.set()
        return (
            {
                "type": "text-input",
                "source": "chzzk_chat",
                "text": "\n".join(f"{item.author}: {item.text}" for item in candidates),
                "broadcast_candidates": [item.payload() for item in candidates],
                "text_stream": True,
                "require_spoken_response": True,
            },
            "collector",
        )
