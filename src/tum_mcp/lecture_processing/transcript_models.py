"""Recognizer and audio-quality protocol parsed at the isolated process boundary."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator

from tum_mcp.lecture_evidence import Interval, Seconds
from tum_mcp.settings import Frozen

# Where a preflight sample or chunk failed: fetching media, reading a checkpoint, decoding
# PCM, measuring audio quality, running the recognizer or checking what it returned.
AudioStage = Literal["acquire", "cache", "decode", "analyze", "recognize", "validate"]


class AudioFailure(Frozen):
    """A failed span's stage and reason, from code-authored messages only (no media or text)."""

    scope: str = Field(pattern=r"^(preflight|chunk_[0-9]+)$")
    interval: Interval
    stage: AudioStage
    code: str = Field(pattern=r"^[a-z_]{1,40}$")
    reason: str = Field(pattern=r"^[a-z_]{1,80}$")


class SpeechWindow(Frozen):
    start_s: Seconds
    end_s: Seconds
    speech_s: Seconds


class ChannelQuality(Frozen):
    channel: int = Field(ge=0, le=7)
    rms: FiniteFloat = Field(ge=0, le=1)
    clipped_fraction: FiniteFloat = Field(ge=0, le=1)
    windows: tuple[SpeechWindow, ...] = Field(max_length=21)

    @property
    def speech_s(self) -> float:
        return sum(window.speech_s for window in self.windows)


class AudioQuality(Frozen):
    duration_s: Seconds = Field(le=610)
    channels: tuple[ChannelQuality, ...] = Field(min_length=1, max_length=8)

    @property
    def selected(self) -> ChannelQuality:
        usable = tuple(channel for channel in self.channels if channel.clipped_fraction < 0.1)
        return max(usable or self.channels, key=lambda channel: channel.speech_s)

    @property
    def uncertain(self) -> bool:
        return self.selected.speech_s < 0.3 or self.selected.clipped_fraction >= 0.1


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Word(Wire):
    start: Seconds
    end: Seconds
    word: str = Field(max_length=1000)
    probability: FiniteFloat = Field(ge=0, le=1)


class RecognizedSegment(Wire):
    start: Seconds
    end: Seconds
    text: str = Field(max_length=20000)
    avg_logprob: FiniteFloat
    no_speech_prob: FiniteFloat = Field(ge=0, le=1)
    compression_ratio: FiniteFloat = Field(ge=0)
    words: tuple[Word, ...] = Field(max_length=5000)


class Recognition(Wire):
    language: str = Field(pattern=r"^[a-z]{2,3}$")
    segments: tuple[RecognizedSegment, ...] = Field(max_length=5000)


class Passage(Frozen):
    interval: Interval
    text: str = Field(min_length=1, max_length=20000)
    origin: Literal["subtitle", "asr"]
    uncertainty: str = Field(default="", max_length=1000)
    words: tuple[Word, ...] = ()

    @model_validator(mode="after")
    def word_bounds(self) -> "Passage":
        if any(
            not self.interval.start_s <= word.start <= word.end <= self.interval.end_s
            for word in self.words
        ):
            raise ValueError("Words must use original time inside their passage.")
        return self
