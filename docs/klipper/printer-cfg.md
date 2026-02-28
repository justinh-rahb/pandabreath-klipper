# printer.cfg Reference

## Module configuration

```ini
[panda_breath]
host: PandaBreath.local   # mDNS hostname or IP address
port: 80                  # WebSocket port (default: 80)
```

| Option | Type | Default | Description |
|---|---|---|---|
| `host` | string | — | **Required.** Hostname or IP of the device |
| `port` | int | `80` | WebSocket port |

The module registers itself as a Klipper `heater_generic` named `panda_breath` and a temperature sensor. No additional `[heater_generic]` or `[temperature_sensor]` blocks are needed.

---

## Behaviour

| Condition | Action |
|---|---|
| Klipper sets `TARGET > 0` | Sends `work_mode: 2, work_on: true` |
| Klipper sets `TARGET = 0` | Sends `work_on: false` |
| `cal_warehouse_temp` received | Reported as current temperature |
| `warehouse_temper` received (fallback) | Reported if `cal_warehouse_temp` absent |
| WebSocket drops | Reconnects; resends last desired state |

The device manages all heater duty-cycling and fan speed internally. The module only tells it to be on or off.

---

## Sample macros

### Pre-heat chamber before print

```ini
[gcode_macro PREHEAT_CHAMBER]
description: Pre-heat chamber to target and wait
gcode:
    {% set TARGET = params.TEMP|default(45)|int %}
    SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET={TARGET}
    TEMPERATURE_WAIT SENSOR="heater_generic panda_breath" MINIMUM={TARGET - 2}
    M117 Chamber ready
```

Usage from slicer start GCode:
```gcode
PREHEAT_CHAMBER TEMP=45
```

### Filament drying

```ini
[gcode_macro DRY_FILAMENT]
description: Run filament drying cycle at target temp for given hours
gcode:
    {% set TEMP = params.TEMP|default(55)|int %}
    {% set HOURS = params.HOURS|default(6)|int %}
    SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET={TEMP}
    M117 Drying filament at {TEMP}C for {HOURS}h
```

!!! note
    The Panda Breath's built-in filament drying mode (with countdown timer) is triggered via `work_mode: 3` over WebSocket. From Klipper, the simplest approach is to use always-on mode (`work_mode: 2`) and let a Klipper timer macro handle the duration.

### Chamber cooldown / print end

```ini
[gcode_macro CHAMBER_OFF]
description: Turn off Panda Breath
gcode:
    SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=0
```

---

## Orca Slicer integration

Orca Slicer sets chamber temperature automatically based on the filament profile. In **Printer Settings → General**, set:

```
Chamber temperature: [HEATER_NAME]
```

Orca will then emit `SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=<temp>` at the start of prints that require chamber heating, and `TARGET=0` at the end.

No custom slicer GCode is needed — this works out of the box with any heater registered in Klipper.

---

## Safety notes

- The Panda Breath reaches up to 60°C chamber temperature
- The module does not implement independent thermal-runaway detection — it relies on the device's built-in PTC sensor monitoring (present in v0.0.0; may have regressed in v1.0.1+)
- The WebSocket has no authentication — only use on a trusted local network
- Always ensure mains AC is disconnected before servicing the device
