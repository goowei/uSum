"""Summarise a transcript into a structured Markdown report using the Claude API."""

from __future__ import annotations

import logging
from typing import List

from .models import TranscriptSegment, VideoInfo

log = logging.getLogger("usum.summarize")

# Rough char budget for a single pass. Well under Claude's context window, leaving
# room for the system prompt and output. Longer transcripts are map-reduced.
SINGLE_PASS_CHARS = 360_000
CHUNK_CHARS = 120_000

SYSTEM_PROMPT = """You are an expert analyst who turns long video transcripts into \
concise, accurate, well-structured notes for later reference.

Write in clean GitHub-flavoured Markdown that pastes cleanly into Microsoft OneNote.
Rules:
- Do NOT invent facts. Summarise only what the transcript supports.
- Be specific: keep names, numbers, definitions, steps and conclusions.
- Use timestamps in [mm:ss] form (taken from the transcript) when pointing to a moment.
- Prefer tight bullet points over long paragraphs.
- Do NOT include a top-level (#) title — start at level-3 (###) subheadings, because the
  caller adds the video title as a heading above your output.

Produce exactly these sections, in order:

### TL;DR
A 2-3 sentence summary of the whole video.

### Key Takeaways
5-10 bullet points capturing the most important, reusable insights.

### Detailed Summary
The substance of the video organised under bold topic labels or `####` sub-headings,
roughly following the video's flow, with [mm:ss] markers.

### Notable Quotes
Up to 5 short, verbatim quotes worth keeping (omit the section if none stand out).

### Action Items / Follow-ups
Concrete things the viewer might do or look into (omit if none apply).
"""


def _fmt_ts(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{sec:02d}"
    return f"{m:d}:{sec:02d}"


def transcript_to_text(segments: List[TranscriptSegment], with_timestamps: bool = True) -> str:
    if with_timestamps:
        return "\n".join(f"[{_fmt_ts(s.start)}] {s.text}" for s in segments)
    return " ".join(s.text for s in segments)


def _chunks(text: str, size: int) -> List[str]:
    lines = text.split("\n")
    out, buf, count = [], [], 0
    for line in lines:
        if count + len(line) > size and buf:
            out.append("\n".join(buf))
            buf, count = [], 0
        buf.append(line)
        count += len(line) + 1
    if buf:
        out.append("\n".join(buf))
    return out


def _call(client, model: str, system: str, user: str, max_tokens: int = 4096) -> str:
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
    )
    return "".join(block.text for block in resp.content if block.type == "text").strip()


def summarize(
    client,
    model: str,
    info: VideoInfo,
    segments: List[TranscriptSegment],
) -> str:
    """Return a Markdown report body (no top-level title)."""
    transcript = transcript_to_text(segments, with_timestamps=True)
    header = f"Video title: {info.title}\nChannel: {info.uploader or 'unknown'}\n\n"

    if len(transcript) <= SINGLE_PASS_CHARS:
        user = f"{header}Transcript:\n\n{transcript}"
        return _call(client, model, SYSTEM_PROMPT, user, max_tokens=4096)

    # Map-reduce for very long videos.
    log.info("Long transcript (%d chars) — using map-reduce summarisation.", len(transcript))
    parts = _chunks(transcript, CHUNK_CHARS)
    map_system = (
        "You are summarising one segment of a longer video transcript. Produce dense, "
        "factual notes as Markdown bullet points, preserving names, numbers and [mm:ss] "
        "markers. Do not add headings or preamble."
    )
    notes = []
    for i, part in enumerate(parts, 1):
        log.info("Summarising segment %d/%d...", i, len(parts))
        notes.append(
            _call(
                client,
                model,
                map_system,
                f"{header}Segment {i} of {len(parts)}:\n\n{part}",
                max_tokens=2048,
            )
        )
    combined = "\n\n".join(notes)
    user = (
        f"{header}Below are ordered notes covering the whole video. Synthesise them into "
        f"the final report.\n\nNotes:\n\n{combined}"
    )
    return _call(client, model, SYSTEM_PROMPT, user, max_tokens=4096)
