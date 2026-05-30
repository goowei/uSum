"""Command-line entry point for uSum."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from typing import List

from . import __version__
from .config import DEFAULT_MODEL, DEFAULT_WHISPER_MODEL, get_api_key
from .models import VideoResult
from .render import render_outputs
from .summarize import summarize
from .transcript import get_transcript, get_video_info

log = logging.getLogger("usum")

VALID_FORMATS = {"md", "docx", "pdf", "txt"}


def _read_url_file(path: str) -> List[str]:
    urls = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)
    return urls


def _parse_formats(value: str) -> List[str]:
    formats = [f.strip().lower() for f in value.split(",") if f.strip()]
    bad = [f for f in formats if f not in VALID_FORMATS]
    if bad:
        raise argparse.ArgumentTypeError(
            f"Unknown format(s): {', '.join(bad)}. Choose from {', '.join(sorted(VALID_FORMATS))}."
        )
    return formats


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="usum",
        description="Summarise YouTube videos into OneNote-friendly reports.",
    )
    p.add_argument("urls", nargs="*", help="YouTube URLs to summarise.")
    p.add_argument("-i", "--input", help="File with one YouTube URL per line.")
    p.add_argument(
        "-f",
        "--formats",
        type=_parse_formats,
        default=["md", "txt"],
        help="Comma-separated output formats: md,docx,pdf,txt (default: md,txt).",
    )
    p.add_argument("-o", "--out", default="out", help="Output directory (default: ./out).")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model (default: {DEFAULT_MODEL}).")
    p.add_argument("--api-key", help="Anthropic API key (else ANTHROPIC_API_KEY / .env).")
    p.add_argument(
        "--lang",
        default="en",
        help="Preferred caption language code (default: en).",
    )
    p.add_argument(
        "--no-whisper",
        action="store_true",
        help="Do not fall back to audio transcription for caption-less videos.",
    )
    p.add_argument(
        "--whisper-model",
        default=DEFAULT_WHISPER_MODEL,
        help=f"faster-whisper model size (default: {DEFAULT_WHISPER_MODEL}).",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging.")
    p.add_argument("--version", action="version", version=f"uSum {__version__}")
    return p


def process_url(
    url: str,
    client,
    model: str,
    languages: List[str],
    use_whisper: bool,
    whisper_model: str,
) -> VideoResult:
    log.info("Processing %s", url)
    try:
        info = get_video_info(url)
    except Exception as exc:
        log.error("Could not read video metadata for %s: %s", url, exc)
        from .models import VideoInfo

        return VideoResult(
            info=VideoInfo(id=url, title=url, url=url),
            error=f"metadata error: {exc}",
        )

    result = VideoResult(info=info)
    try:
        segments, source = get_transcript(
            info, languages=languages, use_whisper=use_whisper, whisper_model=whisper_model
        )
        result.segments = segments
        result.transcript_source = source
        if not segments:
            result.error = "no transcript available (no captions and Whisper disabled/failed)"
            log.warning("No transcript for %s", info.title)
            return result

        log.info("Summarising '%s' (%s)...", info.title, source)
        result.summary_markdown = summarize(client, model, info, segments)
    except Exception as exc:
        result.error = f"summarisation error: {exc}"
        log.error("Failed on %s: %s", info.title, exc)
    return result


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    urls: List[str] = list(args.urls)
    if args.input:
        urls.extend(_read_url_file(args.input))
    # De-duplicate, preserve order.
    seen, ordered = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)
    urls = ordered

    if not urls:
        log.error("No URLs given. Pass URLs as arguments or use --input FILE.")
        return 2

    try:
        api_key = get_api_key(args.api_key)
    except RuntimeError as exc:
        log.error("%s", exc)
        return 2

    try:
        from anthropic import Anthropic
    except ImportError:
        log.error("The 'anthropic' package is not installed. Run: pip install anthropic")
        return 2

    client = Anthropic(api_key=api_key)
    languages = [args.lang]

    results = [
        process_url(
            url, client, args.model, languages, not args.no_whisper, args.whisper_model
        )
        for url in urls
    ]

    now = datetime.now()
    generated_on = now.strftime("%Y-%m-%d %H:%M")
    basename = f"uSum-report-{now.strftime('%Y%m%d-%H%M%S')}"

    written = render_outputs(
        results,
        out_dir=args.out,
        formats=args.formats,
        generated_on=generated_on,
        basename=basename,
    )

    ok = sum(1 for r in results if r.ok)
    failed = len(results) - ok
    print(f"\nDone: {ok} summarised, {failed} failed.")
    if written:
        print("Output files:")
        for p in written:
            print(f"  {p}")
    if "md" in args.formats:
        print("\nTip: open the .md file and paste it into a OneNote page.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
