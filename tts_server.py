"""
Waifu Voice TTS Server
Listens on port 8001 for POST /tts requests.
Receives sentence-sized chunks from waifu_hook.py and queues them for sequential playback.
Also monitors a queue file for legacy text from WSL.
"""

import os
import queue
import threading
import time
import sounddevice as sd
import numpy as np
import onnxruntime as rt
from kokoro_onnx import Kokoro
from flask import Flask, request, jsonify

app = Flask(__name__)
tts_queue = queue.Queue()

# ── Config ────────────────────────────────────────────────────────────────────
VOICE = "af_heart"
SPEED = 1.0
PORT = 8001
QUEUE_FILE = os.path.join(os.path.expanduser("~"), ".waifu-voice-queue.txt")

# ── Batch Tracking & Skip State ───────────────────────────────────────────────
# Tracks the current batch of chunks for skip forward/back navigation.
batch_lock = threading.Lock()
batch_items = []          # list of {"text": str, "chunk_index": int, "total_chunks": int}
batch_current = -1        # index into batch_items of the chunk currently playing
batch_total_chunks = 0    # total_chunks value for current batch
skip_event = threading.Event()  # signals the worker to stop current audio
skip_direction = 0        # -1 = back, 0 = none, 1 = forward

SESSION_OPTIONS = rt.SessionOptions()
SESSION_OPTIONS.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_ALL

# ── Download model if needed ─────────────────────────────────────────────────
KOKORO_DIR = os.path.join(os.path.expanduser("~"), ".kokoro-onnx")
MODEL_PATH = os.path.join(KOKORO_DIR, "model.onnx")
VOICES_PATH = os.path.join(KOKORO_DIR, "voices.bin")


def ensure_model():
    os.makedirs(KOKORO_DIR, exist_ok=True)
    if not os.path.exists(MODEL_PATH):
        print("Downloading Kokoro model (fp16-gpu)...")
        import urllib.request

        urllib.request.urlretrieve(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.fp16-gpu.onnx",
            MODEL_PATH,
        )
    if not os.path.exists(VOICES_PATH):
        print("Downloading voices...")
        import urllib.request

        urllib.request.urlretrieve(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
            VOICES_PATH,
        )


# ── Initialize TTS Engine ─────────────────────────────────────────────────────
print("Initializing Kokoro TTS...")
ensure_model()
providers = (
    ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if "CUDAExecutionProvider" in rt.get_available_providers()
    else ["CPUExecutionProvider"]
)
kokoro = Kokoro.from_session(
    rt.InferenceSession(MODEL_PATH, SESSION_OPTIONS, providers=providers), VOICES_PATH
)
voice_style = kokoro.get_voice_style(VOICE)
device_idx = None
device_name = "Default System Output"
print(f"Using audio device: {device_name}")
print("Kokoro TTS Ready.")


# ── Pre-render Queue ───────────────────────────────────────────────────────────
# Separates TTS generation from playback so next chunk is ready before current finishes.
rendered_queue = queue.Queue()  # holds {"audio": np.array, "sample_rate": int, "item": dict}

# ── Generator Thread ──────────────────────────────────────────────────────────
# Pulls text items from tts_queue, generates audio, puts rendered audio into rendered_queue.
def tts_generator():
    """Pre-render chunks ahead of playback so there's zero gap between them."""
    global batch_current, batch_total_chunks
    while True:
        item = tts_queue.get()
        if item is None:
            rendered_queue.put(None)  # Propagate exit signal to player
            break

        text = item["text"] if isinstance(item, dict) else item
        chunk_index = item.get("chunk_index", "?") if isinstance(item, dict) else "?"
        total_chunks = item.get("total_chunks", "?") if isinstance(item, dict) else "?"

        # Track batch for skip navigation
        if isinstance(item, dict) and "chunk_index" in item:
            with batch_lock:
                ci = item["chunk_index"]
                tc = item["total_chunks"]
                if ci == 0 or (ci == 1 and batch_total_chunks != tc) or tc != batch_total_chunks:
                    if ci == 0 or batch_total_chunks != tc:
                        batch_items.clear()
                while len(batch_items) <= ci:
                    batch_items.append(None)
                batch_items[ci] = {"text": text, "chunk_index": ci, "total_chunks": tc}
                batch_current = ci
                batch_total_chunks = tc

        try:
            print(f"[RENDER] Chunk {chunk_index}/{total_chunks}: \"{text[:80]}{'...' if len(text) > 80 else ''}\"", flush=True)
            audio, sample_rate = kokoro.create(text, voice=voice_style, speed=SPEED)
            rendered_queue.put({
                "audio": audio,
                "sample_rate": sample_rate,
                "item": item,
                "chunk_index": chunk_index,
                "total_chunks": total_chunks,
            })
            print(f"[READY] Chunk {chunk_index}/{total_chunks}", flush=True)
        except Exception as e:
            print(f"[RENDER ERROR] {e}", flush=True)
        tts_queue.task_done()


# ── Player Thread ─────────────────────────────────────────────────────────────
# Pulls pre-rendered audio from rendered_queue and plays it sequentially.
# Handles skip forward/back by discarding or re-queuing rendered items.
def tts_player():
    """Play pre-rendered audio chunks. Handles skip navigation."""
    while True:
        rendered = rendered_queue.get()
        if rendered is None:
            break  # Exit signal

        audio = rendered["audio"]
        sample_rate = rendered["sample_rate"]
        chunk_index = rendered["chunk_index"]
        total_chunks = rendered["total_chunks"]

        try:
            print(f"[SPEAK] Chunk {chunk_index}/{total_chunks}", flush=True)
            skip_event.clear()
            sd.play(audio, samplerate=sample_rate, device=device_idx)

            # Wait for playback to finish OR skip signal
            while sd.get_stream().active:
                if skip_event.is_set():
                    sd.stop()
                    print("[SKIP] Playback interrupted", flush=True)
                    break
                time.sleep(0.05)
            else:
                print("[DONE]", flush=True)

            # Handle skip direction
            if skip_event.is_set():
                direction = skip_direction
                with batch_lock:
                    if direction < 0 and batch_current > 0:
                        target = batch_current - 1
                        prev = batch_items[target] if target < len(batch_items) else None
                        if prev:
                            print(f"[SKIP BACK] Replaying chunk {target}", flush=True)
                            # Drain any pre-rendered audio that's ahead
                            while not rendered_queue.empty():
                                try:
                                    rendered_queue.get_nowait()
                                    rendered_queue.task_done()
                                except queue.Empty:
                                    break
                            # Re-queue the text for re-rendering
                            tts_queue.put(prev)
                    elif direction > 0 and batch_current < len(batch_items) - 1:
                        print(f"[SKIP FORWARD] Skipping to next chunk", flush=True)
                        # Drain one pre-rendered item (the one we're skipping)
                        try:
                            rendered_queue.get_nowait()
                            rendered_queue.task_done()
                        except queue.Empty:
                            pass
                    skip_direction = 0
                    skip_event.clear()
        except Exception as e:
            print(f"[PLAY ERROR] {e}", flush=True)
        rendered_queue.task_done()


generator_thread = threading.Thread(target=tts_generator, daemon=True)
generator_thread.start()

player_thread = threading.Thread(target=tts_player, daemon=True)
player_thread.start()


# ── Queue File Monitor (legacy single-file) ───────────────────────────────────
def monitor_queue_file():
    """Monitor the queue file for legacy text from WSL (single-file write mode)."""
    last_mtime = 0
    while True:
        try:
            if os.path.exists(QUEUE_FILE):
                mtime = os.path.getmtime(QUEUE_FILE)
                if mtime > last_mtime:
                    last_mtime = mtime
                    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                        text = f.read().strip()
                    if text:
                        print(f"[FILE QUEUE] Read: {text[:50]}...")
                        tts_queue.put({"text": text, "chunk_index": 0, "total_chunks": 1})
                        open(QUEUE_FILE, "w").close()
        except Exception as e:
            print(f"[FILE QUEUE] Error: {e}")
        time.sleep(0.1)


queue_monitor = threading.Thread(target=monitor_queue_file, daemon=True)
queue_monitor.start()


# ── Queue Directory Monitor (multi-file chunked) ──────────────────────────────
QUEUE_DIR = os.path.join(os.path.expanduser("~"), ".waifu-voice-queue")
_seen_manifests = set()


def monitor_queue_dir():
    """Monitor the queue directory for manifest files written by waifu_hook.py.

    Each manifest contains a list of chunk filenames (one per line).
    Each chunk file contains the text to speak.
    We read all chunks in order and queue them for TTS.
    """
    while True:
        try:
            if os.path.isdir(QUEUE_DIR):
                # Look for .manifest files
                for fname in sorted(os.listdir(QUEUE_DIR)):
                    if not fname.endswith(".manifest"):
                        continue
                    manifest_path = os.path.join(QUEUE_DIR, fname)
                    if manifest_path in _seen_manifests:
                        continue
                    _seen_manifests.add(manifest_path)

                    try:
                        with open(manifest_path, "r", encoding="utf-8") as f:
                            chunk_files = [line.strip() for line in f if line.strip()]

                        if not chunk_files:
                            continue

                        total = len(chunk_files)
                        print(f"[DIR QUEUE] Manifest {fname}: {total} chunks", flush=True)

                        for i, chunk_fname in enumerate(chunk_files):
                            chunk_path = os.path.join(QUEUE_DIR, chunk_fname)
                            if os.path.exists(chunk_path):
                                with open(chunk_path, "r", encoding="utf-8") as f:
                                    text = f.read().strip()
                                if text:
                                    print(f"[DIR QUEUE] Chunk {i+1}/{total}: \"{text[:70]}{'...' if len(text) > 70 else ''}\"", flush=True)
                                    tts_queue.put({
                                        "text": text,
                                        "chunk_index": i,
                                        "total_chunks": total,
                                    })
                            else:
                                print(f"[DIR QUEUE] Missing chunk file: {chunk_fname}", flush=True)

                    except Exception as e:
                        print(f"[DIR QUEUE] Error reading manifest {fname}: {e}", flush=True)

                # Clean up old manifests (keep set from growing forever)
                if len(_seen_manifests) > 100:
                    _seen_manifests.clear()

        except Exception as e:
            print(f"[DIR QUEUE] Error: {e}", flush=True)
        time.sleep(0.1)


dir_monitor = threading.Thread(target=monitor_queue_dir, daemon=True)
dir_monitor.start()


# ── Request Logging ───────────────────────────────────────────────────────────
@app.before_request
def log_request_info():
    pass  # Suppress per-request logging to reduce noise during chunked playback


# ── API Endpoints ─────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ready", "voice": VOICE, "device": device_name})


@app.route("/tts", methods=["POST"])
@app.route("/speak", methods=["POST"])
def tts_endpoint():
    data = request.json
    if not data or "text" not in data:
        return jsonify({"error": "No text provided"}), 400

    text = data["text"]
    chunk_index = data.get("chunk_index", "?")
    total_chunks = data.get("total_chunks", "?")
    print(f"[TTS] Chunk {chunk_index}/{total_chunks}: \"{text[:70]}{'...' if len(text) > 70 else ''}\"", flush=True)
    # Pass as dict so worker can track batches for skip navigation
    tts_queue.put({
        "text": text,
        "chunk_index": chunk_index if isinstance(chunk_index, int) else 0,
        "total_chunks": total_chunks if isinstance(total_chunks, int) else 1,
    })
    return jsonify({"success": True, "message": "Text queued for TTS"})


@app.route("/clear", methods=["POST"])
def clear_queue():
    """Clear all pending TTS chunks (for interrupt/cancel)."""
    global batch_current, batch_total_chunks
    # Drain text queue
    while not tts_queue.empty():
        try:
            tts_queue.get_nowait()
            tts_queue.task_done()
        except queue.Empty:
            break
    # Drain pre-rendered audio queue
    while not rendered_queue.empty():
        try:
            rendered_queue.get_nowait()
            rendered_queue.task_done()
        except queue.Empty:
            break
    with batch_lock:
        batch_items.clear()
        batch_current = -1
        batch_total_chunks = 0
    skip_event.set()  # interrupt any currently playing audio

    # Also clean the queue directory (multi-file chunked queue)
    try:
        if os.path.isdir(QUEUE_DIR):
            for fname in os.listdir(QUEUE_DIR):
                if fname.endswith((".txt", ".manifest")):
                    try:
                        os.unlink(os.path.join(QUEUE_DIR, fname))
                    except Exception:
                        pass
            _seen_manifests.clear()
    except Exception:
        pass

    print("[TTS] Queue cleared", flush=True)
    return jsonify({"success": True, "message": "Queue cleared"})


def _is_playing():
    """Check if audio is currently playing, safely handling no-stream state."""
    try:
        stream = sd.get_stream()
        return stream.active if stream else False
    except RuntimeError:
        return False


@app.route("/tts/status", methods=["GET"])
def tts_status():
    """Return current TTS queue state for the sprite UI."""
    with batch_lock:
        return jsonify({
            "playing": _is_playing(),
            "queue_size": tts_queue.qsize(),
            "batch_current": batch_current,
            "batch_total": len(batch_items),
            "batch_total_chunks": batch_total_chunks,
            "current_text": batch_items[batch_current]["text"] if 0 <= batch_current < len(batch_items) and batch_items[batch_current] else "",
        })


@app.route("/tts/speed", methods=["GET", "POST"])
def tts_speed():
    """Get or set TTS playback speed."""
    global SPEED
    if request.method == "GET":
        return jsonify({"speed": SPEED})
    data = request.json or {}
    new_speed = data.get("speed", 1.0)
    try:
        new_speed = float(new_speed)
        new_speed = max(0.5, min(2.0, new_speed))  # clamp 0.5x - 2.0x (Kokoro limit)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid speed value"}), 400
    SPEED = new_speed
    print(f"[TTS] Speed set to {SPEED}x", flush=True)
    return jsonify({"success": True, "speed": SPEED})


@app.route("/tts/skip", methods=["POST"])
def tts_skip():
    """Skip forward or backward in the current TTS batch."""
    global skip_direction
    data = request.json or {}
    direction = data.get("direction", "forward")

    with batch_lock:
        if direction == "back" and batch_current <= 0:
            return jsonify({"success": False, "message": "Already at first chunk"})
        if direction == "forward" and batch_current >= len(batch_items) - 1:
            # Nothing to skip forward to — just stop current playback
            skip_direction = 1
            skip_event.set()
            return jsonify({"success": True, "message": "Skipped (last chunk)"})

    skip_direction = -1 if direction == "back" else 1
    skip_event.set()
    print(f"[TTS] Skip {direction}", flush=True)
    return jsonify({"success": True, "message": f"Skip {direction}"})


@app.errorhandler(404)
def page_not_found(e):
    print(f"404 Error: {request.method} {request.path}", flush=True)
    return jsonify(
        {"error": "Not Found", "method": request.method, "path": request.path}
    ), 404


if __name__ == "__main__":
    import logging
    import sys

    # ── Quiet mode: suppress per-request werkzeug logs ──
    QUIET = "--quiet" in sys.argv
    if QUIET:
        log = logging.getLogger("werkzeug")
        log.setLevel(logging.WARNING)  # only show warnings/errors, not INFO requests

    print(f"Starting server on http://127.0.0.1:{PORT}", flush=True)
    app.run(host="0.0.0.0", port=PORT, debug=not QUIET, use_reloader=False)
