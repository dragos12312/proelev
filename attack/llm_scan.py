"""
Local-LLM source code scanner. Points a fresh Ollama instance at a folder
and asks it to surface security issues in every file. Writes findings to
vulns.md so you can hand it to the lab teacher.

Usage:
    # one-time, install ollama from https://ollama.com and pull a small model
    ollama pull llama3.2:3b

    # scan your own code or a peer's repo
    python attack/llm_scan.py ../path/to/peer/proelev
    python attack/llm_scan.py .                       # scan this repo
    python attack/llm_scan.py . --model qwen2.5:7b    # bigger model

Tunables via env vars:
    OLLAMA_URL    default http://localhost:11434
    OLLAMA_MODEL  default llama3.2:3b
    MAX_BYTES     skip files larger than this (default 30 KB) so tiny models cope
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")
MAX_BYTES    = int(os.environ.get("MAX_BYTES", str(30 * 1024)))

# extensions worth scanning, kept narrow so we don't waste tokens on lockfiles
SCAN_EXTS = {".py", ".vue", ".js", ".ts", ".html", ".sql"}

# folders to skip entirely
SKIP_DIRS = {
    "node_modules", ".git", "dist", ".vite", "__pycache__",
    "venv", ".venv", "alembic/versions", "playwright-report",
    ".pytest_cache", "certs",
}

PROMPT = """You are a security auditor. The following is one source file
from a Vue 3 + FastAPI school app called ProElev. List any concrete
security issues you can find, **strictly in this format**, one per line:

  - severity (low|med|high) | line N | short description

If you cannot find any issues, reply with exactly:

  - none

Be terse, no preamble, no advice, no markdown.

File: {path}

```{lang}
{content}
```"""


def ollama_chat(model: str, prompt: str) -> str:
    """Call Ollama's /api/chat in non-streaming mode and return assistant text."""
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.1},
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("message", {}).get("content", "").strip()
    except urllib.error.URLError as e:
        print(f"!! ollama call failed: {e}")
        return "- error contacting ollama"


def should_scan(path: Path) -> bool:
    if path.suffix not in SCAN_EXTS:
        return False
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return False
    if path.stat().st_size > MAX_BYTES:
        return False
    return True


def main() -> None:
    ap = argparse.ArgumentParser(description="Local-LLM source code scanner")
    ap.add_argument("root", help="folder to scan recursively")
    ap.add_argument("--model", default=OLLAMA_MODEL, help="Ollama model (default %(default)s)")
    ap.add_argument("--out", default="vulns.md", help="where to write findings")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"path not found: {root}")
        sys.exit(1)

    files = []
    for p in root.rglob("*"):
        try:
            if p.is_file() and should_scan(p):
                files.append(p)
        except OSError:
            continue
    files.sort()

    out = Path(args.out).resolve()
    print(f"scanning {len(files)} files with model {args.model}")
    print(f"writing findings to {out}")
    print()

    started = time.time()
    with out.open("w", encoding="utf-8") as fh:
        fh.write(f"# LLM scan, {args.model}\n\n")
        fh.write(f"root: `{root}`\n\n")
        for i, p in enumerate(files, 1):
            rel = p.relative_to(root).as_posix()
            try:
                content = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            lang = p.suffix.lstrip(".") or "text"
            prompt = PROMPT.format(path=rel, lang=lang, content=content)
            print(f"[{i:>3}/{len(files)}] {rel}", end=" ", flush=True)
            t0 = time.time()
            answer = ollama_chat(args.model, prompt)
            print(f"({time.time() - t0:.1f}s)")
            fh.write(f"## `{rel}`\n\n")
            fh.write(answer + "\n\n")
            fh.flush()

    print()
    print(f"done in {time.time() - started:.0f}s. open {out}")


if __name__ == "__main__":
    main()
