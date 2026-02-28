# Klipper Integration

## Overview

The Panda Breath has no native Klipper support. This module bridges the gap by speaking the device's WebSocket JSON API and exposing it to Klipper as a standard `heater_generic` — the same interface used by any other chamber heater.

No custom GCode commands are added. Orca Slicer, SuperSlicer, and Klipper macros already know how to interact with a `heater_generic` via `SET_HEATER_TEMPERATURE`. The module just makes that work with the Panda Breath.

---

## Architecture

The module (`panda_breath.py`) is a single Klipper `extras/` file. It:

1. **Maintains a persistent WebSocket connection** to the device at `ws://<host>/ws`, reconnecting automatically on drop
2. **Listens for temperature** — `temp_task` on the device pushes `warehouse_temper` and `cal_warehouse_temp` periodically; no query command needed
3. **Reports current temperature** — prefers `cal_warehouse_temp` (ADC-calibrated) over `warehouse_temper` (raw)
4. **Implements the standard Klipper heater interface** — `set_temp()`, `get_temp()`, `check_busy()`
5. **Enables the device** when Klipper sets a non-zero target temperature: sends `work_mode: 2` (always-on) + `work_on: true`
6. **Disables the device** when target is set to 0: sends `work_on: false`
7. **Uses Klipper's reactor** for I/O (`reactor.register_timer`) — no raw asyncio or threads

### What it does NOT do

- No `PANDA_BREATH_*` GCode commands
- No mode-switching (filament drying, auto mode) via GCode
- No custom macros in the module itself

Filament drying and mode control can be done via standard Klipper macros that call `SET_HEATER_TEMPERATURE`.

---

## Why Always-On Mode

The Panda Breath has three operating modes:

| Mode | Description | Works with Klipper? |
|---|---|---|
| `1` Auto | Turns on when printer bed temp crosses a threshold — reads `bed_temper` from Bambu MQTT | **No** — requires Bambu MQTT |
| `2` Always On | Heater runs while `work_on: true` | **Yes** |
| `3` Filament Drying | Timed run at a target temp | **Yes**, via commands |

The device's auto mode reads bed temperature from a Bambu Lab printer via MQTT over TLS. This protocol is not available on Klipper printers. The module therefore uses `work_mode: 2` (always-on) and Klipper itself becomes the authority on when to turn the heater on or off.

---

## State Management

There is no confirmed "get state" WebSocket command. The module tracks its own sent state rather than querying the device:

- Temperature readings (`cal_warehouse_temp`) arrive periodically from the device's `temp_task` — no polling needed
- When the WebSocket connection drops and reconnects, the module resends its last desired state
- Physical button presses on the device do **not** generate WebSocket messages (confirmed v0.0.0), so the module cannot detect out-of-band changes

This means Klipper is the single source of truth for the desired state. This is appropriate for a Klipper-controlled printer — the slicer or macros set the target, Klipper tracks it.

---

## Key References (for module development)

- `extras/heater_generic.py` — primary pattern to follow
- `extras/temperature_sensor.py` — sensor registration pattern
- Klipper reactor: `self.reactor.register_timer()` for non-blocking I/O
- `extras/webhooks.py` — example of persistent connection management

---

## Python WebSocket Dependency

The module requires the `websocket-client` Python package, which is not included in stock Klipper.

| Environment | Method |
|---|---|
| Production (U1 extended firmware) | Ship as overlay; installed at build time via opkg/entware |
| Development/testing (devel build) | `opkg install python3-websocket` over SSH |

See [Install on U1](install.md) for step-by-step instructions.
