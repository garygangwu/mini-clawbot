#!/usr/bin/env python3
"""
Call the Anthropic Claude API for text generation, Q&A, and long-context analysis.
"""

from __future__ import annotations

import argparse
import os
import sys


def eprint(msg: str) -> None:
    print(msg, file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Call the Anthropic Claude API for text generation and analysis."
    )
    parser.add_argument("--prompt", required=True, help="The question or task to send to Claude.")
    parser.add_argument(
        "--file",
        dest="files",
        action="append",
        metavar="PATH",
        help="File path(s) to inject as context (repeatable).",
    )
    parser.add_argument("--system", default="", help="Optional system prompt.")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Model to use.")
    parser.add_argument("--max-tokens", type=int, default=8192, help="Max output tokens.")
    args = parser.parse_args()

    # Validate ANTHROPIC_API_KEY
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        eprint("Error: ANTHROPIC_API_KEY environment variable is not set.")
        eprint("Set it with: export ANTHROPIC_API_KEY=sk-ant-...")
        return 2

    # Validate anthropic package
    try:
        import anthropic
    except ImportError:
        eprint("Error: 'anthropic' package is not installed.")
        eprint("Install it with: pip install anthropic")
        return 2

    # Build prompt with optional file contexts
    parts: list[str] = []
    for path in args.files or []:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError as exc:
            eprint(f"Error reading file '{path}': {exc}")
            return 2
        parts.append(f"```{path}\n{content}\n```")

    parts.append(args.prompt)
    full_prompt = "\n\n".join(parts)

    # Build message params
    create_kwargs: dict = {
        "model": args.model,
        "max_tokens": args.max_tokens,
        "messages": [{"role": "user", "content": full_prompt}],
    }
    if args.system:
        create_kwargs["system"] = args.system

    # Call the API
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(**create_kwargs)
    except anthropic.APIStatusError as exc:
        eprint(f"Claude API error ({exc.status_code}): {exc.message}")
        return 1
    except anthropic.APIConnectionError as exc:
        eprint(f"Claude API connection error: {exc}")
        return 1
    except Exception as exc:
        eprint(f"Unexpected error: {exc}")
        return 1

    # Print response text
    for block in response.content:
        if hasattr(block, "text"):
            print(block.text, end="")

    # Ensure trailing newline
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
