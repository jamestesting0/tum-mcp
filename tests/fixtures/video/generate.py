"""Regenerate the synthetic Video Notes fixtures with the optional render runtime's Python.

Usage: <video runtime python> -I tests/fixtures/video/generate.py
AAC codec fixture: bash tests/fixtures/video/generate-audio.sh (requires ffmpeg/ffprobe).
speech.wav is the lossless synchrony WAV from review-course's media-gallery recipe
(Kokoro v1.0 fp32, af_heart, en-us, speed 1), not the tone fixture.
"""

import math
import wave
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image

HERE = Path(__file__).parent


def clip() -> None:
    with av.open(str(HERE / "clip.mp4"), "w", options={"movflags": "+faststart"}) as container:
        video = container.add_stream("libx264", rate=15)
        video.width, video.height, video.pix_fmt = 854, 480, "yuv420p"
        video.options = {"crf": "40", "preset": "medium"}
        audio = container.add_stream("aac", rate=48000)
        audio.layout = "mono"
        for index in range(30):
            frame = av.VideoFrame.from_ndarray(
                np.full((480, 854, 3), (16, 26, 40), dtype=np.uint8), format="rgb24"
            )
            frame.pts = index
            frame.time_base = Fraction(1, 15)
            for packet in video.encode(frame):
                container.mux(packet)
        for packet in video.encode():
            container.mux(packet)
        samples = (0.1 * np.sin(2 * math.pi * 220 * np.arange(96000) / 48000)).astype("float32")
        for start in range(0, len(samples), 1024):
            block = samples[start : start + 1024]
            block = np.pad(block, (0, 1024 - len(block)))
            frame = av.AudioFrame.from_ndarray(block.reshape(1, -1), format="flt", layout="mono")
            frame.sample_rate = 48000
            frame.pts = start
            for packet in audio.encode(frame):
                container.mux(packet)
        for packet in audio.encode():
            container.mux(packet)


def tone() -> None:
    rate = 16000
    samples = (0.2 * np.sin(2 * math.pi * 330 * np.arange(int(rate * 0.6)) / rate) * 32767).astype(
        "<i2"
    )
    with wave.open(str(HERE / "tone.wav"), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(samples.tobytes())


def poster() -> None:
    Image.new("RGB", (64, 36), (16, 26, 40)).save(HERE / "poster.jpg", "JPEG", quality=70)


if __name__ == "__main__":
    clip()
    tone()
    poster()
