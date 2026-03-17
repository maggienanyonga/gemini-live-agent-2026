#!/usr/bin/env python3
"""
Circuit Stitcher — Local Execution Client

Connects to the backend /exec-ws WebSocket and translates action events
from Gemini into real mouse/keyboard actions via PyAutoGUI.

Install:  pip install pyautogui websockets
Run:      python client.py
          python client.py ws://localhost:8080   # custom URL
"""
import asyncio
import json
import sys
import time

try:
    import pyautogui
except ImportError:
    print("ERROR: pyautogui not installed. Run: pip install pyautogui websockets")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. Run: pip install pyautogui websockets")
    sys.exit(1)

BACKEND_URL = (sys.argv[1].rstrip("/") + "/exec-ws") if len(sys.argv) > 1 else "ws://localhost:8080/exec-ws"

pyautogui.FAILSAFE = True   # emergency stop: move mouse to top-left corner
pyautogui.PAUSE    = 0.08   # small pause between calls


def _i(action, key, default=0):
    try:
        return int(float(action.get(key, default)))
    except (TypeError, ValueError):
        return default


def _f(action, key, default=0.5):
    try:
        return float(action.get(key, default))
    except (TypeError, ValueError):
        return default


def execute(action: dict) -> str | None:
    """Execute one action. Returns error string or None on success."""
    cmd = action.get("command", "")
    print(f"  → {cmd} {dict((k,v) for k,v in action.items() if k != 'command')}", flush=True)
    try:
        if cmd == "CLICK":
            pyautogui.click(_i(action, "x"), _i(action, "y"))
        elif cmd == "DOUBLE_CLICK":
            pyautogui.doubleClick(_i(action, "x"), _i(action, "y"))
        elif cmd == "RIGHT_CLICK":
            pyautogui.rightClick(_i(action, "x"), _i(action, "y"))
        elif cmd == "MOVE":
            pyautogui.moveTo(_i(action, "x"), _i(action, "y"), duration=0.3)
        elif cmd == "DRAG":
            fx, fy = _i(action, "from_x"), _i(action, "from_y")
            tx, ty = _i(action, "to_x"),   _i(action, "to_y")
            dur    = _f(action, "duration", 0.8)
            pyautogui.moveTo(fx, fy, duration=0.25)
            time.sleep(0.05)
            pyautogui.dragTo(tx, ty, duration=dur, button="left")
        elif cmd == "TYPE":
            text = action.get("text", "")
            pyautogui.write(str(text), interval=0.05)
        elif cmd == "KEY":
            key = str(action.get("key", "")).strip()
            if "+" in key:
                pyautogui.hotkey(*[k.strip() for k in key.split("+")])
            else:
                pyautogui.press(key)
        elif cmd == "SCROLL":
            pyautogui.scroll(_i(action, "amount", -3),
                             x=_i(action, "x"), y=_i(action, "y"))
        elif cmd in ("CLICK_SAVE", "REROUTE"):
            pass  # handled browser-side
        else:
            return f"Unknown command: {cmd}"
        return None
    except pyautogui.FailSafeException:
        return "FAILSAFE triggered — mouse moved to corner"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


async def run():
    print(f"Circuit Stitcher Execution Client", flush=True)
    print(f"Connecting to {BACKEND_URL} …", flush=True)
    while True:
        try:
            async with websockets.connect(BACKEND_URL, ping_interval=20) as ws:
                print("✓ Connected. Waiting for actions…", flush=True)
                await ws.send(json.dumps({"type": "hello", "client": "pyautogui"}))
                async for raw in ws:
                    msg = json.loads(raw)
                    t = msg.get("type")
                    if t == "action":
                        print(f"[ACTION] {msg.get('command')}", flush=True)
                        err = execute(msg)
                        status = "error" if err else "ok"
                        await ws.send(json.dumps({
                            "type": "ack",
                            "command": msg.get("command"),
                            "status": status,
                            "error": err or "",
                        }))
                        if err:
                            print(f"  ERROR: {err}", flush=True)
                    elif t == "status":
                        print(f"[STATUS] {msg.get('message', '')}", flush=True)
        except (websockets.ConnectionClosed, OSError, ConnectionRefusedError) as e:
            print(f"Disconnected ({e}) — retrying in 3s…", flush=True)
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(run())
