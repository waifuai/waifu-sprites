/**
 * clip-browser.js: sanity-check browser for the sprite clip set.
 *
 * Static page, no backend: every clip streams from the same pinned jsDelivr
 * commit the plugin's dashboard frontend uses. Click a card to play it, or
 * turn on auto-cycle to showcase the whole set. Each clip is fetched once
 * per session and reused (blob cache), and only one download is in flight.
 */
(function () {
  'use strict';

  var CDN_BASE = 'https://cdn.jsdelivr.net/gh/waifuai/waifuai.github.io@bfad073b3eec84f12d2d04c98de065e746ff7da2/waifu-sprites/videos/';

  var STATE_LABELS = {
    '1': { label: 'idle',         icon: '\u25b6',  type: 'state' },
    '2': { label: 'listening',    icon: '\u266b',  type: 'state' },
    '3': { label: 'speaking',     icon: '\u266b',  type: 'state' },
    '4': { label: 'thinking',     icon: '\u2026',  type: 'state' },
    '5': { label: 'typing',       icon: '\u2328',  type: 'state' },
    '6': { label: 'searching',    icon: '\u26b2',  type: 'state' },
    '7': { label: 'calculating',  icon: '\u00f7',  type: 'state' },
    '8': { label: 'fixing',       icon: '\u2692',  type: 'state' },
    '9': { label: 'success',      icon: '\u2713',  type: 'state' },
    '10': { label: 'error',       icon: '\u2717',  type: 'state' },
    '11': { label: 'alert',       icon: '\u26a0',  type: 'state' },
    '12': { label: 'sleeping',    icon: '\u263d',  type: 'state' },
    'e1': { label: 'happy',       icon: '\u263a',  type: 'emotion' },
    'e2': { label: 'funny',       icon: '\u263a',  type: 'emotion' },
    'e3': { label: 'empathetic',  icon: '\u2665',  type: 'emotion' },
    'e4': { label: 'curious',     icon: '?',       type: 'emotion' },
    'e5': { label: 'confused',    icon: '?',       type: 'emotion' },
    'e6': { label: 'amazed',      icon: '!',       type: 'emotion' },
    'e7': { label: 'sorry',       icon: '~',       type: 'emotion' },
    'e8': { label: 'found it',    icon: '\u2713',  type: 'emotion' },
    'e9': { label: 'annoyed',     icon: '\u2260',  type: 'emotion' },
    'e10': { label: 'overwhelmed',icon: '\u26a0',  type: 'emotion' },
    'e11': { label: 'planning',   icon: '\u2191',  type: 'emotion' },
    'e12': { label: 'love',       icon: '\u2665',  type: 'emotion' },
  };

  var ALL_CLIPS = [
    '1', '1-1', '2', '2-1', '3', '3-1', '4', '4-1', '4-2', '5', '5-1',
    '6', '6-1', '7', '7-1', '8', '8-1', '9', '9-1', '10', '10-1',
    '11', '11-1', '12', '12-1',
    'e1', 'e1-1', 'e2', 'e2-1', 'e2-2', 'e3', 'e3-1', 'e4', 'e4-1',
    'e5', 'e5-1', 'e6', 'e6-1', 'e7', 'e7-1', 'e8', 'e8-1', 'e9', 'e9-1',
    'e10', 'e10-1', 'e11', 'e11-1', 'e12', 'e12-1'
  ];

  var ALL_STATES = ALL_CLIPS.map(function (num) {
    var base = num.replace(/-\d+$/, '');
    var info = STATE_LABELS[base] || { label: base, icon: '?', type: 'unknown' };
    var variation = num.match(/-(\d+)$/);
    var label = info.label + (variation ? ' v' + variation[1] : '');
    return { num: num, label: label, icon: info.icon, type: info.type };
  });

  var videoEl = document.getElementById('mainVideo');
  var stateLabel = document.getElementById('stateLabel');
  var stateIcon = document.getElementById('stateIcon');
  var eventFeed = document.getElementById('eventFeed');
  var statesGrid = document.getElementById('statesGrid');
  var cycleBtn = document.getElementById('cycleBtn');
  var cycleStatus = document.getElementById('cycleStatus');

  var clipCache = new Map(); // clip name -> object URL
  var currentObjectUrl = null;
  var autoTimer = null;
  var isAutoPlaying = false;

  // ── Build grid ─────────────────────────────────────────────────
  ALL_STATES.forEach(function (s, i) {
    var card = document.createElement('div');
    card.className = 'state-card';
    card.setAttribute('data-index', i);
    card.innerHTML =
      '<div class="state-card-icon">' + s.icon + '</div>' +
      '<div class="state-card-name">' + s.label + '</div>' +
      '<div class="state-card-type">' + s.type + '</div>';
    card.addEventListener('click', function () {
      stopAutoPlay();
      playState(i);
    });
    statesGrid.appendChild(card);
  });

  // ── Play a clip ────────────────────────────────────────────────
  function playState(index) {
    var state = ALL_STATES[index];

    var cards = document.querySelectorAll('.state-card');
    cards.forEach(function (c, i) {
      c.classList.toggle('playing', i === index);
    });

    stateLabel.textContent = state.label;
    stateIcon.innerHTML = state.icon;

    var feedTexts = {
      '1': 'session active | waiting for input',
      '2': '[hook] on_session_start',
      '3': '[llm] generating response...',
      '4': '[llm] processing...',
      '5': '[tool] write_file',
      '6': '[tool] web_search',
      '7': '[tool] execute_code',
      '8': '[tool] terminal',
      '9': '[tool] complete \u2192 idle',
      '10': '[tool] error detected',
      '11': '[hook] clarify requested',
      '12': '[hook] on_session_end',
      'e1': '[emotion] happy',
      'e2': '[emotion] funny',
      'e3': '[emotion] empathetic',
      'e4': '[emotion] curious',
      'e5': '[emotion] confused',
      'e6': '[emotion] amazed',
      'e7': '[emotion] sorry',
      'e8': '[emotion] found it',
      'e9': '[emotion] annoyed',
      'e10': '[emotion] overwhelmed',
      'e11': '[emotion] planning',
      'e12': '[emotion] love',
    };
    eventFeed.textContent = feedTexts[state.num.replace(/-\d+$/, '')] || '';
    eventFeed.style.opacity = '1';
    setTimeout(function () { eventFeed.style.opacity = '0.3'; }, 2500);

    loadClip(state.num, function (url) {
      if (currentObjectUrl && currentObjectUrl !== url) {
        // Keep the blob alive in the cache; only swap the source.
      }
      currentObjectUrl = url;
      videoEl.src = url;
      videoEl.play().catch(function () {});
    });
  }

  function loadClip(clip, onReady) {
    var cached = clipCache.get(clip);
    if (cached) {
      onReady(cached);
      return;
    }
    fetch(CDN_BASE + clip + '.mp4')
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        clipCache.set(clip, url);
        onReady(url);
      })
      .catch(function () {
        // Leave the last clip playing; the badge already shows the target.
      });
  }

  // ── Auto-cycle ─────────────────────────────────────────────────
  // All 50 clips, starting from e12 (love) then wrapping.
  var SHOWCASE_ORDER = [];
  var i;
  for (i = 48; i < ALL_STATES.length; i++) SHOWCASE_ORDER.push(i);
  for (i = 0; i < 48; i++) SHOWCASE_ORDER.push(i);

  function startAutoPlay() {
    isAutoPlaying = true;
    cycleBtn.textContent = 'Auto-cycle: ON';
    cycleBtn.classList.add('active');
    cycleStatus.textContent = 'Playing all ' + SHOWCASE_ORDER.length + ' clips';
    var seqIndex = 0;
    playState(SHOWCASE_ORDER[0]);
    autoTimer = setInterval(function () {
      seqIndex = (seqIndex + 1) % SHOWCASE_ORDER.length;
      playState(SHOWCASE_ORDER[seqIndex]);
    }, 4000);
  }

  function stopAutoPlay() {
    isAutoPlaying = false;
    if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
    cycleBtn.textContent = 'Auto-cycle: OFF';
    cycleBtn.classList.remove('active');
    cycleStatus.textContent = 'Click any clip above';
  }

  cycleBtn.addEventListener('click', function () {
    if (isAutoPlaying) stopAutoPlay();
    else startAutoPlay();
  });

  // ── Init ───────────────────────────────────────────────────────
  // Start with love (e12, index 48), auto-cycle OFF.
  playState(48);
})();
