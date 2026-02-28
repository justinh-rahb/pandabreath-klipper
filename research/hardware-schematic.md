# Panda Breath Hardware Schematic Analysis

Source: `shematic.png` (traced from real device)

## Power Supply Chain

```
AC mains (L/N) → F1 fuse (MTST630AL) → R1 MOV (10D-11) surge protection
→ EMI filter: CX2-0.1uF/275V X2 cap + PDSQAT1212-303MLB common mode choke
→ HLK-PM01 (Hi-Link isolated AC-DC module, 110-240V → 5V)
→ AS1117-3.3 LDO (U5, 5V → 3.3V = MCU-3V3 rail)
```

- `MCU-3V3` rail powers the ESP32 and logic
- `5V` rail powers relay coil, optocoupler drivers
- `L-AC-DC` is the live AC line routed to the heater relay and fan TRIAC

## Microcontroller

**U1: ESP32-C3-MINI-1-H4X** (schematic label; community-confirmed to be functionally an ESP32-C3)

### GPIO Assignments

| Net name | ESP32 pin | Connected to |
|---|---|---|
| `IO02` | 6 | K3 button (10K pullup via R2) |
| `IO03` | 7 | FAN signal |
| `EN` | 8 | RESET button (10K pullup via R4) |
| `TH0` | 12 | NTC thermistor 0 ADC input |
| `TH1` | 13 | NTC thermistor 1 ADC input |
| `IO00` | 15 | K2 button + ZERO crossing |
| `IO10` | 17 | (TBD) |
| `IO04` | 19 | K3-LED |
| `IO05` | 20 | K2-LED |
| `IO06` | 21 | K1-LED |
| `IO07`/`ZERO` | 22 | K1 button / ZERO crossing signal |
| `BOOT` | 23 | SW4 (BOOT button) |
| `RLY_MOSFET` | 26 | Relay drive transistor (Q3 base) |
| `TXD0` | 30 | CH340K UART TX |
| `RXD0` | 31 | CH340K UART RX |

## PTC Heater Control

**Relay: RLY1 — MGR-GJ-5-L** (solid-state relay, AC output)
- AC side: `L-AC-DC` (live AC) → relay → `L-OUT` → PTC heater connector (PTC)
- Control side: 5V coil driven by Q3 (MMS8050-H-TR NPN transistor)
- Q3 base driven by `RLY_MOSFET` GPIO via R16 (100R) + R18 (10K) pulldown
- D5: 1N4148 flyback protection

**On/Off only — no phase angle control on the PTC heater.** The relay either switches full AC power or cuts it. Temperature regulation is achieved by duty-cycling the relay based on the thermistor feedback.

## Fan Speed Control

**TRIAC: Q1 — BT136-800E** (600V, 4A AC switch)
- Controlled via **U4: MOC3021S-TA1** optocoupler TRIAC driver
- Q2 (MMS8050-H-TP NPN) drives the optocoupler LED
- `FAN` GPIO → Q2 base (via R15 10K) → U4 opto → Q1 TRIAC gate
- Fan AC power goes through Q1 TRIAC

**Phase-angle control:** R12 (C8, C9 snubber), R14 (220R gate resistor) — classic TRIAC phase angle speed control synchronized via the ZERO crossing signal.

## Zero-Crossing Detector

**U7: TLP785(GB-TP6,F(C))** — AC optocoupler
- `N` (neutral AC) → R30 (100K) → U7 AC side
- `L-AC-DC` (live) → R29 (470R) → U7 AC side
- Output: `ZERO` signal to ESP32 GPIO
- Used to synchronize TRIAC firing for fan phase-angle speed control

## Temperature Sensors (NTC Thermistors)

Two identical NTC thermistor input circuits:

**TH0** — connected to ESP32 `TH0` ADC:
- 2-pin header connector
- Voltage divider: MCU-3V3 → R22 (33K 0.1%) → TH0 node → thermistor → GND
- Protection: D6 (BAV99 dual Schottky) + R25/R26 (2.37K 1%) series resistors
- Filter cap C13 (0.1uF)

**TH1** — connected to ESP32 `TH1` ADC (identical circuit with R31/R32/R33/D9/C17):

**Which is which?** From firmware strings: `ptc_sensor_status` and `warehouse_sensor_status` are tracked separately. One NTC measures PTC heater element temperature (for thermal runaway protection), the other measures chamber/warehouse air temperature. The `warehouse_temper` (chamber air) is what Klipper sees.

Thermistor spec from BTT Wiki: **NTC 100K** (from top-left quadrant: `R7: NTC 100K/NC` and `R3: 33K/NC 0.1%`)

## Physical Buttons (4 total)

All three labeled buttons are **K6-6140S01** — LED-backlit tactile switches:

| Button | Net | LED net | Notes |
|---|---|---|---|
| SW1 | K1 | K1-LED (IO06) | Via R34 (1K) |
| SW2 | K2 | K2-LED (IO05) | Via R35 (1K) |
| SW3 | K3 | K3-LED (IO04) | Via R36 (1K) |
| SW4 | BOOT | TXD0 LED | Boot/flash mode |

Firmware strings called them K1-K4 (`K1 [RRESS]`... `K4 [RRESS]`) — 4th button may be RESET or a separate SW not shown, or BOOT counts as K4.

## USB Programming Interface

**U8: CH340K** — USB to UART bridge
- `USB_P`/`USB_N` → USB Type-C connector (OTG1)
- `TXD0`/`RXD0` → ESP32 UART
- `RST#`/`DTR#` → U6 (EMM412R dual transistor) → auto-reset/boot circuit for esptool

This allows `esptool` over USB-C to flash the device without pressing buttons manually. The auto-reset circuit (RST# + DTR# via U6) matches standard Arduino/ESP32 programmer behavior.

## Key Hardware Insights for Klipper Integration

1. **`warehouse_temper` is a real NTC ADC reading** — not calculated, not estimated. Two separate physical sensors.

2. **PTC heater is relay-switched (on/off only)** — the firmware duty-cycles the relay for temperature regulation. Klipper doesn't need to know about this; we just tell the device to be on or off.

3. **Fan speed is phase-angle TRIAC controlled** — firmware manages this internally based on mode. Not exposed in the WebSocket API as a user-settable value (no `fan_speed` write field confirmed).

4. **Four physical buttons on the device** — on v0.0.0, button presses do NOT push WebSocket messages (community-confirmed). The module must poll to detect out-of-band state changes rather than relying on push notifications.

5. **`cal_warehouse_temp` is preferred over `warehouse_temper`** — the firmware runs NTC calibration (`adc_cali_raw_to_voltage` with calibration scheme) to produce a corrected reading. Use `cal_warehouse_temp` if available; fall back to `warehouse_temper`.
