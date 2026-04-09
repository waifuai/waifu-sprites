#!/usr/bin/env python3
"""
waifu.py — Reference integration example for waifu-sprites
===========================================================
This is a REFERENCE IMPLEMENTATION showing how to hook waifu-sprites
into a CLI-based AI agent using Python monkey-patching.

This specific version targets hermes-agent (https://github.com/nousresearch/hermes-agent).
Adapt the class names and method signatures for your own agent framework.

The pattern:
  1. Import your agent's CLI module
  2. Save original methods
  3. Wrap them with waifu_hook calls
  4. Monkey-patch the class
  5. Delegate to original CLI main()

Usage:
    cd ~/.hermes/hermes-agent
    python /path/to/waifu.py

Or create a launcher script:
    cd ~/.hermes/hermes-agent && venv/bin/python3 /path/to/waifu.py
"""

import sys
import os
import threading

# Add the directory containing waifu_hook.py to the path.
# If waifu_hook.py is in the same directory as this file:
HOOK_DIR = os.path.abspath(os.path.dirname(__file__))
if HOOK_DIR not in sys.path:
    sys.path.insert(0, HOOK_DIR)

# If your agent's modules are in a different directory, add that too:
# AGENT_DIR = os.path.expanduser("~/.hermes/hermes-agent")
# if AGENT_DIR not in sys.path:
#     sys.path.insert(0, AGENT_DIR)

import waifu_hook


# =============================================================================
# STEP 1: Import your agent's CLI module
# =============================================================================
# Replace this with whatever your agent framework uses.
# For hermes-agent, it's `cli` (the module containing HermesCLI class).

try:
    import cli  # hermes-agent specific
except ImportError as e:
    print(f"[waifu] Error: Could not import agent CLI module: {e}")
    print("[waifu] Make sure you're running from the agent's directory.")
    sys.exit(1)


# =============================================================================
# STEP 2: Save original methods
# =============================================================================
# We'll wrap these to inject waifu hooks without modifying source code.

original_init_agent = cli.HermesCLI._init_agent
original_chat = cli.HermesCLI.chat


# =============================================================================
# STEP 3: Define patched methods
# =============================================================================

def patched_init_agent(self, model_override=None, runtime_override=None, route_label=None):
    """Wrap agent initialization to inject tool lifecycle callbacks."""
    result = original_init_agent(self, model_override=model_override,
                                  runtime_override=runtime_override,
                                  route_label=route_label)

    if self.agent is not None:
        # Wrap tool callbacks
        orig_start = self.agent.tool_start_callback
        orig_complete = self.agent.tool_complete_callback

        def wrapped_tool_start(tool_call_id, function_name, function_args):
            waifu_hook.on_tool_start(tool_call_id, function_name, function_args)
            if orig_start:
                orig_start(tool_call_id, function_name, function_args)

        def wrapped_tool_complete(tool_call_id, function_name, function_args, function_result):
            waifu_hook.on_tool_complete(tool_call_id, function_name, function_args, function_result)
            if orig_complete:
                orig_complete(tool_call_id, function_name, function_args, function_result)

        self.agent.tool_start_callback = wrapped_tool_start
        self.agent.tool_complete_callback = wrapped_tool_complete
        self.agent.thinking_callback = waifu_hook.on_user_input_received

    return result


def patched_chat(self, message, images=None):
    """Wrap the main chat loop for high-level visual states + TTS."""
    # User sent message
    waifu_hook.on_user_input_received()
    waifu_hook.on_agent_speaking()

    # Run original chat
    response = original_chat(self, message, images)

    # Update emotion based on response
    if response:
        emotion = waifu_hook.detect_emotion(response)
        waifu_hook.set_waifu_state(emotion)
        # TTS in background thread
        threading.Thread(
            target=waifu_hook.on_agent_reply, args=(response,), daemon=True
        ).start()
    else:
        waifu_hook.on_agent_idle()

    return response


# =============================================================================
# STEP 4: Apply monkey patches
# =============================================================================

cli.HermesCLI._init_agent = patched_init_agent
cli.HermesCLI.chat = patched_chat


# =============================================================================
# STEP 5: Launch
# =============================================================================

if __name__ == "__main__":
    # Delegates to the original CLI entry point.
    # For hermes-agent, cli.main() uses fire.Fire(HermesCLI).
    cli.main()
