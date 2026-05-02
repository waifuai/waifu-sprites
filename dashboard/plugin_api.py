"""
waifu-sprites dashboard plugin — sprite backend.

Reads state from shared state file (~/.hermes/plugins/waifu-sprites/state.json).
Agent writes to this file via __init__.py hooks.
Serves spritesheet from the plugin's assets/ directory.

Spritesheet format:
  - spritesheet.webp: 1536x1872 atlas, 8 cols x 9 rows, 192x208 per cell
  - Each row is an animation state, each column is a frame
"""

import os
import json
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

# ── Paths ────────────────────────────────────────────────────────

PLUGIN_DIR = Path(__file__).parent.parent
ASSETS_DIR = PLUGIN_DIR / "assets"
SPRITESHEET = ASSETS_DIR / "spritesheet.webp"
STATE_FILE = PLUGIN_DIR / "state.json"

# ── Sprite atlas definition ───────────────────────────────────────

ATLAS_WIDTH = 1536
ATLAS_HEIGHT = 1872
CELL_WIDTH = 192   # 1536 / 8
CELL_HEIGHT = 208  # 1872 / 9
COLS = 8
ROWS = 9

# Row definitions: row index, name, frame count, frame durations (ms)
ATLAS_ROWS = [
    {"row": 0, "name": "idle",          "frames": 6, "duration": 200},
    {"row": 1, "name": "running-right",  "frames": 8, "duration": 120},
    {"row": 2, "name": "running-left",   "frames": 8, "duration": 120},
    {"row": 3, "name": "waving",         "frames": 4, "duration": 250},
    {"row": 4, "name": "jumping",        "frames": 5, "duration": 180},
    {"row": 5, "name": "failed",         "frames": 8, "duration": 150},
    {"row": 6, "name": "waiting",        "frames": 6, "duration": 300},
    {"row": 7, "name": "running",        "frames": 6, "duration": 140},
    {"row": 8, "name": "review",         "frames": 6, "duration": 250},
]

# ── Hermes state → sprite row mapping ─────────────────────────────

STATE_TO_ROW = {
    # Action states
    "idle":         0,  # idle
    "typing":       1,  # running-right (busy/working)
    "listening":    2,  # running-left (attentive)
    "speaking":     3,  # waving (addressing user)
    "searching":    1,  # running-right (same as typing — working)
    "calculating":  7,  # running (heavy work)
    "fixing":       7,  # running (same as calculating)
    "success":      4,  # jumping (celebration)
    "error":        5,  # failed
    "alert":        6,  # waiting (asking user)
    "thinking":     6,  # waiting (processing)
    "sleeping":     0,  # idle (peaceful rest)

    # Emotion states — map to review (affectionate/positive) or nearest
    "happy":        4,  # jumping
    "amused":       4,  # jumping
    "empathetic":   6,  # waiting (gentle)
    "curious":      8,  # review
    "confused":     5,  # failed
    "surprised":    4,  # jumping
    "embarrassed":  3,  # waving (shy)
    "confident":    4,  # jumping
    "annoyed":      5,  # failed
    "overwhelmed":  6,  # waiting
    "determined":   7,  # running
    "affectionate": 8,  # review

    # Legacy e-code emotions
    "e1": 4, "e2": 4, "e3": 6, "e4": 8,
    "e5": 5, "e6": 4, "e7": 3, "e8": 4,
    "e9": 5, "e10": 6, "e11": 7, "e12": 8,
}

EMOTION_NAMES = {
    "e1": "happy", "e2": "amused", "e3": "empathetic", "e4": "curious",
    "e5": "confused", "e6": "surprised", "e7": "embarrassed", "e8": "confident",
    "e9": "annoyed", "e10": "overwhelmed", "e11": "determined", "e12": "affectionate",
}

STATES = [
    "idle", "listening", "speaking", "thinking",
    "typing", "searching", "calculating", "fixing",
    "success", "error", "alert", "sleeping",
]

EMOTIONS = list(EMOTION_NAMES.keys())

# ── Tool → state mapping (kept for API compatibility) ────────────

TOOL_STATES = {
    "read_file": "typing", "write_file": "typing", "patch": "typing",
    "search_files": "typing", "file_read": "typing", "file_write": "typing",
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
    "cronjob": "thinking", "skills_list": "thinking", "skill_view": "thinking",
    "skill_manage": "thinking",
    "clarify": "alert",
    "text_to_speech": "speaking", "send_message": "speaking",
}

EMOTION_KEYWORDS = [
    (["love", "thank you", "you're sweet", "cutie", "heart", "glad i could help",
      "happy to help", "you're welcome", "\u2661", "\u2764"], "e12"),
    (["sorry", "apolog", "unfortunately", "my bad", "oops", "i was wrong",
      "i made an error", "couldn't find", "i can't", "i'm afraid"], "e7"),
    (["this is a lot", "so many", "overwhelm", "massive", "complex"], "e10"),
    (["wow", "whoa", "amazing!", "incredible!", "no way",
      "fascinating", "that's wild", "didn't expect"], "e6"),
    (["hmm", "confus", "unclear", "ambiguous", "what do you mean",
      "not sure what", "i'm not sure", "actually..."], "e5"),
    (["again", "repeatedly", "as i said", "i already", "once more"], "e9"),
    (["what is", "how does", "tell me more", "interesting",
      "i wonder", "curious", "what if"], "e4"),
    (["found it", "here's", "let me show", "perfect", "exactly",
      "done!", "easy", "no problem", "absolutely", "definitely"], "e8"),
    (["let me", "i'll", "going to", "here's how", "step by step",
      "first,", "working on"], "e11"),
    (["haha", "lol", "lmao", "funny", "joke", "silly", "that's great"], "e2"),
    (["i understand", "that's tough", "i'm sorry to hear", "it's okay",
      "don't worry", "take your time", "hang in there"], "e3"),
    (["great", "good", "nice", "awesome", "wonderful", "yes!",
      "sounds good", "let's go", "exciting"], "e1"),
]


# ── State helpers ────────────────────────────────────────────────

def _read_state() -> dict:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {"state": "idle", "emotion": None, "updated_at": 0}


def _write_state(state: str = None, emotion: str = None):
    current = _read_state()
    if state is not None:
        current["state"] = state
        current["emotion"] = None
    if emotion is not None:
        current["emotion"] = emotion
    current["updated_at"] = time.time()
    try:
        STATE_FILE.write_text(json.dumps(current))
    except Exception:
        pass


def _detect_emotion(text: str) -> str:
    if not text:
        return "e1"
    lower = text.lower()
    for keywords, emotion in EMOTION_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return emotion
    return "e1"


def _get_tool_state(fn: str) -> str:
    if not fn:
        return "typing"
    if fn in TOOL_STATES:
        return TOOL_STATES[fn]
    lo = fn.lower()
    for kws, st in [
        (["search", "find", "browse", "navigate", "web"], "searching"),
        (["file", "read", "write", "patch", "edit"], "typing"),
        (["code", "exec", "run", "math", "calcul"], "calculating"),
        (["terminal", "shell", "build", "install", "git"], "fixing"),
        (["delegate", "skill", "todo", "memory", "cron"], "thinking"),
        (["speak", "voice", "say"], "speaking"),
    ]:
        if any(k in lo for k in kws):
            return st
    return "typing"


def _get_row_for_state(state: str, emotion: str = None) -> dict:
    """Get the atlas row info for the current display state."""
    display = emotion or state
    row_idx = STATE_TO_ROW.get(display, 0)
    return ATLAS_ROWS[row_idx]


# ── Routes ───────────────────────────────────────────────────────

@router.get("/status")
async def get_status():
    """Current state with spritesheet row info."""
    data = _read_state()
    state = data.get("state", "idle")
    emotion = data.get("emotion")
    display = emotion or state

    row_info = _get_row_for_state(state, emotion)

    return {
        "state": state,
        "emotion": emotion,
        "emotion_name": EMOTION_NAMES.get(emotion) if emotion else None,
        "display": display,
        "display_label": EMOTION_NAMES.get(display, display),
        "row": row_info["row"],
        "row_name": row_info["name"],
        "frames": row_info["frames"],
        "frame_duration": row_info["duration"],
    }


@router.get("/atlas")
async def get_atlas():
    """Full atlas definition for the frontend sprite animator."""
    return {
        "atlas": {
            "width": ATLAS_WIDTH,
            "height": ATLAS_HEIGHT,
            "cell_width": CELL_WIDTH,
            "cell_height": CELL_HEIGHT,
            "cols": COLS,
            "rows": ROWS,
        },
        "states": ATLAS_ROWS,
        "spritesheet": "/api/plugins/waifu-sprites/spritesheet",
    }


@router.get("/spritesheet")
async def serve_spritesheet():
    """Serve the spritesheet.webp file."""
    if not SPRITESHEET.exists():
        raise HTTPException(404, "Spritesheet not found. Place spritesheet.webp in assets/")
    return FileResponse(
        str(SPRITESHEET),
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/state")
async def set_state(body: dict):
    """Set action state or emotion."""
    state = body.get("state", "")
    emotion = body.get("emotion")

    if emotion and emotion in EMOTIONS:
        _write_state(emotion=emotion)
        return {"ok": True, "emotion": emotion}

    if state in EMOTIONS:
        _write_state(emotion=state)
        return {"ok": True, "emotion": state}

    if state in STATES:
        _write_state(state=state)
        return {"ok": True, "state": state}

    raise HTTPException(400, f"Invalid state: {state}")


@router.post("/tool")
async def on_tool(body: dict):
    """Auto-map tool name to action state."""
    fn = body.get("function_name", "")
    phase = body.get("phase", "start")

    if phase == "start":
        _write_state(state=_get_tool_state(fn))
    elif phase == "complete":
        result = str(body.get("result", "")).lower()
        is_err = any(k in result for k in ["error", "failed", "exception", "traceback"])
        _write_state(state="error" if is_err else "idle")
    elif phase == "error":
        _write_state(state="error")

    data = _read_state()
    return {"ok": True, "state": data.get("state"), "emotion": data.get("emotion")}


@router.post("/emotion")
async def detect_emotion(body: dict):
    """Detect emotion from text and set it."""
    text = body.get("text", "")
    emotion = _detect_emotion(text)
    _write_state(emotion=emotion)
    return {"ok": True, "emotion": emotion, "label": EMOTION_NAMES.get(emotion)}


@router.get("/states")
async def list_states():
    """List all available states and their atlas mapping."""
    return {
        "actions": {s: STATE_TO_ROW.get(s, 0) for s in STATES},
        "emotions": {e: {"name": EMOTION_NAMES[e], "row": STATE_TO_ROW.get(e, 0)} for e in EMOTIONS},
        "atlas": ATLAS_ROWS,
    }
