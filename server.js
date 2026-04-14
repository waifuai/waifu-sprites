const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 8000;
const TTS_PORT = 8001;
const ASSETS_DIR = path.join(__dirname, 'assets');
const VIDEOS_DIR = path.join(__dirname, 'videos');
const DISPLAY_STATS_FILE = path.join(__dirname, 'display_stats.json');

let currentState = 'idle';
let currentEmotion = null; // e1-e12 when set, null when using action state
let currentSet = '';       // which sprite set is active

// --- Display Tracking ---
// Frontend reports what it actually shows, server aggregates
let displayStats = {};
try {
  if (fs.existsSync(DISPLAY_STATS_FILE)) {
    displayStats = JSON.parse(fs.readFileSync(DISPLAY_STATS_FILE, 'utf8'));
    console.log(`Loaded display stats: ${Object.keys(displayStats).length} states`);
  }
} catch { displayStats = {}; }
let lastDisplayLabel = null;
let lastDisplayStart = null;

function saveDisplayStats() {
  try { fs.writeFileSync(DISPLAY_STATS_FILE, JSON.stringify(displayStats, null, 2)); } catch {}
}

function recordDisplayDuration() {
  if (lastDisplayLabel && lastDisplayStart) {
    const ms = Math.round(Date.now() - lastDisplayStart);
    if (!displayStats[lastDisplayLabel]) displayStats[lastDisplayLabel] = { calls: 0, total_ms: 0 };
    displayStats[lastDisplayLabel].calls++;
    displayStats[lastDisplayLabel].total_ms += ms;
    saveDisplayStats();
  }
}

const EMOTION_NAMES = {
  'e1': 'happy', 'e2': 'amused', 'e3': 'empathetic', 'e4': 'curious',
  'e5': 'confused', 'e6': 'surprised', 'e7': 'embarrassed', 'e8': 'confident',
  'e9': 'annoyed', 'e10': 'overwhelmed', 'e11': 'determined', 'e12': 'affectionate',
};

function stateLabel(state, emotion) {
  const display = emotion || state;
  return EMOTION_NAMES[display] || display;
}

// Map display label to numeric/emotion ID key (e.g. "4", "e7")
function labelToFileId(label) {
  // Already an emotion ID (e7, e12, etc) — return as-is
  if (EMOTIONS.includes(label)) return label;
  // Strip common display prefixes like "/// ", "> ", "~ ", "? ", "♥ ", etc.
  const stripped = label.replace(/^[^a-zA-Z]+\s*/, '');
  // Emotion name → emotion ID (embarrassed → e7)
  for (const [eid, ename] of Object.entries(EMOTION_NAMES)) {
    if (ename === stripped) return eid;
  }
  // Action state name → numeric ID (idle → 1, thinking → 4)
  const stateIdx = STATES.indexOf(stripped);
  if (stateIdx !== -1) return String(stateIdx + 1);
  return label;
}

const STATES = [
  'idle', 'listening', 'speaking', 'thinking',
  'typing', 'searching', 'calculating', 'fixing',
  'success', 'error', 'alert', 'sleeping'
];

// Emotion states map to e1-e12 frames
const EMOTIONS = ['e1','e2','e3','e4','e5','e6','e7','e8','e9','e10','e11','e12'];

// AgentState -> frame number (1-indexed, matching Rust app)
function stateToFrame(state) {
  return STATES.indexOf(state) + 1;
}

// AgentState -> e-prefixed frame (for emotion spritesheets)
function stateToEmotionFrame(state) {
  return 'e' + (STATES.indexOf(state) + 1);
}

// Discover waifu sets from the Rust app's assets folder
// Mirrors discover_waifu_sets() from main.rs
function discoverWaifuSets() {
  const sets = [];

  if (!fs.existsSync(ASSETS_DIR)) {
    console.log(`Assets dir not found: ${ASSETS_DIR}`);
    return sets;
  }

  const entries = fs.readdirSync(ASSETS_DIR);
  for (const name of entries) {
    const fullPath = path.join(ASSETS_DIR, name);
    const stat = fs.statSync(fullPath);

    if (stat.isDirectory()) {
      // Directory mode: individual PNG frames (1.png, 2.png, etc.)
      const files = fs.readdirSync(fullPath);
      const frames = files
        .filter(f => f.endsWith('.png'))
        .map(f => parseInt(f.replace('.png', ''), 10))
        .filter(n => !isNaN(n))
        .sort((a, b) => a - b);

      if (frames.length > 0) {
        sets.push({
          name,
          path: fullPath,
          type: 'directory',
          frames,
        });
      }
    } else if (name.endsWith('.png') && stat.size > 1000) {
      // Spritesheet mode: single PNG with UV grid
      sets.push({
        name: name.replace('.png', ''),
        path: fullPath,
        type: 'spritesheet',
        frames: 12,
      });
    } else if (name.endsWith('.mp4') || name.endsWith('.webm')) {
      // Video file at top level
      sets.push({
        name: name.replace(/\.(mp4|webm)$/, ''),
        path: fullPath,
        type: 'video',
      });
    }
  }

  sets.sort((a, b) => a.name.localeCompare(b.name));
  return sets;
}

// Find asset for a given state in a given set
// state can be an action name (e.g. 'idle') or emotion code (e.g. 'e1')
function findAsset(set, state) {
  if (set.type === 'directory') {
    // Direct emotion code (e1, e2, etc.) - check first
    if (EMOTIONS.includes(state)) {
      const emotionPath = path.join(set.path, `${state}.png`);
      if (fs.existsSync(emotionPath)) {
        return { path: emotionPath, type: 'png' };
      }
    }

    const frameNum = stateToFrame(state);
    // Check numbered frame (1.png, 2.png, etc.)
    if (frameNum > 0) {
      const pngPath = path.join(set.path, `${frameNum}.png`);
      if (fs.existsSync(pngPath)) {
        return { path: pngPath, type: 'png' };
      }
    }
    // Check emotion frame via action name (e.g. 'speaking' -> e3)
    const emotionFrame = stateToEmotionFrame(state);
    const emotionPath = path.join(set.path, `${emotionFrame}.png`);
    if (fs.existsSync(emotionPath)) {
      return { path: emotionPath, type: 'png' };
    }
    // Fallback to frame 1
    const fallback = path.join(set.path, '1.png');
    if (fs.existsSync(fallback)) {
      return { path: fallback, type: 'png' };
    }
  } else if (set.type === 'spritesheet') {
    return { path: set.path, type: 'spritesheet' };
  } else if (set.type === 'video') {
    return { path: set.path, type: 'video' };
  }
  return null;
}

// Also check the videos/ folder for MP4 per state
// Supports variants: e12.mp4, e12-1.mp4, e12-2.mp4 — picks one and sticks with it
let cachedVideoState = null;
let cachedVideoPath = null;

function findVideo(stateName) {
  if (!fs.existsSync(VIDEOS_DIR)) return null;

  // Return cached pick if same state (avoids flickering between variants on poll)
  if (cachedVideoState === stateName && cachedVideoPath && fs.existsSync(cachedVideoPath)) {
    return { path: cachedVideoPath, type: 'video' };
  }

  // Scan videos/ dir for all files matching this state (including variants)
  const files = fs.readdirSync(VIDEOS_DIR);
  const candidates = [];

  for (const file of files) {
    const ext = path.extname(file).toLowerCase();
    if (ext !== '.mp4' && ext !== '.webm') continue;

    const base = path.basename(file, ext);
    // Match exact name (e12.mp4) or variant (e12-1.mp4, e12-2.mp4)
    if (base === stateName || base.startsWith(stateName + '-')) {
      candidates.push(path.join(VIDEOS_DIR, file));
    }
  }

  // Also check numbered fallback (e.g. 'idle' -> '3.mp4')
  if (candidates.length === 0) {
    const idx = STATES.indexOf(stateName);
    if (idx >= 0) {
      for (const file of files) {
        const ext = path.extname(file).toLowerCase();
        if (ext !== '.mp4' && ext !== '.webm') continue;
        const base = path.basename(file, ext);
        if (base === String(idx + 1) || base.startsWith(String(idx + 1) + '-')) {
          candidates.push(path.join(VIDEOS_DIR, file));
        }
      }
    }
  }

  if (candidates.length === 0) return null;

  // Pick randomly — cache ensures same pick during polling
  const chosen = candidates[Math.floor(Math.random() * candidates.length)];

  // Cache so polls don't flip-flop between variants
  cachedVideoState = stateName;
  cachedVideoPath = chosen;

  return { path: chosen, type: 'video' };
}

const MIME = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.png': 'image/png',
  '.mp4': 'video/mp4',
  '.webm': 'video/webm',
  '.json': 'application/json',
};

function serveFile(req, res, filePath, mimeOverride) {
  const ext = path.extname(filePath);
  const stat = fs.statSync(filePath);
  const mime = mimeOverride || MIME[ext] || 'application/octet-stream';

  const range = req.headers.range;
  if (range) {
    const parts = range.replace(/bytes=/, '').split('-');
    const start = parseInt(parts[0], 10);
    const end = parts[1] ? parseInt(parts[1], 10) : stat.size - 1;
    res.writeHead(206, {
      'Content-Range': `bytes ${start}-${end}/${stat.size}`,
      'Accept-Ranges': 'bytes',
      'Content-Length': end - start + 1,
      'Content-Type': mime,
    });
    fs.createReadStream(filePath, { start, end }).pipe(res);
  } else {
    res.writeHead(200, {
      'Content-Length': stat.size,
      'Content-Type': mime,
    });
    fs.createReadStream(filePath).pipe(res);
  }
}

let waifuSets = [];

const server = http.createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    return res.end();
  }

  const url = new URL(req.url, `http://localhost:${PORT}`);

  // POST /state
  if (url.pathname === '/state' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { state, set } = JSON.parse(body);
        if (set) currentSet = set;
        if (EMOTIONS.includes(state)) {
          // Emotion state (e1-e12) - takes priority over action state
          if (currentEmotion !== state) {
            currentEmotion = state;
            cachedVideoState = null; // force re-pick on state change
            console.log(`Emotion -> ${EMOTION_NAMES[state] || state}`);
          }
        } else if (STATES.includes(state)) {
          // Action state - clear emotion so action sprite shows
          if (currentState !== state) {
            currentState = state;
            currentEmotion = null;
            cachedVideoState = null; // force re-pick on state change
            console.log(`State -> ${state}`);
          }
        }
        // Track what will actually be displayed
        const label = stateLabel(currentState, currentEmotion);
        recordDisplayDuration();
        lastDisplayLabel = labelToFileId(label);
        lastDisplayStart = Date.now();
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        res.end('OK');
      } catch {
        res.writeHead(400);
        res.end('Bad JSON');
      }
    });
    return;
  }

  // GET /current_state
  if (url.pathname === '/current_state') {
    const setName = url.searchParams.get('set') || waifuSets[0]?.name || '';
    const set = waifuSets.find(s => s.name === setName) || waifuSets[0];
    const asset = set ? findAsset(set, currentState) : null;
    const video = findVideo(currentEmotion || currentState);

    // If emotion is set, find the emotion frame (e1-e12)
    const emotionFrame = currentEmotion;
    const emotionAsset = emotionFrame && set ? findAsset(set, emotionFrame) : null;

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      state: currentState,
      emotion: currentEmotion,
      set: currentSet,
      sets: waifuSets.map(s => ({ name: s.name, type: s.type })),
      currentAsset: asset ? `/asset?set=${encodeURIComponent(set.name)}&state=${currentState}` : null,
      emotionAsset: emotionAsset ? `/asset?set=${encodeURIComponent(set.name)}&state=${emotionFrame}` : null,
      videoAsset: video ? `/videos/${path.basename(video.path)}` : null,
      preferVideo: video != null,
    }));
    return;
  }

  // GET /asset?set=waifu&state=idle
  if (url.pathname === '/asset') {
    const setName = url.searchParams.get('set');
    const state = url.searchParams.get('state') || currentState;
    const set = waifuSets.find(s => s.name === setName);
    if (!set) {
      res.writeHead(404);
      return res.end('Set not found');
    }

    // Check for MP4 in videos/ folder first
    const video = findVideo(state);
    if (video) {
      return serveFile(req, res, video.path);
    }

    const asset = findAsset(set, state);
    if (!asset) {
      res.writeHead(404);
      return res.end('No asset for this state');
    }

    return serveFile(req, res, asset.path);
  }

  // GET /assets/* - direct asset file serving
  if (url.pathname.startsWith('/assets/')) {
    const relativePath = url.pathname.replace('/assets/', '');
    const filePath = path.join(ASSETS_DIR, relativePath);
    if (!fs.existsSync(filePath)) {
      res.writeHead(404);
      return res.end('Not found');
    }
    return serveFile(req, res, filePath);
  }

  // GET /videos/* - video file serving
  if (url.pathname.startsWith('/videos/')) {
    const filename = path.basename(url.pathname);
    const filePath = path.join(VIDEOS_DIR, filename);
    if (!fs.existsSync(filePath)) {
      res.writeHead(404);
      return res.end('Not found');
    }
    return serveFile(req, res, filePath);
  }

  // ── TTS Proxy Helper ──────────────────────────────────────────────────────
  function proxyTTS(targetPath, method, body) {
    return new Promise((resolve, reject) => {
      const options = {
        hostname: '127.0.0.1',
        port: TTS_PORT,
        path: targetPath,
        method: method,
        headers: { 'Content-Type': 'application/json' },
      };
      const req = http.request(options, (tres) => {
        let data = '';
        tres.on('data', c => data += c);
        tres.on('end', () => {
          try { resolve(JSON.parse(data)); }
          catch { resolve({ raw: data, status: tres.statusCode }); }
        });
      });
      req.on('error', () => resolve({ error: 'TTS server unavailable' }));
      if (body) req.write(JSON.stringify(body));
      req.end();
    });
  }

  // GET /tts/status — TTS queue state for the UI
  if (url.pathname === '/tts/status' && req.method === 'GET') {
    proxyTTS('/tts/status', 'GET').then(data => {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(data));
    });
    return;
  }

  // POST /tts/skip — skip forward or backward
  if (url.pathname === '/tts/skip' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      let parsed = {};
      try { parsed = JSON.parse(body); } catch {}
      proxyTTS('/tts/skip', 'POST', parsed).then(data => {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(data));
      });
    });
    return;
  }

  // POST /tts/clear — clear TTS queue
  if (url.pathname === '/tts/clear' && req.method === 'POST') {
    proxyTTS('/clear', 'POST').then(data => {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(data));
    });
    return;
  }

  // GET/POST /tts/speed — get or set TTS playback speed
  if (url.pathname === '/tts/speed') {
    if (req.method === 'GET') {
      proxyTTS('/tts/speed', 'GET').then(data => {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(data));
      });
      return;
    }
    if (req.method === 'POST') {
      let body = '';
      req.on('data', c => body += c);
      req.on('end', () => {
        let parsed = {};
        try { parsed = JSON.parse(body); } catch {}
        proxyTTS('/tts/speed', 'POST', parsed).then(data => {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(data));
        });
      });
      return;
    }
  }

  // GET /sets - list available waifu sets
  if (url.pathname === '/sets') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(waifuSets.map(s => ({
      name: s.name,
      type: s.type,
      path: s.path,
    }))));
    return;
  }

  // GET /display_stats - what the UI actually displayed
  if (url.pathname === '/display_stats') {
    // Flush current duration before returning
    recordDisplayDuration();
    if (lastDisplayLabel) lastDisplayStart = Date.now();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      stats: displayStats,
      set: currentSet,
    }));
    return;
  }

  // POST /display_track - frontend reports actual display state
  if (url.pathname === '/display_track' && req.method === 'POST') {
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { display, set } = JSON.parse(body);
        if (set) currentSet = set;
        if (display) {
          const fileId = labelToFileId(display);
          if (fileId !== lastDisplayLabel) {
            recordDisplayDuration();
            lastDisplayLabel = fileId;
            lastDisplayStart = Date.now();
          }
        }
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        res.end('OK');
      } catch {
        res.writeHead(400);
        res.end('Bad JSON');
      }
    });
    return;
  }

  // GET / - HTML page
  if (url.pathname === '/') {
    const htmlPath = path.join(__dirname, 'index.html');
    res.writeHead(200, { 'Content-Type': 'text/html' });
    return res.end(fs.readFileSync(htmlPath));
  }

  // Serve static files (JS, CSS, etc.)
  const staticExtensions = ['.js', '.css', '.json', '.png', '.jpg', '.gif', '.ico'];
  const ext = path.extname(url.pathname);
  if (staticExtensions.includes(ext)) {
    const filePath = path.join(__dirname, url.pathname);
    if (fs.existsSync(filePath)) {
      return serveFile(req, res, filePath);
    }
  }

  res.writeHead(404);
  res.end('Not found');
});

server.listen(PORT, '0.0.0.0', () => {
  waifuSets = discoverWaifuSets();
  console.log(`Waifu Sprites Web listening on http://localhost:${PORT}`);
  console.log(`Assets dir: ${ASSETS_DIR}`);
  console.log(`Videos dir: ${VIDEOS_DIR}`);
  console.log(`Found ${waifuSets.length} sets:`);
  waifuSets.forEach(s => console.log(`  - ${s.name} (${s.type})`));
});
