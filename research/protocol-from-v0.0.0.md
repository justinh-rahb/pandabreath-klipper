# Panda Breath WebSocket Protocol — Source of Truth

Derived from the **v0.0.0 full flash dump** (clean `esptool flash_read` of a real device).
The web UI JavaScript is embedded in the app binary and was extracted via `strings`. This is the definitive protocol reference.

## Flash Dump Analysis

- Source: `Panda_Breath/Firmware/0.0.0/0.0.0.0_clean.bin` — full 4MB flash read from real device
- Chip: ESP32-C3, compiled Aug 25 2025 14:26:17, ESP-IDF v5.1.4-dirty
- Web UI assets are embedded directly in the app firmware (not in SPIFFS — which is erased/empty on the dump)
- Partition layout:

| Partition | Type | Offset | Size |
|---|---|---|---|
| nvs | data/nvs | 0x9000 | 20K |
| otadata | data/otadata | 0xE000 | 8K |
| app0 | app/ota_0 | 0x10000 | 1920K |
| app1 | app/ota_1 | 0x1F0000 | 1920K |
| spiffs | data/fat | 0x3D0000 | 188K |
| coredump | data/coredump | 0x3FF000 | 4K |

## WebSocket Message Format

All messages are JSON. The top-level key is the **root** which identifies the subsystem. Under that root is an object with one or more field/value pairs.

```js
// JavaScript helper extracted from firmware
function ws_send_data(root, members) {
    let json = {};
    json[root] = members;
    ws_send_json(json);
}
```

So messages look like:
```json
{ "settings": { "work_on": true } }
{ "wifi": { "scan": 1 } }
{ "printer": { "scan": 1 } }
```

## Root Keys

### `settings` — device operation control

| Field | Dir | Type | Notes |
|---|---|---|---|
| `work_on` | →device | bool/int | Enable/disable heating |
| `work_mode` | →device | int | 1=auto, 2=always_on, 3=filament_drying |
| `filament_temp` | →device | int | Filament drying target temperature (°C) |
| `filament_timer` | →device | int | Filament drying duration in **hours** |
| `isrunning` | →device | int | Start (1) / stop (0) drying cycle |
| `reset` | →device | int | Send `{'reset': 1}` to reboot device |
| `factory_reset` | →device | int | Send `{'factory_reset': 1}` to factory reset |
| `language` | →device | string | UI language ID (e.g. `'en'`, `'zh'`) |
| `warehouse_temper` | ←device | float | Current chamber temperature |
| `fw_version` | ←device | string | Firmware version string |
| `work_mode` | ←device | int | Current mode |
| `work_on` | ←device | bool | Current enabled state |
| `filament_drying_mode` | ←device | bool | Filament drying active |
| `remaining_seconds` | ←device | int | Countdown (filament drying) |
| `custom_temp` | ←device | int | Current custom temp setting |
| `custom_timer` | ←device | int | Current custom timer setting |
| `ptc_sensor_status` | ←device | int | PTC sensor health |
| `warehouse_sensor_status` | ←device | int | Chamber sensor health |
| `ptc_heater_status` | ←device | int | PTC heater status |
| `cal_ptc_temp` | ←device | float | Calibrated PTC temp |
| `cal_warehouse_temp` | ←device | float | Calibrated chamber temp |
| `hotbedtemp` | ↔ | int | Bed temp threshold for auto mode |
| `filtertemp` | ↔ | int | Filter temp (TBD: threshold or reading) |
| `app_temp` | ? | int | Unclear — possibly internal |

**Note on `temp` vs `set_temp`:** v0.0.0 JS shows `cJSON temp: %d` on receive — target temp readback from device. The writable field is likely `filament_temp` for drying mode and `hotbedtemp` for auto mode threshold. There is no confirmed general-purpose `set_temp` write — this needs live verification.

### `wifi` — WiFi configuration

| Message | Notes |
|---|---|
| `{'scan': 1}` | Scan for WiFi networks; device responds with scan results |
| `{'ssid': "...", 'password': "..."}` | Connect to a WiFi network |

### `sta` — Station (client WiFi) settings

| Message | Notes |
|---|---|
| `{'hostname': "..."}` | Set mDNS hostname (default appears to be `PandaBreathe` in v0.0.0, `PandaBreath` in later fw) |

### `ap` — Access Point settings

| Message | Notes |
|---|---|
| `{'on': 0}` | Disable AP hotspot |
| `{'on': 1}` | Enable AP hotspot |
| `{'ssid': "...", 'password': "...", 'ip': "..."}` | Configure AP |

### `printer` — Bambu printer binding

| Message | Notes |
|---|---|
| `{'scan': 1}` | Scan for Bambu printers on network (UDP discovery) |
| `{'name': "...", 'sn': "...", 'access_code': "...", 'ip': "..."}` | Bind to a Bambu printer |
| `{'disconnect': 1}` | Disconnect from bound printer |

## Device → Client Push Data (from Bambu MQTT)

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

**These fields will never be populated when using Klipper.** The Klipper module must drive `work_mode: 2` (always_on) and manage auto logic itself.

## OTA Update Protocol

OTA is done via HTTP POST (not WebSocket). Endpoint: `/ota`

Types seen in firmware:
- `ota_fw` — application firmware (max 0x480000 bytes)
- `ota_img` — UI image assets
- `ota_gif` — animation assets
- `ota_get_img` — fetch image from URL

After successful OTA, device requests restart via `ESP_REQ_DELAY_RESTART`.

## Filament Drying Mode Logic (from JS)

```js
// Preset temperatures
btn_pla_click()   → ws_send_data('settings', {'filament_temp': PLA_TEMP})
btn_petg_click()  → ws_send_data('settings', {'filament_temp': PETG_TEMP})

// Custom timer
ws_send_data('settings', {'filament_timer': custom_time_value})  // value in hours
remainingSeconds = custom_time_value * 60 * 60

// Start/stop drying cycle
ws_send_data('settings', {'isrunning': 1})   // start
ws_send_data('settings', {'isrunning': 0})   // stop
// OR triggering by mode:
ws_send_data('settings', {'work_mode': 3})   // enter filament drying mode

// Default drying time: 12 hours
// Hard timeout: "FILAMENT DRYING COMPLETE - 12h elapsed"
```

## NVS Storage Keys

Stored in flash NVS (non-volatile) under the `panda_breath` namespace:

- `wifi_info` — `{hostname, sta.ssid, sta.password, ap.ssid, ap.password, ap.on}`
- `bambu_mqtt_info` — `{name, sn, access_code, ip}` (Bambu printer binding)
- `ui_info` — UI settings
- Settings stored: `settings_temp`, `settings_hotbed_temp`, `work_on`, `current_mode`, `custom_temp`, `custom_timer`

Save triggers seen: `NVS_REQ_SAVE_WIFI`, `NVS_REQ_SAVE_PANDA_BREATH`, `NVS_REQ_FACTORY_RESET`

## Physical Buttons

Device has **4 physical buttons**: K1, K2, K3, K4

Functions TBD from live testing.

## WebSocket Behavior Notes

- Multiple clients can connect simultaneously (`Add Client: %d` / `Del Client: %d` logs)
- Server sends PING frames; clients should respond with PONG (standard WS keepalive)
- Unknown frame types logged as `ws_rcv type: UNKNOW`
- Reconnect handled client-side (device doesn't push reconnect)
- **v0.0.0: button presses and web UI changes do NOT generate WebSocket push messages** (community-confirmed). The device only sends data on its own schedule or in response to commands.
- **No confirmed "get state" request message exists.** The JS `ws_on_open` handler only logs "Connection opened" — it sends nothing to the device after connect. There is no evidence in the embedded JS or firmware strings of a query/poll command that returns full current state.
- **Reconnecting may be the only way to get a fresh state snapshot.** On new client connect the C side logs `Add Client: %d` and the string `init one:%s` appears near `fw_version` — suggesting the device may push an initial state dump to new clients. If this is the case, a reconnect is the equivalent of a state query. **Needs live verification.**
- **For the Klipper module:** since Klipper is the authority on desired state (not the physical buttons), we can track what we last sent and trust that's current. Temperature readings will arrive periodically from `temp_task`. If the connection drops, on reconnect we resend our desired state — no state query needed.

## Klipper Integration Implications

1. Use `work_mode: 2` (always_on) — auto mode needs Bambu MQTT which won't work with Klipper
2. Expose as a Klipper `heater_generic` — Orca Slicer sets chamber temp via `SET_HEATER_TEMPERATURE`; no custom GCodes needed
3. Send `{'settings': {'work_on': true}}` when Klipper sets a non-zero target temperature
4. Send `{'settings': {'work_on': false}}` when target is set to 0
5. Report `warehouse_temper` as current temperature to Klipper
6. For filament drying: expose via standard Klipper temperature interface; Orca/macros can trigger
