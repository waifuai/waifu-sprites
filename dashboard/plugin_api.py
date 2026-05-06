"""
waifu-sprites dashboard plugin — video backend.

Reads state from shared state file. Serves video clips for each state.
Each state maps to a video file in the videos/ directory.
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
DOCS_VIDEOS_DIR = PLUGIN_DIR / "docs" / "videos"
STATE_FILE = PLUGIN_DIR / "state.json"

CONFIG_FILE = PLUGIN_DIR / "config.json"

DEFAULT_CONFIG = {
    "overlay_enabled": True,
    "overlay_size": 320,
    "poll_interval_ms": 2000,
}


def _read_config() -> dict:
    """Read config with defaults."""
    cfg = dict(DEFAULT_CONFIG)
    try:
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text())
            if isinstance(data, dict):
                cfg.update(data)
    except Exception:
        pass
    return cfg


def _write_config(cfg: dict):
    """Write config to disk."""
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    except Exception:
        pass


# ── State definitions ────────────────────────────────────────────

STATES = [
    "idle", "listening", "speaking", "thinking", "typing", "searching",
    "calculating", "fixing", "success", "error", "alert", "sleeping",
]

EMOTION_NAMES = {
    "e1": "happy", "e2": "amused", "e3": "empathetic", "e4": "curious",
    "e5": "confused", "e6": "surprised", "e7": "embarrassed", "e8": "confident",
    "e9": "annoyed", "e10": "overwhelmed", "e11": "determined", "e12": "affectionate",
}

EMOTIONS = list(EMOTION_NAMES.keys())

# ── State → video mapping ────────────────────────────────────────
# Maps state/emotion names to video file numbers.
# Each number may have variations (e.g., 1.mp4 and 1-1.mp4).

STATE_VIDEO_MAP = {
    "idle": "1",
    "listening": "2",
    "speaking": "3",
    "thinking": "4",
    "typing": "5",
    "searching": "6",
    "calculating": "7",
    "fixing": "8",
    "success": "9",
    "error": "10",
    "alert": "11",
    "sleeping": "12",
    # Emotions
    "e1": "e1",
    "e2": "e2",
    "e3": "e3",
    "e4": "e4",
    "e5": "e5",
    "e6": "e6",
    "e7": "e7",
    "e8": "e8",
    "e9": "e9",
    "e10": "e10",
    "e11": "e11",
    "e12": "e12",
}

# ── Tool → state mapping ─────────────────────────────────────────

TOOL_STATES = {
    "read_file": "typing", "write_file": "typing", "patch": "typing",
    "search_files": "typing", "web_search": "searching", "web_extract": "searching",
    "session_search": "searching", "browser_navigate": "searching",
    "browser_snapshot": "searching", "browser_vision": "searching",
    "browser_get_images": "searching", "browser_back": "searching",
    "browser_click": "typing", "browser_type": "typing",
    "browser_press": "typing", "browser_scroll": "typing",
    "execute_code": "calculating", "browser_console": "calculating",
    "terminal": "fixing", "process": "fixing",
    "delegate_task": "thinking", "todo": "thinking", "memory": "thinking",
    "cronjob": "thinking", "skill_view": "thinking", "skill_manage": "thinking",
    "clarify": "alert",
    "text_to_speech": "speaking", "send_message": "speaking",
}

EMOTION_KEYWORDS = [
    (["love", "thank you", "cutie", "heart", "\u2661", "\u2764"], "e12"),
    (["sorry", "apolog", "unfortunately", "my bad", "oops"], "e7"),
    (["this is a lot", "so many", "overwhelm", "massive"], "e10"),
    (["wow", "amazing!", "incredible!", "fascinating"], "e6"),
    (["hmm", "confus", "unclear", "not sure"], "e5"),
    (["again", "as i said", "i already", "repeatedly"], "e9"),
    (["what is", "how does", "curious", "interesting", "tell me more"], "e4"),
    (["found it", "perfect", "exactly", "done!", "no problem"], "e8"),
    (["let me", "i'll", "going to", "step by step", "working on"], "e11"),
    (["haha", "lol", "funny", "silly"], "e2"),
    (["i understand", "that's tough", "it's okay", "don't worry"], "e3"),
    (["great", "good", "nice", "awesome", "yes!", "exciting"], "e1"),
]


# ── Video helpers ────────────────────────────────────────────────

def _get_videos_dir() -> Path:
    """Return the videos directory (prefer docs/videos for GitHub Pages compat)."""
    if DOCS_VIDEOS_DIR.exists() and any(DOCS_VIDEOS_DIR.glob("*.mp4")):
        return DOCS_VIDEOS_DIR
    return VIDEOS_DIR


def _find_video(state_key: str) -> Path | None:
    """Find a video file for the given state/emotion key.

    Tries variations in order: base, -1, -2.
    e.g., for key '1': tries 1.mp4, 1-1.mp4, 1-2.mp4
    """
    vid_dir = _get_videos_dir()
    video_num = STATE_VIDEO_MAP.get(state_key)
    if not video_num:
        return None

    # Try base file first, then variations
    candidates = [f"{video_num}.mp4"]
    for i in range(1, 4):
        candidates.append(f"{video_num}-{i}.mp4")

    for name in candidates:
        path = vid_dir / name
        if path.exists():
            return path
    return None


def _pick_random_video(state_key: str) -> Path | None:
    """Pick a random variation for the given state (for variety)."""
    vid_dir = _get_videos_dir()
    video_num = STATE_VIDEO_MAP.get(state_key)
    if not video_num:
        return None

    matches = list(vid_dir.glob(f"{video_num}*.mp4"))
    if not matches:
        return None
    return random.choice(matches)


# ── State helpers ────────────────────────────────────────────────

def _read_state() -> dict:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {"state": "idle", "emotion": None, "updated_at": 0}


def _write_state(state=None, emotion=None):
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
        (["search", "find", "browse", "web"], "searching"),
        (["file", "read", "write", "patch"], "typing"),
        (["code", "exec", "run", "math"], "calculating"),
        (["terminal", "shell", "build", "git"], "fixing"),
        (["delegate", "skill", "todo", "memory"], "thinking"),
        (["speak", "voice"], "speaking"),
    ]:
        if any(k in lo for k in kws):
            return st
    return "typing"


# ── Routes ───────────────────────────────────────────────────────

@router.get("/status")
async def get_status():
    """Current state with video info."""
    data = _read_state()
    state = data.get("state", "idle")
    emotion = data.get("emotion")
    display = emotion or state
    label = EMOTION_NAMES.get(display, display) if emotion else display

    # Find the video for this state
    video_key = emotion or state
    video_path = _find_video(video_key)

    return {
        "state": state,
        "emotion": emotion,
        "emotion_name": EMOTION_NAMES.get(emotion) if emotion else None,
        "display": display,
        "display_label": label,
        "video": f"/api/plugins/waifu-sprites/video/{video_key}" if video_path else None,
    }


@router.get("/video/{state_key}")
async def serve_video(state_key: str):
    """Serve a video file for the given state/emotion."""
    video_path = _find_video(state_key)
    if not video_path:
        raise HTTPException(404, f"No video for state: {state_key}")
    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/videos")
async def list_videos():
    """List all available video files."""
    vid_dir = _get_videos_dir()
    if not vid_dir.exists():
        return {"videos": []}
    videos = sorted([f.name for f in vid_dir.glob("*.mp4")])
    return {"videos": videos, "dir": str(vid_dir)}


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
    """List all available states and their video mapping."""
    return {
        "actions": {s: STATE_VIDEO_MAP.get(s) for s in STATES},
        "emotions": {e: {"name": EMOTION_NAMES[e], "video": STATE_VIDEO_MAP.get(e)} for e in EMOTIONS},
    }


@router.get("/config")
async def get_config():
    """Read current plugin config."""
    return _read_config()


@router.post("/config")
async def update_config(body: dict):
    """Update plugin config. Merges with existing values."""
    cfg = _read_config()
    allowed = set(DEFAULT_CONFIG.keys())
    for k, v in body.items():
        if k in allowed:
            cfg[k] = v
    _write_config(cfg)
    return {"ok": True, "config": cfg}
