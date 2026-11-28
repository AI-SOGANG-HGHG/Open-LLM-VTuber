"""Batch Chzzk chat candidates between turns for a Studio broadcast."""

import asyncio
from dataclasses import dataclass
import re
import unicodedata

from .proxy_message_queue import ProxyMessageQueue

MAX_CANDIDATES = 5
CANDIDATE_TTL = 15
WORDS = re.compile(r"[^\W_]+", re.UNICODE)
BROADCAST_FEEDBACK = re.compile(
    r"(?:소리|음성|마이크|볼륨|화면|영상|방송).{0,16}"
    r"(?:안\s*(?:들|보|나)|작아|작게|작습니다|커요|큽니다|멈|끊|깨져|밀려)"
)
REQUEST = re.compile(
    r"[?？]|(?:인가요|나요|까요|할까|할래|거야|줘요?|주세요|해\s*봐|부탁해?|알려|궁금)[.!~\s]*$"
    r"|(?:^|\s)(?:뭐|무엇|무슨|언제|어디|누구|얼마|어떤|어떻게|왜|몇)"
)


def _words(text: str) -> list[str]:
    return WORDS.findall(unicodedata.normalize("NFKC", text).casefold())


@dataclass(frozen=True)
class ChatCandidate:
    text: str
    author: str
    received: float
    words: tuple[str, ...]
    request: bool
    feedback: bool


class StudioChatBoard(ProxyMessageQueue):
    def __init__(self, *, max_pending: int) -> None:
        super().__init__(turn_timeout=None, max_pending=max_pending)
        self.candidates: list[ChatCandidate] = []
        self.topic: set[str] = set()

    def set_topic(self, text: str) -> None:
        self.topic = set(_words(text))
        self.candidates.sort(key=self._rank, reverse=True)

    def _rank(self, candidate: ChatCandidate) -> tuple[bool, int, bool, float]:
        return (
            candidate.feedback,
            len(self.topic.intersection(candidate.words)),
            candidate.request,
            candidate.received,
        )

    def _prune(self) -> float:
        cutoff = asyncio.get_running_loop().time() - CANDIDATE_TTL
        self.candidates = [item for item in self.candidates if item.received > cutoff]
        return cutoff

    def offer(self, text: str, author: str, received: float) -> None:
        cutoff = self._prune()
        words = tuple(_words(text))
        if (
            received <= cutoff
            or not words
            or not any(char.isalnum() for char in text)
            or (len(words) >= 3 and len(set(words)) == 1)
            or (len(words) == 1 and len(words[0]) >= 3 and len(set(words[0])) == 1)
        ):
            return

        candidate = ChatCandidate(
            text, author, received, words,
            bool(REQUEST.search(text)), bool(BROADCAST_FEEDBACK.search(text)),
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
            self.notify_pending()

    def has_pending_messages(self) -> bool:
        self._prune()
        return super().has_pending_messages() or bool(self.candidates)

    def _take_next(self) -> tuple[dict, str | None] | None:
        if queued := super()._take_next():
            return queued
        self._prune()
        if not self.candidates:
            return None

        count = 1 if self.candidates[0].feedback else len(self.candidates)
        candidates = self.candidates[:count]
        del self.candidates[:count]
        return (
            {
                "type": "text-input",
                "source": "chzzk_chat",
                "text": "\n".join(item.text for item in candidates),
                "broadcast_candidates": [
                    {"author": item.author, "text": item.text} for item in candidates
                ],
                "text_stream": True,
                "require_spoken_response": True,
            },
            "collector",
        )

    def clear(self) -> None:
        super().clear()
        self.candidates.clear()
