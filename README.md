# uSum — YouTube → OneNote summaries

Pass a list of YouTube URLs and get back a clean, structured summary report you can
keep in **OneNote**, plus optional **Word**, **PDF**, and full **transcript** files.

Runs on **Windows** and **Ubuntu/macOS**. Summaries are produced by Claude — either
through your existing **Claude Code subscription** (Max/Pro, no API key) or the
**Anthropic API** (with a key).

---

## What it does

For each URL:

1. **Metadata** — pulls title / channel / duration with `yt-dlp` (no download).
2. **Transcript** — uses existing YouTube captions when available
   (`youtube-transcript-api`); otherwise downloads the audio and transcribes it
   locally with **faster-whisper**.
3. **Summary** — sends the transcript to **Claude**, which writes a structured
   Markdown report (TL;DR, Key Takeaways, Detailed Summary with `[mm:ss]` markers,
   Notable Quotes, Action Items). Very long videos are map-reduced automatically.
4. **Render** — writes one combined report in your chosen format(s).

```
URL ─▶ yt-dlp (metadata)
   └─▶ captions ──(none?)──▶ yt-dlp audio + faster-whisper
            │
            ▼
   Claude (CLI subscription or API) ─▶ structured Markdown
            │
            ▼
   .md / .docx / .pdf / transcript .txt  (+ optional OneNote page)
```

### Output formats
| Format | Flag value | Notes |
|--------|-----------|-------|
| Markdown | `md` | **OneNote target** — open the file and paste into a OneNote page. Default. |
| Word | `docx` | Opens in Word; in OneNote use *Insert ▸ File Printout* or paste. |
| PDF | `pdf` | Self-contained PDF. Uses a system Unicode font when one is found. |
| Transcript | `txt` | Raw timestamped transcript ("script") per video. Default. |

> **OneNote note:** OneNote can't import Markdown directly. The simplest reliable path
> is to open the `.md` (or `.docx`) and paste its contents into a OneNote page —
> headings and bullets carry over.

---

## Setup

Requires **Python 3.9+**. (Optional but recommended: `ffmpeg` on PATH for the Whisper
fallback.)

### Windows (PowerShell)
```powershell
git clone https://github.com/goowei/uSum.git
cd uSum
.\run.ps1 -Setup
```

### Ubuntu / macOS
```bash
git clone https://github.com/goowei/uSum.git
cd uSum
./run.sh --setup
```

### Manual (any OS)
```bash
python -m venv .venv
# activate it, then:
pip install -r requirements.txt
# or: pip install -e .
```

### Choosing how Claude is reached (`--backend`)

uSum auto-detects this, but you can force it:

- **`cli` (no API key)** — uses the `claude` CLI in headless mode on your existing
  **Claude Code subscription** (Max/Pro). Just have Claude Code installed and logged in
  (`claude` on your PATH). This is the default when no API key is present.
- **`api`** — uses the Anthropic API. Get a key from <https://console.anthropic.com>,
  then put it in `.env` (`ANTHROPIC_API_KEY=...`), export it, or pass `--api-key`.
  This is the default when a key is present. Copy `.env.example` to `.env` to start.

---

## Usage

```bash
# Windows
.\run.ps1 https://youtu.be/VIDEO1 https://youtu.be/VIDEO2 -f md,docx,pdf

# Ubuntu/macOS
./run.sh -i urls.txt -f md,docx,pdf -o reports

# Or directly once deps are installed
python -m usum https://youtu.be/VIDEO -f md,txt
```

### Options
| Option | Description |
|--------|-------------|
| `urls...` | One or more YouTube URLs. |
| `-i, --input FILE` | Read URLs from a file (one per line; `#` comments allowed). |
| `-f, --formats` | `md,docx,pdf,txt` (default `md,txt`). |
| `-o, --out DIR` | Output directory (default `./out`). |
| `--backend` | `cli` (subscription), `api` (key), or `auto` (default). |
| `--model` | Claude model (default per backend — `claude-sonnet-4-6` / `sonnet`, or `USUM_MODEL`). |
| `--lang` | Preferred caption language (default `en`). |
| `--no-whisper` | Skip audio transcription; use captions only. |
| `--whisper-model` | faster-whisper size: `tiny`/`base`/`small`/`medium`/`large-v3`. |
| `--api-key` | Override the API key. |
| `-v, --verbose` | Verbose logging. |

Output is written as `out/uSum-report-<timestamp>.{md,docx,pdf}` with transcripts under
`out/transcripts/`.

---

## Push straight to OneNote (optional)

Instead of pasting Markdown, uSum can create a OneNote page per video via the
Microsoft Graph API.

**One-time setup:**
1. Go to <https://entra.microsoft.com> ▸ *App registrations* ▸ *New registration*.
   Give it any name; under *Supported account types* pick the option that includes
   personal Microsoft accounts if that's where your notebooks live.
2. In the app's *Authentication* page, enable **Allow public client flows**.
3. In *API permissions*, add **Microsoft Graph ▸ Delegated ▸ Notes.ReadWrite**.
4. Copy the **Application (client) ID** into `.env` as `USUM_MS_CLIENT_ID` (or pass
   `--onenote-client-id`).

**Use it:**
```bash
python -m usum https://youtu.be/VIDEO --onenote \
    --onenote-notebook "uSum" --onenote-section "Summaries"
```
The first run prints a microsoft.com/devicelogin code to sign in once; the token is
cached under `~/.usum/` for subsequent runs. Each summarised video becomes its own
page in the chosen notebook/section.

---

## How it's structured

```
usum/
  cli.py          # argument parsing + orchestration
  config.py       # API key / model resolution (.env)
  backends.py     # CLI (subscription) and API summarisation backends
  models.py       # VideoInfo / TranscriptSegment / VideoResult
  transcript.py   # yt-dlp metadata, captions, Whisper fallback
  summarize.py    # Claude prompt + map-reduce for long videos
  render.py       # Markdown / docx / pdf / transcript writers
  onenote.py      # optional Microsoft Graph OneNote push
```

## Notes & limitations
- The Whisper fallback is heavier (downloads a model on first use) and slower than
  captions. Disable with `--no-whisper` if you only want caption-backed videos.
- PDF Unicode fidelity depends on a system TTF (Arial/DejaVu/Liberation). If none is
  found it falls back to a latin-1 core font and transliterates other characters —
  Markdown/Word are unaffected.
- Summaries are only as good as the transcript; the tool is instructed not to invent
  content, but always sanity-check important facts.

## License
MIT — see [LICENSE](LICENSE).
