# printer.cfg Reference

## Configuration options

=== "Stock firmware"

    ```ini
    [panda_breath]
    firmware: stock
    host: PandaBreath.local   # mDNS hostname or IP address
    port: 80                  # WebSocket port (default: 80)
    ```

    | Option | Type | Default | Description |
    |---|---|---|---|
    | `firmware` | string | `stock` | Transport to use: `stock` or `esphome` |
    | `host` | string | — | **Required.** Hostname or IP of the Panda Breath |
    | `port` | int | `80` | WebSocket port |

=== "ESPHome firmware"

    ```ini
    [panda_breath]
    firmware: esphome
    mqtt_broker: 192.168.1.x     # IP of your MQTT broker
    mqtt_port: 1883              # MQTT port (default: 1883)
    mqtt_topic_prefix: panda-breath   # ESPHome topic prefix (default: panda-breath)
    ```

    | Option | Type | Default | Description |
    |---|---|---|---|
    | `firmware` | string | `stock` | Transport to use: `stock` or `esphome` |
    | `mqtt_broker` | string | — | **Required.** IP address of the MQTT broker |
    | `mqtt_port` | int | `1883` | MQTT broker port |
    | `mqtt_topic_prefix` | string | `panda-breath` | Must match `topic_prefix` in ESPHome YAML |

The module registers itself as a Klipper `heater_generic` named `panda_breath` and a temperature sensor. No additional `[heater_generic]` or `[temperature_sensor]` blocks are needed.

---

## Behaviour

=== "Stock firmware"

    | Condition | Action |
    |---|---|
    | Klipper sets `TARGET > 0` | Sends `{"settings": {"work_mode": 2, "work_on": true, "temp": TARGET}}` |
    | Klipper sets `TARGET = 0` | Sends `{"settings": {"work_on": false}}` |
    | `cal_warehouse_temp` received | Reported as current temperature (preferred) |
    | `warehouse_temper` received | Reported as current temperature (fallback) |
    | WebSocket drops | Reconnects; resends last command |

=== "ESPHome firmware"

    | Condition | Action |
    |---|---|
    | Klipper sets `TARGET > 0` | Publishes `TARGET` to `…/climate/chamber/target_temperature/set` and `heat` to `…/climate/chamber/mode/set` |
    | Klipper sets `TARGET = 0` | Publishes `off` to `…/climate/chamber/mode/set` |
    | `…/sensor/chamber_temperature/state` received | Reported as current temperature |
    | MQTT connection drops | Reconnects; republishes last command |

The device manages all heater duty-cycling and fan speed control internally. The module only tells it to be on or off and at what target temperature.

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
description: Run filament drying at target temp
gcode:
    {% set TEMP = params.TEMP|default(55)|int %}
    {% set HOURS = params.HOURS|default(6)|int %}
    SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET={TEMP}
    TEMPERATURE_WAIT SENSOR="heater_generic panda_breath" MINIMUM={TEMP - 2}
    M117 Drying filament at {TEMP}C for {HOURS}h
```

!!! note
    The Panda Breath's built-in filament drying mode (with countdown timer) uses `work_mode: 3` internally. Via Klipper, the simplest approach is to use always-on mode and let a macro or timer handle duration.

### Chamber cooldown / print end

```ini
[gcode_macro CHAMBER_OFF]
description: Turn off Panda Breath
gcode:
    SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=0
```

---

## Orca Slicer integration

Orca Slicer sets chamber temperature automatically based on the filament profile. Set the **Chamber temperature** field in your filament profile. Orca will emit:

```gcode
SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=<temp>
```

at the start of prints that require chamber heating, and `TARGET=0` at the end. No custom slicer GCode is needed.

---

## Safety notes

- The Panda Breath reaches up to 60°C chamber temperature
- **Stock firmware (v0.0.0):** PTC thermal runaway detection is present in the device firmware. v1.0.2 removed this — use v0.0.0 only
- **ESPHome firmware:** thermal runaway protection is implemented directly in the ESPHome config (`esphome/panda_breath.yaml`) and does not depend on BTT firmware
- The stock WebSocket has no authentication — LAN use only
- Always disconnect mains AC before servicing the device
