# Research Methodology

This page explains how the Panda Breath WebSocket protocol was reverse-engineered, what evidence each finding is based on, and what remains unverified. It provides the intellectual foundation for the confidence levels assigned throughout this documentation.

BTT has not published firmware source code. All protocol knowledge is derived from the techniques described here.

---

## Why reverse engineering?

BIQU/BTT released the Panda Breath hardware under CC-BY-NC-ND-4.0, but the firmware source has not been published. The [BTT GitHub repo](https://github.com/bigtreetech/Panda_Breath) contains only firmware binaries, 3D models, and documentation. There is no official WebSocket API documentation.

For Klipper integration to be possible, the protocol must be understood. The three primary sources are:

1. **Binary string extraction** from the released firmware binaries
2. **Full flash dump** of a real device running v0.0.0, which contains embedded web UI JavaScript
3. **Hardware schematic** traced from a real device

---

## Technique 1: Binary string extraction

The released firmware binaries (`panda_breath_v1.0.1.bin`, `panda_breath_v1.0.2.bin`) are ESP32-C3 app images — unencrypted, unsigned. They can be inspected directly.

**Tools used:**
```sh
esptool.py image_info --version 2 panda_breath_v1.0.1.bin
strings -n 4 panda_breath_v1.0.1.bin > strings_v1.0.1.txt
strings -n 4 panda_breath_v1.0.2.bin > strings_v1.0.2.txt
```

The `strings` output reveals:
- JSON field names used in WebSocket messages (`work_on`, `warehouse_temper`, `filament_temp`, etc.)
- RTOS task names (`temp_task`, `ptc_task`, `mqtt_task`, etc.)
- Log format strings that reveal internal logic (e.g. PTC thermal runaway detection strings in v1.0.1)
- HTTP endpoints (`/ota`, `/generate_204`)
- MQTT topic patterns (`device/%s/report`, `device/%s/request`)
- mDNS service name and AP SSID format

**Limitation:** String extraction reveals field *names* but not their data types, direction (read vs write), or valid values. It cannot reveal control flow or how fields are processed.

---

## Technique 2: Full flash dump (v0.0.0)

A community member ran a real Panda Breath device running factory firmware v0.0.0 and performed a full 4MB flash read:

```sh
esptool.py --chip esp32c3 --port /dev/ttyUSB0 --baud 460800 \
  read_flash 0x0 0x400000 0.0.0.0_clean.bin
```

The device was factory-reset before the dump to ensure clean NVS.

**What the dump contains:**

The v0.0.0 firmware embeds the web UI JavaScript directly in the app binary's DROM segment (not in SPIFFS, which was erased). Running `strings -n 4` on the extracted `app0` partition reveals complete JavaScript source including:

```js
function ws_send_data(root, members) {
    let json = {};
    json[root] = members;
    ws_send_json(json);
}
```

This function, and the click handlers that call it, provide the **definitive protocol reference**:
- All root keys (`settings`, `wifi`, `sta`, `ap`, `printer`)
- Exact field names and which root they belong to
- Direction (what the UI sends vs what it receives)
- Data types (bool vs int vs string)
- The `isrunning` start/stop pattern for filament drying
- Filament timer units (hours, converted to seconds client-side)
- `factory_reset` and `reset` commands

This is the highest-confidence source. The JavaScript is the client that was designed to talk to this firmware — it is authoritative for v0.0.0.

**Partition table** was extracted by parsing the binary at offset `0x8000` using the ESP-IDF partition table format.

---

## Technique 3: Hardware schematic

A hardware schematic was traced from a real Panda Breath device and provided by a community member. It is hand-traced, not extracted from CAD, so minor component values may have tolerance errors — but the topology and chip identifications are reliable.

The schematic provided:
- Exact GPIO assignments for the ESP32-C3
- Confirmation that the PTC heater is relay-switched (on/off only, no PWM)
- Fan speed control via TRIAC phase-angle (confirms why there is no `fan_speed` WebSocket field)
- Two separate NTC 100K thermistor circuits (one for chamber temp, one for PTC thermal protection)
- Voltage divider values for thermistor circuits (33K 0.1% reference resistors)
- Identification of CH340K as the USB-UART bridge (explains the esptool auto-reset behavior)
- Power chain (HLK-PM01 → AS1117-3.3)

---

## Technique 4: Community live testing

Community members have tested the device on v0.0.0 via direct WebSocket connections. Key confirmed behaviors:

- Physical button presses **do not** generate WebSocket push messages
- Temperature is pushed periodically without any request
- Multiple simultaneous WebSocket clients are supported
- The mDNS hostname is `PandaBreath.local` (corrected from `PandaBreathe` in v0.0.0)

---

## What remains unverified

The following require live device testing to confirm:

| Question | Status |
|---|---|
| Does the device push an initial state snapshot on new client connect? | Unverified — `init one:` pattern seen in firmware strings suggests it might |
| Which field sets the general target temperature for always-on mode? | Unverified — candidates: `set_temp`, `temp`, `custom_temp` |
| What does `filtertemp` represent — a threshold or a sensor reading? | Unverified |
| Does `app_temp` have a meaningful function? | Unverified |
| Do v1.0.1/v1.0.2 behavior changes affect which fields work? | Partially — thermal calibration strings were removed in v1.0.2 |
| What is the WebSocket message rate for temperature updates? | Unverified |
| Is there a version check or rollback prevention in the OTA flow? | Unverified |

---

## Confidence levels used in documentation

Throughout this documentation:

- **Confirmed** — present in embedded JS source or directly observed in live testing
- **From binary strings** — field name confirmed via `strings` extraction; behavior inferred
- **Unverified** — inferred from firmware strings or log patterns but not confirmed on live hardware
- **TBD** — purpose unknown; needs live device probing
