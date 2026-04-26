# Panda Breath Firmware Integration Handoff

This handoff is for the next agent working in the separate firmware integration repo that consumes `pandabreath-klipper`.

This file is intentionally scoped to the downstream integration work. Do not implement that work in this repo.

## Source branch and commits

Use this branch from `justinh-rahb/pandabreath-klipper` as the source of truth:

- Branch: `panda-breath-conservative-hardening`
- Commit `6487234` `fix: harden Panda Breath stock control path`
- Commit `4a399e6` `feat: add Panda Breath native auto mode support`
- Commit `29e94d1` `feat: add Panda Breath native drying mode support`

## What is now available in this repo

The backend now supports three stock-firmware control paths:

- Manual chamber heating through standard `heater_generic` control
  - Panda `work_mode: 2`
- Native Panda auto mode
  - `PANDA_BREATH_AUTO ENABLE=<0|1> TARGET=<C> FILTERTEMP=<C> HOTBEDTEMP=<C>`
  - Panda `work_mode: 1`
- Native Panda drying mode
  - `PANDA_BREATH_DRY_START TEMP=<C> HOURS=<1-12>`
  - `PANDA_BREATH_DRY_STOP`
  - Panda `work_mode: 3`

Safety hardening already implemented here:

- ordered stock WebSocket writes for better `v1.0.3` compatibility
- explicit fail-off on Klipper connect, disconnect, and shutdown
- stale target lockout after forced-off events
- better heater target synchronization with Moonraker/Mainsail
- `verify_heater` timing fix using MCU print time

## Product direction for the firmware integration repo

Replace the current binary Panda Breath enable/disable setting with a three-state mode:

- `disabled`
- `auto`
- `manual`

Recommended labels:

- `Disabled`
- `Auto (Recommended, requires Panda firmware v1.0.3+)`
- `Manual (Legacy fallback, may be less safe)`

Recommended semantics:

- `disabled`
  - no Panda Breath config/module active
- `auto`
  - use hybrid macros that heat with Klipper/manual mode first, then hand off to Panda native auto mode for hold/cool
  - this is the preferred mode for Panda firmware `v1.0.3+`
- `manual`
  - use only standard `SET_HEATER_TEMPERATURE` / manual chamber heating behavior
  - preserve as compatibility fallback for older Panda firmware

## Why `auto` should be preferred

The intent is to use native Panda auto mode for steady-state behavior instead of leaving the device in pure manual mode.

Desired outcome:

- Heat up with Klipper/manual mode when below target.
- Switch to Panda native auto mode once the target is reached or if already above target.
- Turn fully off for `S=0`.

This preserves compatibility while making the default stock-firmware path safer than a pure manual-mode-only workflow.

## Macro strategy to implement in the firmware integration repo

These are the proposed stock-firmware macros for the `auto` mode path:

```ini
[gcode_macro M141]
description: Set chamber temperature (heat with Klipper, hold/cool with Panda auto)
gcode:
    {% set s = params.S|default(0)|float %}
    {% set current = printer["heater_generic panda_breath"].temperature|float %}
    {% set filtertemp = params.FILTERTEMP|default(30)|int %}
    {% set hotbedtemp = params.HOTBEDTEMP|default(80)|int %}
    {% if s <= 0 %}
        PANDA_BREATH_AUTO ENABLE=0
        SET_HEATER_TEMPERATURE HEATER="panda_breath" TARGET=0
    {% elif s > current %}
        SET_HEATER_TEMPERATURE HEATER="panda_breath" TARGET={s}
    {% else %}
        PANDA_BREATH_AUTO ENABLE=1 TARGET={s} FILTERTEMP={filtertemp} HOTBEDTEMP={hotbedtemp}
    {% endif %}

[gcode_macro M191]
description: Reach and hold chamber temperature
gcode:
    {% set s = params.S|default(0)|float %}
    {% set current = printer["heater_generic panda_breath"].temperature|float %}
    {% set filtertemp = params.FILTERTEMP|default(30)|int %}
    {% set hotbedtemp = params.HOTBEDTEMP|default(80)|int %}
    {% if s <= 0 %}
        M141 S0
    {% elif current < s %}
        SET_HEATER_TEMPERATURE HEATER="panda_breath" TARGET={s}
        TEMPERATURE_WAIT SENSOR="heater_generic panda_breath" MINIMUM={s}
        PANDA_BREATH_AUTO ENABLE=1 TARGET={s} FILTERTEMP={filtertemp} HOTBEDTEMP={hotbedtemp}
    {% else %}
        PANDA_BREATH_AUTO ENABLE=1 TARGET={s} FILTERTEMP={filtertemp} HOTBEDTEMP={hotbedtemp}
        TEMPERATURE_WAIT SENSOR="heater_generic panda_breath" MAXIMUM={s}
    {% endif %}
```

Notes for the next agent:

- These are hybrid macros, not pure auto-only macros.
- Below target: heat with Klipper/manual mode.
- At or above target: hand off to Panda native auto mode.
- Manual fallback mode should keep the older simpler `SET_HEATER_TEMPERATURE` behavior.
- Consider adding a small temperature tolerance when finalizing these macros to avoid sensor-noise flapping.

## Expected firmware integration changes

In the firmware integration repo:

1. Replace the binary Panda Breath setting with `disabled|auto|manual`.
2. Gate `auto` mode behind Panda firmware `v1.0.3+`.
3. Keep `manual` available as a legacy fallback.
4. Make the warning text mode-specific:
   - `auto`: recommended, requires `v1.0.3+`
   - `manual`: may be less safe if connectivity is lost
5. Ship the appropriate config template/macros for each mode.

## Suggested user-facing wording

Use wording along these lines:

- `Auto (Recommended, requires Panda firmware v1.0.3+)`
- `Manual (Legacy fallback, may be less safe on disconnect)`

The key point is that the warning belongs on `manual`, not on the whole Panda Breath integration.

## Acceptance criteria for the next repo

- Users can choose `disabled`, `auto`, or `manual`.
- `auto` mode installs macros that use `PANDA_BREATH_AUTO` after heat-up / for hold behavior.
- `manual` mode installs the older pure manual heating behavior.
- `auto` mode is clearly documented as requiring Panda firmware `v1.0.3+`.
- `manual` mode is clearly documented as a fallback that may be less safe.

## Out of scope for the next repo

- Further changes to `pandabreath-klipper` itself unless a real integration gap is discovered

