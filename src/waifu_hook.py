"""
waifu_hook.py — Agent integration hooks for waifu-sprites
=========================================================
Drop this into any Python AI agent project to get visual state updates
and optional TTS voice output via the waifu-sprites display server.

The display server (server.js) must be running on localhost:8000.
For WSL2/Docker, the host IP is auto-detected.

States sent via POST /state:
  Action states: idle, listening, speaking, thinking, typing,
                 searching, calculating, fixing, success, error, alert, sleeping
  Emotion states: e1 through e12 (see EMOTION_MAP below)

Usage:
    import waifu_hook

    # Visual states
    waifu_hook.set_waifu_state("thinking")
    waifu_hook.on_user_input_received()
    waifu_hook.on_tool_start("web_search")
    waifu_hook.on_tool_complete()
    waifu_hook.on_agent_speaking()

    # Emotion detection from response text
    emotion = waifu_hook.detect_emotion("Great question! Let me look that up...")
    waifu_hook.set_waifu_state(emotion)  # -> "e8" (Confident)

    # TTS (optional)
    waifu_hook.on_agent_reply("Here is the answer you were looking for.")
"""

import subprocess
import os
import re
import time

try:
    import requests
except ImportError:
    requests = None
    print("[waifu_hook] Warning: 'requests' not installed. pip install requests")


# =============================================================================
# Configuration
# =============================================================================

def get_windows_host_ip():
    """Auto-detect Windows host IP from WSL2. Returns 127.0.0.1 otherwise."""
    if "WSL_DISTRO_NAME" in os.environ:
        try:
            result = subprocess.run(["ip", "route"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if line.startswith("default via"):
                    return line.split(" ")[2]
        except Exception:
            pass
    return "127.0.0.1"


# Server URLs — change these if your server runs elsewhere
WAIFU_URL = f"http://{get_windows_host_ip()}:8000/state"
TTS_URL = f"http://{get_windows_host_ip()}:8001/tts"

# TTS queue file (file-based fallback when HTTP TTS isn't available)
# Set to None to disable file queue
QUEUE_FILE = os.path.expanduser("~/.waifu-voice-queue.txt")

# Max chars per TTS chunk
TTS_CHUNK_LIMIT = 300


# =============================================================================
# Core: Set Visual State
# =============================================================================

def set_waifu_state(state: str):
    """Send a state to the waifu-sprites display server.

    Args:
        state: One of the 12 action states or emotion codes (e1-e12).
               See README.md for the full list.
    """
    if requests is None:
        return
    try:
        requests.post(WAIFU_URL, json={"state": state}, timeout=0.1)
    except requests.exceptions.RequestException:
        pass  # Silently fail if server isn't running


# =============================================================================
# Lifecycle Hooks
# =============================================================================
# Call these at the right moment in your agent's execution loop.

def on_user_input_received(*args, **kwargs):
    """Call when the user sends a message."""
    set_waifu_state("thinking")


def on_tool_start(tool_call_id=None, function_name=None, function_args=None):
    """Call when your agent starts executing a tool.

    Automatically picks a visual state based on the tool name:
      - math/calculate -> "calculating"
      - search/browser -> "searching"
      - everything else -> "typing"
    """
    if not function_name:
        return
    if "math" in function_name or "calculate" in function_name:
        set_waifu_state("calculating")
    elif "search" in function_name or "browser" in function_name:
        set_waifu_state("searching")
    else:
        set_waifu_state("typing")


def on_tool_complete(tool_call_id=None, function_name=None,
                     function_args=None, function_result=None):
    """Call when a tool finishes successfully."""
    set_waifu_state("success")
    time.sleep(0.5)  # Brief pause so the success sprite is visible


def on_tool_error(*args, **kwargs):
    """Call when a tool fails."""
    set_waifu_state("error")
    time.sleep(1.5)


def on_agent_speaking(*args, **kwargs):
    """Call when the agent starts generating a response."""
    set_waifu_state("speaking")


def on_agent_idle(*args, **kwargs):
    """Call when the agent is done and waiting for input."""
    set_waifu_state("idle")


# Aliases for convenience
on_tool_success = on_tool_complete
on_tool_failure = on_tool_error


# =============================================================================
# Emotion Detection
# =============================================================================
# Maps response text to emotion sprites (e1-e12).
# Customize EMOTION_KEYWORDS to match your agent's personality.

EMOTION_MAP = {
    "e1":  "Happy",
    "e2":  "Amused",
    "e3":  "Empathetic",
    "e4":  "Curious",
    "e5":  "Confused",
    "e6":  "Surprised",
    "e7":  "Embarrassed",
    "e8":  "Confident",
    "e9":  "Annoyed",
    "e10": "Overwhelmed",
    "e11": "Determined",
    "e12": "Affectionate",
}

# Keyword → emotion mapping. First match wins, so order matters.
# Customize these keywords to fit your agent's personality.
EMOTION_KEYWORDS = [
    # e12 - Affectionate
    (["love", "thank you", "you're sweet", "you're the best",
      "heart", "glad i could help", "happy to help", "you're welcome"],
     "e12"),
    # e7 - Embarrassed / Apologetic
    (["sorry", "apolog", "unfortunately", "my bad", "my mistake",
      "oops", "i was wrong", "couldn't find", "i can't", "i don't have"],
     "e7"),
    # e10 - Overwhelmed
    (["this is a lot", "so many", "overwhelm", "massive", "huge amount",
      "complex", "complicated"],
     "e10"),
    # e6 - Surprised
    (["wow", "whoa", "oh!", "amazing!", "incredible!", "no way",
      "fascinating", "that's wild", "didn't expect"],
     "e6"),
    # e5 - Confused
    (["hmm", "confus", "unclear", "ambiguous", "what do you mean",
      "not sure what", "i'm not sure", "wait"],
     "e5"),
    # e9 - Annoyed
    (["again", "repeatedly", "as i said", "i already", "once more",
      "please don't", "that's not"],
     "e9"),
    # e4 - Curious
    (["?", "what is", "how does", "tell me more", "interesting",
      "i wonder", "curious", "what if", "could you"],
     "e4"),
    # e8 - Confident
    (["found it", "here's", "let me show", "perfect", "exactly",
      "done!", "easy", "no problem", "absolutely", "definitely"],
     "e8"),
    # e11 - Determined
    (["let me", "i'll", "going to", "here's how", "step by step",
      "first,", "here's what we'll do", "working on"],
     "e11"),
    # e2 - Amused
    (["haha", "lol", "lmao", "funny", "joke", "silly", "that's great"],
     "e2"),
    # e3 - Empathetic
    (["i understand", "that's tough", "i'm sorry to hear", "it's okay",
      "don't worry", "take your time", "hang in there"],
     "e3"),
    # e1 - Happy (default for positive)
    (["great", "good", "nice", "awesome", "wonderful", "yes!",
      "sounds good", "let's go", "exciting"],
     "e1"),
]


def detect_emotion(text: str) -> str:
    """Detect emotion from agent response text using keyword matching.

    Returns an emotion state name (e1-e12) for use with set_waifu_state().
    Defaults to "e1" (Happy) if no keywords match.
    """
    if not text:
        return "e1"
    lower = text.lower()
    for keywords, emotion in EMOTION_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return emotion
    return "e1"


# =============================================================================
# TTS (Text-to-Speech) Hook
# =============================================================================
# Sends cleaned response text to a TTS server or file queue.
# Requires a separate TTS server (e.g., Kokoro) listening on port 8001.

def clean_text_for_tts(text: str) -> str:
    """Strip markdown, code, emojis, and kaomoji before sending to TTS."""
    # Remove code blocks and inline code
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)
    # Remove markdown links but keep text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove markdown bold/italic/headers
    text = re.sub(r"\*\*?(.+?)\*\*?", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)
    # Convert list markers to sentence breaks
    text = re.sub(r"^\s*[-*+]\s+", ". ", text, flags=re.MULTILINE)
    # Remove kaomoji/emoticons in parentheses
    text = re.sub(r"\([^\w\s\.,!\?]{2,}\)", "", text)
    # Remove non-ASCII characters
    text = re.sub(r"[^\x20-\x7E\n]", "", text)
    # Clean up punctuation artifacts
    text = re.sub(r"\([^\w\s]*\)", "", text)
    text = re.sub(r"[\^\=\~]{2,}", "", text)
    # Normalize whitespace
    text = re.sub(r"\s+([,.!?;:\)])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Normalize repeated punctuation
    text = re.sub(r"\.+", ".", text)
    text = re.sub(r"^\.+", "", text)
    # Ensure terminal punctuation
    if text and not text.endswith((".", "!", "?")):
        text += "."
    return text


def _write_to_queue_file(text: str):
    """Write text to the file-based TTS queue."""
    if not QUEUE_FILE:
        return
    try:
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def clear_tts_queue():
    """Cancel any pending TTS by emptying the queue."""
    _write_to_queue_file("")


def on_agent_reply(text: str):
    """Call when the agent's full response is ready.

    Cleans the text and sends it to the TTS server (or file queue).
    Runs TTS in the background so it doesn't block the agent.
    """
    if not text:
        return
    cleaned = clean_text_for_tts(text)
    if not cleaned:
        return

    # Try HTTP TTS first
    if requests is not None:
        try:
            requests.post(TTS_URL, json={"text": cleaned}, timeout=0.5)
            return
        except requests.exceptions.RequestException:
            pass  # Fall through to file queue

    # File-based queue fallback
    _write_to_queue_file(cleaned)
