"""Shared data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class VideoInfo:
    id: str
    title: str
    url: str
    uploader: Optional[str] = None
    duration: Optional[int] = None  # seconds
    upload_date: Optional[str] = None  # YYYYMMDD


@dataclass
class TranscriptSegment:
    start: float  # seconds
    duration: float
    text: str


@dataclass
class VideoResult:
    info: VideoInfo
    segments: List[TranscriptSegment] = field(default_factory=list)
    transcript_source: str = "none"  # "captions" | "whisper" | "none"
    summary_markdown: str = ""
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.summary_markdown)
