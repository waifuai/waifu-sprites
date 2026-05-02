# 🐾 waifu-sprites

**Animated sprite overlay for [hermes-agent](https://github.com/nousresearch/hermes-agent).**

A dashboard plugin that displays an animated waifu sprite that reacts to your agent's state in real-time — idle, typing, thinking, calculating, and more.

Drop in pet packages from the [waifu sprite marketplace](https://codex-pet-share.pages.dev), switch between them from the sidebar dropdown.

---

## ✨ Features

- **Real-time state tracking** — sprite animation changes based on agent activity (idle, typing, thinking, speaking, etc.)
- **Multi-pet support** — download pet packages, drop them in `pets/`, switch from the UI
- **Waifu sprite format** — standard 1536×1872 WebP spritesheets (8 cols × 9 rows, 192×208 per cell)
- **Dashboard plugin** — integrates into the hermes dashboard as an overlay + sidebar
- **Zero dependencies** — pure Python backend (FastAPI), vanilla JS frontend
- **Pet marketplace** — browse and download pets from [codex-pet-share.pages.dev](https://codex-pet-share.pages.dev)

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────────┐
│  hermes-agent (WSL2 / Linux)                 │
│                                              │
│  __init__.py                                 │
│  ├─ on_agent_start()  → state.json           │
│  ├─ on_agent_end()    → state.json           │
│  └─ state detection (tool calls, replies)    │
└──────────────┬───────────────────────────────┘
               │ writes state.json
               ▼
┌──────────────────────────────────────────────┐
│  waifu-sprites plugin                        │
│                                              │
│  dashboard/plugin_api.py   (FastAPI backend) │
│  ├─ GET /status            current state     │
│  ├─ GET /atlas             sprite metadata   │
│  ├─ GET /spritesheet       WebP image        │
│  ├─ GET /pets              list all pets     │
│  └─ POST /switch           change active pet │
│                                              │
│  dashboard/dist/index.js   (React frontend)  │
│  ├─ SpriteAnimator          CSS animation    │
│  └─ PetSelector            dropdown switcher │
│                                              │
│  pets/                     pet packages      │
│  ├─ lumina/                                     │
│  ├─ linnea/                                     │
│  └─ ...                                         │
└──────────────────────────────────────────────┘
```

The plugin runs inside the hermes dashboard (port 9119). Agent hooks write `state.json`, the backend reads it and serves sprite data, the frontend animates using CSS `background-position` stepping.

---

## 🎭 State Mapping

12 agent states mapped to 9 sprite animation rows:

| Row | Animation      | Agent States                    |
|-----|---------------|---------------------------------|
| 0   | idle          | idle                            |
| 1   | running-right | typing, searching               |
| 2   | running-left  | listening                       |
| 3   | waving        | speaking                        |
| 4   | jumping       | success, confident, happy       |
| 5   | failed        | error, confused, annoyed        |
| 6   | waiting       | thinking, alert, waiting        |
| 7   | running       | calculating, fixing, determined |
| 8   | review        | affectionate, curious           |

---

## 📦 Pet Packages

Each pet is a directory in `pets/` containing:

```
pets/
├── lumina/
│   ├── pet.json           # metadata (id, displayName, description)
│   └── spritesheet.webp   # 1536×1872 spritesheet (8×9 grid)
├── linnea/
│   ├── pet.json
│   └── spritesheet.webp
└── ...
```

### Installing Pets

1. Download a `.codex-pet.zip` from the [marketplace](https://codex-pet-share.pages.dev)
2. Extract to `pets/<pet-id>/`
3. Rescan plugins: `curl http://127.0.0.1:9119/api/dashboard/plugins/rescan`
4. Select from the sidebar dropdown

Or use the bulk install script:
```bash
cd waifu-sprites
python3 -c "
import zipfile, json, os
for zf in os.listdir('.'):
    if zf.endswith('.codex-pet.zip'):
        with zipfile.ZipFile(zf) as z:
            meta = json.loads(z.read([n for n in z.namelist() if n.endswith('pet.json')][0]))
            z.extractall(f'pets/{meta[\"id\"]}')
"
```

---

## 🚀 Installation

### As a Hermes Plugin

```bash
cd ~/.hermes/plugins
git clone <this-repo> waifu-sprites
```

Or symlink:
```bash
ln -sf /path/to/waifu-sprites ~/.hermes/plugins/waifu-sprites
```

Then rescan:
```bash
curl http://127.0.0.1:9119/api/dashboard/plugins/rescan
```

### Prerequisites

- [hermes-agent](https://github.com/nousresearch/hermes-agent) running
- Python 3.8+ with `fastapi` and `uvicorn` (usually already installed with hermes)

---

## 📁 Project Structure

```
waifu-sprites/
├── __init__.py              # Agent hooks (writes state.json)
├── state.json               # Shared state file
├── config.json              # Plugin configuration
├── plugin.yaml              # Hermes plugin descriptor
├── pets/                    # Pet packages
│   ├── lumina/
│   ├── linnea/
│   └── ...
└── dashboard/
    ├── manifest.json        # Plugin manifest (slots, routes)
    ├── plugin_api.py        # FastAPI backend
    └── dist/
        ├── index.js         # React frontend (sprite + pet selector)
        └── style.css        # Sprite container + UI styles
```

---

## 🛠️ Stack

- **Backend:** Python + FastAPI (served by hermes dashboard)
- **Frontend:** Vanilla JS + CSS animations (no build step)
- **Sprites:** CSS `background-position` stepping on WebP spritesheets
- **Format:** Waifu sprite spec (1536×1872, 8 cols × 9 rows, 192×208 cells)

---

## 📝 API

All endpoints are prefixed by the plugin route (typically `/api/plugins/waifu-sprites/`).

| Endpoint     | Method | Description                          |
|-------------|--------|--------------------------------------|
| `/status`   | GET    | Current state + sprite row/frames    |
| `/atlas`    | GET    | Spritesheet metadata (cols, rows, cell size) |
| `/spritesheet` | GET | Serve the active pet's WebP image   |
| `/pets`     | GET    | List all installed pets              |
| `/switch`   | POST   | Switch active pet `{"pet_id":"..."}` |
| `/state`    | POST   | Set state manually `{"state":"idle"}` |

---

## 🎨 Creating Custom Pets

Create a directory in `pets/` with:

1. **`pet.json`** — metadata:
   ```json
   {
     "id": "my-pet",
     "displayName": "My Pet",
     "description": "A custom waifu sprite pet"
   }
   ```

2. **`spritesheet.webp`** — 1536×1872 image with 8 columns × 9 rows, each cell 192×208 pixels. Rows map to animation states (see table above).

The spritesheet should be in WebP format for optimal size. Each row is a different animation state, each column is a frame in that animation's cycle.
