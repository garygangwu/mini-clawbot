---
name: claude-api
description: Call the Anthropic Claude API directly for text generation, second opinions,
  and long-context analysis (200K token window). Use when: (1) you need Claude's
  perspective on code, architecture, or writing, (2) a file or document is too large
  for the current context, (3) the user explicitly asks to "use Claude" or "ask Claude",
  (4) you want a second opinion from a different model.
metadata:
  {
    "opencrew":
      {
        "emoji": "🟣",
        "requires": { "bins": ["python3"], "env": ["ANTHROPIC_API_KEY"] },
        "primaryEnv": "ANTHROPIC_API_KEY",
      },
  }
---

# Claude API

Call Anthropic's Claude API directly from an agent for text generation, analysis, and long-context tasks.

## Setup

1. Install the `anthropic` package:
   ```bash
   pip install anthropic
   ```
2. Set your API key:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

## Quick start

```bash
python3 {baseDir}/scripts/claude.py --prompt "Explain the CAP theorem in plain English"
```

## With file context

Pass a source file as context alongside your question:

```bash
python3 {baseDir}/scripts/claude.py \
  --prompt "What does this file do and are there any bugs?" \
  --file src/main.py
```

## Multiple files

Pass several files with repeated `--file` arguments:

```bash
python3 {baseDir}/scripts/claude.py \
  --prompt "How do these modules interact? Suggest improvements." \
  --file src/auth.py \
  --file src/db.py \
  --file src/routes.py
```

## System prompt

```bash
python3 {baseDir}/scripts/claude.py \
  --system "You are a senior security engineer. Be concise and direct." \
  --prompt "Review this authentication flow for vulnerabilities" \
  --file src/auth.py
```

## Model selection

| Model | ID | Best for |
|---|---|---|
| Sonnet (default) | `claude-sonnet-4-6` | Balanced — code review, analysis, writing |
| Opus | `claude-opus-4-6` | Complex reasoning, architecture decisions |
| Haiku | `claude-haiku-4-5-20251001` | Fast, cheap — quick Q&A, summaries |

```bash
python3 {baseDir}/scripts/claude.py --model claude-opus-4-6 --prompt "Design a distributed rate limiter"
python3 {baseDir}/scripts/claude.py --model claude-haiku-4-5-20251001 --prompt "Summarize this in 3 bullets" --file notes.txt
```

## Tips

- Claude's context window is 200K tokens — large files and multi-file analysis work well.
- Increase `--max-tokens` (default 8192) for longer outputs: `--max-tokens 16384`
- Output is plain text to stdout; errors go to stderr.
- Exit codes: `0` success, `1` API error, `2` setup error (missing key or package).
