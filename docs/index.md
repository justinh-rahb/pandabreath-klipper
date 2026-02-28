# pandabreath-klipper

Klipper extras module for the **BIQU Panda Breath** smart chamber heater and air filter.
Primary target: **Snapmaker U1**.

!!! note "Status: Research & Planning Phase"
    The WebSocket protocol has been fully reverse-engineered from firmware binaries and a v0.0.0 flash dump. The Klipper module is not yet written. All documentation here reflects confirmed research findings unless marked **unverified**.

---

## What is this?

The [BIQU Panda Breath](https://biqu.equipment/products/biqu-panda-breath-smart-air-filtration-and-heating-system-with-precise-temperature-regulation) is a 300W PTC chamber heater and HEPA/carbon air filter with WiFi control, designed for enclosed 3D printers. It integrates natively with Bambu Lab printers but has **no Klipper support**.

This project reverse-engineers its WebSocket API and wraps it in a standard Klipper `extras/` module, exposing the Panda Breath as a `heater_generic`. No custom GCodes, no special macros — Orca Slicer and other tools already know how to set chamber temperature via `SET_HEATER_TEMPERATURE`, and this module makes that work.

---

## Progress

- [x] Protocol reverse-engineered from firmware strings (v1.0.1, v1.0.2) and embedded JS (v0.0.0 full flash dump)
- [x] Hardware schematic analyzed (ESP32-C3, relay heater, TRIAC fan, NTC thermistors)
- [x] Protocol documented — see [Protocol](protocol.md)
- [ ] Klipper extras module (`panda_breath.py`)
- [ ] Standalone WebSocket test tool (`test_ws.py`)
- [ ] Installation guide for Snapmaker U1

---

## Integration approach

The module will:

1. Maintain a persistent WebSocket connection to the device at `ws://<ip>/ws`
2. Use `work_mode: 2` (always-on) — the device's native auto mode requires a Bambu MQTT connection, which doesn't exist in a Klipper environment
3. Send `work_on: true` when Klipper sets a non-zero target temperature; `work_on: false` when target is 0
4. Report `cal_warehouse_temp` (calibrated NTC ADC reading) as the current temperature
5. Reconnect automatically on connection drop

The device handles all heater duty-cycling and fan speed control internally. The module only tells it to be on or off.

### `printer.cfg` (planned)

```ini
[panda_breath]
host: PandaBreath.local   # or IP address
port: 80
```

---

## Target platform: Snapmaker U1

The Snapmaker U1 runs a modified Klipper + Moonraker stack. The BIQU Panda Breath is officially listed as U1-compatible. The U1 has no built-in active chamber heater — the Panda Breath fills that gap, and this module makes it scriptable.

- Klipper extras path on U1: `/home/lava/klipper/klippy/extras/`
- Community extended firmware: [snapmakeru1-extended-firmware.pages.dev](https://snapmakeru1-extended-firmware.pages.dev)

---

## Quick links

| Topic | Page |
|---|---|
| WebSocket API reference | [Protocol](protocol.md) |
| Hardware schematic analysis | [Hardware](hardware.md) |
| Firmware binary analysis | [Firmware](firmware.md) |
| Klipper module architecture | [Klipper Integration](klipper/index.md) |
| How the protocol was reverse-engineered | [Research Methodology](research/methodology.md) |

---

## Device notes

- Firmware V0.0.0 (Aug 2025) is the only confirmed stable release; V1.0.1+ have thermal regression bugs — see [Firmware](firmware.md)
- WebSocket has no authentication — LAN use only
- Button/UI state changes do **not** push WebSocket messages (confirmed v0.0.0)
- No confirmed state-query command; temperature arrives periodically from the device's internal `temp_task`

---

*All protocol knowledge is derived from reverse engineering. No official API documentation exists from BTT. See [Research Methodology](research/methodology.md) for full provenance.*
