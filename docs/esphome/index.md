# ESPHome Firmware

An alternative to the OEM firmware: reflash the Panda Breath's ESP32-C3 with [ESPHome](https://esphome.io), then use the MQTT transport in `panda_breath.py`.

!!! warning "GPIO verification required before flashing"
    Three GPIO pin assignments in `esphome/panda_breath.yaml` are unconfirmed placeholders. The schematic lists physical IC package pin numbers, not GPIO numbers. **Do not flash until these are resolved** — wrong values risk driving the relay or NTC ADC on incorrect pins. See the [setup guide](https://github.com/justinh-rahb/pandabreath-klipper/blob/main/esphome/README.md) for verification steps.

---

## Why ESPHome?

| Concern | OEM firmware | ESPHome |
|---|---|---|
| Thermal runaway detection | Present in v0.0.0; **removed in v1.0.2** | Configurable; independent of BTT |
| Firmware stability | v0.0.0 stable; v1.0.1+ buggy | ESPHome is maintained and battle-tested |
| Fan speed control | Device-managed (no external control) | Configurable via `ac_dimmer` component |
| OTA updates | BTT releases only | ESPHome OTA — update on your schedule |
| Recovery | Full 4MB v0.0.0 flash dump available | Reflash v0.0.0 from dump at any time |

The primary motivation is safety: v1.0.2 silently removed PTC thermal runaway detection from a 300W mains-connected heater. ESPHome lets you own that logic directly.

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
| Chamber NTC thermistor (TH0) | Unconfirmed — see below | `sensor.ntc` via `sensor.resistance` + `sensor.adc` |
| PTC element NTC thermistor (TH1) | Unconfirmed — see below | `sensor.ntc` (safety monitoring) |
| PTC heater relay (RLY_MOSFET) | Unconfirmed — see below | `switch.gpio` → `climate.bang_bang` |
| Fan TRIAC gate (FAN / IO03) | GPIO3 | `output.ac_dimmer` gate_pin |
| Zero-crossing detector (ZERO / IO07) | GPIO7 | `output.ac_dimmer` zero_cross_pin |
| K2 button (IO00) | GPIO0 | `binary_sensor.gpio` |
| K3 button (IO02) | GPIO2 | `binary_sensor.gpio` |
| K1-LED (IO06) | GPIO6 | `output.gpio` + `light.binary` |
| K2-LED (IO05) | GPIO5 | `output.gpio` + `light.binary` |
| K3-LED (IO04) | GPIO4 | `output.gpio` + `light.binary` |

!!! note "GPIO7 / K1 button conflict"
    GPIO7 is dedicated to the TRIAC zero-crossing interrupt in the ESPHome config. The K1 button (which also uses GPIO7 in the OEM firmware) is therefore not available as a binary sensor. If GPIO0 is confirmed to also carry the zero-crossing signal (needs oscilloscope verification), GPIO0 can be used for zero_cross_pin and GPIO7 freed for K1 button.

### Unconfirmed GPIO pins

Three pins require hardware verification before first flash:

| Substitution in YAML | Placeholder | Physical IC pin | How to verify |
|---|---|---|---|
| `gpio_ntc_chamber` | `GPIO1` | 12 | Continuity from TH0 pad to ESP32-C3 module castellation |
| `gpio_ntc_ptc` | `GPIO19` | 13 | Continuity from TH1 pad — **GPIO19 is USB D+ and almost certainly wrong** |
| `gpio_relay` | `GPIO8` | 26 | Continuity from RLY_MOSFET pad — **GPIO26 doesn't exist on ESP32-C3** |

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
