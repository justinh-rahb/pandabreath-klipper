# printer.cfg Reference

## Configuration options

=== "Stock firmware"

    ```ini
    [panda_breath]
    firmware: stock
    host: PandaBreath.local
    port: 80

    [heater_generic panda_breath]
    heater_pin: panda_breath:pwm
    sensor_type: panda_breath
    control: watermark
    max_delta: 0.5
    min_temp: 15
    max_temp: 80

    [verify_heater panda_breath]
    check_gain_time: 360
    hysteresis: 5
    heating_gain: 1
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
    mqtt_broker: 192.168.1.10
    mqtt_port: 1883
    mqtt_topic_prefix: panda-breath

    [heater_generic panda_breath]
    heater_pin: panda_breath:pwm
    sensor_type: panda_breath
    control: watermark
    max_delta: 0.5
    min_temp: 15
    max_temp: 80

    [verify_heater panda_breath]
    check_gain_time: 360
    hysteresis: 5
    heating_gain: 1
    ```

    | Option | Type | Default | Description |
    |---|---|---|---|
    | `firmware` | string | `stock` | Transport to use: `stock` or `esphome` |
    | `mqtt_broker` | string | — | **Required.** IP address of the MQTT broker |
    | `mqtt_port` | int | `1883` | MQTT broker port |
    | `mqtt_topic_prefix` | string | `panda-breath` | Must match the ESPHome topic prefix |

The module does **not** create the heater section for you. It registers a custom sensor type and a virtual heater pin so you can define a normal `[heater_generic panda_breath]`.

---

## Behaviour

=== "Stock firmware"

    | Condition | Action |
    |---|---|
    | Klipper sets `TARGET > 0` | Sends `isrunning: 0`, `work_mode: 2`, `set_temp: TARGET`, then `work_on: true` |
    | Klipper sets `TARGET = 0` | Sends `isrunning: 0`, then `work_on: false` |
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

## Stock-only optional commands

These commands are available only with `firmware: stock`:

| Command | Parameters | Purpose |
|---|---|---|
| `PANDA_BREATH_AUTO` | `ENABLE`, `TARGET`, `FILTERTEMP`, `HOTBEDTEMP` | Pass through OEM native auto-mode settings |
| `PANDA_BREATH_DRY_START` | `TEMP`, `HOURS` | Start the OEM drying cycle |
| `PANDA_BREATH_DRY_STOP` | none | Stop the OEM drying cycle |

They are optional advanced controls layered on top of the normal Klipper heater path.

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

### Native auto hold on stock firmware

```ini
[gcode_macro PANDA_AUTO_HOLD]
description: Enable Panda Breath native auto mode
gcode:
    {% set TARGET = params.TARGET|default(45)|int %}
    {% set FILTERTEMP = params.FILTERTEMP|default(30)|int %}
    {% set HOTBEDTEMP = params.HOTBEDTEMP|default(80)|int %}
    PANDA_BREATH_AUTO ENABLE=1 TARGET={TARGET} FILTERTEMP={FILTERTEMP} HOTBEDTEMP={HOTBEDTEMP}
```

### Native drying on stock firmware

```ini
[gcode_macro PANDA_DRY]
description: Start Panda Breath native drying mode
gcode:
    {% set TEMP = params.TEMP|default(55)|int %}
    {% set HOURS = params.HOURS|default(6)|int %}
    PANDA_BREATH_DRY_START TEMP={TEMP} HOURS={HOURS}
```

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
