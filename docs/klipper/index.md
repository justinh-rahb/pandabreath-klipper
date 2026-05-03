# Klipper Integration

## Overview

The Panda Breath has no native Klipper support. `panda_breath.py` bridges that gap by giving Klipper a custom sensor type and a virtual heater pin so you can wire the device into a normal `[heater_generic panda_breath]`.

The default integration path is standard Klipper heater control via `SET_HEATER_TEMPERATURE`. For stock OEM firmware, the module also exposes optional passthrough commands for the device's native auto and drying modes.

---

## Architecture

`panda_breath.py` is a single Klipper `extras/` file with **no external Python dependencies**. A transport abstraction supports two firmware paths:

```
[heater_generic panda_breath]
    ├── heater_pin: panda_breath:pwm
    ├── sensor_type: panda_breath
    └── panda_breath.py
        └── transport ──┬── WebSocketTransport    firmware: stock
                        └── MqttTransport         firmware: esphome
```

Both transports run a background I/O thread that pushes state into a thread-safe queue. A Klipper reactor timer drains that queue once per second and updates the module's temperature state. This pattern keeps all Klipper state manipulation on the reactor thread while allowing blocking network I/O on the background thread.

### What it does

1. **Registers a sensor factory** for `sensor_type: panda_breath`
2. **Registers a virtual chip** for `heater_pin: panda_breath:pwm`
3. **Instantiates the appropriate transport** from the `firmware:` config key
4. **Maintains a persistent connection**, reconnecting automatically on any error
5. **Reports current temperature** — stock prefers `cal_warehouse_temp`; ESPHome uses the MQTT temperature topic
6. **Hooks the matching `heater_generic panda_breath`** so Klipper target changes are mirrored to the device
7. **Forces the device off** on Klipper connect, disconnect, and shutdown
8. **Resends the last desired state** after reconnect

### Optional stock-only commands

When `firmware: stock` is used, the module also registers:

- `PANDA_BREATH_AUTO`
- `PANDA_BREATH_DRY_START`
- `PANDA_BREATH_DRY_STOP`

These are raw device-mode controls intended for advanced macros and downstream integrations. They are not required for the normal `heater_generic` path.

### What it does NOT do

- It does not create the `[heater_generic]` section for you
- It does not provision WiFi, MQTT, or printer binding
- It does not ship opinionated `M141` / `M191` macros in the module itself

---

## Why `work_mode: 2` is still the baseline stock path

The Panda Breath has three operating modes:

| Mode | Description | Works with Klipper? |
|---|---|---|
| `1` Auto | Device-native automatic mode | Exposed as an optional stock-only passthrough |
| `2` Always On | Heater runs while `work_on: true` | **Yes** |
| `3` Filament Drying | Timed run at a target temp | Exposed as an optional stock-only passthrough |

For broad compatibility, the module's standard heater path uses `work_mode: 2`, where Klipper is the source of truth for target temperature and on/off state. The stock transport can also pass through native OEM auto/drying settings when a user or downstream integration explicitly opts into them.

---

## State Management

There is no confirmed "get state" command on the stock WebSocket API. The module tracks its own sent state rather than querying the device:

- Temperature readings arrive periodically from the device's `temp_task` — no polling needed
- When the connection drops and reconnects, the module resends its last desired state
- Physical button presses on the device do **not** generate WebSocket messages (confirmed v0.0.0), so the module cannot detect out-of-band changes

This means Klipper remains the single source of truth for the standard heater target, while optional OEM native modes are treated as explicit advanced commands.

---

## Python dependencies — none

The module is implemented entirely in Python standard library:

| Transport | Libraries used |
|---|---|
| Stock WebSocket | `socket`, `hashlib`, `base64`, `struct`, `json`, `os` |
| ESPHome MQTT | `socket`, `struct`, `json` |
| Shared | `threading`, `collections`, `time`, `logging` |

No `pip install`, no separate Python package, and no bundled service layer. Drop the file in and restart Klipper.

---

## Choosing a firmware path

| Consideration | Stock (v0.0.0) | ESPHome |
|---|---|---|
| Device risk | None — keep OEM firmware | Reflash required; recovery via flash dump |
| Thermal runaway protection | Present in v0.0.0; removed in v1.0.2 | Configurable in ESPHome YAML |
| Fan speed control | Device manages internally | Configurable via ESPHome |
| Klipper install complexity | Drop file + `printer.cfg` sections | Drop file + MQTT broker + `printer.cfg` sections |
| GPIO verification needed | No | Yes — 3 pins unconfirmed |

See [ESPHome](../esphome/index.md) for the full ESPHome path documentation.
