# Panda Breath — ESPHome

Alternative firmware approach: replace the BIQU factory firmware with ESPHome
on the ESP32-C3. Rationale: BTT firmware v1.0.1+ has known thermal/timing bugs,
including the removal of PTC thermal runaway detection in v1.0.2. ESPHome provides
a stable, maintainable base with native TRIAC phase-angle fan speed control
(`ac_dimmer` component) and configurable safety logic.

**Recovery:** A full 4MB flash dump of the stable OEM v0.0.0 firmware exists at
`Panda_Breath/Firmware/0.0.0/0.0.0.0_clean.bin`. Restoring it over USB-C is
straightforward — this approach is reversible.

---

## Files

| File | Purpose |
|---|---|
| `panda_breath.yaml` | Main ESPHome configuration |
| `secrets.yaml` | Your actual credentials — **gitignored, never commit** |
| `secrets.yaml.example` | Template showing required keys — copy to `secrets.yaml` |

---

## Prerequisites

- ESPHome installed (`pip install esphome` or use the ESPHome dashboard)
- USB-C cable connected to the Panda Breath (CH340K bridge — auto-reset capable)
- Local MQTT broker reachable by both the Panda Breath and the Snapmaker U1
  (Mosquitto on a LAN Pi or the U1 itself works; `opkg install mosquitto` on devel U1 build)

---

## Blockers — must resolve before first flash

### 1. GPIO pin verification (critical)

The hardware schematic lists ESP32-C3 **physical IC package pin numbers**, not GPIO
numbers. Three GPIOs are unresolved and currently use placeholder substitutions in
`panda_breath.yaml`. **Do not flash until these are confirmed** — wrong values risk
driving the relay or NTC ADC on incorrect pins.

| Substitution | Placeholder | Schematic | What to do |
|---|---|---|---|
| `gpio_ntc_chamber` | `GPIO1` | Physical pin 12 | Continuity from TH0 pad to ESP32-C3 module castellation |
| `gpio_ntc_ptc` | `GPIO19` | Physical pin 13 | Continuity from TH1 pad to module castellation — **GPIO19 is USB D+ and is almost certainly wrong** |
| `gpio_relay` | `GPIO8` | Physical pin 26 | Continuity from RLY_MOSFET pad — **GPIO26 does not exist on ESP32-C3** |

Cross-reference the [ESP32-C3-MINI-1-H4X module pad layout](https://www.espressif.com/sites/default/files/documentation/esp32-c3-mini-1_datasheet_en.pdf)
against the schematic's physical pin column. A multimeter in continuity mode from
TH0/TH1/RLY_MOSFET PCB pads to the ESP32-C3 module castellations will resolve
this definitively.

Edit the `substitutions:` block at the top of `panda_breath.yaml` once confirmed.

### 2. GPIO0 / ZERO crossing conflict

The schematic annotates IO00 (GPIO0) as both "K2 button" and "ZERO crossing".
If GPIO0 also receives the 100/120 Hz signal from the TLP785 optocoupler:

- The K2 `binary_sensor` on GPIO0 will be unreliable (corrupted by AC pulses)
- GPIO0 should become the `zero_cross_pin` for `ac_dimmer` instead of GPIO7
- GPIO7 can then be freed as a `binary_sensor` for the K1 button

**Verify with an oscilloscope or logic analyser:** power the board from AC and
probe GPIO0 and GPIO7 with the device idle. If both show 100/120 Hz pulses, use
GPIO0 for `zero_cross_pin` and add GPIO7 back as `button_k1` in `binary_sensor`.

### 3. AC line frequency

Set `method: leading_pulse` frequency for `ac_dimmer` to match your mains supply.
ESPHome auto-detects from the zero-crossing signal — no explicit config needed —
but confirm the zero-crossing is actually detected before tuning fan speed.

---

## Validation steps after first flash

Run these in order before relying on the device for printing:

1. **NTC readings** — power from 5V USB (no mains), confirm `chamber_temp` and
   `ptc_temp` read plausible room temperature (~20–25°C). If readings are wildly
   wrong or NaN, GPIO assignments for TH0/TH1 are incorrect.

2. **NTC B-constant** — compare ESPHome `chamber_temp` against the OEM firmware's
   `warehouse_temper` value (connect to a device still running OEM firmware with a
   WebSocket client). Adjust `b_constant` in `panda_breath.yaml` if they differ.

3. **Relay continuity** — with mains disconnected, use a multimeter to confirm
   `heater_relay` switch toggling drives the MGR-GJ-5-L SSR coil. Confirm
   `restore_mode: ALWAYS_OFF` holds on boot.

4. **Fan zero-crossing** — with mains connected, confirm the `Fan` entity responds
   to speed changes. Start at 50% and work down to find the actual `min_power`
   stall point for this specific fan. Update the `min_power` value accordingly.

5. **Safety cutoff** — with heater running, confirm the 90°C PTC overheat
   interval fires correctly (you can temporarily lower the threshold to test).
   Adjust the cutoff based on real PTC element measurements.

---

## Klipper integration

The Klipper `panda_breath.py` module needs to be adapted (or rewritten) to use
MQTT rather than the OEM WebSocket JSON protocol. ESPHome publishes to:

```
panda-breath/sensor/chamber_temperature/state       # float, °C
panda-breath/sensor/ptc_element_temperature/state   # float, °C
panda-breath/climate/chamber/state                  # JSON: mode, current_temperature, target_temperature
panda-breath/fan/fan/state                          # ON/OFF
panda-breath/fan/fan/speed                          # 0–100
```

Klipper module publishes to:

```
panda-breath/climate/chamber/target_temperature/set  # float, °C
panda-breath/climate/chamber/mode/set               # "heat" | "off"
panda-breath/fan/fan/speed/set                      # 0–100
panda-breath/fan/fan/command                        # "turn_on" | "turn_off"
```

The Klipper module still exposes a standard `heater_generic` interface — only
the transport layer changes from WebSocket to MQTT.

**MQTT broker on U1:** In the devel extended firmware build (`DEVEL=1`):
```sh
opkg install mosquitto mosquitto-client
```

---

## Recovery — restoring OEM firmware

If ESPHome causes problems, restore the v0.0.0 OEM dump over USB-C:

```sh
esptool.py --chip esp32c3 \
  --port /dev/cu.wchusbserial* \
  --baud 460800 \
  write-flash 0x00000 ../Panda_Breath/Firmware/0.0.0/0.0.0.0_clean.bin
```

The device must be in bootloader mode: hold BOOT (SW4) while pressing RESET,
or let the CH340K auto-reset circuit handle it (DTR/RTS via esptool).

---

## Future improvements

- **PID climate controller** — replace `bang_bang` with `climate.pid` +
  `output.slow_pwm` for tighter temperature regulation. Start with bang-bang
  until NTC calibration is validated.

- **Fan curve automation** — tie fan speed to chamber temperature delta
  (e.g. ramp fan when `chamber_temp` is >5°C below target).

- **K1 button** — currently unusable because GPIO7 is the zero-cross pin.
  Freed if GPIO0 turns out to also carry the ZERO signal (see blocker 2 above).

- **Status LEDs** — wire LED K1/K2/K3 states to climate mode and heater/fan
  state for visual feedback without needing the web UI.
