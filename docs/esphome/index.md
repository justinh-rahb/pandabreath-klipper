# ESPHome Firmware

An alternative to the OEM firmware: reflash the Panda Breath's ESP32-C3 with [ESPHome](https://esphome.io), then use the MQTT transport in `panda_breath.py`.

!!! warning "Continuity testing recommended before flashing"
    GPIO pin assignments for TH0, TH1, and RLY_MOSFET have been inferred by cross-referencing the schematic's module pad numbers with the ESP32-C3-MINI-1 datasheet. The assignments are high-confidence but not yet verified on real hardware. **Continuity testing is recommended before first flash** to confirm the three inferred pins. See the [setup guide](https://github.com/justinh-rahb/pandabreath-klipper/blob/main/esphome/README.md) for verification steps.

---

## Why ESPHome?

| Concern | OEM firmware | ESPHome |
|---|---|---|
| Native Klipper auto-mode support | Available in the current OEM `1.0.3+` line | Not needed; ESPHome uses direct MQTT heater control |
| Firmware risk profile | Current OEM path is improving, but earlier repository analysis flagged regressions in `v1.0.2` | ESPHome is maintained and battle-tested |
| Fan speed control | Device-managed (no external control) | Configurable via `ac_dimmer` component |
| OTA updates | BTT releases only | ESPHome OTA — update on your schedule |
| Recovery | Historical 4MB OEM flash dump available in this repo | Reflash OEM dump at any time |

The primary motivation is still control and safety: repository analysis of `v1.0.2` found regression signals around PTC thermal protection, while ESPHome lets you own that logic directly.

---

## How it works

ESPHome runs on the same ESP32-C3 as the OEM firmware. The `esphome/panda_breath.yaml` config:

- Reads both NTC thermistors (chamber temp + PTC element temp)
- Controls the PTC relay via a bang-bang climate controller
- Controls fan speed via the `ac_dimmer` component (TRIAC phase-angle, zero-crossing synchronised)
- Implements a PTC overheat safety cutoff (restoring the protection BTT removed)
- Publishes sensor state and accepts control commands over MQTT

`panda_breath.py` connects to the MQTT broker, subscribes to the chamber temperature topic, and publishes climate mode/target commands — the same Klipper heater interface as the stock path.

---

## Hardware mapping

The Panda Breath hardware maps directly to ESPHome components:

| Hardware | GPIO | ESPHome component |
|---|---|---|
| Chamber NTC thermistor (TH0) | GPIO0 (ADC1_CH0) ⚠ | `sensor.ntc` via `sensor.resistance` + `sensor.adc` |
| PTC element NTC thermistor (TH1) | GPIO1 (ADC1_CH1) ⚠ | `sensor.ntc` (safety monitoring) |
| PTC heater relay (RLY_MOSFET) | GPIO18 ⚠ | `switch.gpio` → `climate.bang_bang` |
| Fan TRIAC gate (FAN / IO03) | GPIO3 | `output.ac_dimmer` gate_pin |
| Zero-crossing detector (ZERO / IO07) | GPIO7 | `output.ac_dimmer` zero_cross_pin |
| K2 button (IO00) | GPIO0 | `binary_sensor.gpio` |
| K3 button (IO02) | GPIO2 | `binary_sensor.gpio` |
| K1-LED (IO06) | GPIO6 | `output.gpio` + `light.binary` |
| K2-LED (IO05) | GPIO5 | `output.gpio` + `light.binary` |
| K3-LED (IO04) | GPIO4 | `output.gpio` + `light.binary` |

!!! note "GPIO7 — shared between zero-crossing and K1 button"
    GPIO7 serves dual duty in hardware: the TRIAC zero-crossing detector and the K1 button. The OEM firmware handles both — zero-crossing pulses (~100µs at 100/120Hz) are easily distinguished from button presses (50–200ms). In the ESPHome config, GPIO7 is assigned to the `ac_dimmer` zero-crossing pin and K1 is not configured as a binary sensor. Adding K1 support would require a custom component or ISR filter to discriminate pulse widths.

### Inferred GPIO pins

Three pins were resolved by cross-referencing the schematic's module pad numbers with the [ESP32-C3-MINI-1 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-c3-mini-1_datasheet_en.pdf). The OEM firmware's `app_temp.c` confirms both NTC channels use a single `adc_handle` (ADC1). Continuity testing is recommended to confirm.

| Substitution in YAML | Inferred GPIO | Module pad | ADC channel | Notes |
|---|---|---|---|---|
| `gpio_ntc_chamber` | `GPIO0` | 12 | ADC1_CH0 | Chamber/warehouse temperature; shared with K2 button net |
| `gpio_ntc_ptc` | `GPIO1` | 13 | ADC1_CH1 | PTC element temperature (thermal safety) |
| `gpio_relay` | `GPIO18` | 26 | — | Digital output → Q3 NPN → SSR relay |

These are in the `substitutions:` block at the top of `esphome/panda_breath.yaml` for easy editing once confirmed.

---

## Klipper integration via MQTT

ESPHome publishes sensor state and accepts commands over MQTT. `panda_breath.py` with `firmware: esphome` connects to the broker and speaks this interface directly.

**Temperature (subscribe):**
```
panda-breath/sensor/chamber_temperature/state   → float, °C
```

**Heater control (publish):**
```
panda-breath/climate/chamber/target_temperature/set   → float, °C
panda-breath/climate/chamber/mode/set                 → "heat" or "off"
```

**Fan control (publish):**
```
panda-breath/fan/fan/speed/set    → 0–100
panda-breath/fan/fan/command      → "turn_on" or "turn_off"
```

A local MQTT broker is required. Mosquitto works well — on the U1 devel build:
```sh
opkg install mosquitto mosquitto-client
```

---

## Setup guide

The detailed developer setup guide (GPIO verification steps, first-flash procedure, validation sequence, NTC calibration, and recovery instructions) is in the repository:

[`esphome/README.md` on GitHub](https://github.com/justinh-rahb/pandabreath-klipper/blob/main/esphome/README.md)

---

## Recovery

If something goes wrong, the original v0.0.0 OEM firmware can be restored from the full flash dump included in the repository:

```sh
esptool.py --chip esp32c3 \
  --port /dev/cu.wchusbserial* \
  --baud 460800 \
  write-flash 0x00000 Panda_Breath/Firmware/0.0.0/0.0.0.0_clean.bin
```

This is a complete flash write — it restores the bootloader, partition table, application, and clears NVS (WiFi credentials will need to be re-entered).
