# KlipperMCU Firmware

A possible future alternative to the OEM and ESPHome paths: replace the Panda Breath's ESP32-C3 firmware with a custom [ESP-IDF](https://idf.espressif.com/) build that speaks the native **Klipper MCU binary protocol** over USB serial (via the onboard CH340K bridge).

!!! warning "Exploratory status"
    This path is mostly theoretical right now. It has not been validated end-to-end on real hardware and should be treated as an exploration, not a supported solution.

!!! warning "Continuity testing recommended before flashing"
    GPIO pin assignments for TH0, TH1, and RLY_MOSFET have been inferred by cross-referencing the schematic's module pad numbers with the ESP32-C3-MINI-1 datasheet. The assignments are high-confidence but not yet verified on real hardware. **Continuity testing is recommended before first flash** to confirm the three inferred pins. See [Inferred GPIO pins](#inferred-gpio-pins) below.

!!! tip "Design direction"
    The long-term attraction of this path is that Klipper could talk to the Panda Breath directly as a native `[mcu panda_breath]`, with no Python extras module, no MQTT broker, and no WiFi dependency. That remains a design goal rather than a completed implementation today.

---

## Why KlipperMCU?

| Concern | OEM firmware | ESPHome | KlipperMCU |
|---|---|---|---|
| Thermal runaway | Present in v0.0.0; **removed in v1.0.2** | Configurable | **Klipper's own `verify_heater`** |
| PID control | Device-managed | ESPHome bang-bang | **Klipper PID — fully tunable** |
| Klipper extras module | Required | Required | **Not needed** |
| MQTT broker | Not needed | Required | Not needed |
| WiFi | Required | Optional (MQTT) | **Not needed** |
| Transport | WebSocket (WiFi) | MQTT (WiFi) | **USB serial** |
| Fan speed | Device-managed | Configurable | Internal firmware — follows heater relay |
| OTA updates | BTT releases only | ESPHome OTA | Serial flash (USB) |

The primary advantages would be simplicity and reliability: a single USB cable replacing WiFi dependency and MQTT infrastructure, with Klipper's native PID and thermal safety applying directly. Those advantages are still aspirational until the path is validated.

---

## How it works

The custom firmware (`klipper-firmware/`) is an ESP-IDF 5.x project that compiles the [Klipper MCU C core](https://github.com/Klipper3d/klipper) (the same code that runs on printer mainboards) with a Panda Breath-specific board HAL.

```
Klipper host (U1)
      │
      │  USB-C cable
      ▼
  CH340K (USB-to-serial)
      │
      │  UART0 @ 250000 baud
      ▼
  ESP32-C3 — klipper-firmware
      ├── Klipper MCU binary protocol (HDLC framing)
      ├── NTC chamber temperature → Klipper ADC
      ├── PTC relay → Klipper digital_out (heater_pin)
      ├── TRIAC fan → internal FreeRTOS task (not visible to Klipper)
      └── Buttons / LEDs → Klipper GPIOs
```

**Fan control** is handled entirely inside the firmware: a FreeRTOS task watches the relay GPIO that Klipper sets, and drives the TRIAC via a zero-crossing ISR and phase-angle timer. Klipper never sees the fans — it only sees the relay (heater pin) and temperature sensor.

---

## Hardware mapping

| Hardware | GPIO | Klipper reference | Notes |
|---|---|---|---|
| Chamber NTC thermistor (TH0) | `GPIO0` ⚠ | `panda_breath:gpio0` | **Inferred** — module pad 12 = GPIO0 (ADC1_CH0) |
| PTC element NTC (TH1) | `GPIO1` ⚠ | Internal only | **Inferred** — module pad 13 = GPIO1 (ADC1_CH1) |
| PTC heater relay (RLY_MOSFET) | `GPIO18` ⚠ | `panda_breath:gpio18` | **Inferred** — module pad 26 = GPIO18 |
| Fan TRIAC gate (IO03) | `GPIO3` ✓ | Internal only | Confirmed from schematic IO label |
| Zero-crossing detector (IO07) | `GPIO7` ✓ | Internal only | Confirmed from schematic IO label |
| K2 button (IO00) | `GPIO0` ✓ | `panda_breath:gpio0` | Confirmed (shared with TH0 ADC) |
| K3 button (IO02) | `GPIO2` ✓ | `panda_breath:gpio2` | Confirmed |
| K1-LED (IO06) | `GPIO6` ✓ | `panda_breath:gpio6` | Confirmed |
| K2-LED (IO05) | `GPIO5` ✓ | `panda_breath:gpio5` | Confirmed |
| K3-LED (IO04) | `GPIO4` ✓ | `panda_breath:gpio4` | Confirmed |
| UART0 TX | `GPIO21` ✓ | — | CH340K bridge, confirmed |
| UART0 RX | `GPIO20` ✓ | — | CH340K bridge, confirmed |

### Inferred GPIO pins

Three pins were resolved by cross-referencing the schematic's module pad numbers with the [ESP32-C3-MINI-1 datasheet](https://www.espressif.com/sites/default/files/documentation/esp32-c3-mini-1_datasheet_en.pdf) pad layout. The OEM firmware's `app_temp.c` strings confirm both NTC channels use a single `adc_handle` (ADC1), constraining them to GPIO0–GPIO4.

| Pin name | Inferred GPIO | Module pad | ADC channel | Evidence |
|---|---|---|---|---|
| `GPIO_NTC_CHAMBER` (TH0) | `GPIO0` | 12 | ADC1_CH0 | Module pad 12 = GPIO0; only remaining ADC1 pin after IO-labeled pins allocated |
| `GPIO_NTC_PTC` (TH1) | `GPIO1` | 13 | ADC1_CH1 | Module pad 13 = GPIO1; adjacent to TH0 on the module |
| `GPIO_RELAY` (RLY_MOSFET) | `GPIO18` | 26 | — | Module pad 26 = GPIO18; digital output, no ADC needed |

Edit `klipper-firmware/components/klipper/board/panda_breath_pins.h` once values are confirmed.

!!! note "GPIO7 — shared between zero-crossing and K1 button"
    GPIO7 serves dual duty: the TRIAC zero-crossing detector (brief ~100µs pulses at 100/120Hz) and the K1 button. The OEM firmware handles both on the same pin — zero-crossing pulses are short and periodic, while button presses are sustained (50–200ms), making them easily distinguishable in an ISR. In the KlipperMCU firmware, GPIO7 is dedicated to the zero-crossing ISR in `fan.c` and K1 is not currently implemented. Adding K1 support would require pulse-width discrimination in the ISR or time-multiplexing the pin configuration.

---

## Build

**Prerequisites:** [ESP-IDF v5.x](https://docs.espressif.com/projects/esp-idf/en/stable/esp32c3/get-started/index.html) installed and activated (`idf.py` on `PATH`).

The Klipper source is included as a git submodule. Initialise it first:

```sh
cd klipper-firmware
git submodule update --init --recursive
```

Build:

```sh
idf.py set-target esp32c3
idf.py build
```

A successful build produces:
- `build/panda_breath.bin` — the firmware image
- `build/klipper/klipper.dict` — the Klipper command dictionary (required by the host)

---

## Flash

Connect the Panda Breath via USB-C. The CH340K bridge will enumerate as `/dev/ttyUSBx` on Linux or `/dev/cu.wchusbserial*` on macOS.

```sh
idf.py -p /dev/cu.wchusbserial* flash
```

Copy the command dictionary to the Klipper host:

```sh
scp build/klipper/klipper.dict lava@<u1-ip>:/home/lava/klipper/
```

The Klipper host needs this file to decode the MCU protocol. Specify its path in `printer.cfg` (see below).

---

## `printer.cfg`

```ini
[mcu panda_breath]
serial: /dev/ttyUSB0        # adjust port — check: ls /dev/ttyUSB*
baud: 250000

[heater_generic chamber]
heater_pin: panda_breath:gpio18          # GPIO_RELAY (module pad 26) — inferred, continuity test recommended
sensor_type: NTC 100K beta 3950
sensor_pin: panda_breath:gpio0           # GPIO_NTC_CHAMBER (module pad 12) — inferred, continuity test recommended
control: pid
pid_kp: 10
pid_ki: 0.1
pid_kd: 100
min_temp: 0
max_temp: 60

[verify_heater chamber]
max_error: 200
check_gain_time: 300
hysteresis: 5
heating_gain: 1
```

!!! tip "PID tuning"
    After confirming GPIO assignments on hardware, run Klipper's built-in PID calibration:
    ```
    PID_CALIBRATE HEATER=chamber TARGET=40
    ```
    Replace the placeholder `pid_kp/ki/kd` values with the output.

---

## Differences from the Python extras paths

The KlipperMCU path makes the Panda Breath look like any other Klipper MCU (printer mainboard). This means:

- `[heater_generic chamber]` is configured directly in `printer.cfg` — no `[panda_breath]` section
- `panda_breath.py` is **not needed** and should not be loaded
- Klipper's own PID, `verify_heater`, and thermal safety apply directly
- The device must be connected via USB — WiFi is not used at runtime

The fan is not visible to Klipper. It operates autonomously: active at 40% phase angle while the relay is on, then holds at 25% for a 60-second cooldown after the relay goes low.

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

---

## Multi-instance architecture with Klipper Router

The default KlipperMCU setup adds the Panda Breath as a secondary `[mcu panda_breath]` to the main printer's Klipper instance. An alternative is to run a **dedicated Klipper instance** for the Panda Breath and bridge it to the printer using [Klipper Router](https://github.com/paxx12/klipper-router) — a JSON-RPC bridge by paxx12 (same author as the U1 extended firmware).

The key advantage is **fault isolation**: if the Panda Breath's Klipper instance crashes (USB disconnect, MCU timeout, thermal fault), the main printer keeps running. With a single-instance `[mcu panda_breath]` setup, any MCU communication error triggers Klipper's emergency shutdown and kills the print. In the multi-instance setup, Klipper's `verify_heater` and thermal protections still apply to the Panda Breath instance — it shuts down safely on its own — but the printer is unaffected.

This is useful when:

- You want a crash-safe setup — Panda Breath faults don't kill active prints
- The Snapmaker U1's modified Klipper makes adding a second MCU difficult
- You want the printer to react to chamber temperature changes via event subscriptions

### How it works

Klipper Router connects to multiple Klipper instances over their Unix sockets and registers shared remote methods on each. The main printer can query chamber temperature, send heater commands, and subscribe to status updates — all via G-code macros.

```
Klipper (main printer)           Klipper Router           Klipper (Panda Breath)
  klippy_host_main.sock  ◄────►  router.cfg   ◄────►   klippy_host_pb.sock
                                                              │
                                                        [mcu panda_breath]
                                                          serial: /dev/ttyUSB0
```

### Example: subscribe to chamber temperature

On the main printer, a macro can subscribe to the Panda Breath's heater status:

```ini
[gcode_macro SUBSCRIBE_CHAMBER]
gcode:
    {action_call_remote_method("router/objects/subscribe",
        target="panda_breath",
        objects={"heater_generic chamber": ["temperature"]},
        gcode_callback="ON_CHAMBER_UPDATE")}

[gcode_macro ON_CHAMBER_UPDATE]
gcode:
    {% set temp = params.HEATER_GENERIC_CHAMBER_TEMPERATURE|default(0)|float %}
    M118 Chamber: {temp}°C
```

### Example: send heater commands across instances

```ini
[gcode_macro SET_CHAMBER_TEMP]
gcode:
    {% set target = params.TARGET|default(0)|int %}
    {action_call_remote_method("router/gcode/script",
        target="panda_breath",
        script="SET_HEATER_TEMPERATURE HEATER=chamber TARGET=" ~ target)}
```

See the [Klipper Router README](https://github.com/paxx12/klipper-router) for full configuration and API reference.
