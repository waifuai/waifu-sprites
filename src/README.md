# src/ — Agent Integration

**This is the canonical location** for all Python agent integration code. Other projects symlink here.

## Files

- **`waifu_hook.py`** — The core library. Provides visual state hooks (`on_tool_start`, `on_agent_speaking`, etc.), emotion detection from response text (maps to e1-e12 emotion sprites), and TTS output with sentence chunking.
- **`waifu.py`** — Monkey-patches hermes-agent's `HermesCLI` class to automatically call the hooks. Run with `python waifu.py` from the hermes-agent directory.

## Symlink Setup

hermes-agent points here via symlinks. To recreate them after a hermes update or fresh clone:

```bash
cd ~/.hermes/hermes-agent
ln -sf /path/to/waifu-sprites/src/waifu_hook.py waifu_hook.py
ln -sf /path/to/waifu-sprites/src/waifu.py waifu.py
```

Verify:
```bash
ls -la ~/.hermes/hermes-agent/waifu*.py
# Should show: waifu_hook.py -> /path/to/waifu-sprites/src/waifu_hook.py
#              waifu.py -> /path/to/waifu-sprites/src/waifu.py
```

## Quick Start (other agents)

### 1. Symlink or copy `waifu_hook.py`

```bash
# Symlink (recommended — edits here affect all consumers)
ln -s /path/to/waifu-sprites/src/waifu_hook.py /path/to/your/agent/waifu_hook.py

# Or copy
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

If your agent has a similar CLI architecture (a class with `chat()` method, tool callbacks, etc.), copy `waifu.py` and adapt the class/method names.

## Configuration

`waifu_hook.py` auto-detects the environment:

- **WSL2:** Finds Windows host IP via `ip route`, auto-detects Windows username for queue file path
- **Windows native:** Uses `~/.waifu-voice-queue.txt`

Override if needed:
```python
# Server address (auto-detected for WSL2)
WAIFU_URL = "http://127.0.0.1:8000/state"

# TTS voice URL (for non-file-queue setups)
VOICE_URL = "http://127.0.0.1:8001/tts"

# File-based TTS queue (used by default from WSL2)
QUEUE_FILE = "~/.waifu-voice-queue.txt"
```

## TTS Chunking

`on_agent_reply()` cleans the text (strips markdown, code, emojis, kaomoji), splits into sentences, groups into chunks under 300 chars, and sends each chunk to the TTS server. First chunk plays immediately while later chunks are still being sent.

The TTS server (`tts_server.py`) queues chunks and plays them sequentially via Kokoro. Skip forward/back controls are available in the sprite UI.

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
