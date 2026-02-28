# Hardware

> Source: schematic traced from a real device. Chip identification community-confirmed.

---

## Overview

| Component | Part | Notes |
|---|---|---|
| MCU | ESP32-C3 (ESP32-C3-MINI-1-H4X) | WiFi 2.4GHz, USB-C flashing via CH340K |
| Heater | 300W PTC element | Relay-switched (on/off only) |
| Heater relay | MGR-GJ-5-L SSR | AC solid-state relay |
| Fan control | BT136-800E TRIAC | Phase-angle speed control |
| Fan driver | MOC3021S-TA1 optocoupler | TRIAC gate driver |
| Zero-crossing | TLP785 AC optocoupler | For TRIAC phase sync |
| Chamber sensor | NTC 100K thermistor | → `warehouse_temper` / `cal_warehouse_temp` |
| PTC sensor | NTC 100K thermistor | Thermal runaway protection only |
| AC-DC | HLK-PM01 | 110–240V AC → 5V isolated |
| LDO | AS1117-3.3 | 5V → 3.3V MCU rail |
| USB-UART | CH340K | USB Type-C programming interface |

---

## Power Supply Chain

```
AC mains (L/N)
  → F1 fuse (MTST630AL)
  → R1 MOV (10D-11) surge protection
  → EMI filter: CX2-0.1uF/275V X2 cap + PDSQAT1212-303MLB common mode choke
  → HLK-PM01 (isolated AC-DC, 110-240V → 5V)
  → AS1117-3.3 LDO (U5, 5V → 3.3V = MCU-3V3 rail)
```

- `MCU-3V3` rail powers the ESP32 and logic
- `5V` rail powers relay coil driver and optocoupler
- `L-AC-DC` is the live AC line routed to the heater relay and fan TRIAC

---

## ESP32-C3 GPIO Assignments

| Net name | ESP32 pin | Connected to |
|---|---|---|
| `IO02` | 6 | K3 button (10K pullup via R2) |
| `IO03` | 7 | FAN TRIAC signal |
| `EN` | 8 | RESET button (10K pullup via R4) |
| `TH0` | 12 | NTC thermistor 0 ADC input |
| `TH1` | 13 | NTC thermistor 1 ADC input |
| `IO00` | 15 | K2 button + ZERO crossing |
| `IO04` | 19 | K3-LED |
| `IO05` | 20 | K2-LED |
| `IO06` | 21 | K1-LED |
| `IO07` / `ZERO` | 22 | K1 button / ZERO crossing signal |
| `BOOT` | 23 | SW4 (BOOT button, K4) |
| `RLY_MOSFET` | 26 | Relay drive transistor (Q3 base) |
| `TXD0` | 30 | CH340K UART TX |
| `RXD0` | 31 | CH340K UART RX |

---

## PTC Heater Control

**Relay: MGR-GJ-5-L** (solid-state relay, AC output)

- AC side: `L-AC-DC` (live AC) → relay → `L-OUT` → PTC heater connector
- Control side: 5V coil driven by Q3 (MMS8050-H-TR NPN transistor)
- Q3 base driven by `RLY_MOSFET` GPIO via R16 (100Ω) + R18 (10K) pulldown
- D5: 1N4148 flyback diode

!!! note "On/off only"
    The relay either switches full AC power to the PTC element or cuts it. There is no phase-angle or PWM control on the heater. Temperature regulation is achieved by the firmware duty-cycling the relay based on thermistor feedback. The Klipper module does not need to manage this — it only sends `work_on: true/false`.

---

## Fan Speed Control

**TRIAC: BT136-800E** (600V, 4A AC switch)

- Controlled via **MOC3021S-TA1** optocoupler TRIAC driver
- Q2 (MMS8050-H-TP NPN) drives the optocoupler LED
- `FAN` GPIO → Q2 base (via R15 10K) → U4 opto → Q1 TRIAC gate
- Fan AC power goes through Q1 TRIAC

Phase-angle control: R12 snubber network, R14 (220Ω gate resistor) — classic TRIAC phase-angle speed control, firing synchronized to the zero-crossing signal. Fan speed is managed entirely by the firmware; there is no user-settable `fan_speed` field in the WebSocket API.

---

## Zero-Crossing Detector

**TLP785(GB-TP6,F(C))** — AC optocoupler

- Neutral AC → R30 (100K) → U7 AC side
- Live AC → R29 (470Ω) → U7 AC side
- Output: `ZERO` signal to ESP32 GPIO
- Used to synchronize TRIAC firing for fan phase-angle speed control

---

## Temperature Sensors

Two identical NTC 100K thermistor input circuits:

**TH0** — chamber air temperature

- Voltage divider: MCU-3V3 → R22 (33K 0.1%) → TH0 node → thermistor → GND
- Protection: D6 (BAV99 dual Schottky) + R25/R26 (2.37K 1%) series resistors
- Filter cap C13 (0.1µF)
- Firmware publishes as `warehouse_temper` (raw) and `cal_warehouse_temp` (ADC-calibrated)

**TH1** — PTC element temperature (identical circuit)

- Monitors PTC heater element temperature for thermal runaway protection
- Firmware publishes as `cal_ptc_temp`
- Not used for user-facing temperature targeting

!!! tip
    Use `cal_warehouse_temp` in preference to `warehouse_temper`. The firmware applies ADC calibration (`adc_cali_raw_to_voltage`) to produce the calibrated reading, which is more accurate than the raw ADC value.

---

## Physical Buttons

All three labeled buttons are **K6-6140S01** — LED-backlit tactile switches.

| Button | Net | LED net | GPIO |
|---|---|---|---|
| SW1 | K1 | K1-LED | IO06 (LED), IO07 (button) |
| SW2 | K2 | K2-LED | IO05 (LED), IO00 (button) |
| SW3 | K3 | K3-LED | IO04 (LED), IO02 (button) |
| SW4 | BOOT | — | BOOT pin (K4 / flash mode) |

!!! warning "Buttons do not push WebSocket messages"
    On v0.0.0, physical button presses do **not** generate WebSocket messages. The Klipper module cannot rely on push notifications to detect out-of-band state changes from the physical buttons.

---

## USB Programming Interface

**CH340K** — USB to UART bridge

- USB Type-C connector (`USB_P`/`USB_N`)
- `TXD0`/`RXD0` → ESP32 UART
- `RST#`/`DTR#` → EMM412R dual transistor → auto-reset/boot circuit

The auto-reset circuit allows `esptool` to enter bootloader mode automatically without pressing buttons:

```sh
esptool.py --chip esp32c3 --port /dev/ttyUSB0 --baud 460800 write-flash 0x0 firmware.bin
```

On macOS the port will be `/dev/cu.usbserial-*` or `/dev/cu.wchusbserial*` (CH340K).

---

## Klipper Integration Insights

1. **`warehouse_temper` is a real NTC ADC reading** — two separate physical sensors, independently wired. Use `cal_warehouse_temp` (calibrated) where available.

2. **PTC heater is relay-switched (on/off only)** — the firmware duty-cycles the relay for temperature regulation. The Klipper module just sends `work_on: true/false`.

3. **Fan speed is TRIAC phase-angle controlled** — firmware manages this entirely. There is no `fan_speed` write field in the WebSocket API.

4. **Button presses do not push WebSocket messages** — the module must poll (or reconnect) to detect out-of-band changes rather than relying on push.

5. **`cal_warehouse_temp` is the preferred temperature field** — it applies ADC calibration correction. Fall back to `warehouse_temper` if `cal_warehouse_temp` is absent.
