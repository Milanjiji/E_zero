# goal_refine.py
import requests
import json
import re
import ast
from prompts import GOAL_QUESTIONS_PROMPT, GOAL_SUMMARIZE_PROMPT

API_URL = "http://localhost:8000/v1/chat/completions"

def _call_completion(messages, temperature=0.0, max_tokens=200, timeout=15):
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "local-model",
        "stream": False,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages
    }
    r = requests.post(API_URL, json=payload, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    # try chat-style content
    if "choices" in data and len(data["choices"]) > 0:
        choice = data["choices"][0]
        if isinstance(choice, dict):
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"].strip()
            if "text" in choice:
                return choice["text"].strip()
            if "content" in choice:
                return choice["content"].strip()
    if "content" in data:
        return data["content"].strip()
    # fallback: raw response to string
    return json.dumps(data)

def _extract_json_array(text):
    """
    Find the first JSON array ( [...] ) in text and parse it.
    Returns Python object or None.
    """
    if not text:
        return None
    # find first '[' ... ']' segment
    m = re.search(r'\[.*\]', text, flags=re.DOTALL)
    if not m:
        return None
    arr_text = m.group(0)
    try:
        return json.loads(arr_text)
    except Exception:
        try:
            return ast.literal_eval(arr_text)
        except Exception:
            return None

def refine_goal_interactive(raw_goal: str):
    """
    1) Ask model to produce JSON array of clarifying questions for raw_goal.
    2) Loop through array, prompt user to answer each question.
    3) Send original goal + collected Q&A to model to produce one concise paragraph.
    4) Print and return the final paragraph.
    """
    # Step 1: request questions
    q_prompt = GOAL_QUESTIONS_PROMPT + raw_goal
    try:
        q_text = _call_completion(
            messages=[{"role":"user","content": q_prompt}],
            temperature=0.0,
            max_tokens=300
        )
    except Exception as e:
        q_text = ""

    questions = _extract_json_array(q_text)

    # If model didn't return JSON array, create a fallback: single open text question
    if not isinstance(questions, list) or len(questions) == 0:
        questions = [
            {"id": 1, "question": "Please describe what specific kind of project you want (1–2 short words).", "type": "text", "choices": []}
        ]

    # Normalize questions: ensure fields exist
    norm_questions = []
    for idx, q in enumerate(questions, start=1):
        if isinstance(q, dict):
            question_text = q.get("question") or q.get("q") or str(q)
            qtype = q.get("type", "text")
            choices = q.get("choices", []) or []
            # if choices given as dict or string, normalize to list
            if isinstance(choices, str):
                choices = [c.strip() for c in choices.split("|") if c.strip()]
            norm_questions.append({
                "id": q.get("id", idx),
                "question": question_text.strip(),
                "type": "choice" if qtype.lower().startswith("cho") and choices else "text",
                "choices": choices
            })
        else:
            norm_questions.append({
                "id": idx,
                "question": str(q),
                "type": "text",
                "choices": []
            })

    # Step 2: loop and get answers from user
    qa_list = []
    for q in norm_questions:
        if q["type"] == "choice" and q["choices"]:
            # present choices numerically and alphabetically as A/B/C
            print("\n" + q["question"])
            for i, choice in enumerate(q["choices"], start=1):
                letter = chr(ord('A') + i - 1)
                print(f"  {letter}) {choice}")
            ans = input("Your choice (letter or text): ").strip()
            # normalize letter -> choice text
            if len(ans) == 1 and ans.upper() >= 'A' and (ord(ans.upper()) - 65) < len(q["choices"]):
                idx = ord(ans.upper()) - 65
                answer = q["choices"][idx]
            else:
                answer = ans
        else:
            # free text
            answer = input("\n" + q["question"] + "\nYour answer: ").strip()
        qa_list.append({"question": q["question"], "answer": answer})

    # Step 3: summarize into one concise paragraph
    # Build a compact input for summarizer
    qa_json = json.dumps(qa_list, ensure_ascii=False)
    summarize_input = f"Original Goal: {raw_goal}\nClarifying Q&A: {qa_json}"

    try:
        summary = _call_completion(
            messages=[{"role":"user","content": GOAL_SUMMARIZE_PROMPT + "\n" + summarize_input}],
            temperature=0.15,
            max_tokens=160
        )
    except Exception:
        summary = raw_goal.strip()

    # Take only first paragraph / line(s)
    # Remove excessive whitespace
    final = " ".join(line.strip() for line in summary.splitlines() if line.strip())
    print("\nRefined Goal:\n")
    print(final + "\n")

    # return structured result for downstream use
    return {
        "refined_goal_paragraph": final,
        "qa": qa_list,
        "original_goal": raw_goal
    }
