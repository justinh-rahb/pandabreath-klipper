# Klipper Integration

## Overview

The Panda Breath has no native Klipper support. This module bridges the gap by exposing the device to Klipper as a standard `heater_generic` — the same interface used by any other chamber heater.

No custom GCode commands are added. Orca Slicer, SuperSlicer, and Klipper macros already know how to interact with a `heater_generic` via `SET_HEATER_TEMPERATURE`. The module just makes that work with the Panda Breath.

---

## Architecture

`panda_breath.py` is a single Klipper `extras/` file with **no external Python dependencies** — it uses only the standard library. A transport abstraction supports two firmware paths:

```
PandaBreath  (Klipper heater_generic interface)
    ├── get_temp() / set_temp() / check_busy()   ← identical either way
    └── transport ──┬── WebSocketTransport        firmware: stock
                    └── MqttTransport             firmware: esphome
```

Both transports run a background I/O thread that pushes state into a thread-safe queue. A Klipper reactor timer drains that queue once per second and updates the module's temperature state. This pattern keeps all Klipper state manipulation on the reactor thread while allowing blocking network I/O on the background thread.

### What it does

1. **Instantiates the appropriate transport** based on the `firmware:` config key
2. **Maintains a persistent connection**, reconnecting automatically on any error
3. **Reports current temperature** — stock: prefers `cal_warehouse_temp` (ADC-calibrated) over `warehouse_temper` (raw); ESPHome: reads from the MQTT climate sensor topic
4. **Implements the standard Klipper heater interface** — `set_temp()`, `get_temp()`, `check_busy()`
5. **Enables the device** when Klipper sets a non-zero target; **disables it** when target is 0
6. **Resends the last command on reconnect** so the device is always in sync after a connection drop

### What it does NOT do

- No `PANDA_BREATH_*` GCode commands
- No mode-switching (filament drying, auto mode) via GCode
- No custom macros in the module itself — use standard Klipper macros instead

---

## Why Always-On Mode (stock firmware)

The Panda Breath has three operating modes:

| Mode | Description | Works with Klipper? |
|---|---|---|
| `1` Auto | Turns on when bed temp crosses a threshold — reads `bed_temper` from Bambu MQTT | **No** — requires Bambu MQTT |
| `2` Always On | Heater runs while `work_on: true` | **Yes** |
| `3` Filament Drying | Timed run at a target temp | **Yes**, via commands |

The device's auto mode reads bed temperature from a Bambu Lab printer via MQTT over TLS — a protocol not available on Klipper. The module therefore uses `work_mode: 2` (always-on) and Klipper becomes the authority on when to turn the device on or off.

---

## State Management

There is no confirmed "get state" command on the stock WebSocket API. The module tracks its own sent state rather than querying the device:

- Temperature readings arrive periodically from the device's `temp_task` — no polling needed
- When the connection drops and reconnects, the module resends its last desired state
- Physical button presses on the device do **not** generate WebSocket messages (confirmed v0.0.0), so the module cannot detect out-of-band changes

This means Klipper is the single source of truth for desired state, which is appropriate — the slicer or macros set the target, Klipper tracks it.

---

## Python dependencies — none

The module is implemented entirely in Python standard library:

| Transport | Libraries used |
|---|---|
| Stock WebSocket | `socket`, `hashlib`, `base64`, `struct`, `json`, `os` |
| ESPHome MQTT | `socket`, `struct`, `json` |
| Shared | `threading`, `collections`, `time`, `logging` |

No `pip install`, no `opkg install`, no firmware overlay packages. Drop the file in and restart Klipper.

---

## Choosing a firmware path

| Consideration | Stock (v0.0.0) | ESPHome |
|---|---|---|
| Device risk | None — keep OEM firmware | Reflash required; recovery via flash dump |
| Thermal runaway protection | Present in v0.0.0; removed in v1.0.2 | Configurable in ESPHome YAML |
| Fan speed control | Device manages internally | Configurable via ESPHome |
| Klipper install complexity | Drop file, done | Drop file + MQTT broker |
| GPIO verification needed | No | Yes — 3 pins unconfirmed |

See [ESPHome](../esphome/index.md) for the full ESPHome path documentation.
