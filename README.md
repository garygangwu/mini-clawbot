# Mini-ClawBot

A lightweight CLI chatbot with tool use, streaming responses, and a pluggable skills system. Currently uses OpenAI-compatible APIs, extensible to any LLM provider.

## Features

- **Streaming chat** — real-time token streaming with support for reasoning/thinking models
- **Tool use** — the model can execute shell commands, read/write files, fetch web pages, extract PDFs, generate videos, and spawn sub-agents
- **50+ skills** — self-contained skill packs (weather, Slack, Discord, GitHub, Spotify, Notion, and more) discovered automatically at startup
- **Session persistence** — conversation history saved to disk and resumed across runs
- **Sub-agents** — spawn isolated child agents for independent subtasks

## Quick Start

```bash
# Clone the repo
git clone https://github.com/user/mini-clawbot.git
cd mini-clawbot

# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key
export OPENAI_API_KEY="sk-..."

# Run
python main.py
```

## Usage

```
> what's the weather in NYC?
> summarize this PDF: https://example.com/report.pdf
> read main.py and explain what it does
> /help
> /history
> /clear
> /quit
```

| Command    | Description                    |
|------------|--------------------------------|
| `/help`    | Show available commands        |
| `/history` | Print conversation history     |
| `/clear`   | Clear conversation history     |
| `/quit`    | Exit the REPL                  |

## Architecture

```
User Input
    |
    v
main.py (REPL)
    |
    v
agent.chat(message)
    |
    +---> Builds system prompt (base + skill listing)
    +---> Calls OpenAI API (streaming)
    |
    v
_run_agent_loop()
    |
    +---> Stream text / thinking tokens to stdout
    +---> Tool calls? --YES--> tools.run_tool() --+
    |                                              |
    |         <--- tool results appended ----------+
    |         (loop back to API)
    |
    +---> No tool calls --> return final text
    |
    v
Save to session
```

### Core Modules

| File         | Purpose                                                    |
|--------------|------------------------------------------------------------|
| `main.py`    | CLI entry point — REPL loop, slash commands                |
| `agent.py`   | Agent orchestration — streaming, tool execution loop       |
| `tools.py`   | Tool schemas (sent to OpenAI) and implementations          |
| `skills.py`  | Skill discovery (`skills/*/SKILL.md`) and loading          |
| `session.py` | Conversation persistence in JSONL format                   |
| `config.py`  | Configuration loading with defaults                        |

## Tools

The model has access to these tools during a conversation:

| Tool             | Description                                              |
|------------------|----------------------------------------------------------|
| `exec`           | Run a shell command (30s timeout)                        |
| `read_file`      | Read a file's contents                                   |
| `write_file`     | Write content to a file (creates dirs as needed)         |
| `web_fetch`      | Fetch a URL and convert HTML to markdown                 |
| `pdf_fetch`      | Download a PDF and extract text                          |
| `generate_video` | Generate a video clip with OpenAI Sora                   |
| `use_skill`      | Load a skill's full instructions by name                 |
| `spawn_agent`    | Spawn a sub-agent for an independent subtask             |

## Skills

Skills live in `skills/<name>/SKILL.md`. Each file has YAML frontmatter with a `name` and `description`, followed by detailed instructions the model loads on demand via the `use_skill` tool.

At startup, all skills are discovered and listed in the system prompt so the model knows what's available. When a skill is relevant, the model calls `use_skill("weather")` to fetch the full instructions before acting.

**Included skills (52):**

| Category       | Skills                                                                                  |
|----------------|-----------------------------------------------------------------------------------------|
| Productivity   | apple-notes, apple-reminders, bear-notes, notion, obsidian, things-mac, trello, canvas  |
| Communication  | slack, discord, imsg, bluebubbles, voice-call                                           |
| Developer      | coding-agent, github, clawhub, mcporter, tmux                                           |
| Media          | openai-image-gen, nano-pdf, video-frames, camsnap, nano-banana-pro, openai-whisper, openai-whisper-api, sherpa-onnx-tts |
| Music/Home     | spotify-player, sonoscli, songsee, openhue, eightctl, blucli                            |
| Information    | weather, summarize, oracle, blogwatcher, gifgrep, model-usage, session-logs             |
| Services       | food-order, goplaces, local-places, ordercli, wacli, 1password                         |
| Utility        | healthcheck, peekaboo, sag, gog, himalaya, skill-creator, gemini                        |

### Creating a Skill

Create a new directory under `skills/` with a `SKILL.md` file:

```
skills/my-skill/SKILL.md
```

```markdown
---
name: my-skill
description: One-line description of what this skill does.
---

# My Skill

Detailed instructions for the model on how to use this skill.
Include example commands, API patterns, tips, etc.
```

The skill will be automatically discovered on the next run.

## Configuration

Configuration is stored at `~/.mini-clawbot/config.json` and merged with defaults.

```json
{
  "model": "gpt-5.2",
  "system_prompt": "You are Mini-ClawBot, a helpful AI assistant."
}
```

| Key             | Default                                          | Description              |
|-----------------|--------------------------------------------------|--------------------------|
| `model`         | `gpt-5.2`                                        | OpenAI model ID          |
| `system_prompt` | `You are Mini-ClawBot, a helpful AI assistant.`  | Base system prompt        |

Sessions are stored at `~/.mini-clawbot/sessions/default.jsonl`.

## Dependencies

```
openai>=1.0.0
requests>=2.31.0
beautifulsoup4>=4.12.0
markdownify>=0.13.0
pymupdf>=1.25.0
```

## License

MIT
