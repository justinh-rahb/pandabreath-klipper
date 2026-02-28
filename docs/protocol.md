# BIQU Panda Breath — WebSocket Protocol Documentation

> **Status:** Reverse-engineered. Derived from firmware binary strings, full flash dump (v0.0.0) embedded JavaScript source, schematic analysis, and live testing by community members.
> No official API documentation exists. BTT has not published firmware source.
>
> Tested firmware: **v0.0.0** (confirmed working), v1.0.1 and v1.0.2 have known stability issues.

---

## Connection

| Property | Value |
|---|---|
| Protocol | WebSocket (RFC 6455) |
| URL | `ws://<device-ip>/ws` |
| Port | 80 |
| Authentication | None |
| Concurrent clients | Multiple supported |
| Hostname (mDNS) | `PandaBreath.local` |
| AP fallback IP | `192.168.254.1` |
| AP SSID format | `Panda_Breath_XXXXXXXXXXXX` (MAC-based) |
| AP password | `987654321` (default) |

The device responds to HTTP as well as WebSocket upgrades on port 80. The web UI is served from `/` (assets embedded in firmware). OTA update is via HTTP POST to `/ota`.

---

## Message Format

All messages are JSON. The top-level key is a **root** that identifies the subsystem. Under it is an object with one or more field/value pairs.

**Sending a command:**
```json
{ "<root>": { "<field>": <value>, ... } }
```

**Receiving state:**
```json
{ "settings": { "warehouse_temper": 38.5 } }
```

The device sends fields individually or in small groups — not necessarily a full state dump in one message.

---

## Roots

### `settings` — Device operation

The primary control and telemetry root.

#### Writable fields (client → device)

| Field | Type | Description |
|---|---|---|
| `work_on` | bool | `true` = heating on, `false` = off |
| `work_mode` | int | `1` = Auto, `2` = Always On, `3` = Filament Drying |
| `hotbedtemp` | int | Bed temperature (°C) that triggers Auto mode |
| `filament_temp` | int | Target temperature for filament drying (°C) |
| `filament_timer` | int | Filament drying duration in **hours** |
| `isrunning` | int | `1` = start drying cycle, `0` = stop |
| `reset` | int | `1` = reboot device |
| `factory_reset` | int | `1` = factory reset (clears NVS, WiFi, binding) |
| `language` | string | UI language: `"en"` or `"zh"` |

> **Note on target temperature:** The field for setting the general heating target temperature has not been confirmed via live testing. Candidates from firmware strings: `set_temp`, `temp`, `custom_temp`. Use `filament_temp` for drying mode. For always-on mode, the device heats toward its internally stored target.

#### Read-only fields (device → client)

| Field | Type | Description |
|---|---|---|
| `warehouse_temper` | float | Chamber air temperature, raw ADC reading (°C) |
| `cal_warehouse_temp` | float | Chamber air temperature, calibrated (°C) — **prefer this** |
| `cal_ptc_temp` | float | PTC heater element temperature, calibrated (°C) |
| `temp` | int | Target temperature readback |
| `fw_version` | string | Firmware version string |
| `work_on` | bool | Current on/off state |
| `work_mode` | int | Current operating mode |
| `filament_drying_mode` | bool/int | Filament drying cycle active |
| `remaining_seconds` | int | Drying countdown (seconds) |
| `custom_temp` | int | Custom mode temperature setting |
| `custom_timer` | int | Custom mode timer setting |
| `filtertemp` | int | Filter temperature (threshold or reading — TBD) |
| `ptc_sensor_status` | int | PTC thermistor health (`0` = OK, non-zero = fault) |
| `warehouse_sensor_status` | int | Chamber thermistor health |
| `ptc_heater_status` | int | PTC heater element status |

#### Example commands

```json
// Turn on in always-on mode
{ "settings": { "work_on": true, "work_mode": 2 } }

// Turn off
{ "settings": { "work_on": false } }

// Set auto mode trigger at 50°C bed temp
{ "settings": { "work_mode": 1, "hotbedtemp": 50 } }

// Start filament drying at 55°C for 6 hours
{ "settings": { "work_mode": 3, "filament_temp": 55, "filament_timer": 6, "isrunning": 1 } }

// Stop drying
{ "settings": { "isrunning": 0 } }

// Reboot
{ "settings": { "reset": 1 } }
```

#### Example device push

```json
{ "settings": { "warehouse_temper": 38.5 } }
{ "settings": { "cal_warehouse_temp": 37.9 } }
{ "settings": { "work_on": true, "work_mode": 2 } }
{ "settings": { "fw_version": "V1.0.2" } }
```

---

### `wifi` — WiFi configuration

| Message | Description |
|---|---|
| `{ "wifi": { "scan": 1 } }` | Scan for nearby WiFi networks |
| `{ "wifi": { "ssid": "...", "password": "..." } }` | Connect to a WiFi network |

---

### `sta` — Station (client WiFi) settings

| Message | Description |
|---|---|
| `{ "sta": { "hostname": "PandaBreath" } }` | Set mDNS hostname (accessible as `hostname.local`) |

---

### `ap` — Access Point settings

| Message | Description |
|---|---|
| `{ "ap": { "on": 1 } }` | Enable hotspot |
| `{ "ap": { "on": 0 } }` | Disable hotspot |
| `{ "ap": { "ssid": "...", "password": "...", "ip": "..." } }` | Configure hotspot SSID, password, and IP |

> Modifying AP settings while connected via AP will disconnect you.

---

### `printer` — Bambu printer binding

| Message | Description |
|---|---|
| `{ "printer": { "scan": 1 } }` | Discover Bambu printers on the local network (UDP) |
| `{ "printer": { "name": "...", "sn": "...", "access_code": "...", "ip": "..." } }` | Bind to a Bambu printer |
| `{ "printer": { "disconnect": 1 } }` | Disconnect from bound printer |

> **Klipper note:** This subsystem is irrelevant for Klipper printers. The device connects to Bambu printers via MQTT over TLS and reads `bed_temper`, `nozzle_temper`, `gcode_state` etc. to drive Auto mode. This won't work with Klipper — use `work_mode: 2` (Always On) instead.

---

## Operating Modes

| `work_mode` | Name | Behaviour |
|---|---|---|
| `1` | Auto | Heater turns on when printer bed temperature crosses `hotbedtemp` threshold. Requires Bambu MQTT binding to work as designed. |
| `2` | Always On | Heater runs continuously while `work_on` is true. Target temperature controlled internally. **Use this mode for Klipper.** |
| `3` | Filament Drying | Runs at `filament_temp` for `filament_timer` hours. Countdown tracked via `remaining_seconds`. Hard timeout at 12 hours. |

---

## Push Behaviour

- **Temperature** (`warehouse_temper`, `cal_warehouse_temp`) is pushed periodically by the device's internal `temp_task`. No request needed.
- **State changes triggered by buttons or the web UI do NOT generate WebSocket messages** (confirmed on v0.0.0). The device does not broadcast unsolicited state changes.
- **No confirmed "get state" request command exists.** The device may push an initial state snapshot when a new client connects (seen pattern: `init one:` + `fw_version` in firmware logs). Reconnecting is the likely mechanism to re-sync state. **Unverified on live hardware.**
- On initial connect the web UI sends nothing — it just waits for incoming messages.

---

## Connection Lifecycle

```
Client                          Device
  |                               |
  |--- WebSocket upgrade -------->|
  |<-- 101 Switching Protocols ---|  "Add Client: N"
  |                               |
  |<-- (initial state push?) -----|  "init one:fw_version" (unverified)
  |<-- warehouse_temper ----------|  periodic from temp_task
  |<-- cal_warehouse_temp --------|  periodic
  |                               |
  |--- {"settings":{"work_on":true}} ->|
  |                               |
  |<-- (ack or silence) ----------|  unverified
  |                               |
  |--- PING ----------------------|  WS keepalive
  |<-- PONG ----------------------|
  |                               |
  |--- close ------------------->|
  |                               |  "Del Client: N"
```

---

## NVS Persistent Storage

Settings are saved to ESP32 NVS flash under the `panda_breath` namespace. The following are persisted across reboots:

- `wifi_info` — WiFi SSID, password, hostname, AP config
- `bambu_mqtt_info` — Bound printer name, serial, access code, IP
- `ui_info` — Language and UI settings
- `panda_breath` namespace — `settings_temp`, `settings_hotbed_temp`, `work_on`, `current_mode`, `custom_temp`, `custom_timer`

---

## Hardware Summary (for context)

| Component | Detail |
|---|---|
| MCU | ESP32-C3 |
| Heater control | Solid-state relay (on/off; firmware duty-cycles for regulation) |
| Fan control | TRIAC phase-angle (speed managed internally) |
| Chamber sensor | NTC 100K thermistor → `warehouse_temper` / `cal_warehouse_temp` |
| PTC sensor | NTC 100K thermistor (thermal protection only, not for user targeting) |
| USB | CH340K UART bridge for flashing |
| Flashing | `esptool.py --chip esp32c3 --port /dev/ttyUSB0 --baud 460800 write-flash 0x0 <image.bin>` |

---

## Known Issues (v1.0.1 / v1.0.2)

- Thermal/timing regressions introduced in v1.0.1 — self-calibration code present in v1.0.1 was removed or rewritten in v1.0.2 without clear improvement
- Some fields (target temperature write, auto mode trigger) may behave unreliably on v1.0.1+
- v0.0.0 (Aug 2025) is the only community-confirmed stable firmware

---

*Derived from: firmware binary strings analysis, full flash dump JavaScript extraction, schematic reverse engineering, and community testing. No official documentation from BTT exists.*
