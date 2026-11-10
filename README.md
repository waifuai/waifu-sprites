# 🎬 waifu-sprites

**Video-based AI companion for [hermes-agent](https://github.com/nousresearch/hermes-agent).**

A dashboard plugin that displays a video-based waifu companion that reacts to your agent's state in real-time — idle, typing, thinking, calculating, and more.

---

## ✨ Features

- **Real-time state tracking** — companion video changes based on agent activity (idle, typing, thinking, speaking, etc.)
- **Emotion detection** — agent replies are scanned for emotional cues and matched to expressive clips; a RANSOC picker keeps repeats varied so the same face never plays twice in a row
- **Floating overlay** — draggable sprite that stays visible over any dashboard page, or dock it inside the plugin tab
- **Manual controls** — trigger any of the 12 states or 12 emotions from the dashboard tab
- **Settings** — overlay toggle and size, state refresh interval, and clip source, editable right in the tab
- **Zero dependencies** — pure Python backend (FastAPI, already part of Hermes) and a single hand-written frontend file; no build step

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
│  ├─ GET /video/{key}       serve local clips │
│  ├─ POST /state            manual override   │
│  └─ GET/POST /config       settings          │
│                                              │
│  dashboard/waifu.js        (frontend, IIFE)  │
│  ├─ Video player           crossfade swaps   │
│  ├─ Floating overlay       draggable         │
│  └─ Controls + settings                      │
└──────────────────────────────────────────────┘
```

Agent hooks update `state.json`, the backend exposes it under
`/api/plugins/waifu-sprites/*` (behind dashboard auth), and the frontend polls
`/status` and plays the matching clip.

**Clips:** by default the frontend streams clips from a pinned commit of the
sprite set hosted on jsDelivr, so the plugin itself stays small. Drop `.mp4`
files into `videos/` (or `docs/videos/`) and set **Clips → Local** (or Auto) to
serve them from the plugin instead — useful offline. Clip files are numbered:
`1.mp4`–`12.mp4` for states, `e1.mp4`–`e12.mp4` for emotions, with `-1`/`-2`
alternates.

---

## 🎭 State Mapping

Agent states and emotions map to video files:

| State/Emotion | Video File | Description |
|---------------|------------|-------------|
| idle          | 1.mp4      | Default waiting state |
| listening     | 2.mp4      | When agent is waiting for input |
| speaking      | 3.mp4      | While agent is generating text |
| thinking      | 4.mp4      | During LLM processing |
| typing        | 5.mp4      | During file or code edits |
| searching     | 6.mp4      | During web or file searches |
| ...           | ...        | See `plugin_api.py` for the full map |

Emotions are detected from reply text (celebratory → happy, apologies → sorry,
"let me…" → planning, and so on) — the keyword tables live in `__init__.py`
and `plugin_api.py`.

---

## 🔧 Configuration

Settings are editable in the dashboard tab and stored in `config.json`:

| Key               | Default | Meaning                                      |
|-------------------|---------|----------------------------------------------|
| `overlay_enabled` | `true`  | Show the floating draggable sprite           |
| `overlay_size`    | `320`   | Overlay width in pixels (120–480)            |
| `poll_interval_ms`| `2000`  | How often the frontend polls agent state     |
| `video_source`    | `auto`  | `auto` (local clips if present, else CDN), `cdn`, or `local` |

---

## 🔒 Privacy & Network

- The **only** third-party network traffic is fetching video clips from
  `cdn.jsdelivr.net` (a pinned, immutable commit) when `video_source` is
  `auto`/`cdn`. Point the plugin at local clips to run fully offline.
- **No telemetry, no analytics, no phone-home.**
- The backend API is served only through the authenticated dashboard.
- `state.json` (sprite state only — no conversation content) lives beside the
  plugin; `config.json` stores your display preferences.

---

## 🚀 Installation

```bash
cd ~/.hermes/plugins
git clone <this-repo> waifu-sprites
```

Then restart the dashboard (plugin routes mount at startup) and enable the
plugin if prompted. Requires hermes-agent 0.13 or newer (`requires_hermes:
">=0.13"`).

---

## 📁 Project Structure

```
waifu-sprites/
├── __init__.py              # Agent hooks (updates state.json)
├── state.json               # Shared state file (created at runtime)
├── config.json              # Plugin configuration
├── plugin.yaml              # Hermes plugin descriptor
├── videos/                  # Optional local video clips (MP4)
└── dashboard/
    ├── manifest.json        # Dashboard plugin manifest
    ├── plugin_api.py        # FastAPI backend
    ├── waifu.js             # Frontend (vanilla IIFE, no build step)
    └── waifu.css            # Frontend styles
```

---

## 🛠️ Stack

- **Backend:** Python + FastAPI (mounted by the Hermes dashboard)
- **Frontend:** hand-written IIFE on the Hermes dashboard plugin SDK (React provided by the host)
- **Video:** HTML5 video with two stacked elements for gapless crossfade swaps
