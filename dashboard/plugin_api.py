"""
waifu-sprites dashboard plugin — sprite backend.

Reads state from shared state file. Manages multiple installed pets.
Each pet is a folder in pets/ with pet.json + spritesheet.webp.
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
PETS_DIR = PLUGIN_DIR / "pets"
STATE_FILE = PLUGIN_DIR / "state.json"

# ── Sprite atlas (fixed for all pets) ────────────────────────────

ATLAS = {
    "width": 1536,
    "height": 1872,
    "cell_width": 192,
    "cell_height": 208,
    "cols": 8,
    "rows": 9,
}

ROWS = [
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

# ── State → row mapping ─────────────────────────────────────────

STATE_TO_ROW = {
    "idle": 0, "typing": 1, "listening": 2, "speaking": 3,
    "searching": 1, "calculating": 7, "fixing": 7,
    "success": 4, "error": 5, "alert": 6, "thinking": 6, "sleeping": 0,
    "happy": 4, "amused": 4, "empathetic": 6, "curious": 8,
    "confused": 5, "surprised": 4, "embarrassed": 3, "confident": 4,
    "annoyed": 5, "overwhelmed": 6, "determined": 7, "affectionate": 8,
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
    "idle", "listening", "speaking", "thinking", "typing", "searching",
    "calculating", "fixing", "success", "error", "alert", "sleeping",
]
EMOTIONS = list(EMOTION_NAMES.keys())

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


# ── Pet management ───────────────────────────────────────────────

def _scan_pets() -> list:
    """Scan pets/ directory and return list of pet metadata."""
    pets = []
    if not PETS_DIR.exists():
        return pets
    for entry in sorted(PETS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        manifest = entry / "pet.json"
        sheet = entry / "spritesheet.webp"
        if not manifest.exists() or not sheet.exists():
            continue
        try:
            data = json.loads(manifest.read_text())
            data["_dir"] = entry.name
            data["_spritesheet"] = str(sheet)
            data["_size"] = sheet.stat().st_size
            pets.append(data)
        except Exception:
            continue
    return pets


def _get_active_pet_id() -> str:
    """Get the currently active pet ID from state."""
    data = _read_state()
    return data.get("active_pet", "")


def _get_active_pet() -> dict | None:
    """Get the active pet's metadata."""
    pet_id = _get_active_pet_id()
    if pet_id:
        for pet in _scan_pets():
            if pet.get("id") == pet_id or pet.get("_dir") == pet_id:
                return pet
    # Default to first available pet
    pets = _scan_pets()
    if pets:
        _set_active_pet(pets[0].get("id", pets[0].get("_dir", "")))
        return pets[0]
    return None


def _set_active_pet(pet_id: str):
    """Set the active pet."""
    data = _read_state()
    data["active_pet"] = pet_id
    try:
        STATE_FILE.write_text(json.dumps(data))
    except Exception:
        pass


# ── State helpers ────────────────────────────────────────────────

def _read_state() -> dict:
    try:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text())
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {"state": "idle", "emotion": None, "updated_at": 0, "active_pet": ""}


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


def _get_row_info(state: str, emotion: str = None) -> dict:
    display = emotion or state
    row_idx = STATE_TO_ROW.get(display, 0)
    return ROWS[row_idx]


# ── Routes ───────────────────────────────────────────────────────

@router.get("/pets")
async def list_pets():
    """List all installed pets."""
    pets = _scan_pets()
    active_id = _get_active_pet_id()
    result = []
    for pet in pets:
        pid = pet.get("id", pet.get("_dir", ""))
        result.append({
            "id": pid,
            "displayName": pet.get("displayName", pid),
            "description": pet.get("description", ""),
            "active": pid == active_id,
        })
    return {"pets": result, "active": active_id}


@router.post("/pets/active")
async def set_active(body: dict):
    """Switch the active pet."""
    pet_id = body.get("id", "")
    if not pet_id:
        raise HTTPException(400, "Missing pet id")
    # Verify pet exists
    for pet in _scan_pets():
        if pet.get("id") == pet_id or pet.get("_dir") == pet_id:
            _set_active_pet(pet_id)
            return {"ok": True, "active": pet_id}
    raise HTTPException(404, f"Pet not found: {pet_id}")


@router.get("/status")
async def get_status():
    """Current state with active pet info."""
    data = _read_state()
    state = data.get("state", "idle")
    emotion = data.get("emotion")
    display = emotion or state
    row_info = _get_row_info(state, emotion)
    pet = _get_active_pet()

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
        "pet": {
            "id": pet.get("id", "") if pet else "",
            "displayName": pet.get("displayName", "No pet") if pet else "No pet",
            "description": pet.get("description", "") if pet else "",
        } if pet else None,
    }


@router.get("/atlas")
async def get_atlas():
    """Atlas definition + active pet spritesheet URL."""
    pet = _get_active_pet()
    return {
        "atlas": ATLAS,
        "states": ROWS,
        "spritesheet": f"/api/plugins/waifu-sprites/spritesheet?v={pet.get('id', '')}" if pet else None,
        "pet": {
            "id": pet.get("id", ""),
            "displayName": pet.get("displayName", ""),
            "description": pet.get("description", ""),
        } if pet else None,
    }


@router.get("/spritesheet")
async def serve_spritesheet():
    """Serve the active pet's spritesheet."""
    pet = _get_active_pet()
    if not pet:
        raise HTTPException(404, "No pet installed")
    sheet_path = Path(pet["_spritesheet"])
    if not sheet_path.exists():
        raise HTTPException(404, "Spritesheet not found")
    return FileResponse(
        str(sheet_path),
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
        "atlas": ROWS,
    }
