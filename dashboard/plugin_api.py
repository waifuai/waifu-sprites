"""
waifu-sprites dashboard plugin — video sprite backend.

Reads state from shared state file (~/.hermes/plugins/waifu-sprites/state.json).
Agent writes to this file via waifu_hook.py or direct POST.
Serves video sprites from the plugin's videos/ directory.
"""

import os
import json
import time
import random
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

# ── Paths ────────────────────────────────────────────────────────

PLUGIN_DIR = Path(__file__).parent.parent
VIDEOS_DIR = PLUGIN_DIR / "videos"
STATE_FILE = PLUGIN_DIR / "state.json"

# ── State definitions ────────────────────────────────────────────

STATES = [
    "idle", "listening", "speaking", "thinking",
    "typing", "searching", "calculating", "fixing",
    "success", "error", "alert", "sleeping",
]

EMOTION_NAMES = {
    "e1": "happy", "e2": "amused", "e3": "empathetic", "e4": "curious",
    "e5": "confused", "e6": "surprised", "e7": "embarrassed", "e8": "confident",
    "e9": "annoyed", "e10": "overwhelmed", "e11": "determined", "e12": "affectionate",
}

EMOTIONS = list(EMOTION_NAMES.keys())

# Tool → action state mapping
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


# ── Video cache ──────────────────────────────────────────────────

_cached_video_state = None
_cached_video_path = None


def _read_state() -> dict:
    """Read current state from the shared state file."""
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {"state": "idle", "emotion": None, "updated_at": 0}


def _write_state(state: str = None, emotion: str = None):
    """Write state to the shared file."""
    global _cached_video_state
    current = _read_state()
    if state is not None:
        current["state"] = state
        current["emotion"] = None  # action clears emotion
    if emotion is not None:
        current["emotion"] = emotion
    current["updated_at"] = time.time()
    _cached_video_state = None  # force video re-pick
    try:
        STATE_FILE.write_text(json.dumps(current))
    except Exception:
        pass


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


def _detect_emotion(text: str) -> str:
    if not text:
        return "e1"
    lower = text.lower()
    for keywords, emotion in EMOTION_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return emotion
    return "e1"


def _find_video(state_name: str):
    global _cached_video_state, _cached_video_path

    if not VIDEOS_DIR.exists():
        return None

    if (_cached_video_state == state_name and _cached_video_path
            and os.path.exists(_cached_video_path)):
        return _cached_video_path

    files = os.listdir(VIDEOS_DIR)
    candidates = []

    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext not in (".mp4", ".webm"):
            continue
        base = os.path.splitext(f)[0]
        if base == state_name or base.startswith(state_name + "-"):
            candidates.append(str(VIDEOS_DIR / f))

    # Fallback: numbered file for action states
    if not candidates and state_name in STATES:
        idx = STATES.index(state_name)
        num = str(idx + 1)
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in (".mp4", ".webm"):
                continue
            base = os.path.splitext(f)[0]
            if base == num or base.startswith(num + "-"):
                candidates.append(str(VIDEOS_DIR / f))

    if not candidates:
        return None

    chosen = random.choice(candidates)
    _cached_video_state = state_name
    _cached_video_path = chosen
    return chosen


# ── Routes ───────────────────────────────────────────────────────

@router.get("/status")
async def get_status():
    """Current state — reads from shared state file."""
    data = _read_state()
    state = data.get("state", "idle")
    emotion = data.get("emotion")
    display = emotion or state
    video = _find_video(display)

    return {
        "state": state,
        "emotion": emotion,
        "emotion_name": EMOTION_NAMES.get(emotion) if emotion else None,
        "display": display,
        "display_label": EMOTION_NAMES.get(display, display),
        "video": f"/api/plugins/waifu-sprites/video/{os.path.basename(video)}" if video else None,
    }


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


@router.get("/video/{filename}")
async def serve_video(filename: str):
    """Serve a video file."""
    clean = os.path.basename(filename)
    filepath = VIDEOS_DIR / clean
    if not filepath.exists():
        raise HTTPException(404, "Video not found")
    return FileResponse(
        str(filepath),
        media_type="video/mp4",
        headers={"Cache-Control": "no-store", "Accept-Ranges": "bytes"},
    )


@router.get("/states")
async def list_states():
    """List all available states and their videos."""
    result = {"actions": {}, "emotions": {}}
    if VIDEOS_DIR.exists():
        files = os.listdir(VIDEOS_DIR)
        for st in STATES:
            idx = STATES.index(st) + 1
            vids = [f for f in files if f.startswith(f"{idx}.") or f.startswith(f"{idx}-")]
            if vids:
                result["actions"][st] = vids
        for emo in EMOTIONS:
            vids = [f for f in files if f.startswith(f"{emo}.") or f.startswith(f"{emo}-")]
            if vids:
                result["emotions"][emo] = {"name": EMOTION_NAMES[emo], "videos": vids}
    return result
