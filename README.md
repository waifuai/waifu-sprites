# 🎬 waifu-sprites

**Video-based AI companion for [hermes-agent](https://github.com/nousresearch/hermes-agent).**

A dashboard plugin that displays a video-based waifu companion that reacts to your agent's state in real-time — idle, typing, thinking, calculating, and more.

---

## ✨ Features

- **Real-time state tracking** — companion video changes based on agent activity (idle, typing, thinking, speaking, etc.)
- **Emotion detection** — detects emotions from agent responses and switches to matching video clips
- **Dashboard integration** — floating draggable overlay, sidebar widget, and full settings dashboard
- **Zero dependencies** — pure Python backend (FastAPI), React-based frontend (via Hermes SDK)

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────┐
│  hermes-agent                                │
│                                              │
│  __init__.py                                 │
│  └─ Hooks (pre_tool, post_llm, etc.)         │
└──────────────┬───────────────────────────────┘
               │ writes state.json
               ▼
┌──────────────────────────────────────────────┐
│  waifu-sprites plugin                        │
│                                              │
│  dashboard/plugin_api.py   (FastAPI backend) │
│  ├─ GET /status            current state     │
│  ├─ GET /video/{key}       serve mp4 clips   │
│  └─ POST /config           update settings   │
│                                              │
│  dashboard/dist/index.js   (React frontend)  │
│  ├─ VideoPlayer            MP4 playback      │
│  └─ WaifuOverlay           Draggable UI      │
│                                              │
│  videos/                   video clips       │
│  ├─ 1.mp4 (idle)                             │
│  ├─ e1.mp4 (happy)                           │
│  └─ ...                                      │
└──────────────────────────────────────────────┘
```

The plugin runs inside the hermes dashboard. Agent hooks update `state.json`, the backend reads it and serves the corresponding video clips, and the frontend handles seamless playback and UI.

---

## 🎭 State Mapping

Agent states and emotions map to video files in the `videos/` (or `docs/videos/`) directory:

| State/Emotion | Video File | Description |
|---------------|------------|-------------|
| idle          | 1.mp4      | Default waiting state |
| listening     | 2.mp4      | When agent is waiting for input |
| speaking      | 3.mp4      | While agent is generating text |
| thinking      | 4.mp4      | During LLM processing |
| typing        | 5.mp4      | During file or code edits |
| searching     | 6.mp4      | During web or file searches |
| ...           | ...        | See `plugin_api.py` for full map |

---

## 🚀 Installation

### As a Hermes Plugin

```bash
cd ~/.hermes/plugins
git clone <this-repo> waifu-sprites
```

Then rescan plugins from the Hermes dashboard or via CLI:
```bash
curl http://127.0.0.1:9119/api/dashboard/plugins/rescan
```

### Prerequisites

- [hermes-agent](https://github.com/nousresearch/hermes-agent) installed
- Python 3.8+ (FastAPI and Uvicorn are used by the dashboard)

---

## 📁 Project Structure

```
waifu-sprites/
├── __init__.py              # Agent hooks (updates state.json)
├── state.json               # Shared state file
├── config.json              # Plugin configuration
├── plugin.yaml              # Hermes plugin descriptor
├── videos/                  # Video clips (MP4)
└── dashboard/
    ├── manifest.json        # Plugin manifest
    ├── plugin_api.py        # FastAPI backend
    └── dist/
        ├── index.js         # React frontend
        └── style.css        # Dashboard and overlay styles
```

---

## 🛠️ Stack

- **Backend:** Python + FastAPI
- **Frontend:** React (via Hermes Plugin SDK)
- **Video:** HTML5 Video with MP4 source
