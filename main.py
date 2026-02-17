#!/usr/bin/env python3
"""AutoCrew: a multi-agent team CLI powered by OpenAI."""

import sys

import agent
import session
import team


COMMANDS = {
    "/quit": "Exit the chat",
    "/clear": "Clear conversation history",
    "/history": "Show conversation history",
    "/team": "Start a multi-agent team run (usage: /team <task>)",
    "/help": "Show available commands",
}


def print_help():
    print("Commands:")
    for cmd, desc in COMMANDS.items():
        print(f"  {cmd:12s} {desc}")


def print_history():
    turns = session.load()
    if not turns:
        print("(no history)")
        return
    for turn in turns:
        role = turn["role"]
        prefix = "You" if role == "user" else "Bot"
        print(f"[{prefix}] {turn['content']}")


def main():
    print("AutoCrew (type /help for commands, /quit to exit)")
    print()

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        if user_input == "/quit":
            break
        elif user_input == "/clear":
            session.clear()
            print("History cleared.")
            continue
        elif user_input == "/history":
            print_history()
            continue
        elif user_input == "/help":
            print_help()
            continue
        elif user_input.startswith("/team "):
            task = user_input[6:].strip()
            if not task:
                print("Usage: /team <task description>")
                continue
            try:
                run = team.TeamRun(task)
                summary = run.run()
                session.append("user", f"/team {task}")
                session.append("assistant", f"[Team result] {summary}")
                print(f"\n{summary}")
            except Exception as e:
                print(f"Team error: {e}", file=sys.stderr)
            continue

        try:
            agent.chat(user_input)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
