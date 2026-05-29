#!/usr/bin/env python3
import sys
import json
import logging
import time

try:
    from panda_breath import _WebSocketTransport
except ImportError:
    print("Error: Could not import panda_breath. Make sure test_ws.py is in the same directory as panda_breath.py.")
    sys.exit(1)

# Only show warnings from the transport module to keep standard output clean
logging.basicConfig(level=logging.WARNING)

def on_message(data):
    pass

def on_disconnect():
    print("\n--- Disconnected from device ---")

def main():
    host = sys.argv[1] if len(sys.argv) > 1 else 'PandaBreath.local'
    print(f"Connecting to ws://{host}/ws ...")

    transport = _WebSocketTransport(host, 80, on_message, on_disconnect)

    # Monkey patch dispatch to see raw incoming messages
    orig_dispatch = transport._dispatch
    def debug_dispatch(payload):
        print(f"\n[DEVICE -> CLIENT] {payload.decode('utf-8', errors='replace')}")
        return orig_dispatch(payload)
    transport._dispatch = debug_dispatch

    transport.start()

    print("\nInstructions:")
    print("Type a JSON body to send as settings. Example: {\"work_on\": true}")
    print("Device state should automatically print when pushed.")
    print("Type 'q' to quit or 'help' for examples.")

    try:
        while True:
            cmd = input("\n[CLIENT -> DEVICE] settings: ").strip()
            if cmd.lower() == 'q':
                break
            elif cmd.lower() == 'help':
                print("Examples:")
                print("  Turn ON:   {\"work_on\": true}")
                print("  Turn OFF:  {\"work_on\": false}")
                print("  Mode Auto: {\"work_mode\": 1}")
                print("  Mode ALON: {\"work_mode\": 2}")
                print("  Target 45: {\"set_temp\": 45, \"target_temp\": 45}")
                print("  Stop dry:  {\"isrunning\": 0, \"drying_running\": false}")
                continue
            
            if cmd:
                try:
                    parsed = json.loads(cmd)
                    transport._send_settings(parsed)
                    print(f"Sent settings via WebSocket: {parsed}")
                except json.JSONDecodeError:
                    print("Invalid JSON.")
    except KeyboardInterrupt:
        pass
    finally:
        transport.stop()

if __name__ == "__main__":
    main()
