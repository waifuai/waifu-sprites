# 🐾 waifu-sprites

**A lightweight web-based display server for local AI Agents.**

`waifu-sprites` is a browser-based companion UI that acts as the "Face" for headless, agentic LLM orchestrators (like `hermes-agent`).

Uses a simple Node.js server + HTML/CSS/JS frontend. The browser handles all rendering, image display, and MP4 video decoding natively.

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
`waifu-sprites` acts as a "dumb" visual terminal. It contains zero AI logic.

1. It runs a local HTTP server using **Node.js** on `localhost:8000`.
2. Your AI backend (running in WSL2, Docker, or Python) sends a tiny JSON payload: `{"state": "typing"}`.
3. The browser frontend polls for state changes and displays the matching asset (PNG or MP4).

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

### Run

```bash
cd waifu-sprites
node server.js
# Open http://localhost:8000
```

Or double-click `waifu-sprites.bat` on Windows.

### Connect Your Backend (Python/Node/Bash)
Same API as before — drop-in compatible.

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

---

## 🛠️ Stack
- **Runtime:** [Node.js](https://nodejs.org/) (zero npm dependencies)
- **Server:** Built-in `http` module
- **Frontend:** Vanilla HTML/CSS/JS
- **Video:** Browser-native `<video>` element (H.264/VP8)
- **Images:** Browser-native `<img>` element (PNG/JPG/SVG)
- **Spritesheets:** CSS `background-position` cropping (4x3 grid)
