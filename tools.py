import io
import json
import os
import subprocess
import tempfile
import time

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify
from openai import OpenAI
import pymupdf

import skills

# --- Tool schemas (sent to OpenAI) ---

# Callback set by agent.py to avoid circular import
_agent_loop_fn = None


def set_agent_loop(fn):
    global _agent_loop_fn
    _agent_loop_fn = fn


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "exec",
            "description": "Execute a shell command and return its output. Use for running programs, installing packages, git operations, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file and return them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates the file if it doesn't exist, overwrites if it does. Creates parent directories as needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or relative path to the file",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetch a web page URL and return its content as readable markdown text. Use for HTML pages, articles, blog posts, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pdf_fetch",
            "description": "Download a PDF from a URL and extract its text content. Use for PDF documents, reports, filings, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL of the PDF file",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_video",
            "description": (
                "Generate a video from a text prompt using OpenAI's Sora model. "
                "The video is saved to ~/mini-clawbot-output/ and the file path is returned. "
                "Generation takes 30 seconds to a few minutes. Use for creating short video clips."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Text description of the video to generate (max 500 chars)",
                    },
                    "seconds": {
                        "type": "integer",
                        "description": "Video length in seconds. Allowed: 4, 8, or 12. Default: 4",
                    },
                    "size": {
                        "type": "string",
                        "description": "Video resolution. Options: 1280x720 (landscape), 720x1280 (portrait), 1792x1024 (wide), 1024x1792 (tall). Default: 1280x720",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "use_skill",
            "description": "Load the full instructions for a skill by name. Call this before performing a skill to get its detailed instructions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The skill name (e.g. 'weather', 'slack')",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_agent",
            "description": (
                "Spawn a sub-agent to handle an independent subtask. "
                "The sub-agent gets its own conversation with the LLM and access to all tools (except spawn_agent). "
                "It runs synchronously and returns its final answer. "
                "Use this when a subtask is self-contained and can be solved independently."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "A clear, self-contained description of what the sub-agent should do",
                    },
                },
                "required": ["task"],
            },
        },
    },
]


# --- Tool implementations ---


def exec_command(command: str) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += result.stderr
        if result.returncode != 0:
            output += f"\n(exit code {result.returncode})"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 30 seconds"


def read_file(path: str) -> str:
    path = os.path.expanduser(path)
    try:
        with open(path) as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: file not found: {path}"
    except PermissionError:
        return f"Error: permission denied: {path}"


def write_file(path: str, content: str) -> str:
    path = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Wrote {len(content)} bytes to {path}"
    except PermissionError:
        return f"Error: permission denied: {path}"


MAX_CONTENT_CHARS = 50000  # truncate to fit LLM context

FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) MiniClawBot/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def web_fetch(url: str) -> str:
    try:
        resp = requests.get(url, headers=FETCH_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"Error fetching URL: {e}"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove non-content elements
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe"]):
        tag.decompose()

    # Try to find main content area first
    main = soup.find("article") or soup.find("main") or soup.find("body")
    html = str(main) if main else str(soup)

    text = markdownify(html, heading_style="ATX", strip=["img"]).strip()

    # Collapse excessive blank lines
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")

    if len(text) > MAX_CONTENT_CHARS:
        text = text[:MAX_CONTENT_CHARS] + f"\n\n... (truncated at {MAX_CONTENT_CHARS} chars)"

    return text or "Error: no readable content found"


def pdf_fetch(url: str) -> str:
    try:
        resp = requests.get(url, headers=FETCH_HEADERS, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as e:
        return f"Error fetching PDF: {e}"

    try:
        doc = pymupdf.open(stream=resp.content, filetype="pdf")
    except Exception as e:
        return f"Error parsing PDF: {e}"

    pages = []
    for i, page in enumerate(doc):
        page_text = page.get_text().strip()
        if page_text:
            pages.append(f"--- Page {i + 1} ---\n{page_text}")
    doc.close()

    text = "\n\n".join(pages)

    if not text:
        return "Error: no text found in PDF (may be image-based)"

    if len(text) > MAX_CONTENT_CHARS:
        text = text[:MAX_CONTENT_CHARS] + f"\n\n... (truncated at {MAX_CONTENT_CHARS} chars)"

    return text


VIDEO_OUTPUT_DIR = os.path.expanduser("~/mini-clawbot-output")

# SDK accepts seconds as string literals
VALID_SECONDS = ("4", "8", "12")
VALID_SIZES = ("720x1280", "1280x720", "1024x1792", "1792x1024")


def generate_video(prompt: str, seconds: int = 4, size: str = "1280x720") -> str:
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

    # Validate and coerce params
    sec_str = str(seconds)
    if sec_str not in VALID_SECONDS:
        return f"Error: seconds must be 4, 8, or 12 (got {seconds})"
    if size not in VALID_SIZES:
        return f"Error: size must be one of {VALID_SIZES} (got {size})"

    client = OpenAI()

    # create_and_poll handles submission + polling in one call
    print(f"  [video] Generating ({sec_str}s, {size})...", flush=True)
    try:
        video = client.videos.create_and_poll(
            model="sora-2",
            prompt=prompt,
            seconds=sec_str,
            size=size,
            poll_interval_ms=10000,  # check every 10s
        )
    except Exception as e:
        return f"Error during video generation: {e}"

    if video.status != "completed":
        error_msg = getattr(video, "error", "unknown error")
        return f"Video generation failed (status={video.status}): {error_msg}"

    # Download via SDK
    print(f"  [video] Downloading video...", flush=True)
    try:
        content = client.videos.download_content(video.id)
    except Exception as e:
        return f"Error downloading video: {e}"

    filename = f"video_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    filepath = os.path.join(VIDEO_OUTPUT_DIR, filename)
    content.stream_to_file(filepath)

    size_kb = os.path.getsize(filepath) // 1024
    return f"Video saved to {filepath} ({size_kb} KB, {sec_str}s, {size})"


def spawn_agent(task: str) -> str:
    if _agent_loop_fn is None:
        return "Error: agent loop not registered"

    # Sub-agent gets a fresh conversation with only its task
    messages = [
        {"role": "system", "content": "You are a focused sub-agent. Complete the given task and return a clear, concise result. You have access to exec, read_file, write_file, web_fetch, and pdf_fetch tools."},
        {"role": "user", "content": task},
    ]

    # Remove spawn_agent from sub-agent's tools to prevent recursive spawning
    sub_tools = [t for t in TOOL_SCHEMAS if t["function"]["name"] != "spawn_agent"]

    print(f"  [sub-agent starting: {task[:80]}...]" if len(task) > 80 else f"  [sub-agent starting: {task}]")
    result = _agent_loop_fn(messages, sub_tools)
    print(f"  [sub-agent finished]")
    return result


# --- Dispatch ---

HANDLERS = {
    "exec": lambda args: exec_command(args["command"]),
    "read_file": lambda args: read_file(args["path"]),
    "write_file": lambda args: write_file(args["path"], args["content"]),
    "web_fetch": lambda args: web_fetch(args["url"]),
    "pdf_fetch": lambda args: pdf_fetch(args["url"]),
    "generate_video": lambda args: generate_video(
        args["prompt"],
        args.get("seconds", 4),
        args.get("size", "1280x720"),
    ),
    "use_skill": lambda args: skills.load_skill(args["name"]),
    "spawn_agent": lambda args: spawn_agent(args["task"]),
}


def run_tool(name: str, arguments: str) -> str:
    args = json.loads(arguments)
    handler = HANDLERS.get(name)
    if not handler:
        return f"Error: unknown tool: {name}"
    return handler(args)
