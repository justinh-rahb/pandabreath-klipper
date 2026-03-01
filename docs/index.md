# pandabreath-klipper

Klipper extras module for the **BIQU Panda Breath** smart chamber heater and air filter.
Primary target: **Snapmaker U1**.

!!! tip "Status: Module implemented — hardware testing in progress"
    `panda_breath.py` is written and ready to deploy. The module supports both stock OEM firmware (WebSocket) and ESPHome firmware (MQTT) with no external Python dependencies — just copy the file and restart Klipper.

---

## What is this?

The [BIQU Panda Breath](https://biqu.equipment/products/biqu-panda-breath-smart-air-filtration-and-heating-system-with-precise-temperature-regulation) is a 300W PTC chamber heater and HEPA/carbon air filter with WiFi control, designed for enclosed 3D printers. It integrates natively with Bambu Lab printers but has **no Klipper support**.

This project provides a Klipper `extras/` module that exposes the Panda Breath as a standard `heater_generic`. No custom GCodes, no special macros — Orca Slicer and other tools already know how to set chamber temperature via `SET_HEATER_TEMPERATURE`, and this module makes that work.

Two firmware paths are supported:

| Path | Device firmware | Transport | Notes |
|---|---|---|---|
| **Stock** | OEM v0.0.0 | WebSocket JSON | Minimal risk; keep original firmware |
| **ESPHome** | ESPHome (reflash) | MQTT | Better reliability; restores thermal runaway protection |

From Klipper's perspective both paths are identical — same `printer.cfg` block, same GCode interface.

---

## Progress

- [x] Protocol reverse-engineered from firmware strings (v1.0.1, v1.0.2) and embedded JS (v0.0.0 full flash dump)
- [x] Hardware schematic analyzed (ESP32-C3, relay heater, TRIAC fan, NTC thermistors)
- [x] Protocol documented — see [Protocol](protocol.md)
- [x] Klipper extras module (`panda_breath.py`) — stock WebSocket + ESPHome MQTT, stdlib only
- [x] ESPHome configuration (`esphome/panda_breath.yaml`) — GPIO verification pending on hardware
- [ ] Standalone WebSocket test tool (`test_ws.py`)
- [ ] Hardware validation on Snapmaker U1
- [ ] ESPHome GPIO pin mapping verified on real hardware

---

## Quick start

=== "Stock firmware (OEM v0.0.0)"

    ```ini
    [panda_breath]
    firmware: stock
    host: PandaBreath.local   # or IP address
    port: 80
    ```

=== "ESPHome firmware"

    ```ini
    [panda_breath]
    firmware: esphome
    mqtt_broker: 192.168.1.x
    mqtt_port: 1883
    mqtt_topic_prefix: panda-breath
    ```

Copy `panda_breath.py` to `/home/lava/klipper/klippy/extras/` and restart Klipper. No other install steps — the module uses Python standard library only.

See [Install on U1](klipper/install.md) for the full procedure.

---

## Target platform: Snapmaker U1

The Snapmaker U1 runs a modified Klipper + Moonraker stack. The BIQU Panda Breath is officially listed as U1-compatible. The U1 has no built-in active chamber heater — the Panda Breath fills that gap, and this module makes it scriptable.

- Klipper extras path on U1: `/home/lava/klipper/klippy/extras/`
- Community extended firmware: [snapmakeru1-extended-firmware.pages.dev](https://snapmakeru1-extended-firmware.pages.dev)

---

## Quick links

| Topic | Page |
|---|---|
| Klipper module architecture | [Klipper Integration](klipper/index.md) |
| Install on Snapmaker U1 | [Install on U1](klipper/install.md) |
| `printer.cfg` reference | [printer.cfg Reference](klipper/printer-cfg.md) |
| ESPHome firmware (reflash alternative) | [ESPHome](esphome/index.md) |
| WebSocket API reference | [Protocol](protocol.md) |
| Hardware schematic analysis | [Hardware](hardware.md) |
| Firmware binary analysis | [Firmware](firmware.md) |
| How the protocol was reverse-engineered | [Research Methodology](research/methodology.md) |

---

## Device notes

- Firmware V0.0.0 (Aug 2025) is the only confirmed stable OEM release; V1.0.1+ have thermal regression bugs — see [Firmware](firmware.md)
- V1.0.2 silently removed PTC thermal runaway detection — the ESPHome path restores this
- WebSocket has no authentication — LAN use only
- Button/UI state changes do **not** push WebSocket messages (confirmed v0.0.0)
- No confirmed state-query command; temperature arrives periodically from the device's internal `temp_task`

---

*All protocol knowledge is derived from reverse engineering. No official API documentation exists from BTT. See [Research Methodology](research/methodology.md) for full provenance.*
