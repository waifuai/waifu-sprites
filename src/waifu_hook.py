import subprocess
import os
import re
import requests
import time

# --- TTS Chunking Config ---
CHUNK_LIMIT = 300  # Max chars per TTS chunk (kept for future HTTP support)


def get_windows_host_ip():
    """Get the Windows host IP address from WSL2."""
    if "WSL_DISTRO_NAME" in os.environ:
        try:
            # Get default gateway from ip route (the Windows Host VM switch)
            result = subprocess.run(["ip", "route"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if line.startswith("default via"):
                    return line.split(" ")[2]
        except Exception:
            pass
    return "127.0.0.1"


# --- Configuration ---
WAIFU_URL = f"http://{get_windows_host_ip()}:8000/state"
VOICE_URL = f"http://{get_windows_host_ip()}:8001/tts"


def set_waifu_state(state: str):
    """Set the agent's visual state in the Waifu Sprites UI."""
    try:
        payload = {"state": state}
        # Short timeout to avoid blocking the agent if the UI is closed
        requests.post(WAIFU_URL, json=payload, timeout=0.1)
    except requests.exceptions.RequestException:
        pass


# --- Visual State Hooks ---


def on_user_input_received(*args, **kwargs):
    """Triggered when the user enters a prompt."""
    set_waifu_state("thinking")


def on_tool_start(tool_call_id=None, function_name=None, function_args=None):
    """Triggered when a tool starts execution."""
    if not function_name:
        return

    if "math" in function_name or "calculate" in function_name:
        set_waifu_state("calculating")
    elif "search" in function_name or "browser" in function_name:
        set_waifu_state("searching")
    else:
        set_waifu_state("typing")


def on_tool_complete(
    tool_call_id=None, function_name=None, function_args=None, function_result=None
):
    """Triggered when a tool completes successfully."""
    set_waifu_state("success")
    # Brief pause so the success sprite is visible
    time.sleep(0.5)


def on_tool_error(*args, **kwargs):
    """Manual trigger for tool errors."""
    set_waifu_state("error")
    time.sleep(1.5)


# --- Aliases for backward compatibility with older manual patches ---


def on_tool_success(*args, **kwargs):
    """Alias for on_tool_complete."""
    return on_tool_complete(*args, **kwargs)


def on_tool_failure(*args, **kwargs):
    """Alias for on_tool_error."""
    return on_tool_error(*args, **kwargs)


# --- Emotion Detection from Text ---


# Keyword → emotion mapping. Order matters (first match wins).
# Emotions: e1-e12 matching 12-emotion-prompts.txt
#   e1=Happy  e2=Amused  e3=Empathetic  e4=Curious
#   e5=Confused  e6=Surprised  e7=Embarrassed  e8=Confident
#   e9=Annoyed  e10=Overwhelmed  e11=Determined  e12=Affectionate
EMOTION_KEYWORDS = [
    # e12 - Affectionate (check first, compliments are specific)
    (["love", "thank you", "you're sweet", "you're the best", "cutie",
      "heart", "glad i could help", "happy to help", "you're welcome",
      "♡", "❤"], "e12"),
    # e7 - Embarrassed / Apologetic
    (["sorry", "apolog", "unfortunately", "my bad", "my mistake",
      "oops", "i was wrong", "i made an error", "couldn't find",
      "i can't", "i'm afraid", "i don't have"], "e7"),
    # e10 - Overwhelmed
    (["this is a lot", "so many", "overwhelm", "massive", "huge amount",
      "complex", "complicated"], "e10"),
    # e6 - Surprised
    (["wow", "whoa", "oh!", "amazing!", "incredible!", "no way",
      "fascinating", "that's wild", "didn't expect"], "e6"),
    # e5 - Confused
    (["hmm", "confus", "unclear", "ambiguous", "what do you mean",
      "not sure what", "i'm not sure", "wait", "actually..."], "e5"),
    # e9 - Annoyed
    (["again", "repeatedly", "as i said", "i already", "once more",
      "please don't", "that's not"], "e9"),
    # e4 - Curious
    (["?", "what is", "how does", "tell me more", "interesting",
      "i wonder", "curious", "what if", "could you"], "e4"),
    # e8 - Confident
    (["found it", "here's", "let me show", "perfect", "exactly",
      "nailed", "done!", "easy", "no problem", "absolutely",
      "definitely", "certainly"], "e8"),
    # e11 - Determined
    (["let me", "i'll", "going to", "here's how", "step by step",
      "first,", "here's what we'll do", "working on"], "e11"),
    # e2 - Amused
    (["haha", "lol", "lmao", "funny", "joke", "silly",
      "that's great", "nyaa", "nya~"], "e2"),
    # e3 - Empathetic (sad/comforting)
    (["i understand", "that's tough", "i'm sorry to hear", "it's okay",
      "don't worry", "take your time", "hang in there"], "e3"),
    # e1 - Happy (default for positive responses)
    (["great", "good", "nice", "awesome", "wonderful", "yes!",
      "sounds good", "let's go", "exciting"], "e1"),
]


def detect_emotion(text: str) -> str:
    """Detect the best emotion from response text using keyword matching.
    Returns an emotion state name (e1-e12)."""
    if not text:
        return "e1"
    lower = text.lower()
    for keywords, emotion in EMOTION_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return emotion
    return "e1"


def on_agent_speaking(*args, **kwargs):
    """Triggered when the agent starts responding."""
    set_waifu_state("speaking")


def on_agent_idle(*args, **kwargs):
    """Triggered when the agent is waiting for input."""
    set_waifu_state("idle")


# --- Voice/TTS Hook ---


def clean_text_for_tts(text: str) -> str:
    """Remove emojis, kaomoji, markdown, and formatting from text before TTS."""
    # 1. Remove code blocks and inline code
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)

    # 2. Remove markdown links but keep text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # 3. Remove markdown bold/italic/headers
    text = re.sub(r"\*\*?(.+?)\*\*?", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # 4. Remove URLs
    text = re.sub(r"https?://\S+", "", text)

    # 5. Handle list markers (convert to sentence breaks)
    text = re.sub(r"^\s*[-*+]\s+", ". ", text, flags=re.MULTILINE)

    # 6. Target common kaomoji/emoticons primarily inside parentheses
    text = re.sub(r"\([^\w\s\.,!\?]{2,}\)", "", text)

    # 7. Specifically remove common "cat" or "waifu" style symbols and non-ASCII
    non_ascii_symbols = [r"ฅ", r"•", r"ﻌ", r"´", r"ω", r"`", r"・", r"^", r"~"]
    for symbol in non_ascii_symbols:
        text = text.replace(symbol, "")

    # 8. Remove remaining non-ASCII characters
    text = re.sub(r"[^\x20-\x7E\n]", "", text)

    # 9. Clean up leftover punctuation artifacts from stripped emojis
    text = re.sub(r"\([^\w\s]*\)", "", text)
    text = re.sub(r"[\^\=\~]{2,}", "", text)

    # 10. Normalize spaces before punctuation and after parens
    text = re.sub(r"\s+([,\.!?;:\)])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)

    # 11. Convert newlines to sentence breaks and collapse whitespace
    text = re.sub(r"\n+", ". ", text)
    text = re.sub(r"\s+", " ", text).strip()

    # 12. Final punctuation cleanup
    text = re.sub(r"\.+", ".", text)
    text = re.sub(r"^\.+", "", text)

    # Ensure terminal punctuation if missing
    if text and not text.endswith((".", "!", "?")):
        text += "."

    return text


def split_into_sentences(text: str) -> list:
    """Split text into sentences by punctuation terminators.
    Mirrors waifu-companion's splitIntoSentences() logic."""
    matches = re.findall(r'[^.!?…]+[.!?…]?\s*|[^.!?…]+$', text)
    return [s.strip() for s in matches if s.strip()]


def chunk_text(text: str, limit: int = CHUNK_LIMIT) -> list:
    """Group sentences into chunks under the character limit.
    Mirrors waifu-companion's tts_queue_manager chunking logic."""
    sentences = split_into_sentences(text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) > limit and current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            current_chunk += (" " if current_chunk else "") + sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def _get_queue_file():
    """Get path to the TTS queue file, accessible from both WSL2 and Windows."""
    if "WSL_DISTRO_NAME" in os.environ:
        # Running in WSL2 — need Windows path via /mnt/c/Users/<name>/
        try:
            result = subprocess.run(
                ["cmd.exe", "/c", "echo", "%USERNAME%"],
                capture_output=True, text=True
            )
            win_user = result.stdout.strip()
            if win_user:
                return f"/mnt/c/Users/{win_user}/.waifu-voice-queue.txt"
        except Exception:
            pass
    # Running on Windows or fallback
    return os.path.join(os.path.expanduser("~"), ".waifu-voice-queue.txt")

QUEUE_FILE = _get_queue_file()

# HTTP TTS doesn't work from WSL2 → Windows (networking issues).
# Use file queue exclusively — the server polls QUEUE_FILE for changes.
_HTTP_TTS_AVAILABLE = False


def _write_to_queue_file(text: str):
    """Write text to the queue file the server monitors."""
    try:
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


def clear_tts_queue():
    """Clear pending TTS by emptying the queue file."""
    _write_to_queue_file("")


def on_agent_reply(text: str):
    """Triggered when a full response is ready to be spoken.
    Writes cleaned text to the queue file for the server to pick up."""
    try:
        if not text:
            return
        cleaned = clean_text_for_tts(text)
        if not cleaned:
            return
        # File queue: write all text at once (server polls for file changes).
        # Chunking is kept for future HTTP support but not used with file queue
        # since each write overwrites the file.
        _write_to_queue_file(cleaned)
    except Exception:
        pass
