/**
 * waifu.js: dashboard frontend for the waifu-sprites plugin.
 *
 * A single hand-written IIFE (no build step, reviewer-readable source). It
 * registers a dashboard tab that hosts the sprite player, manual state and
 * emotion controls, and plugin settings.
 *
 * The player is the two-stacked-videos crossfade design: the next clip loads
 * in the hidden element and only swaps in once it can play, so a clip still
 * downloading never shows a blank frame. Emotions play the detected clip
 * directly — the sprite's appearance always matches the reported state.
 *
 * Clips come from a pinned commit of the sprite set hosted on jsDelivr by
 * default; clips placed in the plugin's videos/ (or docs/videos/) directory
 * are served by the plugin backend and can be used instead via the
 * video_source setting. Each clip is downloaded at most once per session
 * (blob cache) and only one download is ever in flight — a new request
 * supersedes the previous one. The only third-party network traffic is the
 * clip CDN, and the session token is never sent to it. There is no telemetry.
 */
(function () {
  'use strict';

  var SDK = window.__HERMES_PLUGIN_SDK__;
  var PLUGINS = window.__HERMES_PLUGINS__;
  if (!SDK || !PLUGINS || !SDK.React) {
    console.warn('waifu-sprites: dashboard SDK not present; plugin not registered');
    return;
  }
  var React = SDK.React;
  var h = React.createElement;

  var API = '/api/plugins/waifu-sprites';

  // Pinned jsDelivr commit of the sprite clip set.
  var CDN_BASE = 'https://cdn.jsdelivr.net/gh/waifuai/waifuai.github.io@bfad073b3eec84f12d2d04c98de065e746ff7da2/waifu-sprites/videos/';

  // ── States and emotions ──────────────────────────────────────────
  // Clips are numbered: 1..12 for states, e1..e12 for emotions, most with
  // one or two alternates (N-1.mp4, N-2.mp4).

  var STATE_NUM = {
    idle: 1, listening: 2, speaking: 3, thinking: 4, typing: 5, searching: 6,
    calculating: 7, fixing: 8, success: 9, error: 10, alert: 11, sleeping: 12,
  };

  var EMOTION_NUM = {
    happy: 1, funny: 2, empathetic: 3, curious: 4, confused: 5, amazed: 6,
    sorry: 7, found_it: 8, annoyed: 9, overwhelmed: 10, planning: 11, love: 12,
  };

  // Backend emotions arrive as e-keys; labels use the sprite set's vocabulary.
  var EMOTION_BY_KEY = {};
  Object.keys(EMOTION_NUM).forEach(function (name) {
    EMOTION_BY_KEY['e' + EMOTION_NUM[name]] = name;
  });

  function stateLabel(name) {
    return name.charAt(0).toUpperCase() + name.slice(1);
  }

  function emotionLabel(name) {
    return name === 'found_it' ? 'Found it' : name.charAt(0).toUpperCase() + name.slice(1);
  }

  // Clips with a second alternate (most have one: N.mp4 and N-1.mp4).
  var EXTRA_VARIANTS = { '4': ['4-2'], 'e2': ['e2-2'] };

  function variantsOf(base) {
    return [base, base + '-1'].concat(EXTRA_VARIANTS[base] || []);
  }

  // ── Player ───────────────────────────────────────────────────────
  // Imperative player engine. The two <video> elements live in whichever
  // container is active (the tab or the floating overlay); moving them between
  // containers keeps playback running across layout switches.

  function createPlayer(onChange) {
    var videos = [];
    var front = 0;
    var lastClip = '';
    var loadToken = 0;
    var current = { kind: 'state', name: 'idle', label: 'Idle' };
    var container = null;
    var source = 'cdn'; // 'cdn' | 'local'
    var destroyed = false;

    // Each clip is fetched once per session and reused as a blob URL.
    var clipCache = new Map(); // clip name -> object URL
    var CACHE_LIMIT = 40;
    var inflight = null; // { abort() } for the single in-flight download

    for (var i = 0; i < 2; i++) {
      var v = document.createElement('video');
      v.muted = true;
      v.loop = true;
      v.playsInline = true;
      v.setAttribute('playsinline', '');
      v.setAttribute('webkit-playsinline', '');
      v.className = 'waifu-sprites-video';
      videos.push(v);
    }
    videos[0].className = 'waifu-sprites-video waifu-sprites-front';

    // The backend serves by state/emotion key ('4', 'e4'), not by filename.
    function clipKey(clip) {
      return clip.replace(/-\d+$/, '');
    }

    function clipUrl(clip) {
      return source === 'local'
        ? API + '/video/' + clipKey(clip)
        : CDN_BASE + clip + '.mp4';
    }

    function cachePut(clip, url) {
      clipCache.set(clip, url);
      if (clipCache.size > CACHE_LIMIT) {
        var oldest = clipCache.keys().next().value;
        var oldUrl = clipCache.get(oldest);
        clipCache.delete(oldest);
        URL.revokeObjectURL(oldUrl);
      }
    }

    // Resolve a clip to a playable URL, then hand it to onReady. Downloads
    // run one at a time: a newer request aborts the older one. Same-origin
    // (backend) URLs carry the session token; the CDN never sees it.
    function resolveClip(clip, token, onReady, onError) {
      if (destroyed) return;
      var cached = clipCache.get(clip);
      if (cached) {
        onReady(cached);
        return;
      }
      if (inflight) {
        inflight.abort();
        inflight = null;
      }
      var url = clipUrl(clip);
      var headers = {};
      if (url.charAt(0) === '/' && window.__HERMES_SESSION_TOKEN__) {
        headers['X-Hermes-Session-Token'] = window.__HERMES_SESSION_TOKEN__;
      }
      var controller = new AbortController();
      inflight = { controller: controller };
      fetch(url, { signal: controller.signal, credentials: 'same-origin', headers: headers })
        .then(function (r) {
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.blob();
        })
        .then(function (blob) {
          if (inflight && inflight.controller === controller) inflight = null;
          if (destroyed || token !== loadToken) return;
          var objectUrl = URL.createObjectURL(blob);
          cachePut(clip, objectUrl);
          onReady(objectUrl);
        })
        .catch(function () {
          if (inflight && inflight.controller === controller) inflight = null;
          if (!destroyed && token === loadToken) onError();
        });
    }

    function play(clip, label) {
      if (destroyed) return;
      lastClip = clip;
      current.label = label;
      onChange(current);
      if (!container) return;

      var token = ++loadToken;
      resolveClip(clip, token, function (url) {
        if (token !== loadToken || destroyed) return;
        var next = videos[1 - front];
        var shown = videos[front];
        next.oncanplay = function () {
          if (token !== loadToken) return;
          next.oncanplay = null;
          var p = next.play();
          if (p) p.then(function () {
            if (token !== loadToken) return;
            next.classList.add('waifu-sprites-front');
            shown.classList.remove('waifu-sprites-front');
            front = 1 - front;
            setTimeout(function () {
              if (token === loadToken) shown.pause();
            }, 300);
          }).catch(function () { /* autoplay retry happens on first pointer event */ });
        };
        next.src = url;
      }, function () {
        if (token !== loadToken) return;
        // Fall back to the plain clip if an alternate fails, then to CDN.
        var plain = clip.replace(/-\d+$/, '');
        if (plain !== clip) {
          play(plain, label);
        } else if (source !== 'cdn') {
          source = 'cdn';
          play(plain, label);
        }
      });
    }

    function chooseClip(base) {
      var options = variantsOf(base).filter(function (v) { return v !== lastClip; });
      if (!options.length) options = variantsOf(base);
      return options[Math.floor(Math.random() * options.length)];
    }

    function setState(name) {
      if (!STATE_NUM[name]) return;
      current = { kind: 'state', name: name, label: stateLabel(name) };
      play(chooseClip(String(STATE_NUM[name])), stateLabel(name));
    }

    // Arrives as an e-key ('e4'); the matching clip plays directly.
    function setEmotion(key) {
      var name = EMOTION_BY_KEY[key];
      if (!name) return false;
      current = { kind: 'emotion', name: name, label: emotionLabel(name) };
      play(chooseClip('e' + EMOTION_NUM[name]), emotionLabel(name));
      return true;
    }

    // Some browsers wait for a gesture before autoplaying muted video.
    function unlock() {
      var v = videos[front];
      if (v && v.paused) v.play().catch(function () {});
    }
    ['pointerdown', 'keydown', 'touchstart'].forEach(function (ev) {
      document.addEventListener(ev, unlock, { once: true, passive: true });
    });

    return {
      mount: function (el) {
        container = el;
        if (!el.contains(videos[front])) {
          el.appendChild(videos[front]);
          el.appendChild(videos[1 - front]);
        }
      },
      setSource: function (s) {
        source = s === 'local' ? 'local' : 'cdn';
        // Replay the current clip through the new source.
        if (current.kind === 'emotion') setEmotion('e' + EMOTION_NUM[current.name]);
        else setState(current.name);
      },
      setState: setState,
      setEmotion: setEmotion,
      current: function () { return current; },
      pause: function () { videos.forEach(function (v) { v.pause(); }); },
      destroy: function () {
        destroyed = true;
        if (inflight) {
          inflight.controller.abort();
          inflight = null;
        }
        videos.forEach(function (v) { v.pause(); v.removeAttribute('src'); v.load(); });
        clipCache.forEach(function (url) { URL.revokeObjectURL(url); });
        clipCache.clear();
      },
    };
  }

  // ── Floating overlay ─────────────────────────────────────────────
  // Our own element appended to <body>; the app's markup is never read or
  // modified. Dragging moves only this node.

  function createOverlay(player, getSize) {
    var el = document.createElement('div');
    el.className = 'waifu-sprites-overlay';
    var stage = document.createElement('div');
    stage.className = 'waifu-sprites-overlay-stage';
    el.appendChild(stage);
    document.body.appendChild(el);

    var dragging = false;
    var offX = 0, offY = 0;

    el.addEventListener('pointerdown', function (e) {
      dragging = true;
      offX = e.clientX - el.offsetLeft;
      offY = e.clientY - el.offsetTop;
      el.setPointerCapture(e.pointerId);
    });
    el.addEventListener('pointermove', function (e) {
      if (!dragging) return;
      var w = el.offsetWidth, ht = el.offsetHeight;
      var x = Math.min(Math.max(0, e.clientX - offX), window.innerWidth - w);
      var y = Math.min(Math.max(0, e.clientY - offY), window.innerHeight - ht);
      el.style.left = x + 'px';
      el.style.top = y + 'px';
    });
    el.addEventListener('pointerup', function () { dragging = false; });
    el.addEventListener('pointercancel', function () { dragging = false; });

    function applySize() {
      var px = Math.max(120, Math.min(480, getSize() || 320));
      el.style.width = px + 'px';
    }

    return {
      stage: stage,
      applySize: applySize,
      destroy: function () {
        if (el.parentNode) el.parentNode.removeChild(el);
      },
    };
  }

  // ── API helpers ──────────────────────────────────────────────────

  function apiGet(path) {
    if (SDK.fetchJSON) return SDK.fetchJSON(API + path);
    var headers = {};
    // Older dashboards expose the session token as a global instead of SDK.fetchJSON.
    if (window.__HERMES_SESSION_TOKEN__) {
      headers['X-Hermes-Session-Token'] = window.__HERMES_SESSION_TOKEN__;
    }
    return fetch(API + path, { credentials: 'same-origin', headers: headers }).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  function apiPost(path, body) {
    var headers = { 'Content-Type': 'application/json' };
    // Older dashboards expose the session token as a global instead of SDK.fetchJSON.
    if (window.__HERMES_SESSION_TOKEN__) {
      headers['X-Hermes-Session-Token'] = window.__HERMES_SESSION_TOKEN__;
    }
    var init = {
      method: 'POST',
      headers: headers,
      credentials: 'same-origin',
      body: JSON.stringify(body),
    };
    return fetch(API + path, init).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  // ── Dashboard tab component ──────────────────────────────────────

  function WaifuTab() {
    var state = React.useState({ status: null, config: null, error: null });
    var status = state[0].status;
    var config = state[0].config;
    var error = state[0].error;
    var setState = state[1];

    var stageRef = React.useRef(null);
    var playerRef = React.useRef(null);
    var overlayRef = React.useRef(null);
    var cfgRef = React.useRef(null);
    cfgRef.current = config;

    // One-time engine setup: player, overlay, clip source, first clip.
    React.useEffect(function () {
      var player = createPlayer(function () {});
      playerRef.current = player;

      var overlay = null;
      apiGet('/config').then(function (cfg) {
        setState(function (s) { return Object.assign({}, s, { config: cfg }); });
        applyOverlay(cfg);
        resolveSource(cfg);
      }).catch(function () {
        applyOverlay(null);
        resolveSource(null);
      });

      function applyOverlay(cfg) {
        var enabled = !cfg || cfg.overlay_enabled !== false;
        if (enabled && !overlay) {
          overlay = createOverlay(player, function () {
            return cfgRef.current && cfgRef.current.overlay_size;
          });
          overlayRef.current = overlay;
          overlay.applySize();
          player.mount(overlay.stage);
        } else if (!enabled && overlay) {
          player.pause();
          overlay.destroy();
          overlay = null;
          overlayRef.current = null;
        }
      }

      function resolveSource(cfg) {
        var mode = (cfg && cfg.video_source) || 'auto';
        if (mode === 'cdn') {
          player.setSource('cdn');
          player.setState('idle');
          return;
        }
        apiGet('/videos').then(function (res) {
          var hasLocal = res && res.videos && res.videos.length > 0;
          var src = mode === 'local' || (mode === 'auto' && hasLocal) ? 'local' : 'cdn';
          player.setSource(src);
          player.setState('idle');
        }).catch(function () {
          player.setSource('cdn');
          player.setState('idle');
        });
      }

      return function cleanup() {
        player.destroy();
        if (overlay) overlay.destroy();
        playerRef.current = null;
        overlayRef.current = null;
      };
    }, []);

    // Poll the backend for agent state; drive the player from it.
    React.useEffect(function () {
      var stopped = false;
      var timer = null;
      var applied = null;

      function tick() {
        apiGet('/status').then(function (s) {
          if (stopped) return;
          setState(function (prev) { return Object.assign({}, prev, { status: s, error: null }); });
          var player = playerRef.current;
          // The same state persists across polls; only re-drive the player
          // when the reported state/emotion actually changes.
          var sig = (s.emotion || '') + '>' + (s.state || '');
          if (player && sig !== applied) {
            applied = sig;
            if (s.emotion) {
              if (!player.setEmotion(s.emotion)) player.setState(s.state || 'idle');
            } else if (s.state) {
              player.setState(s.state);
            }
          }
          schedule();
        }).catch(function (err) {
          if (stopped) return;
          setState(function (prev) {
            return Object.assign({}, prev, { error: 'backend unreachable — ' + err.message });
          });
          schedule();
        });
      }

      function schedule() {
        if (stopped) return;
        var ms = 2000;
        if (cfgRef.current && cfgRef.current.poll_interval_ms) {
          ms = Math.max(500, cfgRef.current.poll_interval_ms);
        }
        timer = setTimeout(tick, ms);
      }

      tick();
      return function cleanup() {
        stopped = true;
        if (timer) clearTimeout(timer);
      };
    }, []);

    function saveConfig(patch) {
      return apiPost('/config', patch).then(function (res) {
        var cfg = (res && res.config) || null;
        setState(function (s) { return Object.assign({}, s, { config: cfg }); });
        if (playerRef.current && overlayRef.current) overlayRef.current.applySize();
        return cfg;
      }).catch(function (err) {
        setState(function (s) { return Object.assign({}, s, { error: 'config save failed — ' + err.message }); });
        return null;
      });
    }

    function toggleOverlay() {
      var enabled = !(cfgRef.current && cfgRef.current.overlay_enabled !== false);
      saveConfig({ overlay_enabled: enabled }).then(function (cfg) {
        var player = playerRef.current;
        if (!player) return;
        if (cfg && cfg.overlay_enabled === false) {
          if (overlayRef.current) {
            player.pause();
            overlayRef.current.destroy();
            overlayRef.current = null;
          }
          player.mount(stageRef.current);
        } else if (cfg) {
          var overlay = createOverlay(player, function () { return cfg.overlay_size; });
          overlayRef.current = overlay;
          overlay.applySize();
          player.mount(overlay.stage);
        }
      });
    }

    function setManual(body) {
      apiPost('/state', body).catch(function (err) {
        setState(function (s) {
          return Object.assign({}, s, { error: 'state change failed — ' + err.message });
        });
      });
    }

    var display = status ? (status.emotion ? status.emotion : status.state) : null;
    var labelText = status
      ? (status.emotion ? emotionLabel(EMOTION_BY_KEY[status.emotion] || status.emotion)
                        : stateLabel(status.state || 'idle'))
      : 'Waiting for agent…';

    var stateButtons = Object.keys(STATE_NUM).map(function (name) {
      return h('button', {
        key: name,
        className: 'waifu-sprites-chip' + (display === name ? ' waifu-sprites-active' : ''),
        onClick: function () { setManual({ state: name }); },
      }, stateLabel(name));
    });

    var emotionButtons = Object.keys(EMOTION_NUM).map(function (key) {
      var eKey = 'e' + EMOTION_NUM[key];
      return h('button', {
        key: key,
        className: 'waifu-sprites-chip' + (display === eKey ? ' waifu-sprites-active' : ''),
        onClick: function () { setManual({ emotion: eKey }); },
      }, emotionLabel(key));
    });

    var overlayOn = config ? config.overlay_enabled !== false : true;

    return h('div', { className: 'waifu-sprites-tab' },
      h('div', { className: 'waifu-sprites-header' },
        h('h2', { className: 'waifu-sprites-title' }, 'Waifu Sprites'),
        h('span', { className: 'waifu-sprites-pill' }, labelText)
      ),
      error ? h('div', { className: 'waifu-sprites-error' }, error) : null,
      h('div', { className: 'waifu-sprites-panel' },
        h('div', {
          ref: stageRef,
          className: 'waifu-sprites-stage' + (overlayOn ? ' waifu-sprites-stage-overlay' : ''),
        })
      ),
      overlayOn ? h('div', { className: 'waifu-sprites-note' },
        'The sprite floats above the dashboard — drag it anywhere. Uncheck the overlay to dock it here.') : null,
      h('div', { className: 'waifu-sprites-section' },
        h('div', { className: 'waifu-sprites-section-title' }, 'States'),
        h('div', { className: 'waifu-sprites-chips' }, stateButtons)
      ),
      h('div', { className: 'waifu-sprites-section' },
        h('div', { className: 'waifu-sprites-section-title' }, 'Emotions'),
        h('div', { className: 'waifu-sprites-chips' }, emotionButtons)
      ),
      h('div', { className: 'waifu-sprites-section' },
        h('div', { className: 'waifu-sprites-section-title' }, 'Settings'),
        h('div', { className: 'waifu-sprites-settings' },
          h('label', { className: 'waifu-sprites-setting' },
            h('input', {
              type: 'checkbox',
              checked: overlayOn,
              onChange: toggleOverlay,
            }),
            ' Floating overlay'
          ),
          h('label', { className: 'waifu-sprites-setting' },
            'Size ',
            h('input', {
              type: 'range',
              min: 120,
              max: 480,
              step: 20,
              value: (config && config.overlay_size) || 320,
              onChange: function (e) { saveConfig({ overlay_size: parseInt(e.target.value, 10) }); },
            }),
            h('span', { className: 'waifu-sprites-value' }, (config && config.overlay_size) || 320, 'px')
          ),
          h('label', { className: 'waifu-sprites-setting' },
            'Refresh ',
            h('select', {
              value: String((config && config.poll_interval_ms) || 2000),
              onChange: function (e) { saveConfig({ poll_interval_ms: parseInt(e.target.value, 10) }); },
            },
              h('option', { value: '1000' }, '1s'),
              h('option', { value: '2000' }, '2s'),
              h('option', { value: '5000' }, '5s')
            )
          ),
          h('label', { className: 'waifu-sprites-setting' },
            'Clips ',
            h('select', {
              value: (config && config.video_source) || 'auto',
              onChange: function (e) {
                var mode = e.target.value;
                saveConfig({ video_source: mode }).then(function (cfg) {
                  if (!playerRef.current) return;
                  if (mode === 'cdn') playerRef.current.setSource('cdn');
                  else if (mode === 'local') playerRef.current.setSource('local');
                  else {
                    apiGet('/videos').then(function (res) {
                      playerRef.current.setSource(res && res.videos && res.videos.length ? 'local' : 'cdn');
                    }).catch(function () { playerRef.current.setSource('cdn'); });
                  }
                });
              },
            },
              h('option', { value: 'auto' }, 'Auto (local if present)'),
              h('option', { value: 'cdn' }, 'CDN (pinned)'),
              h('option', { value: 'local' }, 'Local videos/ only')
            )
          )
        )
      )
    );
  }

  PLUGINS.register('waifu-sprites', WaifuTab);
})();
