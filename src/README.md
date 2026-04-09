# src/ — Agent Integration

Drop-in Python files for connecting your AI agent to the waifu-sprites display server.

## Files

- **`waifu_hook.py`** — The core library. Import this into any Python agent project.
  Provides `set_waifu_state()`, lifecycle hooks (`on_tool_start`, `on_agent_speaking`, etc.),
  emotion detection from response text, and optional TTS output.

- **`waifu.py`** — Reference implementation showing how to monkey-patch a CLI agent
  (specifically hermes-agent) to automatically call the hooks. Adapt for your framework.

## Quick Start

### 1. Copy `waifu_hook.py` into your project

```bash
cp src/waifu_hook.py /path/to/your/agent/
```

### 2. Call hooks at the right moments

```python
import waifu_hook

# When user sends a message
waifu_hook.on_user_input_received()

# When your agent starts/finishes a tool
waifu_hook.on_tool_start(function_name="web_search")
waifu_hook.on_tool_complete()

# When generating/responding
waifu_hook.on_agent_speaking()

# After getting a response, detect emotion and do TTS
emotion = waifu_hook.detect_emotion(response_text)
waifu_hook.set_waifu_state(emotion)
waifu_hook.on_agent_reply(response_text)

# When idle
waifu_hook.on_agent_idle()
```

### 3. Or use `waifu.py` as a template

If your agent has a similar CLI architecture (a class with `chat()` method, tool callbacks, etc.),
copy `waifu.py` and adapt the class/method names.

## Configuration

Edit these variables in `waifu_hook.py` if your setup differs:

```python
# Server address (default: auto-detects WSL2 host IP, port 8000)
WAIFU_URL = "http://127.0.0.1:8000/state"

# TTS server (default: port 8001, set to None to disable)
TTS_URL = "http://127.0.0.1:8001/tts"

# File-based TTS queue fallback (set to None to disable)
QUEUE_FILE = "~/.waifu-voice-queue.txt"
```

## Emotion System

`detect_emotion()` maps response text to 12 emotion sprites (e1-e12):

| Code | Emotion    | Example triggers               |
|------|------------|-------------------------------|
| e1   | Happy      | "great", "awesome", "yes!"    |
| e2   | Amused     | "haha", "lol", "funny"        |
| e3   | Empathetic | "i understand", "don't worry" |
| e4   | Curious    | "what is", "interesting", "?" |
| e5   | Confused   | "hmm", "confus", "unclear"    |
| e6   | Surprised  | "wow", "whoa", "amazing!"     |
| e7   | Embarrassed| "sorry", "my bad", "oops"     |
| e8   | Confident  | "found it", "perfect", "done!"|
| e9   | Annoyed    | "as i said", "again"          |
| e10  | Overwhelmed| "so many", "complex"          |
| e11  | Determined | "let me", "step by step"      |
| e12  | Affectionate| "thank you", "love"           |

Customize the `EMOTION_KEYWORDS` list in `waifu_hook.py` to match your agent's personality.
