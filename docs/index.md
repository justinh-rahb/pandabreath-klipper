# pandabreath-klipper

Klipper integration and firmware research for the **BIQU Panda Breath** smart chamber heater and air filter.

!!! tip "Status"
    The stock OEM firmware plus `panda_breath.py` is the practical path today. The ESPHome and KlipperMCU directions remain experimental and are currently de-emphasized.

## Overview

This repository exists because the Panda Breath has no official Klipper support. It documents one practical path and two experimental ones:

| Path | Device firmware | Klipper side | Notes |
|---|---|---|---|
| Stock | OEM firmware | `panda_breath.py` | Current recommended path |
| ESPHome | ESPHome reflash | `panda_breath.py` | Incomplete and untested |
| KlipperMCU | Custom ESP-IDF reflash | Native `[mcu]` | Exploratory and mostly theoretical right now |

For the stock and ESPHome paths, the module gives Klipper a `sensor_type: panda_breath` and a virtual `heater_pin: panda_breath:pwm`. You still define the actual `[heater_generic panda_breath]` yourself.

## Quick start

=== "Stock firmware"

    ```ini
    [panda_breath]
    firmware: stock
    host: PandaBreath.local   # or an IP / hostname your Klipper host can resolve
    port: 80

    [heater_generic panda_breath]
    heater_pin: panda_breath:pwm
    sensor_type: panda_breath
    control: watermark
    max_delta: 0.5
    min_temp: 15
    max_temp: 80
    ```

=== "ESPHome firmware (experimental)"

    ```ini
    [panda_breath]
    firmware: esphome
    mqtt_broker: 192.168.1.10
    mqtt_port: 1883
    mqtt_topic_prefix: panda-breath

    ; Experimental path — not fully validated
    ```

=== "KlipperMCU firmware (exploratory)"

    ```ini
    [mcu panda_breath]
    serial: /dev/ttyUSB0

    [heater_generic chamber]
    heater_pin: panda_breath:gpio18
    sensor_type: NTC 100K beta 3950
    sensor_pin: panda_breath:gpio0
    control: pid
    min_temp: 0
    max_temp: 60
    ```

The baseline control path is normal Klipper heater control:

```gcode
SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=45
SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=0
```

## Optional stock-only commands

The stock transport also exposes optional passthrough commands for OEM native modes:

- `PANDA_BREATH_AUTO ENABLE=<0|1> TARGET=<C> FILTERTEMP=<C> HOTBEDTEMP=<C>`
- `PANDA_BREATH_DRY_START TEMP=<C> HOURS=<1-12>`
- `PANDA_BREATH_DRY_STOP`

These are useful for advanced macros and downstream integrations, but they are not required for the normal `heater_generic` path.

BTT's Panda Breath wiki now lists `V1.0.3` as adding the ability to bind Klipper printers, so `1.0.3+` is the right stock-firmware baseline for native auto-mode workflows.

## Quick links

| Topic | Page |
|---|---|
| Klipper module architecture | [Klipper Integration](klipper/index.md) |
| Install the module | [Install](klipper/install.md) |
| `printer.cfg` reference | [printer.cfg Reference](klipper/printer-cfg.md) |
| ESPHome reflash path | [ESPHome (experimental)](esphome/index.md) |
| KlipperMCU reflash path | [KlipperMCU (exploratory)](klipper-mcu/index.md) |
| WebSocket API reference | [Protocol](protocol.md) |
| Hardware schematic analysis | [Hardware](hardware.md) |
| Firmware binary analysis | [Firmware](firmware.md) |
| Reverse-engineering methodology | [Research Methodology](research/methodology.md) |

## Notes

- Use OEM firmware `1.0.3+` for the current stock-firmware Klipper path.
- Earlier repository analysis found regression signals in `v1.0.2`, including apparent removal of some thermal-protection logic.
- The ESPHome implementation is incomplete and untested.
- The KlipperMCU path is still exploratory and not yet a validated solution.
- The stock API has no authentication and should be treated as LAN-only.
- Downstream projects may wrap this module with device-specific packaging, macros, and UI.

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/wildtang3nt)

*All protocol knowledge in this repository is derived from reverse engineering. See [Research Methodology](research/methodology.md).*
