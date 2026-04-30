"""
waifu-sprites state hook — writes to shared state file.

Import and call from agent hooks to drive sprite animations.

Usage:
    from waifu_hook import set_state, set_emotion, on_tool, detect_emotion

    set_state("thinking")
    set_emotion("e12")
    on_tool("terminal", "start")
    on_tool("terminal", "complete", result="success")
    detect_emotion("Great, that worked perfectly!")
"""

import json
import time
import os
from pathlib import Path

STATE_FILE = Path(os.path.expanduser("~/.hermes/plugins/waifu-sprites/state.json"))
VIDEOS_DIR = Path(os.path.expanduser("~/.hermes/plugins/waifu-sprites/videos"))
ASSETS_DIR = Path(os.path.expanduser("~/.hermes/plugins/waifu-sprites/assets"))

STATES = [
    "idle", "listening", "speaking", "thinking",
    "typing", "searching", "calculating", "fixing",
    "success", "error", "alert", "sleeping",
]

EMOTIONS = [
    "e1", "e2", "e3", "e4", "e5", "e6",
    "e7", "e8", "e9", "e10", "e11", "e12",
]

TOOL_STATES = {
    "read_file": "typing", "write_file": "typing", "patch": "typing",
    "search_files": "typing",
    "web_search": "searching", "web_extract": "searching",
    "session_search": "searching", "browser_navigate": "searching",
    "browser_snapshot": "searching", "browser_vision": "searching",
    "execute_code": "calculating",
    "terminal": "fixing", "process": "fixing",
    "delegate_task": "thinking", "todo": "thinking", "memory": "thinking",
    "skill_view": "thinking", "skill_manage": "thinking",
    "clarify": "alert",
    "text_to_speech": "speaking",
}

EMOTION_KEYWORDS = [
    (["love", "thank you", "cutie", "heart", "\u2661", "\u2764"], "e12"),
    (["sorry", "apolog", "unfortunately", "my bad", "oops"], "e7"),
    (["wow", "amazing!", "incredible!", "fascinating"], "e6"),
    (["hmm", "confus", "unclear", "not sure"], "e5"),
    (["what is", "how does", "curious", "interesting", "tell me more"], "e4"),
    (["found it", "perfect", "exactly", "done!", "no problem"], "e8"),
    (["let me", "i'll", "going to", "step by step", "working on"], "e11"),
    (["haha", "lol", "funny", "silly"], "e2"),
    (["i understand", "that's tough", "it's okay", "don't worry"], "e3"),
    (["great", "good", "nice", "awesome", "yes!", "exciting"], "e1"),
    (["this is a lot", "so many", "overwhelm", "massive"], "e10"),
    (["again", "as i said", "i already", "repeatedly"], "e9"),
]


def _read():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {"state": "idle", "emotion": None, "updated_at": 0}


def _write(state=None, emotion=None):
    data = _read()
    if state is not None:
        data["state"] = state
        data["emotion"] = None
    if emotion is not None:
        data["emotion"] = emotion
    data["updated_at"] = time.time()
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data))


def set_state(state: str):
    """Set an action state directly."""
    if state in STATES:
        _write(state=state)


def set_emotion(emotion: str):
    """Set an emotion state (e1-e12)."""
    if emotion in EMOTIONS:
        _write(emotion=emotion)


def on_tool(function_name: str, phase: str = "start", result: str = ""):
    """Map a tool call to the best sprite state."""
    if phase == "start":
        # Find best matching state
        state = TOOL_STATES.get(function_name)
        if not state:
            lo = function_name.lower()
            for kws, st in [
                (["search", "find", "browse", "web"], "searching"),
                (["file", "read", "write", "patch"], "typing"),
                (["code", "exec", "run"], "calculating"),
                (["terminal", "shell", "build", "git"], "fixing"),
                (["delegate", "skill", "todo", "memory"], "thinking"),
                (["speak", "voice"], "speaking"),
            ]:
                if any(k in lo for k in kws):
                    state = st
                    break
            if not state:
                state = "typing"
        _write(state=state)
    elif phase == "complete":
        is_err = any(k in str(result).lower() for k in [
            "error", "failed", "exception", "traceback",
        ])
        _write(state="error" if is_err else "idle")
    elif phase == "error":
        _write(state="error")


def detect_emotion(text: str) -> str:
    """Detect emotion from text and set it. Returns the emotion code."""
    if not text:
        return "e1"
    lower = text.lower()
    for keywords, emotion in EMOTION_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                _write(emotion=emotion)
                return emotion
    _write(emotion="e1")
    return "e1"


def idle():
    """Shorthand for idle state."""
    _write(state="idle")


def thinking():
    """Shorthand for thinking state."""
    _write(state="thinking")


def sleeping():
    """Shorthand for sleeping state."""
    _write(state="sleeping")
