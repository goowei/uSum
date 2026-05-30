"""Fetch video metadata and a transcript.

Strategy:
  1. Pull metadata with yt-dlp (no download).
  2. Try YouTube captions via youtube-transcript-api (fast, free).
  3. If no captions and Whisper is enabled, download audio with yt-dlp and
     transcribe locally with faster-whisper.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import List, Optional

from .models import TranscriptSegment, VideoInfo

log = logging.getLogger("usum.transcript")


def get_video_info(url: str) -> VideoInfo:
    """Extract metadata without downloading the media."""
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    return VideoInfo(
        id=info["id"],
        title=info.get("title") or info["id"],
        url=info.get("webpage_url", url),
        uploader=info.get("uploader") or info.get("channel"),
        duration=info.get("duration"),
        upload_date=info.get("upload_date"),
    )


def fetch_captions(
    video_id: str, languages: Optional[List[str]] = None
) -> Optional[List[TranscriptSegment]]:
    """Return caption segments, preferring manual captions in the given languages."""
    languages = languages or ["en"]
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:  # pragma: no cover
        log.warning("youtube-transcript-api not installed; skipping captions")
        return None

    api = YouTubeTranscriptApi()
    try:
        listing = api.list(video_id)
    except Exception as exc:  # TranscriptsDisabled, video unavailable, etc.
        log.debug("No transcript listing for %s: %s", video_id, exc)
        return None

    transcript = None
    for finder in ("find_manually_created_transcript", "find_generated_transcript"):
        try:
            transcript = getattr(listing, finder)(languages)
            break
        except Exception:
            continue
    if transcript is None:
        # Fall back to any available transcript, translating to the first preference.
        try:
            transcript = next(iter(listing))
            if transcript.is_translatable and languages[0] not in transcript.language_code:
                transcript = transcript.translate(languages[0])
        except Exception:
            return None

    try:
        fetched = transcript.fetch()
    except Exception as exc:
        log.debug("Failed fetching transcript for %s: %s", video_id, exc)
        return None

    return [
        TranscriptSegment(
            start=float(snippet.start),
            duration=float(snippet.duration),
            text=" ".join(snippet.text.split()),
        )
        for snippet in fetched
        if snippet.text.strip()
    ]


def transcribe_with_whisper(
    url: str, whisper_model: str = "base"
) -> Optional[List[TranscriptSegment]]:
    """Download audio with yt-dlp and transcribe locally with faster-whisper."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log.warning(
            "faster-whisper not installed; cannot transcribe '%s'. "
            "Install with: pip install faster-whisper",
            url,
        )
        return None

    import yt_dlp

    with tempfile.TemporaryDirectory(prefix="usum_") as tmp:
        outtmpl = os.path.join(tmp, "audio.%(ext)s")
        opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                audio_path = ydl.prepare_filename(info)
        except Exception as exc:
            log.warning("Audio download failed for %s: %s", url, exc)
            return None

        if not os.path.exists(audio_path):
            log.warning("Downloaded audio not found for %s", url)
            return None

        log.info("Transcribing audio with Whisper (model=%s)...", whisper_model)
        model = WhisperModel(whisper_model, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(audio_path, vad_filter=True)

        result: List[TranscriptSegment] = []
        for seg in segments:
            text = seg.text.strip()
            if text:
                result.append(
                    TranscriptSegment(
                        start=float(seg.start),
                        duration=float(seg.end - seg.start),
                        text=text,
                    )
                )
        return result or None


def get_transcript(
    info: VideoInfo,
    languages: Optional[List[str]] = None,
    use_whisper: bool = True,
    whisper_model: str = "base",
) -> tuple[List[TranscriptSegment], str]:
    """Return (segments, source) where source is 'captions', 'whisper' or 'none'."""
    segments = fetch_captions(info.id, languages)
    if segments:
        return segments, "captions"

    if use_whisper:
        segments = transcribe_with_whisper(info.url, whisper_model)
        if segments:
            return segments, "whisper"

    return [], "none"
