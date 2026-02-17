# AutoCrew

A lightweight CLI chatbot with **self-organizing multi-agent teams**. Give it a complex task and it designs a team of specialized agents — custom roles, system prompts, and tools — all on the fly. Powered by OpenAI-compatible APIs.

## Highlights

- **Self-organizing teams** — `/team <task>` has the LLM design a custom team for your task. No predefined roles — the model invents agents tailored to the job.
- **Message-driven scheduling** — agents activate each other through messages, not fixed rounds. Only the agents that have work to do actually run.
- **Extensible tool system** — 8 built-in tools + 50+ skill packs. Add new tools by defining a schema and handler. Add new skills by dropping a markdown file.
- **Single-agent mode** — for simple tasks, just chat directly with full tool access.

## Quick Start

```bash
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."
python main.py
```

## Usage

**Single-agent mode** — ask anything directly:

```
> read main.py and explain the architecture
> fetch https://news.ycombinator.com and summarize the top 5 stories
> write a Python script that converts CSV to JSON, save it to convert.py, then test it
```

**Multi-agent mode** — tackle complex, multi-step tasks with `/team`:

```
> /team Research the top 3 trending Hacker News stories, write a blog post
      summarizing each one, then review the post for accuracy and tone

> /team Build a Python CLI calculator with add/subtract/multiply/divide,
      write comprehensive unit tests, then code-review both files

> /team Fetch the OpenAI and Anthropic pricing pages, compare their model
      pricing in a markdown table, and fact-check the numbers

> /team Design a REST API schema for a todo app, implement it in Flask,
      write integration tests, and generate API documentation
```

| Command          | Description                          |
|------------------|--------------------------------------|
| `/team <task>`   | Start a multi-agent team run         |
| `/help`          | Show available commands              |
| `/history`       | Print conversation history           |
| `/clear`         | Clear conversation history           |
| `/quit`          | Exit                                 |

## Multi-Agent Team Architecture

The `/team` command implements a **self-organizing, message-driven multi-agent framework**:

```
/team <task>
    |
    v
+---------------------+
| Meta-Orchestrator   |   LLM reads the task and designs the team:
| (roster planning)   |   - Invents role names (e.g. "api_designer", "test_writer")
|                     |   - Writes system prompts for each role
|                     |   - Assigns tools from the available set
+---------------------+
    |
    v
+---------------------+     post_message("researcher_1", ...)
| Orchestrator Agent  | --------> activates researcher_1
|                     | --------> activates writer_1 (queued, runs after)
+---------------------+
    |                         |
    |    +--------------------+--------------------+
    |    |                                         |
    v    v                                         v
+--------------+    post_message(...)    +--------------+
| researcher_1 | ---------------------->| writer_1     |
| [web_fetch,  |                        | [write_file, |
|  read_file]  |                        |  web_fetch]  |
+--------------+                        +--------------+
                                               |
                              post_message("orchestrator_1", ...)
                                               |
                                               v
                                  +---------------------+
                                  | Orchestrator Agent  |
                                  | calls declare_done  |
                                  +---------------------+
```

**Key design decisions:**

- **No predefined roles** — the LLM creates roles, prompts, and tool assignments specific to each task. A haiku task gets a `haiku_poet` and `syllable_checker`; a coding task gets an `api_designer` and `test_writer`.
- **Message-driven activation** — each `post_message(to=...)` enqueues the recipient. Agents only run when addressed. Multiple recipients are queued in FIFO order.
- **Shared message board** — all agents communicate via a persistent JSONL message log. Each agent sees messages addressed to it, its role, or "all".
- **Per-agent context** — each agent maintains its own conversation history, keeping context windows small and focused.
- **Deadlock prevention** — if no agent is addressed, the orchestrator gets a fallback turn. Two consecutive fallbacks end the run. Max 30 turns total.

## Tools

Tools are the actions agents can perform. The system is designed to be **highly extensible** — adding a new tool is two steps:

1. **Define the schema** (OpenAI function-calling format) in `tools.py`
2. **Add a handler** (a Python function) in the `HANDLERS` dict

That's it. The new tool is immediately available to all agents.

### Built-in Tools

| Tool             | Description                              |
|------------------|------------------------------------------|
| `exec`           | Run any shell command (30s timeout)      |
| `read_file`      | Read a file's contents                   |
| `write_file`     | Write content to a file                  |
| `web_fetch`      | Fetch a URL and convert to markdown      |
| `pdf_fetch`      | Download and extract PDF text            |
| `generate_video` | Generate a video clip (OpenAI Sora)      |
| `use_skill`      | Load a skill's instructions by name      |
| `spawn_agent`    | Spawn a sub-agent for a subtask          |

### Team-only Tools

| Tool              | Description                                     |
|-------------------|-------------------------------------------------|
| `post_message`    | Send a message and activate the recipient agent |
| `read_messages`   | Read the shared message board                   |
| `read_artifacts`  | List files in the team workspace                |
| `declare_done`    | End the team run (orchestrator only)            |

## Skills

Skills extend what agents can do without writing code. Drop a markdown file in `skills/<name>/SKILL.md` and it's auto-discovered at startup.

```markdown
---
name: my-skill
description: One-line description.
---
Detailed instructions the model follows when this skill is activated.
```

**50+ included:** apple-notes, bear-notes, notion, obsidian, slack, discord, github, spotify-player, weather, openai-image-gen, 1password, tmux, and many more.

## Configuration

Stored at `~/.autocrew/config.json`:

```json
{
  "model": "gpt-5.2",
  "system_prompt": "You are AutoCrew, a helpful AI assistant."
}
```

## License

MIT
