import base64
import io
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave

from pydub import AudioSegment

from src.open_llm_vtuber.utils.stream_audio import prepare_audio_payload


class Mp3PayloadTests(unittest.TestCase):
    def test_edge_mp3_is_decoded_and_lip_volumes_computed_without_ffprobe(self):
        bundled = (
            Path(__file__).resolve().parents[1] / "tmp/tools/ffmpeg/bin/ffmpeg.exe"
        )
        ffmpeg = shutil.which("ffmpeg") or (str(bundled) if bundled.is_file() else None)
        if not ffmpeg:
            self.skipTest("FFmpeg is required for the MP3 regression")
        workspace = Path(__file__).resolve().parents[1]
        temporary_root = workspace / "tmp"
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=temporary_root, prefix="mp3-test-"
        ) as directory:
            self.assertTrue(Path(directory).resolve().is_relative_to(workspace))
            source = Path(directory) / "tone.wav"
            encoded = Path(directory) / "tone.mp3"
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(
                    b"".join(
                        struct.pack(
                            "<h", int(10000 * math.sin(2 * math.pi * 440 * i / 16000))
                        )
                        for i in range(4800)
                    )
                )
            subprocess.run(
                [ffmpeg, "-loglevel", "error", "-y", "-i", str(source), str(encoded)],
                check=True,
                capture_output=True,
            )
            with (
                patch.object(AudioSegment, "converter", ffmpeg),
                patch(
                    "pydub.audio_segment.mediainfo_json",
                    side_effect=AssertionError("ffprobe must not be called"),
                ),
            ):
                payload = prepare_audio_payload(str(encoded))
            decoded = base64.b64decode(payload["audio"])
            with wave.open(io.BytesIO(decoded), "rb") as audio:
                self.assertGreater(audio.getnframes(), 0)
            self.assertGreater(max(payload["volumes"]), 0)
