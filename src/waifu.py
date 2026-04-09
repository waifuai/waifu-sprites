#!/usr/bin/env python3
"""
Waifu AI Integration Wrapper for Hermes Agent
=============================================
This script acts as a non-destructive wrapper for the Hermes CLI.
It patches the original modules at runtime to inject Waifu AI visual/voice hooks.

Usage:
    python waifu.py [args]
"""

import sys
import os
import threading

# --- 1. Environment Setup ---
# Ensure we can import modules from the hermes-agent directory
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# --- 2. Import Hermes CLI and Waifu Hooks ---
try:
    import cli
    import waifu_hook
except ImportError as e:
    print(f"[!] Error: Could not import required modules: {e}")
    sys.exit(1)

# --- 3. Define Patched Methods ---

# Save original methods for delegation
original_init_agent = cli.HermesCLI._init_agent
original_chat = cli.HermesCLI.chat


def patched_init_agent(
    self, model_override=None, runtime_override=None, route_label=None
):
    """
    Interpose agent initialization to inject lifecycle callbacks.
    """
    # 1. Call the original initialization (creates self.agent)
    result = original_init_agent(
        self,
        model_override=model_override,
        runtime_override=runtime_override,
        route_label=route_label,
    )

    # 2. If agent was initialized, wrap its callbacks
    if self.agent is not None:
        # Wrap tool_start_callback
        orig_start = self.agent.tool_start_callback

        def wrapped_tool_start(tool_call_id, function_name, function_args):
            waifu_hook.on_tool_start(tool_call_id, function_name, function_args)
            if orig_start:
                orig_start(tool_call_id, function_name, function_args)

        # Wrap tool_complete_callback
        orig_complete = self.agent.tool_complete_callback

        def wrapped_tool_complete(
            tool_call_id, function_name, function_args, function_result
        ):
            waifu_hook.on_tool_complete(
                tool_call_id, function_name, function_args, function_result
            )
            if orig_complete:
                orig_complete(
                    tool_call_id, function_name, function_args, function_result
                )

        self.agent.tool_start_callback = wrapped_tool_start
        self.agent.tool_complete_callback = wrapped_tool_complete

        # thinking_callback is usually None in CLI, so we can just set it
        self.agent.thinking_callback = waifu_hook.on_user_input_received

    return result


def patched_chat(self, message, images=None):
    """
    Interpose the main chat loop to trigger high-level states.
    """
    # 1. User sent message -> Thinking
    waifu_hook.on_user_input_received()

    # 2. Indicate transition to speaking/generating
    waifu_hook.on_agent_speaking()

    # 3. Call original chat logic
    response = original_chat(self, message, images)

    # 4. Detect emotion from response and set sprite
    if response:
        emotion = waifu_hook.detect_emotion(response)
        waifu_hook.set_waifu_state(emotion)
    else:
        waifu_hook.on_agent_idle()

    # 5. TTS in background thread
    if response:
        threading.Thread(
            target=waifu_hook.on_agent_reply, args=(response,), daemon=True
        ).start()

    return response


# --- 4. Apply Monkey Patches ---
cli.HermesCLI._init_agent = patched_init_agent
cli.HermesCLI.chat = patched_chat


# --- 5. Execution ---
if __name__ == "__main__":
    # Delegates to the original cli.main()
    # cli.main uses fire.Fire(HermesCLI)
    cli.main()
