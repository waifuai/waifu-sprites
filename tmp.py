import subprocess
import os
import requests
import json
import time

def get_windows_host_ip():
    if "WSL_DISTRO_NAME" in os.environ:
        try:
            # Get default gateway from ip route (the Windows Host VM switch)
            result = subprocess.run(["ip", "route"], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                if line.startswith("default via"):
                    return line.split(" ")[2]
        except Exception:
            pass
    return "127.0.0.1"

WAIFU_URL = f"http://{get_windows_host_ip()}:8000/state"

def set_waifu_state(state: str):
    """
    Sends a command to the Rust waifu-sprites UI to change the 12-PNG frame.
    Valid states: "idle", "listening", "speaking", "thinking", "typing", 
                  "searching", "calculating", "fixing", "success", "error", 
                  "alert", "sleeping"
    """
    try:
        payload = {"state": state}
        # We use a short timeout so Hermes doesn't freeze if the UI is closed
        requests.post(WAIFU_URL, json=payload, timeout=0.1)
    except requests.exceptions.RequestException:
        # If the Rust app isn't running, just silently fail so Hermes keeps working
        pass

# --- Example Hooks to put inside Hermes Agent ---

def on_user_input_received():
    """Call this when the user hits 'Enter' in the terminal."""
    set_waifu_state("thinking")

def on_tool_start(tool_name: str):
    """Call this right before Hermes executes a Python/Bash tool."""
    if "math" in tool_name or "calculate" in tool_name:
        set_waifu_state("calculating")
    elif "search" in tool_name or "browser" in tool_name:
        set_waifu_state("searching")
    else:
        set_waifu_state("typing") # Default tool execution state

def on_tool_error(error_message: str):
    """Call this if the Python script crashes."""
    set_waifu_state("error")
    time.sleep(2) # Let the user see her drop the plates

def on_tool_success():
    """Call this when a tool finishes successfully."""
    set_waifu_state("success")
    time.sleep(1) # Let the user see the thumbs up

def on_agent_speaking():
    """Call this while Hermes is streaming text or playing TTS."""
    set_waifu_state("speaking")

def on_agent_idle():
    """Call this when Hermes is waiting for the user."""
    set_waifu_state("idle")
