# pandabreath-klipper

Klipper extras module for the **BIQU Panda Breath** smart chamber heater and air filter. Primary target: **Snapmaker U1**.

---

## What is this?

The [BIQU Panda Breath](https://biqu.equipment/products/biqu-panda-breath-smart-air-filtration-and-heating-system-with-precise-temperature-regulation) is a 300W PTC chamber heater and HEPA/carbon air filter with WiFi control, designed for enclosed 3D printers. It has native Bambu Lab integration but no Klipper support.

This project reverse-engineers its WebSocket API and wraps it in a standard Klipper `extras/` module, exposing the Panda Breath as a `heater_generic` — no custom GCodes, no special macros. Orca Slicer and other tools already know how to set chamber temperature via `SET_HEATER_TEMPERATURE`; this module makes that work.

---

## Status

**Research and protocol documentation phase.** The WebSocket protocol has been reverse-engineered from firmware binaries and a full flash dump. The Klipper module is not yet written.

- [x] Protocol reverse-engineered from firmware strings (v1.0.1, v1.0.2) and embedded JS (v0.0.0 full flash dump)
- [x] Hardware schematic analyzed (ESP32-C3, relay heater, TRIAC fan, NTC thermistors)
- [x] Protocol documented: [docs/protocol.md](docs/protocol.md)
- [ ] Klipper extras module (`panda_breath.py`)
- [ ] Standalone WebSocket test tool (`test_ws.py`)
- [ ] Installation guide for Snapmaker U1 (`docs/klipper_install.md`)

---

## Integration approach

The module will:

1. Maintain a persistent WebSocket connection to the device at `ws://<ip>/ws`
2. Set `work_mode: 2` (always-on) — the device's native auto mode requires a Bambu MQTT connection, which doesn't exist in a Klipper environment
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

## Protocol summary

The device speaks JSON over WebSocket. All messages use a root key identifying the subsystem:

```json
{ "settings": { "work_on": true, "work_mode": 2 } }
{ "settings": { "warehouse_temper": 38.5 } }
```

See [docs/protocol.md](docs/protocol.md) for the full reference.

> No official API documentation exists from BTT. All protocol knowledge is derived from reverse engineering. See [research/](research/) for methodology and raw findings.

---

## Target platform: Snapmaker U1

The Snapmaker U1 runs a modified Klipper + Moonraker stack. The BIQU Panda Breath is officially listed as U1-compatible. The U1 has no built-in active chamber heater — the Panda Breath fills that gap, and this module makes it scriptable.

- Klipper extras path on U1: `/home/lava/klipper/klippy/extras/`
- Community extended firmware (SSH access, opkg): [snapmakeru1-extended-firmware.pages.dev](https://snapmakeru1-extended-firmware.pages.dev)

---

## Research

| File | Contents |
|---|---|
| [research/firmware-analysis.md](research/firmware-analysis.md) | Binary metadata, strings extraction, RTOS tasks, HTTP endpoints, v1.0.1→v1.0.2 diff |
| [research/protocol-from-v0.0.0.md](research/protocol-from-v0.0.0.md) | Definitive protocol reference extracted from embedded JS in v0.0.0 full flash dump |
| [research/hardware-schematic.md](research/hardware-schematic.md) | Schematic analysis: GPIO map, heater/fan circuits, thermistor circuits, power chain |

---

## Device notes

- Firmware V0.0.0 (Aug 2025) is the only confirmed stable release; V1.0.1+ have thermal regression bugs
- WebSocket has no authentication — LAN use only
- Button/UI state changes do **not** push WebSocket messages (confirmed v0.0.0)
- No confirmed state-query command; temperature arrives periodically from the device's internal `temp_task`

---

## License

This project (Klipper module and documentation) is MIT licensed.

The BIQU Panda Breath hardware and firmware are © 2025 BIQU, licensed CC-BY-NC-ND-4.0.
