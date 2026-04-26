import subprocess
import os
import requests
import time
import random
import json





# --- Configuration ---
# Use 127.0.0.1 since node server runs in WSL (same machine)
WAIFU_URL = "http://127.0.0.1:8000/state"





# --- Sprite Usage Tracking ---
# Tracks total duration and call count per state.
# Duration is measured from when a state starts until the next state change.

_sprite_stats = {}       # {state: {"calls": int, "total_ms": float}}
_active_state = None     # Currently displayed state
_active_start = None     # time.monotonic() when it started
STATS_FILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "sprite_stats.json")

_STATE_NAMES = {
    "e1": "happy", "e2": "amused", "e3": "empathetic", "e4": "curious",
    "e5": "confused", "e6": "surprised", "e7": "embarrassed", "e8": "confident",
    "e9": "annoyed", "e10": "overwhelmed", "e11": "determined", "e12": "affectionate",
}

def _state_label(state: str) -> str:
    """Convert state code to human-readable label."""
    return _STATE_NAMES.get(state, state)


def _record_duration():
    """Record elapsed time for the currently active state."""
    global _active_state, _active_start
    if _active_state is not None and _active_start is not None:
        elapsed_ms = round((time.monotonic() - _active_start) * 1000)
        label = _state_label(_active_state)
        if label not in _sprite_stats:
            _sprite_stats[label] = {"calls": 0, "total_ms": 0}
        _sprite_stats[label]["calls"] += 1
        _sprite_stats[label]["total_ms"] += elapsed_ms
        _save_stats()


def _save_stats():
    """Persist tracking data to JSON file."""
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(_sprite_stats, f, indent=2)
    except Exception:
        pass


def get_sprite_stats() -> dict:
    """Get current tracking data (hook-side: requested states)."""
    return dict(_sprite_stats)


def get_display_stats() -> dict:
    """Get display tracking data from the UI server (what was actually shown)."""
    try:
        r = requests.get(f"{WAIFU_URL}/display_stats", timeout=0.5)
        return r.json()
    except Exception:
        return {"stats": {}, "set": ""}


def _track_emotion(emotion: str):
    """Track an emotion state sent directly (bypassing set_waifu_state)."""
    global _active_state, _active_start
    _record_duration()
    _active_state = emotion
    _active_start = time.monotonic()


def set_waifu_state(state: str):
    """Set the agent's visual state in the Waifu Sprites UI."""
    global _active_state, _active_start
    try:
        # Track duration of previous state before switching
        _record_duration()
        _active_state = state
        _active_start = time.monotonic()

        payload = {"state": state}
        # Short timeout to avoid blocking the agent if the UI is closed
        requests.post(WAIFU_URL, json=payload, timeout=0.1)
    except requests.exceptions.RequestException:
        pass


# --- Tool → State Mapping ---
# Maps every known tool to its best-matching sprite state.

TOOL_STATES = {
    # File operations → typing (screen work)
    'read_file': 'typing',
    'write_file': 'typing',
    'file_read': 'typing',
    'file_write': 'typing',
    'file_patch': 'typing',
    'file_tools': 'typing',
    'patch': 'typing',
    'search_files': 'typing',

    # Web/research → searching
    'web_search': 'searching',
    'web_extract': 'searching',
    'session_search': 'searching',
    'browser_navigate': 'searching',
    'browser_snapshot': 'searching',
    'browser_vision': 'searching',
    'browser_get_images': 'searching',
    'browser_back': 'searching',

    # Browser interaction → typing
    'browser_click': 'typing',
    'browser_type': 'typing',
    'browser_press': 'typing',
    'browser_scroll': 'typing',

    # Code/math → calculating
    'execute_code': 'calculating',
    'code_execution_tool': 'calculating',
    'browser_console': 'calculating',

    # Terminal/build → fixing
    'terminal': 'fixing',
    'terminal_tool': 'fixing',
    'process': 'fixing',
    'process_registry': 'fixing',

    # Agent coordination → thinking
    'delegate_task': 'thinking',
    'todo': 'thinking',
    'memory': 'thinking',
    'cronjob': 'thinking',
    'skills_list': 'thinking',
    'skill_view': 'thinking',
    'skill_manage': 'thinking',
    'skill_commands': 'thinking',

    # Clarification → alert (asking user)
    'clarify': 'alert',

    # Speech
    'text_to_speech': 'speaking',
    'send_message': 'speaking',
}


def _get_tool_state(function_name: str) -> str:
    """Map a tool function name to the best sprite state."""
    if not function_name:
        return 'typing'
    
    # Direct lookup
    if function_name in TOOL_STATES:
        return TOOL_STATES[function_name]
    
    # Fuzzy matching by keywords in tool name
    name_lower = function_name.lower()
    
    if any(k in name_lower for k in ['search', 'find', 'browse', 'navigate', 'web']):
        return 'searching'
    elif any(k in name_lower for k in ['file', 'read', 'write', 'patch', 'edit']):
        return 'typing'
    elif any(k in name_lower for k in ['code', 'exec', 'run', 'math', 'calcul']):
        return 'calculating'
    elif any(k in name_lower for k in ['terminal', 'shell', 'build', 'install', 'git']):
        return 'fixing'
    elif any(k in name_lower for k in ['delegate', 'skill', 'todo', 'memory', 'cron']):
        return 'thinking'
    elif any(k in name_lower for k in ['speak', 'voice', 'say']):
        return 'speaking'
    else:
        return 'typing'


# --- Emotion Rotation ---



# --- Visual State Hooks ---


def on_user_input_received(*args, **kwargs):
    """Triggered when the user enters a prompt — agent is 'listening'."""
    set_waifu_state("listening")


def on_model_thinking(*args, **kwargs):
    """Triggered when the model is generating (thinking_callback)."""
    set_waifu_state("thinking")


def on_tool_start(tool_call_id=None, function_name=None, function_args=None):
    """Triggered when a tool starts execution."""
    if not function_name:
        return

    # Pick the best action state for this tool (typing, searching, etc.)
    state = _get_tool_state(function_name)
    set_waifu_state(state)


def on_tool_complete(
    tool_call_id=None, function_name=None, function_args=None, function_result=None
):
    """Triggered when a tool completes successfully."""
    # Check result for error signals - not always "success"!
    is_error = False
    if function_result:
        result_str = str(function_result).lower()
        is_error = any(k in result_str for k in [
            'error', 'failed', 'exception', 'traceback', 'not found',
            'denied', 'forbidden', 'unauthorized', 'timeout'
        ])

    if is_error:
        set_waifu_state("error")
    else:
        set_waifu_state("idle")


def on_tool_error(*args, **kwargs):
    """Manual trigger for tool errors."""
    set_waifu_state("error")


# --- Aliases for backward compatibility with older manual patches ---


def on_tool_success(*args, **kwargs):
    """Alias for on_tool_complete."""
    return on_tool_complete(*args, **kwargs)


def on_tool_failure(*args, **kwargs):
    """Alias for on_tool_error."""
    return on_tool_error(*args, **kwargs)


# --- Emotion Detection from Text ---


# Keyword → emotion mapping. Order matters (first match wins).
# Emotions: e1-e12 matching 12-emotion-prompts.txt
#   e1=Happy  e2=Amused  e3=Empathetic  e4=Curious
#   e5=Confused  e6=Surprised  e7=Embarrassed  e8=Confident
#   e9=Annoyed  e10=Overwhelmed  e11=Determined  e12=Affectionate
EMOTION_KEYWORDS = [
    # e12 - Affectionate (check first, compliments are specific)
    (["love", "thank you", "you're sweet", "you're the best", "cutie",
      "heart", "glad i could help", "happy to help", "you're welcome",
      "\u2661", "\u2764"], "e12"),
    # e7 - Embarrassed / Apologetic
    (["sorry", "apolog", "unfortunately", "my bad", "my mistake",
      "oops", "i was wrong", "i made an error", "couldn't find",
      "i can't", "i'm afraid", "i don't have"], "e7"),
    # e10 - Overwhelmed
    (["this is a lot", "so many", "overwhelm", "massive", "huge amount",
      "complex", "complicated"], "e10"),
    # e6 - Surprised
    (["wow", "whoa", "oh!", "amazing!", "incredible!", "no way",
      "fascinating", "that's wild", "didn't expect"], "e6"),
    # e5 - Confused
    (["hmm", "confus", "unclear", "ambiguous", "what do you mean",
      "not sure what", "i'm not sure", "wait", "actually..."], "e5"),
    # e9 - Annoyed
    (["again", "repeatedly", "as i said", "i already", "once more",
      "please don't", "that's not"], "e9"),
    # e4 - Curious
    (["?", "what is", "how does", "tell me more", "interesting",
      "i wonder", "curious", "what if", "could you"], "e4"),
    # e8 - Confident
    (["found it", "here's", "let me show", "perfect", "exactly",
      "nailed", "done!", "easy", "no problem", "absolutely",
      "definitely", "certainly"], "e8"),
    # e11 - Determined
    (["let me", "i'll", "going to", "here's how", "step by step",
      "first,", "here's what we'll do", "working on"], "e11"),
    # e2 - Amused
    (["haha", "lol", "lmao", "funny", "joke", "silly",
      "that's great", "nyaa", "nya~"], "e2"),
    # e3 - Empathetic (sad/comforting)
    (["i understand", "that's tough", "i'm sorry to hear", "it's okay",
      "don't worry", "take your time", "hang in there"], "e3"),
    # e1 - Happy (default for positive responses)
    (["great", "good", "nice", "awesome", "wonderful", "yes!",
      "sounds good", "let's go", "exciting"], "e1"),
]


def detect_emotion(text: str) -> str:
    """Detect the best emotion from response text using keyword matching.
    Returns an emotion state name (e1-e12)."""
    if not text:
        return "e1"
    lower = text.lower()
    for keywords, emotion in EMOTION_KEYWORDS:
        for kw in keywords:
            if kw in lower:
                return emotion
    return "e1"


def on_agent_speaking(*args, **kwargs):
    """Triggered when the agent starts responding."""
    set_waifu_state("speaking")


def on_agent_idle(*args, **kwargs):
    """Triggered when the agent is waiting for input — show sleeping."""
    set_waifu_state("sleeping")



















def _is_terminal_focused():
    """Check if the terminal window is currently in the foreground. Returns True if focused or if check fails."""
    try:
        if "WSL_DISTRO_NAME" not in os.environ:
            return True
        csharp_code = (
            'using System; using System.Runtime.InteropServices; using System.Text;'
            'public class Focus {'
            '[DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();'
            '[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int nMaxCount);'
            '[DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);'
            'public static string GetTitle() {'
            'var h = GetForegroundWindow();'
            'var sb = new StringBuilder(GetWindowTextLength(h) + 1);'
            'GetWindowText(h, sb, sb.Capacity);'
            'return sb.ToString(); }'
            '}'
        )
        ps_cmd = (
            "Add-Type -TypeDefinition '" + csharp_code + "' -Language CSharp; "
            "$t = [Focus]::GetTitle(); "
            "if ($t -match 'Windows Terminal|PowerShell|Command Prompt|pwsh|Waifu Hermes') { 'True' } else { 'False' }"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=3
        )
        return "True" in result.stdout
    except Exception:
        return True  # If check fails, assume focused (no spam)


def _flash_taskbar():
    """Show balloon notification in system tray when Neko-chan replies (only if unfocused)."""
    if _is_terminal_focused():
        return
    try:
        if "WSL_DISTRO_NAME" in os.environ:
            ps_notify = (
                'Add-Type -AssemblyName System.Windows.Forms;'
                '$balloon = New-Object System.Windows.Forms.NotifyIcon;'
                '$balloon.Icon = [System.Drawing.SystemIcons]::Information;'
                '$balloon.Visible = $true;'
                '$balloon.ShowBalloonTip(3000, "Neko-chan", "Reply received nya~",'
                '[System.Windows.Forms.ToolTipIcon]::Info);'
                'Start-Sleep -Seconds 4; $balloon.Dispose()'
            )
            subprocess.Popen(
                ["powershell.exe", "-NoProfile", "-Command", ps_notify],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except Exception:
        pass





def on_agent_reply(text: str):
    """Called when agent reply is ready — flash taskbar notification."""
    try:
        _flash_taskbar()
    except Exception:
        pass
