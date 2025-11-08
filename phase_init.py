# phase_init.py
import requests
import json
import re
import ast

from prompts import PHASE_PLANNING_PROMPT

API_URL = "http://localhost:8000/v1/chat/completions"

YELLOW = "\033[33m"
RESET = "\033[0m"

class Phase:
    @staticmethod
    def init(user_task: str, temperature: float = 0.7, max_tokens: int = -1):
        """
        Streams response from local model but does not print intermediate tokens.
        At the end it parses and prints ONLY a Python list of short phase titles.
        """

        # Build the final prompt (prompt + user task)
        prompt_text = PHASE_PLANNING_PROMPT + user_task

        headers = {"Content-Type": "application/json"}
        payload = {
            "model": "local-model",
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt_text}
            ],
        }

        # Collect streamed tokens silently
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
                    if token:
                        buffer += token
                except Exception:
                    # ignore malformed chunks
                    continue

        # Try parse: 1) extract bracketed list substring, 2) json.loads -> ast.literal_eval -> fallback extract lines
        cleaned = buffer.strip()

        # Attempt to find the first [...] segment (greedy, DOTALL)
        list_match = re.search(r'\[.*\]', cleaned, flags=re.DOTALL)
        parsed = None

        if list_match:
            list_text = list_match.group(0)
            # Try JSON first
            try:
                parsed = json.loads(list_text)
            except Exception:
                # Try Python literal eval (single quotes allowed)
                try:
                    parsed = ast.literal_eval(list_text)
                except Exception:
                    parsed = None

        # Fallback: extract top-level phase headings (lines that look like short titles)
        if parsed is None:
            # Extract lines that are not code blocks and not empty
            lines = []
            for line in cleaned.splitlines():
                # remove markdown/numbering prefixes like "1.", "- ", "Phase 1:", etc
                s = re.sub(r'^\s*[-*]\s*', '', line)            # bullets
                s = re.sub(r'^\s*\d+\.\s*', '', s)              # numbering
                s = re.sub(r'^\s*Phase\s*\d+\s*:?\s*', '', s, flags=re.IGNORECASE)  # "Phase 1:"
                s = s.strip()
                # reject code fence lines and empty lines
                if not s:
                    continue
                if s.startswith("```") or s.startswith("```"):
                    continue
                # keep only short lines (heuristic)
                if 2 <= len(s.split()) <= 10:
                    lines.append(s)
            # Deduplicate while preserving order
            seen = set()
            dedup = []
            for l in lines:
                if l not in seen:
                    seen.add(l)
                    dedup.append(l)
            parsed = dedup if dedup else [cleaned]  # if nothing parsed, return the raw text as single item

        # Normalize parsed into a list of short strings
        if isinstance(parsed, list):
            phases = []
            for item in parsed:
                if isinstance(item, str):
                    s = item.strip()
                    # If the item contains "Phase" prefix, remove it
                    s = re.sub(r'^\s*Phase\s*\d+\s*[:\-]?\s*', '', s, flags=re.IGNORECASE).strip()
                    phases.append(s)
                else:
                    # convert other types to string
                    phases.append(str(item).strip())
        else:
            phases = [str(parsed).strip()]

        # Final normalization: keep short titles only (truncate extras)
        final = []
        for p in phases:
            # strip trailing punctuation
            p = p.rstrip(" .:-")
            # collapse multiple spaces
            p = re.sub(r'\s+', ' ', p)
            final.append(p)

        # Print only the Python list (single line)
        print(f"\n{YELLOW}{final}{RESET}\n")
        return final
