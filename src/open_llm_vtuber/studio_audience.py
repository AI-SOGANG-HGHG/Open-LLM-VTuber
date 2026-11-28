"""Choice questions shared by the Studio broadcaster and its dialogue prompts."""

import random
import re
from dataclasses import dataclass, field
from uuid import uuid4


# The broadcaster rotates these questions; option order also defines 1번 and 2번.
QUESTIONS = {
    "late_snack": ("오늘 야식으로 뭘 먹을까?", ("라면", "치킨")),
    "travel": ("같이 여행 간다면 어디가 좋을까?", ("바다", "산")),
    "weather": ("산책하기에 어느 계절이 더 좋아?", ("봄", "가을")),
    "minecraft_shelter": (
        "마인크래프트 첫날 밤이야. 우리 어디에 집을 지을까?",
        ("동굴", "나무 위"),
    ),
    "stock_gossip": (
        "갑자기 목돈이 생겼어. 너희라면 어느 회사 주식을 살래?",
        ("SK하이닉스", "삼성전자"),
    ),
    "fish_bread": (
        "우리 붕어빵 가게에서 신메뉴 하나만 낸다면 뭘로 속을 채울까?",
        ("피자", "떡볶이"),
    ),
    "friend_or_date": (
        "10년 지기 여사친이나 남사친이 내 생일에 단둘이 저녁 먹자고 했어. 이거 우정이야, 플러팅이야?",
        ("우정", "플러팅"),
    ),
    "chinese_food": (
        "오늘은 중식이 땡기네. 짜장면 먹을까 짬뽕 먹을까?",
        ("짜장면", "짬뽕"),
    ),
}
ANSWER_SECONDS = 10


def shuffled_topics():
    """Shuffle each round, including the first question of a new session."""
    previous = None
    while QUESTIONS:
        topics = random.sample(list(QUESTIONS), k=len(QUESTIONS))
        if len(topics) > 1 and topics[0] == previous:
            topics[0], topics[-1] = topics[-1], topics[0]
        yield from topics
        previous = topics[-1]


@dataclass
class AudienceQuestion:
    topic: str
    request_id: str = field(default_factory=lambda: uuid4().hex)
    votes: list[int] = field(default_factory=lambda: [0, 0])
    opened_at: float | None = None
    closes_at: float | None = None

    def collect(self, text: str, received_at: float) -> bool:
        if (
            self.opened_at is None
            or received_at < self.opened_at
            or (self.closes_at is not None and received_at >= self.closes_at)
        ):
            return False
        _, options = QUESTIONS[self.topic]
        for index, option in enumerate(options, start=1):
            answer = (
                rf"(?:저는\s*|전\s*)?(?:{re.escape(option)}|{index}(?:\s*번)?)"
                r"(?:이요|요|이야|입니다)?[.!~！？\s]*"
            )
            if re.fullmatch(answer, text.strip(), re.IGNORECASE):
                self.votes[index - 1] += 1
                return True
        return False


def audience_prompt(reason: str, topic: object, votes: object) -> str | None:
    if not isinstance(topic, str) or topic not in QUESTIONS:
        return None
    question, (first, second) = QUESTIONS[topic]
    if reason == "audience_question":
        return (
            f"방송에서 '{question}'라는 질문을 네 말투로 시청자에게 건네. "
            f"1번 {first}, 2번 {second}를 이 순서로 둘 다 정확히 말하고 "
            f"{ANSWER_SECONDS}초 동안 채팅에 번호나 선택지 이름으로 답해 달라고 해."
        )
    if (
        not isinstance(votes, list)
        or len(votes) != 2
        or not all(type(count) is int and count >= 0 for count in votes)
    ):
        return None
    return (
        f"방금 네가 시청자들에게 물은 질문은 '{question}'야. "
        f"채팅 집계 결과는 {first} {votes[0]}표, {second} {votes[1]}표야. "
        "실제 표수와 동점 여부를 지키면서 네 말투로 한두 문장 반응해. "
        "시청자 이름이나 발언을 지어내거나 다시 투표를 시작하지 마."
    )
