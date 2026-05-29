# WebSocket Protocol

> **Status:** Reverse-engineered. Derived from firmware binary strings (v1.0.1–v1.0.4), a historical OEM full-flash dump (v0.0.0), schematic analysis, and live testing by community members.
> No official API documentation exists. BTT has not published firmware source.
>
> Historical reverse-engineering baseline: `v0.0.0` full-flash dump. Current release: **V1.0.4** (May 2026) with native HA MQTT auto-discovery. V1.0.3+ adds Klipper `printer_type` support.

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

The helper function extracted from the historical OEM embedded JavaScript dump:

```js
function ws_send_data(root, members) {
    let json = {};
    json[root] = members;
    ws_send_json(json);
}
```

---

## Roots

### `settings` — Device operation

The primary control and telemetry root.

#### Writable fields (client → device)

| Field | Type | Description |
|---|---|---|
| `work_on` | bool | `true` = heating on, `false` = off |
| `work_mode` | int | `1` = Auto, `2` = Always On, `3` = Filament Drying |
| `set_temp` | int | Legacy WebSocket target temperature used by the module for Always On control |
| `temp` | int | Legacy native-auto target temperature |
| `hotbedtemp` | int | Bed temperature (°C) that triggers Auto mode |
| `filtertemp` | int | Legacy filter trigger temperature |
| `filament_temp` | int | Target temperature for filament drying (°C) |
| `filament_timer` | int | Filament drying duration in **hours** |
| `filament_drying_mode` | int | `1` = PLA, `2` = PETG, `3` = custom (v1.0.3+) |
| `printer_type` | int | `1` = BambuLab, `2` = Klipper (v1.0.3+) — communication mode only, does not change auto-mode behavior |
| `isrunning` | int | `1` = start drying cycle, `0` = stop |
| `reset` | int | `1` = reboot device |
| `factory_reset` | int | `1` = factory reset (clears NVS, WiFi, binding) |
| `language` | string | UI language: `"en"` or `"zh"` |
| `target_temp` | int | Target temperature, 0–60°C (v1.0.4+ HA alias; module mirrors alongside legacy target keys) |
| `filter_temp` | int | Filter trigger temperature, 0–120°C (v1.0.4+) |
| `heater_temp` | int | Heater trigger temperature, 40–120°C (v1.0.4+) |
| `drying_running` | bool | Start/stop drying timer, ON/OFF (v1.0.4+) |

!!! note "Target temperature write field"
    The Klipper stock transport keeps writing the confirmed legacy keys and mirrors compatible v1.0.4 aliases. Normal `work_mode: 2` heater control sends `set_temp` plus `target_temp`; native auto mode sends `temp` plus `target_temp` and `filtertemp` plus `filter_temp`; drying start/stop sends `isrunning` plus `drying_running`. This is intentionally backward-compatible: older firmware should ignore unknown alias keys, while v1.0.4 can consume the newer names if they are accepted on WebSocket.

#### Read-only fields (device → client)

| Field | Type | Description |
|---|---|---|
| `warehouse_temper` | float | Chamber air temperature, raw ADC reading (°C) |
| `cal_warehouse_temp` | float | Chamber air temperature, calibrated (°C) — **prefer this** |
| `cal_ptc_temp` | float | PTC heater element temperature, calibrated (°C) |
| `temp` | int | Target temperature readback |
| `target_temp` | int | Target temperature readback / HA alias (v1.0.4+) |
| `fw_version` | string | Firmware version string |
| `work_on` | bool | Current on/off state |
| `work_mode` | int | Current operating mode |
| `filament_drying_mode` | int | Filament drying mode: 1=PLA, 2=PETG, 3=custom |
| `remaining_seconds` | int | Drying countdown (seconds) |
| `custom_temp` | int | Custom mode temperature setting (40–60°C) |
| `custom_timer` | int | Custom mode timer setting (1–99h) |
| `filtertemp` | int | Filter temperature threshold |
| `filter_temp` | int | Filter temperature threshold alias (v1.0.4+) |
| `heater_temp` | int | Heater trigger temperature (v1.0.4+) |
| `ptc_sensor_status` | int | PTC thermistor health: `0` = OK, `1` = open circuit, `2` = short circuit |
| `warehouse_sensor_status` | int | Chamber thermistor health |
| `ptc_heater_status` | int | PTC heater element status |
| `filament_button` | int | Physical button state (values 1/2/3; v1.0.4+) |
| `chamber_temp` | float | Chamber temperature (v1.0.4+ HA alias for `warehouse_temper`) |
| `drying_running` | bool/string/int | Drying active state; parser accepts `true`/`false`, `1`/`0`, and `ON`/`OFF` |
| `drying_remaining_min` | int | Drying time remaining in minutes (v1.0.4+) |
| `printer_bind` | string | Printer bind status (v1.0.4+) |
| `printer_ip` | string | Bound printer IP (v1.0.4+) |
| `printer_name` | string | Bound printer name (v1.0.4+) |
| `printer_sn` | string | Bound printer serial number (v1.0.4+) |

#### Example commands

```json
// Turn on in always-on mode
{ "settings": { "work_mode": 2 } }
{ "settings": { "set_temp": 45, "target_temp": 45 } }
{ "settings": { "work_on": true } }

// Turn off
{ "settings": { "work_on": false } }

// Set auto mode trigger at 50°C bed temp
{ "settings": { "work_mode": 1 } }
{ "settings": { "temp": 45, "target_temp": 45 } }
{ "settings": { "filtertemp": 30, "filter_temp": 30 } }
{ "settings": { "hotbedtemp": 50 } }

// Start filament drying at 55°C for 6 hours
{ "settings": { "work_mode": 3, "filament_temp": 55, "filament_timer": 6, "isrunning": 1, "drying_running": true } }

// Stop drying
{ "settings": { "isrunning": 0, "drying_running": false } }

// Reboot
{ "settings": { "reset": 1 } }

// Factory reset
{ "settings": { "factory_reset": 1 } }
```

#### Example device push

```json
{ "settings": { "warehouse_temper": 38.5 } }
{ "settings": { "cal_warehouse_temp": 37.9 } }
{ "settings": { "work_on": true, "work_mode": 2 } }
{ "settings": { "fw_version": "V1.0.4" } }
{ "settings": { "printer_type": 2 } }
{ "settings": { "filament_button": 1 } }
{ "settings": { "chamber_temp": 38.5, "target_temp": 45 } }
{ "settings": { "drying_running": "ON", "drying_remaining_min": 72 } }
```

---

### Native MQTT (v1.0.4+)

v1.0.4 adds a `btt_mqtt` client that connects to a user-configured MQTT broker and publishes Home Assistant auto-discovery configs. This is independent of the Bambu `bambu_mqtt` client.

**Topic structure:**
```
<prefix>/<device_id>/state         # JSON state (published by device)
<prefix>/<device_id>/command       # JSON commands (subscribed by device)
<prefix>/<device_id>/availability  # "online" / "offline" (LWT)
```

**HA auto-discovery entities** are published to `homeassistant/...` topics covering: `chamber_temp`, `work_on`, `mode`, `filament_drying_mode`, `target_temp` (0–60°C), `filter_temp` (0–120°C), `heater_temp` (40–120°C), `custom_temp` (40–60°C), `custom_timer` (1–99h), `drying_running`, `drying_remaining_min`, `printer_sn`, `printer_bind`, `printer_ip`, `printer_name`.

The MQTT command payloads use JSON matching the WS `settings` format (e.g. `{"target_temp": 45}`, `{"work_on": "ON"}`).

**NVS key:** `ha_mqtt_info` — stores broker IP, port, username, password.

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

!!! warning
    Modifying AP settings while connected via AP will disconnect you.

---

### `printer` — Bambu printer binding

| Message | Description |
|---|---|
| `{ "printer": { "scan": 1 } }` | Discover Bambu printers on the local network (UDP) |
| `{ "printer": { "name": "...", "sn": "...", "access_code": "...", "ip": "..." } }` | Bind to a Bambu printer |
| `{ "printer": { "disconnect": 1 } }` | Disconnect from bound printer |

!!! note "Klipper note"
    The baseline Klipper heater path in this repo uses `work_mode: 2` (Always On). Recent module builds also expose raw passthrough commands for the device's native auto-mode settings. V1.0.3 added `printer_type: 2` (Klipper) as a selectable communication mode — this controls how the device communicates to the host, not auto-mode behavior.

When connected to a Bambu printer, the device subscribes to `device/<sn>/report` via MQTT over TLS and pushes these fields to WebSocket clients:

| Field | Description |
|---|---|
| `gcode_state` | Current print state (idle/printing/paused/failed/etc.) |
| `nozzle_temper` | Nozzle temperature |
| `bed_temper` | Bed current temperature |
| `bed_target_temper` | Bed target temperature |
| `ams_status` | AMS filament system status |
| `print_error` | Error code |
| `mc_remaining_time` | Remaining print time (minutes) |
| `mc_remaining` | Remaining percentage |
| `chamber_light` | Chamber light on/off |

---

## Operating Modes

| `work_mode` | Name | Behaviour |
|---|---|---|
| `1` | Auto | Heater turns on when printer bed temperature crosses `hotbedtemp` threshold. V1.0.3+ adds `printer_type: 2` (Klipper) as a communication mode. |
| `2` | Always On | Heater runs continuously while `work_on` is true. Target temperature controlled internally. **Use this for Klipper.** |
| `3` | Filament Drying | Runs at `filament_temp` for `filament_timer` hours. Countdown tracked via `remaining_seconds`. Hard timeout at 12 hours. |

### Filament drying logic (from embedded JS)

```js
// Set filament type preset temperature
ws_send_data('settings', { filament_temp: PLA_TEMP })   // PLA preset
ws_send_data('settings', { filament_temp: PETG_TEMP })  // PETG preset

// Set custom timer (value in hours; device converts to seconds internally)
ws_send_data('settings', { filament_timer: 6 })

// Start / stop drying cycle
ws_send_data('settings', { isrunning: 1 })   // start
ws_send_data('settings', { isrunning: 0 })   // stop

// Default drying time: 12 hours (hard timeout)
```

---

## OTA Update Protocol

OTA is done via HTTP POST (not WebSocket). Endpoint: `/ota`

| Type | Description |
|---|---|
| `ota_fw` | Application firmware (max 0x480000 bytes) |
| `ota_img` | UI image assets |
| `ota_gif` | Animation assets |
| `ota_get_img` | Fetch image from URL |

After successful OTA, device requests restart via `ESP_REQ_DELAY_RESTART`.

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

| Key | Contents |
|---|---|
| `wifi_info` | WiFi SSID, password, hostname, AP config |
| `bambu_mqtt_info` | Bound printer name, serial, access code, IP |
| `ha_mqtt_info` | HA broker IP, port, username, password (v1.0.4+) |
| `ui_info` | Language and UI settings |
| `panda_breath` namespace | `settings_temp`, `settings_hotbed_temp`, `work_on`, `current_mode`, `custom_temp`, `custom_timer` |

Save triggers observed in firmware: `NVS_REQ_SAVE_WIFI`, `NVS_REQ_SAVE_PANDA_BREATH`, `NVS_REQ_FACTORY_RESET`

---

## Hardware Summary

| Component | Detail |
|---|---|
| MCU | ESP32-C3 |
| Heater control | Solid-state relay (on/off; firmware duty-cycles for regulation) |
| Fan control | TRIAC phase-angle (speed managed internally) |
| Chamber sensor | NTC 100K thermistor → `warehouse_temper` / `cal_warehouse_temp` |
| PTC sensor | NTC 100K thermistor (thermal protection only) |
| USB | CH340K UART bridge for flashing |

---

*Derived from: firmware binary strings analysis, full flash dump JavaScript extraction, schematic reverse engineering, and community testing. No official documentation from BTT exists.*
