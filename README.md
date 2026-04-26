# pandabreath-klipper

Klipper extras module for the **BIQU Panda Breath** smart chamber heater and air filter. Primary target: **Snapmaker U1**.

---

## What is this?

The [BIQU Panda Breath](https://biqu.equipment/products/biqu-panda-breath-smart-air-filtration-and-heating-system-with-precise-temperature-regulation) is a 300W PTC chamber heater and HEPA/carbon air filter with WiFi control, designed for enclosed 3D printers. It has native Bambu Lab integration but no Klipper support.

This project reverse-engineers its WebSocket API and wraps it in a standard Klipper `extras/` module, exposing the Panda Breath as a `heater_generic`. Orca Slicer and other tools already know how to set chamber temperature via `SET_HEATER_TEMPERATURE`; this module makes that work. For stock firmware, it also exposes optional `PANDA_BREATH_AUTO` and `PANDA_BREATH_DRY_*` commands to configure the device's native modes from Klipper macros.

---

## Status

**Research and protocol documentation phase complete. Klipper integration is functional!**

- [x] Protocol reverse-engineered from firmware strings (v1.0.1, v1.0.2) and embedded JS (v0.0.0 full flash dump)
- [x] Hardware schematic analyzed (ESP32-C3, relay heater, TRIAC fan, NTC thermistors)
- [x] Protocol documented: [docs/protocol.md](docs/protocol.md)
- [x] Klipper extras module (`panda_breath.py`)
- [x] Standalone WebSocket test tool (`test_ws.py`)
- [x] Installation guide / overlay for Snapmaker U1 (`docs/klipper_install.md`)

---

## Integration approach

The module will:

1. Maintain a persistent WebSocket connection to the device at `ws://<ip>/ws`
2. Use `work_mode: 2` (always-on) for normal `heater_generic` chamber heating
3. Optionally configure the device's native auto mode (`work_mode: 1`) via `PANDA_BREATH_AUTO`
4. Optionally start and stop the device's native filament drying mode (`work_mode: 3`)
5. Send `work_on: true` when Klipper sets a non-zero target temperature; `work_on: false` when target is 0
6. Report `cal_warehouse_temp` (calibrated NTC ADC reading) as the current temperature
7. Reconnect automatically on connection drop

The device handles all heater duty-cycling and fan speed control internally. The module only tells it to be on or off.

### `printer.cfg`

```ini
[panda_breath]
host: PandaBreath.local   # or IP address
port: 80

[heater_generic panda_breath]
heater_pin: panda_breath:pwm
sensor_type: panda_breath
control: watermark
max_delta: 0.5
min_temp: 15
max_temp: 80

[verify_heater panda_breath]
check_gain_time: 360
hysteresis: 5
heating_gain: 1

[gcode_macro M141]
description: Set chamber temperature (Panda Breath)
gcode:
    {% set s = params.S|default(0)|float %}
    SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET={s}

[gcode_macro M191]
description: Wait for chamber temperature (Panda Breath)
gcode:
    {% set s = params.S|default(0)|float %}
    M141 S{s}
    {% if s > 0 %}
        TEMPERATURE_WAIT SENSOR="heater_generic panda_breath" MINIMUM={s}
    {% endif %}
```

### Native auto mode (stock firmware only)

For stock Panda Breath firmware, the module also exposes a `PANDA_BREATH_AUTO` command that switches the device into its own native auto mode (`work_mode: 1`) instead of the normal Klipper-controlled heating mode (`work_mode: 2`).

This is mainly useful if you want macros to toggle and configure the Panda's built-in automatic behavior directly.

```ini
[gcode_macro PANDA_AUTO_ON]
description: Enable Panda Breath native auto mode
gcode:
    PANDA_BREATH_AUTO ENABLE=1 TARGET=45 FILTERTEMP=30 HOTBEDTEMP=80

[gcode_macro PANDA_AUTO_OFF]
description: Disable Panda Breath native auto mode
gcode:
    PANDA_BREATH_AUTO ENABLE=0
```

`TARGET`, `FILTERTEMP`, and `HOTBEDTEMP` are Panda firmware auto-mode settings, not standard Klipper heater targets.

### Native drying mode (stock firmware only)

For stock Panda Breath firmware, the module also exposes `PANDA_BREATH_DRY_START` and `PANDA_BREATH_DRY_STOP` to control the Panda's built-in drying cycle (`work_mode: 3`) directly from macros.

```ini
[gcode_macro PANDA_DRY_START]
description: Start Panda Breath native drying mode
gcode:
    PANDA_BREATH_DRY_START TEMP=55 HOURS=6

[gcode_macro PANDA_DRY_STOP]
description: Stop Panda Breath native drying mode
gcode:
    PANDA_BREATH_DRY_STOP
```

`TEMP` is the Panda drying target in Celsius and `HOURS` is the drying-cycle duration in whole hours.

---

## Protocol summary

The device speaks JSON over WebSocket. All messages use a root key identifying the subsystem:

```json
{ "settings": { "work_on": true, "work_mode": 2, "set_temp": 45 } }
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

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/wildtang3nt)

## License

This project (Klipper module and documentation) is MIT licensed.

The BIQU Panda Breath hardware and firmware are © 2025 BIQU, licensed CC-BY-NC-ND-4.0.
