"""Stream the Studio character's synthetic reference voice through MLX Audio."""

import base64
from os import getenv
from pathlib import Path

import httpx

REFERENCE_TEXT = "어, 왔어요? 딱 맞춰 왔네요. 저 이거 발견했는데, 같이 볼래요?"


def enabled() -> bool:
    return bool(
        getenv("STUDIO_KANG_ISEO_TTS_URL") and getenv("STUDIO_KANG_ISEO_TTS_MODEL")
    )


async def stream_pcm(text: str):
    reference = (
        Path(__file__).resolve().parents[3]
        / "characters/voices/kang-iseo-reference.wav"
    )
    payload = {
        "model": getenv("STUDIO_KANG_ISEO_TTS_MODEL"),
        "input": text,
        "ref_audio": getenv("STUDIO_KANG_ISEO_TTS_REFERENCE", str(reference)),
        "ref_text": REFERENCE_TEXT,
        "lang_code": "Korean",
        "response_format": "pcm",
        "stream": True,
        # Three 80 ms codec frames per chunk balance first sound and playback gaps.
        "streaming_interval": 0.24,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=4)) as client:
        async with client.stream(
            "POST", getenv("STUDIO_KANG_ISEO_TTS_URL"), json=payload
        ) as result:
            result.raise_for_status()
            if result.headers.get("content-type", "").split(";")[0] != "audio/pcm":
                raise ValueError("Expected a PCM audio stream")
            # HTTP chunk boundaries need not coincide with 16-bit sample boundaries.
            tail = b""
            async for part in result.aiter_bytes():
                data = tail + part
                end = len(data) - len(data) % 2
                if end:
                    yield base64.b64encode(data[:end]).decode("ascii")
                tail = data[end:]
            if tail:
                raise ValueError("Truncated PCM sample")
