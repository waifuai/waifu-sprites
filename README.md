# 🐾 waifu-sprites

**A lightweight web-based display server + TTS for local AI Agents.**

`waifu-sprites` is a browser-based companion UI that acts as the "Face" for headless, agentic LLM orchestrators (like `hermes-agent`).

**Single source of truth** — sprite server, TTS server, agent hooks, and integration code all live here. Hermes-agent symlinks to `src/` so edits take effect immediately.

---

## ⚡ Why this exists
Modern AI agents are incredibly smart (they can write files, execute Python, and search the web autonomously), but their user interfaces are often underwhelming:
- **Boring** command-line terminal windows.
- **Bloated** 500MB+ Web UI wrappers that drain your laptop's battery.
- **Complex** 3D VTuber setups that are fragile and resource-heavy.

`waifu-sprites` fixes this by decoupling the **Brain** (your Python/WSL2 Agent) from the **Face** (this web server).

* **CPU/RAM Usage:** Minimal (browser does the work).
* **Launch Time:** Instant.
* **Moddability:** Edit HTML/CSS/JS, refresh browser, done.
* **MP4 Support:** Native — just drop `.mp4` files in `videos/`.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────┐
│  waifu-sprites (Windows native)                 │
│                                                 │
│  server.js (:8000)        tts_server.py (:8001) │
│  Sprite display server    Kokoro TTS server     │
│  ├─ POST /state           ├─ POST /tts          │
│  ├─ GET /current_state    ├─ POST /clear         │
│  ├─ GET /tts/status ──────┤ GET /tts/status      │
│  ├─ POST /tts/skip ───────┤ POST /tts/skip       │
│  └─ POST /tts/clear ──────┘                      │
│                                                 │
│  index.html (browser)                           │
│  ├─ Sprite display + manual browse              │
│  └─ TTS controls (⏮ ⏹ ⏭ chunk display)         │
└─────────────────────────────────────────────────┘
         ▲                    ▲
         │ HTTP :8000         │ file queue
         │                    │
┌────────┴────────────────────┴────────┐
│  WSL2 / hermes-agent                 │
│                                      │
│  waifu_hook.py (symlink → src/)      │
│  ├─ set_waifu_state() → :8000        │
│  ├─ on_agent_reply() → queue file    │
│  └─ emotion detection, TTS chunking  │
│                                      │
│  waifu.py (symlink → src/)           │
│  └─ Monkey-patches HermesCLI         │
└──────────────────────────────────────┘
```

- **server.js** (Node.js, port 8000) — serves the sprite UI and proxies TTS control requests
- **tts_server.py** (Python/Flask, port 8001) — Kokoro TTS with chunk queuing and skip support
- **src/waifu_hook.py** — agent-side hooks (visual states, emotion detection, TTS chunking)
- **src/waifu.py** — monkey-patches hermes-agent CLI to inject hooks automatically

WSL2 can't reach Windows localhost, so agent → TTS uses a **file queue** (`~/.waifu-voice-queue.txt`). The TTS server polls it. Skip controls work over HTTP because browser + server.js both run on Windows.

---

## 🎨 Character System
`waifu-sprites` supports multiple characters via the `assets/` folder. Auto-discovers all sets on startup.

### Directory Mode
Individual PNG frames per state:

```
assets/
├── waifu/
│   ├── 1.png   # idle
│   ├── 2.png   # listening
│   ├── 3.png   # speaking
│   ├── ...
│   ├── e1.png  # emotion: idle
│   └── ...
```

### Spritesheet Mode
Single PNG with a 4x3 grid of frames. Automatically cropped via CSS `background-position` to show the correct frame per state.

```
assets/
├── ori.png              # spritesheet (4x3 grid)
└── hologram-simple.png  # spritesheet (4x3 grid)
```

### MP4 Mode
Drop MP4 files in `videos/` for animated sprites — takes priority over PNGs when present:

```
videos/
├── idle.mp4
├── speaking.mp4
├── thinking.mp4
└── ...
```

Or use numbered files: `1.mp4`, `2.mp4`, etc. (1=idle, 2=listening, ...)

Browsers decode H.264 MP4 natively with hardware acceleration. Much smaller than GIFs.

### Waifu Selector
Dropdown in the UI to switch between sets. Selection is saved to `localStorage` and persists across reloads.

---

## 🎮 Manual Browse Mode
Click the ⏸ button to pause auto-follow and browse states manually with the buttons. Click ▶ to resume following the server. State label shows `[manual]` when in browse mode.

---

## 🔊 TTS Controls
When TTS is active, a control bar appears below the emotion buttons:

- **⏮** Skip back — replay previous chunk
- **⏹** Stop — clear queue and stop audio
- **⏭** Skip forward — skip to next chunk
- **2/5** — shows current chunk / total chunks in the batch

The TTS bar auto-hides when idle. Polls status every 500ms.

---

## 🎭 States
12 agent states, mapped to frame numbers:

| # | State | # | State |
|---|-------|---|-------|
| 1 | idle | 7 | calculating |
| 2 | listening | 8 | fixing |
| 3 | speaking | 9 | success |
| 4 | thinking | 10 | error |
| 5 | typing | 11 | alert |
| 6 | searching | 12 | sleeping |

---

## 🚀 Getting Started

### Prerequisites
- [Node.js](https://nodejs.org/) (any recent version)
- [Python 3](https://www.python.org/) (for TTS server)
- `pip install flask sounddevice numpy onnxruntime kokoro-onnx` (for TTS)

### Run

**Start both servers:**
```bash
cd waifu-sprites
node server.js          # Sprite display on :8000
python tts_server.py    # TTS on :8001
```

Or double-click `voice.bat` for TTS, and run `node server.js` separately.

**Open** http://localhost:8000

### Hermes Agent Setup (WSL2)

Symlink from hermes-agent to waifu-sprites so edits take effect immediately:
```bash
cd ~/.hermes/hermes-agent
ln -sf /path/to/waifu-sprites/src/waifu_hook.py waifu_hook.py
ln -sf /path/to/waifu-sprites/src/waifu.py waifu.py
```

Then launch with:
```bash
cd ~/.hermes/hermes-agent && python3 waifu.py
```

### Connect Your Backend (Python/Node/Bash)

The simplest way — just POST a JSON state to the server:

**From any terminal:**
```bash
curl -X POST http://127.0.0.1:8000/state \
     -H "Content-Type: application/json" \
     -d '{"state": "thinking"}'
```

**From Python:**
```python
import requests

def update_waifu(state):
    requests.post("http://127.0.0.1:8000/state", json={"state": state})

update_waifu("typing")
```

### API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/state` | POST | Set current state `{"state": "speaking"}` |
| `/current_state` | GET | Get current state + available sets |
| `/asset?set=waifu&state=idle` | GET | Serve asset for state |
| `/sets` | GET | List discovered waifu sets |
| `/assets/*` | GET | Direct asset file access |
| `/videos/*` | GET | Direct video file access |
| `/tts/status` | GET | TTS queue state (chunk info, playing status) |
| `/tts/skip` | POST | Skip TTS `{"direction": "forward"}` or `{"direction": "back"}` |
| `/tts/clear` | POST | Clear TTS queue and stop audio |

---

## 📁 File Structure

```
waifu-sprites/
├── server.js           # Sprite display server (:8000)
├── tts_server.py       # Kokoro TTS server (:8001)
├── index.html          # Browser UI (sprites + TTS controls)
├── send-tts.ps1        # PowerShell TTS helper
├── src/
│   ├── waifu_hook.py   # Agent hooks (visual states, emotion, TTS)
│   └── waifu.py        # Hermes CLI monkey-patch wrapper
├── assets/             # Sprite PNGs and spritesheets
└── videos/             # MP4 animated sprites (gitignored)
```

## 🛠️ Stack
- **Sprite Server:** Node.js built-in `http` module (zero npm dependencies)
- **TTS Server:** Python + Flask + Kokoro ONNX
- **Frontend:** Vanilla HTML/CSS/JS
- **Video:** Browser-native `<video>` element (H.264/VP8)
- **Images:** Browser-native `<img>` element (PNG/JPG/SVG)
- **Spritesheets:** CSS `background-position` cropping (4x3 grid)
