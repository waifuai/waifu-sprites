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


# ── Worker Thread (chunk-aware, skip-aware) ────────────────────────────────────
# Each queue item is a dict with text + optional chunk metadata.
# The worker processes them sequentially and supports skip forward/back.
def tts_worker():
    global batch_current, batch_total_chunks
    while True:
        item = tts_queue.get()
        if item is None:
            break  # Exit signal

        text = item["text"] if isinstance(item, dict) else item
        chunk_index = item.get("chunk_index", "?") if isinstance(item, dict) else "?"
        total_chunks = item.get("total_chunks", "?") if isinstance(item, dict) else "?"

        # Track batch for skip navigation
        if isinstance(item, dict) and "chunk_index" in item:
            with batch_lock:
                ci = item["chunk_index"]
                tc = item["total_chunks"]
                # New batch detected: first chunk or total_chunks changed
                if ci == 0 or (ci == 1 and batch_total_chunks != tc) or tc != batch_total_chunks:
                    if ci == 0 or batch_total_chunks != tc:
                        batch_items.clear()
                # Ensure list is big enough
                while len(batch_items) <= ci:
                    batch_items.append(None)
                batch_items[ci] = {"text": text, "chunk_index": ci, "total_chunks": tc}
                batch_current = ci
                batch_total_chunks = tc

        try:
            print(f"[SPEAK] Chunk {chunk_index}/{total_chunks}: \"{text[:80]}{'...' if len(text) > 80 else ''}\"", flush=True)
            audio, sample_rate = kokoro.create(text, voice=voice_style, speed=SPEED)
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
                        # Skip back: re-queue the previous chunk
                        target = batch_current - 1
                        prev = batch_items[target] if target < len(batch_items) else None
                        if prev:
                            print(f"[SKIP BACK] Replaying chunk {target}", flush=True)
                            tts_queue.put(prev)
                    elif direction > 0 and batch_current < len(batch_items) - 1:
                        # Skip forward: remove next item from queue if it's in our batch,
                        # let the worker pick up the one after
                        # (The next queue_get will handle it automatically)
                        print(f"[SKIP FORWARD] Skipping to next chunk", flush=True)
                    skip_direction = 0
                    skip_event.clear()
        except Exception as e:
            print(f"[ERROR] {e}", flush=True)
        tts_queue.task_done()


worker_thread = threading.Thread(target=tts_worker, daemon=True)
worker_thread.start()


# ── Queue File Monitor (legacy) ───────────────────────────────────────────────
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
    while not tts_queue.empty():
        try:
            tts_queue.get_nowait()
            tts_queue.task_done()
        except queue.Empty:
            break
    with batch_lock:
        batch_items.clear()
        batch_current = -1
        batch_total_chunks = 0
    skip_event.set()  # interrupt any currently playing audio
    print("[TTS] Queue cleared", flush=True)
    return jsonify({"success": True, "message": "Queue cleared"})


@app.route("/tts/status", methods=["GET"])
def tts_status():
    """Return current TTS queue state for the sprite UI."""
    with batch_lock:
        return jsonify({
            "playing": sd.get_stream().active if sd.get_stream() else False,
            "queue_size": tts_queue.qsize(),
            "batch_current": batch_current,
            "batch_total": len(batch_items),
            "batch_total_chunks": batch_total_chunks,
            "current_text": batch_items[batch_current]["text"] if 0 <= batch_current < len(batch_items) and batch_items[batch_current] else "",
        })


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

    logging.basicConfig(level=logging.DEBUG)
    print(f"Starting server on http://127.0.0.1:{PORT}", flush=True)
    app.run(host="0.0.0.0", port=PORT, debug=True, use_reloader=False)
