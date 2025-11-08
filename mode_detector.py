# mode_detector.py
import requests
import re
from prompts import MODE_DETECTION_PROMPT

API_URL = "http://localhost:8000/v1/chat/completions"

# regex to catch clear task/imperative phrases that indicate phase-mode
PHRASE_REGEX = re.compile(
    r"\b(create|build|make|setup|set up|initialize|initialise|install|deploy|generate|scaffold|bootstrap|start|how to|how do i|steps?|step-by-step|guide|roadmap|plan|break down|break into steps)\b",
    flags=re.IGNORECASE
)

def _call_model(user_input: str):
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": "local-model",
        "stream": False,
        "temperature": 0.0,
        "max_tokens": 8,
        "messages": [
            {"role": "user", "content": MODE_DETECTION_PROMPT + user_input}
        ]
    }
    try:
        r = requests.post(API_URL, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        # try chat completion format then fallback
        if "choices" in data and len(data["choices"]) > 0:
            # chat style: choices[0].message.content or choices[0].delta in streaming
            choice = data["choices"][0]
            # In some servers the content is in choice["message"]["content"]
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"].strip().lower()
            # Or sometimes 'text' or 'content' fields
            if "text" in choice:
                return choice["text"].strip().lower()
            if "content" in choice:
                return choice["content"].strip().lower()
        # Fallback: if server returns top-level 'content'
        if "content" in data:
            return data["content"].strip().lower()
    except Exception:
        pass
    return None

def detect_mode(user_input: str) -> str:
    """
    Return 'phase' or 'normal'.
    Uses a regex-first quick check for imperative/task words (fast),
    then asks the model. If model disagrees but regex detects task keywords,
    prefer 'phase'.
    """
    text = user_input.strip()

    # FAST deterministic check first
    if PHRASE_REGEX.search(text):
        # If obvious task wording, return phase immediately
        return "phase"

    # Otherwise call model for classification
    model_out = _call_model(text)
    if model_out in ("phase", "normal"):
        return model_out

    # If model output is unexpected or empty, fallback to normal
    return "normal"
