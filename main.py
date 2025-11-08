import requests
import json
import re
from phase_init import Phase
from mode_detector import detect_mode
from goal_refine import refine_goal_interactive
from micro_tasks import generate_microtasks_for_phases
from run_commands import execute_microtask_output

API_URL = "http://localhost:8000/v1/chat/completions"

# ANSI Colors
YELLOW = "\033[33m"
GREEN = "\033[32m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
RESET = "\033[0m"

def colorize(text, in_block):
    # --- Detect triple backticks (enter/exit code block) ---
    if "```" in text:
        in_block = not in_block
        # Print the triple backtick line itself normally
        return GREEN + text + RESET if in_block else RESET + text + RESET, in_block

    # --- If inside code block → color entire line green ---
    if in_block:
        return GREEN + text + RESET, in_block

    # Inline code: `file.py` → blue
    text = re.sub(r"`([^`]+)`", rf"{BLUE}\1{RESET}", text)

    # Bold text: **title** → magenta
    text = re.sub(r"\*\*([^*]+)\*\*", rf"{MAGENTA}\1{RESET}", text)

    return text, in_block


def stream_chat(prompt):
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "local-model",
        "stream": True,
        "temperature": 0.7,
        "max_tokens": -1,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    print(f"\n{YELLOW}--- Streaming Response ---{RESET}\n")

    in_code_block = False
    buffer = ""

    with requests.post(API_URL, json=payload, headers=headers, stream=True) as r:
        for raw in r.iter_lines():
            if not raw:
                continue
            if not raw.startswith(b"data: "):
                continue

            data = raw[len(b"data: "):]
            if data == b"[DONE]":
                break

            try:
                msg = json.loads(data.decode())
                token = msg["choices"][0]["delta"].get("content", "")
                if not token:
                    continue

                buffer += token

                # Print only when we see complete newlines:
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    colored, in_code_block = colorize(line, in_code_block)
                    print(colored + "\n", end="", flush=True)

            except:
                continue

    print(f"\n{YELLOW}--- End of Response ---{RESET}\n")

if __name__ == "__main__":
    while True:
        user_message = input("You: ").strip()

        if user_message.lower() in ["quit", "exit"]:
            print("Goodbye!")
            break

        # --- Auto detect mode ---
        mode = detect_mode(user_message)
        print(f"[Mode detected: {mode}]")

        # --- Phase Mode ---
        if mode == "phase":
            result = refine_goal_interactive(user_message)
            refined_goal = result["refined_goal_paragraph"]

            phases = Phase.init(refined_goal)
            micro_paragraphs = generate_microtasks_for_phases(refined_goal, phases)  # This streams & prints already
            # print("Execution process ...")

            # # run commands for each microtask paragraph (one by one)
            # from run_commands import execute_microtask_output

            # for para in micro_paragraphs:
            #     execute_microtask_output(para)

            # If Phase.init returns the list instead of printing, uncomment below:
            # for p in phases:
            #     print("- " + p)

        # --- Normal Chat Mode (streaming) ---
        else:
            print("\nResponse:\n")
            stream_chat(user_message)