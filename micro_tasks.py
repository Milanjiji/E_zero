# micro_tasks.py
import requests
import json
import re
import time

API_URL = "http://localhost:8000/v1/chat/completions"

# ANSI Colors
YELLOW = "\033[33m"
GREEN = "\033[32m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
RESET = "\033[0m"


def _render_line_for_terminal(line: str):
    """
    Properly highlight single-line and multi-line <cmd>...</cmd> blocks.
    Stateful: tracks whether we are inside a <cmd> block across lines.
    """
    if not hasattr(_render_line_for_terminal, "in_cmd"):
        _render_line_for_terminal.in_cmd = False

    # Handle opening and closing tags on same line
    if "<cmd>" in line and "</cmd>" in line:
        line2 = line.replace("<cmd>", "").replace("</cmd>", "")
        return f"{GREEN}{line2}{RESET}"

    # Opening tag
    if "<cmd>" in line:
        _render_line_for_terminal.in_cmd = True
        line2 = line.replace("<cmd>", "")
        return f"{GREEN}{line2}{RESET}"

    # Closing tag
    if "</cmd>" in line:
        _render_line_for_terminal.in_cmd = False
        line2 = line.replace("</cmd>", "")
        return f"{GREEN}{line2}{RESET}"

    # Inside block => color whole line
    if _render_line_for_terminal.in_cmd:
        return f"{GREEN}{line}{RESET}"

    # Inline replacements for single-line <cmd>...</cmd>
    line = re.sub(r"<cmd>(.*?)</cmd>", lambda m: f"{GREEN}{m.group(1)}{RESET}", line, flags=re.DOTALL)
    line = re.sub(r"`([^`]+)`", rf"{BLUE}\1{RESET}", line)
    line = re.sub(r"\*\*([^*]+)\*\*", rf"{MAGENTA}\1{RESET}", line)
    return line


def _extract_cmds(text: str):
    if not text:
        return []
    return [c.strip() for c in re.findall(r"<cmd>(.*?)</cmd>", text, flags=re.DOTALL)]


def _normalize_cmd(cmd: str):
    """Normalize command string for comparison (strip whitespace, collapse spaces)."""
    return re.sub(r"\s+", " ", cmd.strip())


def _remove_duplicate_cmd_blocks(paragraph: str, executed_set: set):
    """
    Remove <cmd> blocks that match commands already executed.
    Replace the block with a short marker 'Already done' to keep flow.
    """
    if not paragraph:
        return paragraph

    def repl(m):
        cmd = m.group(1).strip()
        if _normalize_cmd(cmd) in executed_set:
            return " (already done) "
        return f"<cmd>{cmd}</cmd>"

    return re.sub(r"<cmd>(.*?)</cmd>", repl, paragraph, flags=re.DOTALL)


def _dedupe_sentences(paragraph: str):
    """
    Remove exact duplicate sentences (heuristic). Preserve order.
    Also removes sentences that are near-duplicates by exact command match.
    """
    if not paragraph:
        return paragraph

    # split by sentence terminators (., ?, !). Keep terminator.
    parts = re.split(r'(?<=[\.\?\!])\s+', paragraph)
    seen = set()
    out = []
    for p in parts:
        s = p.strip()
        if not s:
            continue
        # Remove trailing duplicated whitespace
        s_norm = re.sub(r'\s+', ' ', s)
        if s_norm in seen:
            continue
        # If sentence contains a command that is already repeated earlier, skip it
        cmds = _extract_cmds(s_norm)
        skip = False
        for c in cmds:
            if _normalize_cmd(c) in seen:
                skip = True
                break
        if skip:
            continue
        # mark sentence as seen
        seen.add(s_norm)
        # also mark commands inside as seen to prevent future repeats
        for c in cmds:
            seen.add(_normalize_cmd(c))
        out.append(s_norm)
    return " ".join(out)


def _replace_editor_requests(paragraph: str):
    """
    If the model requests to 'open in editor', convert that to
    preferred terminal file-write commands suggestion, but do not invent large content.
    Here we simply replace occurrences of "open .* editor" with a suggestion to use printf/cat.
    """
    if not paragraph:
        return paragraph
    # replace common phrases like "open main.py in your preferred editor" -> suggest cat > main.py or printf
    paragraph = re.sub(r'open\s+([^\s,]+)\s+in\s+(your|the)\s+preferred\s+editor', r'use <cmd>cat > \1 <<\'EOF\'\\n...\\nEOF</cmd>', paragraph, flags=re.I)
    paragraph = re.sub(r'open\s+([^\s,]+)\s+in\s+an?\s+editor', r'use <cmd>cat > \1 <<\'EOF\'\\n...\\nEOF</cmd>', paragraph, flags=re.I)
    # avoid suggesting interactive editors like nano/vim explicitly
    paragraph = re.sub(r'\b(nano|vim|code|subl|gedit)\b', 'editor', paragraph, flags=re.I)
    return paragraph


def generate_micro_task_stream(
    goal: str,
    phase: str,
    previous_context: str = "",
    executed_commands: list = None,
    temperature: float = 0.25,
    max_tokens: int = -1,
):
    """
    Stream a micro-task paragraph for a single phase.

    Behavior:
    - Sends a trimmed previous_context and the list of executed_commands to the model.
    - Streams output live and colors <cmd> blocks.
    - Post-processes to remove duplicate commands/sentences and convert editor instructions
      to terminal-based suggestions.
    - Returns the final cleaned paragraph (with <cmd> tags where appropriate).
    """
    from prompts import MICRO_TASK_PROMPT

    executed_commands = executed_commands or []
    executed_set = set(_normalize_cmd(c) for c in executed_commands if c)

    # trim previous_context to keep recent context
    prev_trim = "None yet."
    if previous_context and previous_context.strip():
        prev_trim = previous_context.strip()[-900:]  # keep last ~900 chars

    # construct executed commands snippet for prompt
    prev_cmds_snippet = "None"
    if executed_set:
        prev_cmds_snippet = " ".join(f"<cmd>{c}</cmd>" for c in executed_set)

    user_prompt = (
        f"{MICRO_TASK_PROMPT}\n"
        f"Goal: {goal}\n"
        f"Phase: {phase}\n"
        f"Previous Steps Context: {prev_trim}\n"
        f"Previously executed commands: {prev_cmds_snippet}\n\n"
        f"Now produce the next connected paragraph."
    )

    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "local-model",
        "stream": True,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    print(f"\n{YELLOW}--- Micro Task: {phase} ---{RESET}\n")

    full_text = ""
    buffer = ""
    try:
        with requests.post(API_URL, json=payload, headers=headers, stream=True, timeout=300) as resp:
            for raw in resp.iter_lines():
                if not raw:
                    continue
                if not raw.startswith(b"data: "):
                    continue
                data = raw[len(b"data: "):]
                if data == b"[DONE]":
                    break
                try:
                    msg = json.loads(data.decode("utf-8"))
                except Exception:
                    continue

                token = ""
                try:
                    token = msg["choices"][0]["delta"].get("content", "")
                except Exception:
                    token = msg.get("content", "")

                if not token:
                    continue

                buffer += token
                full_text += token

                # print complete lines to preserve coloring
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    rendered = _render_line_for_terminal(line)
                    print(rendered + "\n", end="", flush=True)

            # remaining buffer
            if buffer.strip():
                rendered = _render_line_for_terminal(buffer)
                print(rendered, end="", flush=True)

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Stream error: {e}\n")

    paragraph = full_text.strip()

    # Post-process: convert editor requests -> terminal suggestion, remove duplicates
    paragraph = _replace_editor_requests(paragraph)
    paragraph = _remove_duplicate_cmd_blocks(paragraph, executed_set)
    paragraph = _dedupe_sentences(paragraph)

    # If all commands removed and paragraph became empty-ish, return a short fallback
    if not paragraph or paragraph.strip() in ("", "(already done)", "No action required."):
        paragraph = "No action required."

    # separator for readability
    print("\n")

    return paragraph


def generate_microtasks_for_phases(goal: str, phases: list, delay_between: float = 0.12):
    """
    Generate microtasks sequentially, passing previous context and executed commands.
    Returns list of paragraph strings (each may contain <cmd> tags).
    """
    results = []
    previous_context = ""
    executed_commands = []  # ordered unique list

    for ph in phases:
        paragraph = generate_micro_task_stream(goal, ph, previous_context, executed_commands)
        results.append(paragraph)

        # update executed_commands from this paragraph
        new_cmds = _extract_cmds(paragraph)
        for c in new_cmds:
            nc = _normalize_cmd(c)
            if nc and nc not in ( _normalize_cmd(x) for x in executed_commands ):
                executed_commands.append(c.strip())

        # update previous_context, keep tail to limit prompt size
        if previous_context:
            previous_context = (previous_context + "\n" + paragraph).strip()
        else:
            previous_context = paragraph.strip()

        if len(previous_context) > 1200:
            previous_context = previous_context[-1200:]

        if delay_between:
            time.sleep(delay_between)

    return results
