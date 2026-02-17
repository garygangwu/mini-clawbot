"""Multi-agent team runner."""

import json
import os
import time
import uuid

from openai import OpenAI

import config
import skills
import tools
from agent import run_agent_loop

# Tools available for assignment to agents (team tools are always added separately)
ASSIGNABLE_TOOLS = [s["function"]["name"] for s in tools.TOOL_SCHEMAS]
# Team tools that are always given to every agent
MANDATORY_TEAM_TOOLS = ["post_message", "read_messages", "read_artifacts"]

TEAMS_DIR = os.path.join(os.path.expanduser("~"), ".autocrew", "teams")

# --- Team tool schemas (not added to global tools.TOOL_SCHEMAS) ---

TEAM_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "post_message",
            "description": "Post a message to the team message board. Every recipient you address will be activated in order after your turn ends. Use 'to' to address a specific agent (by agent_id or role) or 'all' to hand off to the next agent in the roster.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient: an agent_id (e.g. 'coder_1'), a role (e.g. 'researcher'), or 'all'",
                    },
                    "content": {
                        "type": "string",
                        "description": "The message content",
                    },
                },
                "required": ["to", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_messages",
            "description": "Read recent messages from the team message board. Returns messages addressed to you, your role, or 'all'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "last_n": {
                        "type": "integer",
                        "description": "Number of recent messages to return (default 20)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_artifacts",
            "description": "List all files in the team artifacts directory.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "declare_done",
            "description": "Declare that the team's task is complete. Only the orchestrator should call this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "A summary of what was accomplished",
                    },
                },
                "required": ["summary"],
            },
        },
    },
]

TEAM_TOOL_NAMES = {s["function"]["name"] for s in TEAM_TOOL_SCHEMAS}


class TeamRun:
    def __init__(self, task: str):
        self.task = task
        self.run_id = uuid.uuid4().hex[:12]
        self.workspace = os.path.join(TEAMS_DIR, self.run_id)
        self.messages_file = os.path.join(self.workspace, "messages.jsonl")
        self.artifacts_dir = os.path.join(self.workspace, "artifacts")
        self.done = False
        self.done_summary = ""
        self.roster: list[dict] = []
        self.agent_histories: dict[str, list] = {}
        self._pending_agents: list[str] = []  # queue of resolved agent_ids to activate
        self._current_agent: str = ""
        self._consecutive_fallbacks: int = 0

        os.makedirs(self.artifacts_dir, exist_ok=True)
        # Create empty messages file
        open(self.messages_file, "w").close()

    # --- Message board ---

    def post_message(self, from_agent: str, to: str, content: str) -> str:
        entry = {
            "ts": time.time(),
            "from": from_agent,
            "to": to,
            "content": content,
        }
        with open(self.messages_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
        # Resolve recipient to an agent_id and enqueue if not already pending
        resolved = self._resolve_recipient(to)
        if resolved and resolved not in self._pending_agents:
            print(f"enqueueing agent: {resolved}, to: {to}", flush=True)
            self._pending_agents.append(resolved)
        print(f"pending agents: {self._pending_agents}", flush=True)
        return "Message posted."

    def read_messages(self, for_agent: str, last_n: int = 20) -> str:
        all_msgs = []
        with open(self.messages_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    all_msgs.append(json.loads(line))

        # Find the role for this agent
        agent_role = None
        for a in self.roster:
            if a["agent_id"] == for_agent:
                agent_role = a["role"]
                break

        # Filter: last N global + all addressed to this agent
        global_recent = all_msgs[-last_n:] if len(all_msgs) > last_n else all_msgs
        addressed = [
            m for m in all_msgs
            if m["to"] in (for_agent, agent_role, "all")
        ]

        # Deduplicate and sort by timestamp
        seen = set()
        combined = []
        for m in global_recent + addressed:
            key = (m["ts"], m["from"], m["content"])
            if key not in seen:
                seen.add(key)
                combined.append(m)
        combined.sort(key=lambda m: m["ts"])

        if not combined:
            return "(no messages yet)"

        lines = []
        for m in combined:
            lines.append(f"[{m['from']} → {m['to']}]: {m['content']}")
        return "\n".join(lines)

    def read_artifacts(self) -> str:
        files = []
        for root, _, filenames in os.walk(self.artifacts_dir):
            for fname in filenames:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, self.artifacts_dir)
                files.append(rel)
        if not files:
            return "(no artifacts yet)"
        return "Artifacts:\n" + "\n".join(f"- {f}" for f in sorted(files))

    def declare_done(self, summary: str) -> str:
        self.done = True
        self.done_summary = summary
        return "Team run marked as done."

    # --- Meta-orchestrator: plan the roster ---

    def plan_roster(self, client: OpenAI, model: str) -> list[dict]:
        tools_list = ", ".join(ASSIGNABLE_TOOLS)
        skill_names = [s["name"] for s in skills.list_skills()]
        skills_section = ""
        if skill_names:
            skills_section = (
                "\n\nAvailable skills (give agents 'use_skill' tool to access these):\n"
                + ", ".join(skill_names)
            )

        prompt = (
            "You are a meta-orchestrator. Given a task, design a team of specialized agents "
            "to accomplish it. Create custom roles tailored to this specific task.\n\n"
            f"Task: {self.task}\n\n"
            f"Available tools you can assign to agents: {tools_list}\n"
            f"(Every agent automatically gets: post_message, read_messages, read_artifacts)"
            f"{skills_section}\n\n"
            "Respond with a JSON object containing a 'roster' array. Each entry has:\n"
            '- "role": a short snake_case role name you invent (e.g. "haiku_poet", "fact_checker")\n'
            '- "count": how many of this role (usually 1, max 3)\n'
            '- "focus": what this agent should focus on\n'
            '- "system_prompt": instructions for this agent (2-4 sentences describing its job)\n'
            '- "tools": array of tool names from the available list above\n\n'
            "Rules:\n"
            "- Always include exactly 1 orchestrator role with tools: [] "
            "(it only needs the automatic team tools + declare_done)\n"
            "- The orchestrator coordinates and calls declare_done when finished\n"
            "- Total agents must be at most 6\n"
            "- Only create roles that are needed for this task\n"
            "- Keep system_prompts concise and task-specific\n\n"
            "Example:\n"
            '{"roster": [\n'
            '  {"role": "orchestrator", "count": 1, "focus": "Coordinate and finalize",\n'
            '   "system_prompt": "You coordinate the team. Delegate work, review progress, call declare_done when complete.",\n'
            '   "tools": []},\n'
            '  {"role": "haiku_poet", "count": 1, "focus": "Write haiku about recursion",\n'
            '   "system_prompt": "You are a poet. Write haiku in strict 5-7-5 syllable form. Post your drafts to the message board.",\n'
            '   "tools": ["write_file"]}\n'
            "]}"
        )

        print(f"\n[team] Planning roster for: {self.task}", flush=True)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        data = json.loads(raw)
        roster_spec = data.get("roster", [])

        # Build the valid tool name set for validation
        valid_tools = set(ASSIGNABLE_TOOLS) | TEAM_TOOL_NAMES

        # Expand into individual agents
        agents = []
        role_counts: dict[str, int] = {}
        for entry in roster_spec:
            role_name = entry["role"]
            count = min(entry.get("count", 1), 3)
            focus = entry.get("focus", "")
            system_prompt = entry.get("system_prompt", f"You are a {role_name} agent.")
            # Validate and filter tools
            agent_tools = [t for t in entry.get("tools", []) if t in valid_tools]
            # Add mandatory team tools
            for t in MANDATORY_TEAM_TOOLS:
                if t not in agent_tools:
                    agent_tools.append(t)
            # Orchestrator always gets declare_done
            if role_name == "orchestrator" and "declare_done" not in agent_tools:
                agent_tools.append("declare_done")

            for _ in range(count):
                role_counts[role_name] = role_counts.get(role_name, 0) + 1
                agent_id = f"{role_name}_{role_counts[role_name]}"
                agents.append({
                    "role": role_name,
                    "agent_id": agent_id,
                    "focus": focus,
                    "system_prompt": system_prompt,
                    "allowed_tools": agent_tools,
                })

        # Enforce constraints: ensure exactly 1 orchestrator
        has_orchestrator = any(a["role"] == "orchestrator" for a in agents)
        if not has_orchestrator:
            agents.insert(0, {
                "role": "orchestrator",
                "agent_id": "orchestrator_1",
                "focus": "Coordinate the team and declare done when finished",
                "system_prompt": (
                    "You coordinate the team. Delegate work to other agents, "
                    "review progress, and call declare_done when complete."
                ),
                "allowed_tools": MANDATORY_TEAM_TOOLS + ["declare_done"],
            })

        # Remove extra orchestrators, cap at 6
        orch_count = 0
        filtered = []
        for a in agents:
            if a["role"] == "orchestrator":
                orch_count += 1
                if orch_count > 1:
                    continue
            filtered.append(a)
        agents = filtered[:6]

        self.roster = agents

        print(f"[team] Roster ({len(agents)} agents):", flush=True)
        for a in agents:
            agent_tools_str = ", ".join(
                t for t in a["allowed_tools"] if t not in MANDATORY_TEAM_TOOLS
            )
            print(f"  - {a['agent_id']}: {a['focus']} [tools: {agent_tools_str}]", flush=True)

        return agents

    # --- Build tools for an agent ---

    def build_agent_tools(self, agent_id: str, agent_entry: dict) -> tuple[list[dict], dict]:
        """Return (tool_schemas, handler_overrides) for one agent turn."""
        allowed = set(agent_entry["allowed_tools"])

        # Filter global tool schemas
        schemas = [s for s in tools.TOOL_SCHEMAS if s["function"]["name"] in allowed]

        # Filter and add team tool schemas
        for s in TEAM_TOOL_SCHEMAS:
            if s["function"]["name"] in allowed:
                schemas.append(s)

        # Build team handlers that capture agent_id
        handler_overrides = {}
        if "post_message" in allowed:
            handler_overrides["post_message"] = lambda args, _aid=agent_id: self.post_message(
                _aid, args["to"], args["content"]
            )
        if "read_messages" in allowed:
            handler_overrides["read_messages"] = lambda args, _aid=agent_id: self.read_messages(
                _aid, args.get("last_n", 20)
            )
        if "read_artifacts" in allowed:
            handler_overrides["read_artifacts"] = lambda args: self.read_artifacts()
        if "declare_done" in allowed:
            handler_overrides["declare_done"] = lambda args: self.declare_done(args["summary"])

        return schemas, handler_overrides

    # --- Build system prompt for an agent ---

    def build_system_prompt(self, agent_entry: dict) -> str:
        roster_text = "\n".join(
            f"- {a['agent_id']} ({a['role']}): {a['focus']}" for a in self.roster
        )
        prompt = (
            f"{agent_entry['system_prompt']}\n\n"
            f"You are {agent_entry['agent_id']} (role: {agent_entry['role']}).\n"
            f"Your focus: {agent_entry['focus']}\n\n"
            f"Team roster:\n{roster_text}\n\n"
            f"Artifacts directory: {self.artifacts_dir}\n\n"
            f"IMPORTANT: When you post_message to an agent, that agent will be activated "
            f"automatically after your turn ends. Do NOT poll read_messages waiting for a "
            f"reply — it won't arrive until your turn is over. Post your message(s) and "
            f"then finish your turn by responding with text (even just 'Done.')."
        )

        # Add skill info if agent has use_skill
        if "use_skill" in agent_entry["allowed_tools"]:
            skill_list = skills.list_skills()
            if skill_list:
                lines = ["\n\n## Available Skills\n"]
                lines.append("Call the `use_skill` tool with the skill name to load its full instructions before performing it.\n")
                for s in skill_list:
                    lines.append(f"- **{s['name']}**: {s['description']}")
                prompt += "\n".join(lines)

        return prompt

    # --- Resolve recipients and manage the activation queue ---

    def _resolve_recipient(self, to: str) -> str | None:
        """Resolve a post_message 'to' value to a concrete agent_id."""
        # Roster order: non-orchestrators first, orchestrator last
        non_orch = [a for a in self.roster if a["role"] != "orchestrator"]
        orch = [a for a in self.roster if a["role"] == "orchestrator"]
        agent_order = non_orch + orch

        # Exact agent_id match
        for a in agent_order:
            if a["agent_id"] == to:
                return to

        # Role name match — return first agent of that role
        for a in agent_order:
            if a["role"] == to:
                return a["agent_id"]

        return None

    def _pop_next_agent(self) -> str | None:
        """Pop and return the next agent from the pending queue."""
        if self._pending_agents:
            return self._pending_agents.pop(0)
        return None

    # --- Main runner ---

    def run(self) -> str:
        cfg = config.load()
        client = OpenAI()
        model = cfg["model"]

        # Step 1: Plan roster
        self.plan_roster(client, model)

        # Step 2: Post initial task
        self.post_message("system", "all", f"TASK: {self.task}")

        # Step 3: Find orchestrator — it always kicks things off
        orch_id = None
        for a in self.roster:
            if a["role"] == "orchestrator":
                orch_id = a["agent_id"]
                break
        next_agent = orch_id

        max_turns = 30
        turn_count = 0

        while next_agent and turn_count < max_turns and not self.done:
            turn_count += 1
            self._current_agent = next_agent

            # Find agent entry
            agent_entry = None
            for a in self.roster:
                if a["agent_id"] == next_agent:
                    agent_entry = a
                    break
            if not agent_entry:
                break

            print(f"\n{'='*60}", flush=True)
            print(f"  TURN {turn_count}/{max_turns} — {next_agent}", flush=True)
            print(f"  remaining agents: {self._pending_agents}", flush=True)
            print(f"{'='*60}", flush=True)

            # Build tools and handlers
            schemas, handler_overrides = self.build_agent_tools(next_agent, agent_entry)

            # Temporarily inject team handlers
            original_handlers = {}
            for name, handler in handler_overrides.items():
                original_handlers[name] = tools.HANDLERS.get(name)
                tools.HANDLERS[name] = handler

            try:
                # Build messages
                system_prompt = self.build_system_prompt(agent_entry)
                history = self.agent_histories.get(next_agent, [])

                board_snapshot = self.read_messages(next_agent, last_n=20)
                user_msg = (
                    f"Turn {turn_count}. Continue working on your tasks.\n\n"
                    f"Current message board:\n{board_snapshot}"
                )

                messages = [{"role": "system", "content": system_prompt}]
                messages.extend(history)
                messages.append({"role": "user", "content": user_msg})

                # Run agent loop (cap iterations so agents yield their turn)
                reply = run_agent_loop(client, model, messages, schemas, max_iterations=16)

                # Save to per-agent history (trimmed)
                history.append({"role": "user", "content": user_msg})
                history.append({"role": "assistant", "content": reply})
                if len(history) > 6:
                    history = history[-6:]
                self.agent_histories[next_agent] = history

            finally:
                for name, orig in original_handlers.items():
                    if orig is None:
                        tools.HANDLERS.pop(name, None)
                    else:
                        tools.HANDLERS[name] = orig

            if self.done:
                break

            # Resolve next agent from the pending queue
            resolved = self._pop_next_agent()
            print('^'*60, flush=True)
            print(f"POP the next agent: {resolved}", flush=True)
            print(f"remaining agents: {self._pending_agents}", flush=True)
            print('^'*60, flush=True)
            if resolved:
                next_agent = resolved
                self._consecutive_fallbacks = 0
            else:
                # Fallback to orchestrator
                self._consecutive_fallbacks += 1
                if self._consecutive_fallbacks >= 2:
                    self.done_summary = "(team ended: orchestrator could not route work)"
                    print(f"\n[team] {self.done_summary}", flush=True)
                    break
                next_agent = orch_id

        if self.done:
            print(f"\n[team] Done! Summary: {self.done_summary}", flush=True)
        elif turn_count >= max_turns:
            self.done_summary = "(team reached max turns without completing)"
            print(f"\n[team] {self.done_summary}", flush=True)

        return self.done_summary
