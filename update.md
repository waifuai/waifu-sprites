# Hermes Agent Update Guide (applying Waifu Sprites)

Whenever you run `hermes update`, Git will detect our "glue" scripts and branding changes as local conflicts. It will stash them, update the code, and often fail to reapply the stash due to structural changes in the upstream code.

If you are forced to do a `git reset --hard` to make the agent functional again, follow this guide to reapply all the Waifu UI hooks.

All paths below assume you are working inside the `~/.hermes/hermes-agent/` directory in your WSL2 instance.

---

## Part 1: Recreate `waifu_hook.py`
Create `waifu_hook.py` in the root of the `hermes-agent` directory (`~/.hermes/hermes-agent/waifu_hook.py`):

```python
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
    try:
        payload = {"state": state}
        # We use a short timeout so Hermes doesn't freeze if the UI is closed
        requests.post(WAIFU_URL, json=payload, timeout=0.1)
    except requests.exceptions.RequestException:
        pass

# --- Hooks ---
def on_user_input_received():
    set_waifu_state("thinking")

def on_tool_start(tool_name: str):
    if "math" in tool_name or "calculate" in tool_name:
        set_waifu_state("calculating")
    elif "search" in tool_name or "browser" in tool_name:
        set_waifu_state("searching")
    else:
        set_waifu_state("typing")

def on_tool_error(error_message: str):
    set_waifu_state("error")
    time.sleep(2)

def on_tool_success():
    set_waifu_state("success")
    time.sleep(1)

def on_agent_speaking():
    set_waifu_state("speaking")

def on_agent_idle():
    set_waifu_state("idle")
```

---

## Part 2: Hooking `cli.py`
Open `cli.py` and make the following injections.

**1. The Import**
Find the standard imports (around line 58) and add `waifu_hook`:
```python
import queue
import waifu_hook # <--- ADD THIS
```

**2. Agent Speaking Hook**
Find `def chat(self, message, images: list = None) -> Optional[str]:` and add the speaking hook immediately inside:
```python
    def chat(self, message, images: list = None) -> Optional[str]:
        waifu_hook.on_agent_speaking() # <--- ADD THIS
```

**3. User Input Hook**
Find where the `payload` is built from user input inside the chat loop. Add the hook right after the payload assignment:
```python
                payload = (text, images) if images else text
                waifu_hook.on_user_input_received() # <--- ADD THIS
```

**4. Agent Idle Hook**
Find the end of the `chat` method where the TTS thread is joined. Add the idle hook:
```python
            if tts_thread is not None and tts_thread.is_alive():
                tts_thread.join(timeout=5)
            waifu_hook.on_agent_idle() # <--- ADD THIS
```

---

## Part 3: Hooking `run_agent.py`
Open `run_agent.py` to intercept tool execution (cognition).

**1. The Import**
At the top of the file, add the import:
```python
import weakref
import waifu_hook # <--- ADD THIS
```

**2. Concurrent Tool Execution**
Find the `def _run_tool(index, tool_call, function_name, function_args):` method. Add the start, success, and error hooks inside the try/except block:
```python
        def _run_tool(index, tool_call, function_name, function_args):
            """Worker function executed in a thread."""
            start = time.time()
            waifu_hook.on_tool_start(function_name) # <--- ADD THIS
            try:
                result = self._invoke_tool(function_name, function_args, effective_task_id)
                waifu_hook.on_tool_success() # <--- ADD THIS
            except Exception as tool_error:
                waifu_hook.on_tool_error(str(tool_error)) # <--- ADD THIS
                result = f"Error executing tool '{function_name}': {tool_error}"
```

**3. Sequential Tool Execution**
Find `def _execute_tool_calls_sequential(self, ...)` and add the start hook:
```python
            function_name = tool_call.function.name
            waifu_hook.on_tool_start(function_name) # <--- ADD THIS
```
Then, search down slightly for where the `tool_msg` is appended, and add the success hook:
```python
            messages.append(tool_msg)
            waifu_hook.on_tool_success() # <--- ADD THIS
```

---
