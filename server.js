const http = require('http');
const fs = require('fs');
const path = require('path');

const PORT = 8000;
const TTS_PORT = 8001;
const ASSETS_DIR = path.join(__dirname, 'assets');
const VIDEOS_DIR = path.join(__dirname, 'videos');

let currentState = 'idle';
let currentEmotion = null; // e1-e12 when set, null when using action state

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
function findVideo(stateName) {
  for (const ext of ['.mp4', '.webm']) {
    const p = path.join(VIDEOS_DIR, stateName + ext);
    if (fs.existsSync(p)) return { path: p, type: 'video' };
  }
  const idx = STATES.indexOf(stateName);
  if (idx >= 0) {
    for (const ext of ['.mp4', '.webm']) {
      const p = path.join(VIDEOS_DIR, `${idx + 1}${ext}`);
      if (fs.existsSync(p)) return { path: p, type: 'video' };
    }
  }
  return null;
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
        const { state } = JSON.parse(body);
        if (EMOTIONS.includes(state)) {
          // Emotion state (e1-e12) - takes priority over action state
          currentEmotion = state;
          console.log(`Emotion -> ${state}`);
        } else if (STATES.includes(state)) {
          // Action state - clear emotion so action sprite shows
          currentState = state;
          currentEmotion = null;
          console.log(`State -> ${state}`);
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

  // GET /current_state
  if (url.pathname === '/current_state') {
    const setName = url.searchParams.get('set') || waifuSets[0]?.name || '';
    const set = waifuSets.find(s => s.name === setName) || waifuSets[0];
    const asset = set ? findAsset(set, currentState) : null;
    const video = findVideo(currentState);

    // If emotion is set, find the emotion frame (e1-e12)
    const emotionFrame = currentEmotion;
    const emotionAsset = emotionFrame && set ? findAsset(set, emotionFrame) : null;

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      state: currentState,
      emotion: currentEmotion,
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

  // GET / - HTML page
  if (url.pathname === '/') {
    const htmlPath = path.join(__dirname, 'index.html');
    res.writeHead(200, { 'Content-Type': 'text/html' });
    return res.end(fs.readFileSync(htmlPath));
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
