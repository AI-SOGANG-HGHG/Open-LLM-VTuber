"""Safety filter for live chat messages and viewer nicknames.

Detects banned words, risky topics, and prompt-injection attempts in chat
text and author nicknames before they are forwarded to the LLM.
"""

from collections.abc import Iterable, Mapping
import re
import unicodedata

from loguru import logger

ANONYMOUS_NAME = "익명시청자"
MAX_TEXT_LENGTH = 300
MAX_AUTHOR_LENGTH = 20

# Characters that let a nickname imitate prompt structure ("[SYSTEM]",
# "<tag>", "role:"). Checked after normalization, so fullwidth forms count.
AUTHOR_FORBIDDEN_CHARS = frozenset("[]<>{}:|`")

# Placeholder nicknames that carry no identity and map to ANONYMOUS_NAME.
_EMPTY_AUTHOR_NAMES = frozenset({"anonymous"})

# Banned words per category, matched as substrings of _despace() output.
# Entries are lowercase; a space inside an entry matches zero or more spaces.
# Avoid short stems that occur inside everyday words (e.g. "씹" in "껌 씹어",
# "시바" in "시바견", "야스" in "야스오").
BANNED_WORDS: dict[str, tuple[str, ...]] = {
    "profanity": (
        "씨발",
        "시발",
        "씨빨",
        "씨팔",
        "시팔",
        "ㅅㅂ",
        "ㅆㅂ",
        "병신",
        "븅신",
        "빙신",
        "ㅂㅅ",
        "ㅄ",
        "개새",
        "개새끼",
        "개새기",
        "씹새",
        "씹년",
        "엿먹어",
        "좆같",
        "좆",
        "좃같",
        "지랄",
        "ㅈㄹ",
        "존나",
        "ㅈㄴ",
        "미친놈",
        "미친년",
        "니애미",
        "느금마",
        "엠창",
        "fuck",
        "shit",
        "bitch",
        "asshole",
    ),
    "hate": (
        "한남충",
        "김치녀",
        "된장녀",
        "맘충",
        "급식충",
        "틀딱",
        "일베충",
        "메갈",
        "짱깨",
        "쪽바리",
        "깜둥이",
        "nigger",
        "nigga",
        "faggot",
        "retard",
    ),
    "politics": (
        "정치",
        "대통령",
        "탄핵",
        "국민의힘",
        "국힘",
        "민주당",
        "정의당",
        "좌파",
        "우파",
        "좌빨",
        "수꼴",
        "빨갱이",
        "윤석열",
        "이재명",
        "문재인",
        "박근혜",
    ),
    "unsafe": (
        "섹스",
        "야동",
        "포르노",
        "porn",
        "hentai",
        "누드",
        "nude",
        "자살",
        "자해",
        "죽고 싶",
        "kill yourself",
        "주민등록번호",
        "주민번호",
        "계좌번호",
        "마약",
        "대마초",
        "필로폰",
    ),
}

# Everyday words that contain a banned word. Removed before matching.
ALLOWED_EXCEPTIONS: tuple[str, ...] = (
    "시발점",
    "시발역",
    "시발택시",
    "시발자동차",
    "자살골",
    "정치외교",
    "마약김밥",
)

# Prompt-injection patterns, applied to _normalize() output (lowercase,
# single spaces). Group order is the check order and defines the reason code.
# False-positive rule: a bare verb such as "무시해" is allowed; a directive
# verb must appear together with a target (명령/프롬프트/규칙, instructions...).
INJECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "ignore": (
        r"(이전|위의|위에\s*있는|모든|기존).{0,10}"
        r"(명령|지시|프롬프트|설정|규칙).{0,10}(무시|잊)",
        r"(명령|지시|프롬프트|규칙)(을|를|은|는)?\s*(전부|다|모두)?\s*(무시|잊어|잊고|어겨)",
        r"ignore\s+(all\s+|any\s+|the\s+|your\s+|my\s+)*"
        r"(previous|prior|above|earlier|preceding|instructions|rules|prompts?)\b",
        r"disregard\s+(all\s+|any\s+|the\s+|your\s+)*"
        r"(previous|prior|above|instructions|rules|prompts?)\b",
        r"forget\s+(all\s+|about\s+)?(everything|your\s+(instructions|rules|prompt))",
    ),
    "leak": (
        r"(시스템|system)\s*(프롬프트|prompt)",
        r"(프롬프트|prompt|지시문).{0,10}(알려|보여|출력|말해|공개|뭐야|뭐임|읊어)",
        r"(reveal|show|print|tell|repeat|display|output)\s+(me\s+)?"
        r"(your|the\s+system|the\s+initial|the\s+hidden)\s+(prompt|instructions|rules)",
        r"\b(your|ur)\s+(instructions|system\s+message|initial\s+prompt)",
    ),
    "role": (
        r"^\s*(system|assistant|user|developer|시스템)\s*:",
        r"(^|[\s\[(<{])(system|assistant|developer)\s*:",
        r"<\|?\s*im_(start|end)",
        r"\[/?inst\]",
        r"###\s*(instruction|system)",
        r"<\s*/?\s*system\s*>",
        r"jailbreak",
        r"탈옥",
        r"(개발자|developer|dev)\s*(모드|mode)",
        r"\bdan\s*(mode|모드)",
        r"do\s*anything\s*now",
        r"(너는|넌)\s*(이제|지금)\s*(부터)?.{0,15}"
        r"(역할|인격|페르소나|ai|인공지능|봇|어시스턴트)",
        r"(이제|지금)\s*부터\s*(너는|넌).{0,15}"
        r"(역할|인격|페르소나|ai|인공지능|봇|어시스턴트)",
        r"(역할|인격|페르소나)(을|를)?\s*(바꿔|바꾸|변경|버려|해제|잊어)",
        r"(from\s+now\s+on|starting\s+now)\s*,?\s*you\s+(are|will|must)",
        r"you\s+are\s+now\s+(a\s+|an\s+|in\s+)?"
        r"(dan|ai|assistant|bot|unrestricted|unfiltered|evil|jailbroken)",
        r"pretend\s+(you\s+are|to\s+be\s+(a\s+|an\s+)?"
        r"(different|evil|unrestricted|unfiltered|dan|ai|bot))",
    ),
    "command": (
        r"(시스템|system|관리자|admin|운영자)\s*(명령|권한|command|override)",
        r"\boverride\b",
        r"\[\s*(system|시스템|admin|관리자)",
        r"(제한|필터|검열|안전\s*장치)(을|를|이|가)?\s*(풀어|해제|없애|꺼|끄|무시|우회)",
    ),
}

# Patterns applied to _compact() output (no spaces or symbols) to catch
# splitting tricks such as "i g n o r e previous" or "시 스 템 프 롬 프 트".
# Kept as specific keyword chains, since compact text merges word boundaries.
COMPACT_INJECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "ignore": (
        r"(이전|위의|위에있는|모든|기존).{0,8}(명령|지시|프롬프트|설정|규칙).{0,8}(무시|잊)",
        r"(명령|지시|프롬프트|규칙)(을|를)?(전부|다|모두)?(무시|잊어|잊고)",
        r"ignore(all|any|the|your|my)*"
        r"(previous|prior|above|earlier|preceding|instructions|rules|prompts?)",
        r"disregard(all|any|the|your)*(previous|prior|above|instructions|rules|prompts?)",
        r"forget(all|about)?(everything|yourinstructions|yourrules|yourprompt)",
    ),
    "leak": (
        r"(시스템|system)(프롬프트|prompt)",
        r"(프롬프트|prompt|지시문).{0,6}(알려|보여|출력|말해|공개|뭐야|뭐임|읊어)",
        r"(reveal|show|print|tell|repeat|display|output)(me)?"
        r"(your|thesystem|theinitial|thehidden)(prompt|instructions|rules)",
    ),
    "role": (
        r"jailbreak",
        r"탈옥",
        r"(개발자|developer)(모드|mode)",
        r"dan(mode|모드)",
        r"doanythingnow",
        r"fromnowonyou(are|will|must)",
    ),
    "command": (
        r"(시스템|system|관리자|admin|운영자)(명령|권한|command|override)",
        r"(제한|필터|검열|안전장치)(을|를|이|가)?(풀어|해제|없애|꺼|끄|무시|우회)",
    ),
}

# Characters that render as blank or nothing but are not caught by Unicode
# category checks (Hangul fillers are category "Lo", braille blank is "So").
_INVISIBLE_CHARS = frozenset(
    {
        "\u115f",  # HANGUL CHOSEONG FILLER
        "\u1160",  # HANGUL JUNGSEONG FILLER
        "\u3164",  # HANGUL FILLER (common "blank" nickname trick)
        "\uffa0",  # HALFWIDTH HANGUL FILLER
        "\u2800",  # BRAILLE PATTERN BLANK
    }
)

# NFKC maps compatibility jamo (ㅅ, U+3145) to conjoining jamo (U+1109),
# which would break matching of initial-consonant slang such as "ㅅㅂ".
# Runs of compatibility jamo are therefore kept out of NFKC.
_COMPAT_JAMO_RUN = re.compile(r"([ㄱ-ㆎ]+)")


def _build_halfwidth_jamo_table() -> dict[int, str]:
    """Build a translation table from halfwidth to compatibility Hangul jamo.

    Returns:
        A ``str.translate`` table mapping halfwidth jamo code points
        (e.g. U+FFA1) to compatibility jamo characters (e.g. U+3131).
    """
    table: dict[int, str] = {}
    for code_point in range(0xFFA1, 0xFFDD):
        name = unicodedata.name(chr(code_point), "")
        if not name.startswith("HALFWIDTH HANGUL LETTER "):
            continue
        try:
            table[code_point] = unicodedata.lookup(name.removeprefix("HALFWIDTH "))
        except KeyError:
            continue
    return table


_HALFWIDTH_JAMO_TABLE = _build_halfwidth_jamo_table()

# Characters kept by _compact: ASCII letters/digits, Hangul syllables,
# and Hangul compatibility jamo.
_NON_COMPACT_CHARS = re.compile(r"[^0-9a-z가-힣ㄱ-ㆎ]")


def _nfkc_preserving_jamo(text: str) -> str:
    """Apply NFKC to everything except runs of Hangul compatibility jamo.

    Args:
        text: The string to normalize.

    Returns:
        The NFKC-normalized string with compatibility jamo left untouched.
    """
    parts = _COMPAT_JAMO_RUN.split(text)
    # re.split with a capturing group puts the jamo runs at odd indices.
    return "".join(
        part if index % 2 else unicodedata.normalize("NFKC", part)
        for index, part in enumerate(parts)
    )


def _normalize(value: object) -> str:
    """Normalize text so that visual tricks cannot bypass pattern matching.

    Steps: coerce to str, drop invisible fillers, unify halfwidth jamo,
    NFKC (fullwidth -> ASCII etc.), lowercase, remove control/format
    characters and combining marks, turn whitespace into single spaces.

    Args:
        value: Raw chat text or nickname. ``None`` becomes an empty string.

    Returns:
        The normalized string.
    """
    if value is None:
        return ""
    text = str(value)
    text = "".join(ch for ch in text if ch not in _INVISIBLE_CHARS)
    text = text.translate(_HALFWIDTH_JAMO_TABLE)
    text = _nfkc_preserving_jamo(text).lower()

    cleaned: list[str] = []
    for ch in text:
        if ch.isspace():
            cleaned.append(" ")
            continue
        category = unicodedata.category(ch)
        # C*: control, format (zero-width), surrogate, private use, unassigned.
        # Mn: combining marks used for zalgo / strike-through obfuscation.
        if category.startswith("C") or category == "Mn":
            continue
        if ch in _INVISIBLE_CHARS:  # NFKC may produce fillers (U+FFA0 -> U+1160)
            continue
        cleaned.append(ch)

    return " ".join("".join(cleaned).split())


def _compact(value: object) -> str:
    """Normalize, then keep only ASCII letters/digits and Hangul.

    Removing spaces, punctuation, and symbols defeats splitting tricks such
    as "시 발", "시.발", or "s.y.s.t.e.m".

    Args:
        value: Raw or already-normalized text (normalization is idempotent).

    Returns:
        The compacted string.
    """
    return _NON_COMPACT_CHARS.sub("", _normalize(value))


def _despace(value: object) -> str:
    """Normalize, strip symbols inside words, and join runs of 1-char tokens.

    Unlike _compact, real word boundaries are kept, so "다시 발표" does not
    turn into "다시발표" (which contains "시발"). Spacing tricks built from
    single characters are still undone: "시 발" -> "시발", "ㅅ ㅂ" -> "ㅅㅂ",
    "시.발" -> "시발".

    Args:
        value: Raw or already-normalized text.

    Returns:
        Space-separated tokens made only of characters kept by _compact.
    """
    merged: list[str] = []
    run = ""
    for raw_token in _normalize(value).split(" "):
        token = _NON_COMPACT_CHARS.sub("", raw_token)
        if not token:
            continue
        if len(token) == 1:
            run += token
            continue
        if run:
            merged.append(run)
            run = ""
        merged.append(token)
    if run:
        merged.append(run)
    return " ".join(merged)


def _word_regex(words: Iterable[str]) -> re.Pattern[str] | None:
    """Compile literal words into one case-insensitive alternation regex.

    Args:
        words: Literal words. A space inside a word matches zero or more
            whitespace characters.

    Returns:
        The compiled pattern, or None if no non-blank word was given.
    """
    parts = [
        r"\s*".join(re.escape(piece) for piece in word.lower().split())
        for word in words
        if word.strip()
    ]
    if not parts:
        return None
    return re.compile("|".join(parts), re.IGNORECASE)


def _preview(value: object, limit: int = 50) -> str:
    """Build a short preview of a value for logs without ever raising.

    Args:
        value: Any value, typically the raw chat text.
        limit: Maximum number of characters to keep.

    Returns:
        The ``repr`` of the truncated text, or ``"<unprintable>"``.
    """
    try:
        return repr(str(value)[:limit])
    except Exception:
        return "<unprintable>"


def _clean_display(text: str) -> str:
    """Strip invisible/format characters but keep the original spelling.

    Args:
        text: A nickname that already passed the safety checks.

    Returns:
        The nickname without invisible characters and with spaces collapsed.
    """
    visible = "".join(
        " " if ch.isspace() else ch
        for ch in text
        if ch not in _INVISIBLE_CHARS
        and (ch.isspace() or not unicodedata.category(ch).startswith("C"))
    )
    return " ".join(visible.split())


def _compile_groups(
    base: Mapping[str, Iterable[str]],
    extra: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, tuple[re.Pattern[str], ...]]:
    """Compile grouped regex strings, appending optional extra patterns.

    Args:
        base: Built-in regex strings per group name.
        extra: Additional regex strings per group name. Unknown groups are
            appended after the built-in ones.

    Returns:
        Compiled case-insensitive patterns per group, in check order.
    """
    merged: dict[str, list[str]] = {group: list(items) for group, items in base.items()}
    for group, items in (extra or {}).items():
        merged.setdefault(group, []).extend(items)
    return {
        group: tuple(re.compile(pattern, re.IGNORECASE) for pattern in items)
        for group, items in merged.items()
    }


class ChatSafetyFilter:
    """Stateless safety checker for live chat text and viewer nicknames."""

    def __init__(
        self,
        extra_banned_words: Mapping[str, Iterable[str]] | None = None,
        extra_patterns: Mapping[str, Iterable[str]] | None = None,
    ) -> None:
        """Pre-compile detection patterns.

        Args:
            extra_banned_words: Additional literal banned words per category.
                Unknown category names become new categories checked after
                the built-in ones.
            extra_patterns: Additional injection regexes per group, matched
                against normalized text. Unknown group names become new
                groups checked after the built-in ones.
        """
        self._injection_patterns = _compile_groups(INJECTION_PATTERNS, extra_patterns)
        self._compact_injection_patterns = _compile_groups(COMPACT_INJECTION_PATTERNS)

        banned: dict[str, list[str]] = {
            category: list(words) for category, words in BANNED_WORDS.items()
        }
        for category, words in (extra_banned_words or {}).items():
            banned.setdefault(category, []).extend(words)
        self._banned_patterns: dict[str, re.Pattern[str]] = {}
        for category, words in banned.items():
            pattern = _word_regex(words)
            if pattern is not None:
                self._banned_patterns[category] = pattern
        self._exception_pattern = _word_regex(ALLOWED_EXCEPTIONS)

    def validate(self, author: str | None, text: str | None) -> tuple[bool, str]:
        """Decide whether a chat message may be forwarded to the LLM.

        Args:
            author: Viewer nickname from the payload.
            text: Chat or donation message body.

        Returns:
            ``(True, safe_author)`` when the message passes; the second value
            is the nickname to use (original or ``ANONYMOUS_NAME``).
            ``(False, reason_code)`` when the message must be dropped, e.g.
            ``"text:injection:ignore"`` or ``"text:banned:profanity"``.
            Unexpected errors fail closed with ``"filter:error"``.
        """
        try:
            reason = self.check_text(text)
            if reason is not None:
                return False, reason
            return True, self.sanitize_author(author)
        except Exception:
            logger.exception(
                f"[ChatSafetyFilter] unexpected error, message dropped: "
                f"text={_preview(text)}"
            )
            return False, "filter:error"

    def check_text(self, text: str | None) -> str | None:
        """Return a reason code if the message body must be blocked.

        Args:
            text: Chat or donation message body.

        Returns:
            ``None`` if safe, otherwise one of ``text:empty``,
            ``text:too_long``, ``text:injection:<group>``,
            ``text:banned:<category>``.
        """
        normalized = _normalize(text)
        if not normalized:
            return "text:empty"
        if len(normalized) > MAX_TEXT_LENGTH:
            return "text:too_long"
        injection_group = self._detect_injection(normalized, _compact(normalized))
        if injection_group is not None:
            return f"text:injection:{injection_group}"
        banned_category = self._detect_banned(normalized)
        if banned_category is not None:
            return f"text:banned:{banned_category}"
        return None

    def _detect_injection(self, normalized: str, compact: str) -> str | None:
        """Find the first prompt-injection group that matches the text.

        Args:
            normalized: Output of ``_normalize``.
            compact: Output of ``_compact``.

        Returns:
            The matching group name (e.g. ``"ignore"``), or None.
        """
        for group, patterns in self._injection_patterns.items():
            if any(pattern.search(normalized) for pattern in patterns):
                return group
            compact_patterns = self._compact_injection_patterns.get(group, ())
            if any(pattern.search(compact) for pattern in compact_patterns):
                return group
        return None

    def _detect_banned(self, normalized: str) -> str | None:
        """Find the first banned-word category that matches the text.

        Args:
            normalized: Output of ``_normalize``.

        Returns:
            The matching category name (e.g. ``"profanity"``), or None.
        """
        despaced = _despace(normalized)
        if self._exception_pattern is not None:
            despaced = self._exception_pattern.sub(" ", despaced)
        for category, pattern in self._banned_patterns.items():
            if pattern.search(despaced):
                return category
        return None

    def _author_violation(self, author: object) -> str | None:
        """Check whether a nickname must be replaced with ``ANONYMOUS_NAME``.

        Args:
            author: Raw nickname from the chat payload.

        Returns:
            A violation code such as ``"forbidden_char"`` or
            ``"injection:role"``, or None if the nickname is usable.
        """
        raw = "" if author is None else str(author)
        normalized = _normalize(raw)
        if not normalized or normalized in _EMPTY_AUTHOR_NAMES:
            return "empty"
        if any(unicodedata.category(ch) == "Cc" for ch in raw):
            return "control_char"
        if len(normalized) > MAX_AUTHOR_LENGTH:
            return "too_long"
        if any(ch in AUTHOR_FORBIDDEN_CHARS for ch in normalized):
            return "forbidden_char"
        injection_group = self._detect_injection(normalized, _compact(normalized))
        if injection_group is not None:
            return f"injection:{injection_group}"
        banned_category = self._detect_banned(normalized)
        if banned_category is not None:
            return f"banned:{banned_category}"
        return None

    def sanitize_author(self, author: object) -> str:
        """Return a nickname that is safe to show to the LLM.

        Unsafe, empty, or placeholder nicknames become ``ANONYMOUS_NAME``.
        Safe nicknames keep their original spelling (case, fullwidth forms)
        with only invisible/format characters removed and spaces collapsed.

        Args:
            author: Raw nickname from the chat payload.

        Returns:
            The original display nickname, or ``ANONYMOUS_NAME``.
        """
        violation = self._author_violation(author)
        if violation is not None:
            if violation != "empty":
                logger.info(
                    f"[ChatSafetyFilter] nickname replaced ({violation}): "
                    f"{str(author)[:30]!r}"
                )
            return ANONYMOUS_NAME
        return _clean_display(str(author))
