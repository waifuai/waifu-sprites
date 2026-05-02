"""
waifu-sprites agent plugin — auto-maps agent activity to sprite states.

Hooks into the agent lifecycle:
  pre_tool_call  → set sprite to the matching action state (typing, searching, etc.)
  post_tool_call → set sprite to idle (success) or error
  post_llm_call  → detect emotion from response text
  on_session_start → set sprite to listening
  on_session_end   → set sprite to sleeping
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATE_FILE = Path.home() / ".hermes" / "plugins" / "waifu-sprites" / "state.json"

# ── State definitions ────────────────────────────────────────────

STATES = [
    "idle", "listening", "speaking", "thinking",
    "typing", "searching", "calculating", "fixing",
    "success", "error", "alert", "sleeping",
]

TOOL_STATES = {
    "read_file": "typing", "write_file": "typing", "patch": "typing",
    "search_files": "typing",
    "web_search": "searching", "web_extract": "searching",
    "session_search": "searching", "browser_navigate": "searching",
    "browser_snapshot": "searching", "browser_vision": "searching",
    "browser_get_images": "searching", "browser_back": "searching",
    "browser_click": "typing", "browser_type": "typing",
    "browser_press": "typing", "browser_scroll": "typing",
    "execute_code": "calculating", "code_execution_tool": "calculating",
    "browser_console": "calculating",
    "terminal": "fixing", "terminal_tool": "fixing", "process": "fixing",
    "delegate_task": "thinking", "todo": "thinking", "memory": "thinking",
    "cronjob": "thinking", "skill_view": "thinking", "skill_manage": "thinking",
    "skills_list": "thinking",
    "clarify": "alert",
    "text_to_speech": "speaking", "send_message": "speaking",
    "vision_analyze": "searching",
}

EMOTION_KEYWORDS = [
    (["love", "thank you", "you're sweet", "cutie", "heart",
      "glad i could help", "happy to help", "you're welcome", "\u2661", "\u2764"], "e12"),
    (["sorry", "apolog", "unfortunately", "my bad", "oops",
      "i was wrong", "i made an error", "couldn't find"], "e7"),
    (["this is a lot", "so many", "overwhelm", "massive", "complex"], "e10"),
    (["wow", "amazing!", "incredible!", "fascinating", "that's wild"], "e6"),
    (["hmm", "confus", "unclear", "not sure", "actually..."], "e5"),
    (["again", "as i said", "i already", "repeatedly"], "e9"),
    (["what is", "how does", "curious", "interesting", "tell me more", "what if"], "e4"),
    (["found it", "perfect", "exactly", "done!", "no problem", "absolutely"], "e8"),
    (["let me", "i'll", "going to", "step by step", "working on"], "e11"),
    (["haha", "lol", "lmao", "funny", "silly", "that's great"], "e2"),
    (["i understand", "that's tough", "it's okay", "don't worry", "hang in there"], "e3"),
    (["great", "good", "nice", "awesome", "wonderful", "yes!", "exciting"], "e1"),
]


def _write_state(state=None, emotion=None):
    """Write state to the shared file."""
    try:
        data = {}
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
        if state is not None:
            data["state"] = state
            data["emotion"] = None
        if emotion is not None:
            data["emotion"] = emotion
        data["updated_at"] = time.time()
        STATE_FILE.write_text(json.dumps(data))
    except Exception as e:
        logger.debug("waifu-sprites: failed to write state: %s", e)


def _get_tool_state(fn: str) -> str:
    """Map a tool name to the best action state."""
    if not fn:
        return "typing"
    if fn in TOOL_STATES:
        return TOOL_STATES[fn]
    lo = fn.lower()
    for kws, st in [
        (["search", "find", "browse", "web"], "searching"),
        (["file", "read", "write", "patch"], "typing"),
        (["code", "exec", "run", "math"], "calculating"),
        (["terminal", "shell", "build", "git"], "fixing"),
        (["delegate", "skill", "todo", "memory", "cron"], "thinking"),
        (["speak", "voice"], "speaking"),
    ]:
        if any(k in lo for k in kws):
            return st
    return "typing"


def _detect_emotion(text: str) -> str:
    """Detect emotion from text via keyword matching."""
    if not text:
        return "e1"
    lower = text.lower()
    for keywords, emotion in EMOTION_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return emotion
    return "e1"


# ── Hook callbacks ───────────────────────────────────────────────

def _on_pre_tool_call(*, tool_name: str = "", args: Any = None,
                      task_id: str = "", session_id: str = "", **_):
    """Before tool runs — set sprite to the matching action state."""
    state = _get_tool_state(tool_name)
    _write_state(state=state)


def _on_post_tool_call(*, tool_name: str = "", args: Any = None,
                       result: Any = None, task_id: str = "",
                       session_id: str = "", **_):
    """After tool completes — check result for errors."""
    is_err = False
    if result:
        r = str(result).lower()
        is_err = any(k in r for k in [
            "error", "failed", "exception", "traceback",
            "not found", "denied", "forbidden", "timeout",
        ])
    _write_state(state="error" if is_err else "idle")


def _on_pre_llm_call(*, task_id: str = "", session_id: str = "", **_):
    """Before LLM starts processing — show thinking."""
    _write_state(state="thinking")


def _on_post_llm_call(*, task_id: str = "", session_id: str = "",
                      assistant_response: Any = None,
                      assistant_message: Any = None,
                      assistant_tool_call_count: int = 0, **_):
    """After LLM responds — detect emotion from text response."""
    # If the model is calling tools, don't override (tool hooks will handle it)
    if assistant_tool_call_count > 0:
        _write_state(state="thinking")
        return

    # Extract response text
    text = ""
    if assistant_response and isinstance(assistant_response, str):
        text = assistant_response
    elif assistant_message is not None:
        content = getattr(assistant_message, "content", None)
        if content and isinstance(content, str):
            text = content

    if text:
        emotion = _detect_emotion(text)
        _write_state(state="speaking", emotion=emotion)
    else:
        _write_state(state="idle")


def _on_session_start(*, session_id: str = "", **_):
    """Agent session started — show listening."""
    _write_state(state="listening")


def _on_session_end(*, session_id: str = "", completed: bool = False,
                     interrupted: bool = False, **_):
    """Agent turn ended — preserve emotion from post_llm_call.

    on_session_end fires after every run_conversation() call (every turn),
    NOT just when the session truly exits. Setting 'sleeping' here would
    overwrite the detected emotion immediately after every response.

    Only set sleeping when the session is truly ending (atexit handler).
    """
    # Don't override emotion on normal turn completion.
    # The emotion from post_llm_call stays visible until next activity.
    pass


# ── Plugin registration ──────────────────────────────────────────

def register(ctx) -> None:
    """Called by the plugin loader. Registers all hooks."""
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("post_llm_call", _on_post_llm_call)
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
    logger.info("waifu-sprites: hooks registered — sprite state driven by agent activity")
