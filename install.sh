#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

panda_host="PandaBreath.local"
panda_port="80"
firmware="stock"
mqtt_broker=""
mqtt_port="1883"
mqtt_topic_prefix="panda-breath"
target_user="${SUDO_USER:-${USER:-}}"
home_dir="${HOME}"
if [[ -n "$target_user" ]] && command -v getent >/dev/null 2>&1; then
  home_dir="$(getent passwd "$target_user" | cut -d: -f6 || true)"
fi
if [[ -z "$home_dir" ]]; then
  home_dir="${HOME}"
fi

klipper_dir="${home_dir}/klipper"
extras_dir=""
config_dir="${home_dir}/printer_data/config"
printer_cfg=""
fragment=""
module_source="${repo_dir}/panda_breath.py"
template_dir="${repo_dir}/config"
link_module=0
include_fragment=1
with_macros=1
no_backup=0
dry_run=0
restart_klipper=0
service_name="klipper"

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]

Install panda_breath.py into a generic Klipper host and create a config fragment.
Defaults match MainsailOS-style installs:

  ~/klipper/klippy/extras/panda_breath.py
  ~/printer_data/config/panda_breath.cfg
  ~/printer_data/config/printer.cfg

Options:
  --host HOST                 Panda Breath host for stock firmware config
  --port PORT                 Panda Breath WebSocket port
  --firmware stock|esphome    Config fragment type
  --mqtt-broker HOST          MQTT broker for --firmware esphome
  --mqtt-port PORT            MQTT broker port
  --mqtt-topic-prefix PREFIX  ESPHome MQTT topic prefix
  --klipper-dir PATH          Klipper checkout path
  --extras-dir PATH           Klipper extras directory
  --config-dir PATH           Printer config directory
  --printer-cfg PATH          printer.cfg path
  --fragment PATH             Generated Panda Breath fragment path
  --module-source PATH        panda_breath.py source path
  --template-dir PATH         Config template directory
  --link                      Symlink module instead of copying
  --no-include                Do not edit printer.cfg
  --no-macros                 Do not add M141/M191 macros to the fragment
  --no-backup                 Do not create timestamped backups
  --dry-run                   Print planned changes without writing files
  --restart                   Restart Klipper after installing
  --service NAME              Systemd service to restart
  -h, --help                  Show this help

Stock firmware binding is intentionally separate:
  python3 panda_breath_cli.py bind-klipper --host HOST --printer-ip PRINTER_IP
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

say() {
  echo ">> $*"
}

run() {
  if [[ "$dry_run" -eq 1 ]]; then
    printf 'Would run:'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

backup_file() {
  local path="$1"
  [[ -e "$path" || -L "$path" ]] || return 0
  [[ "$no_backup" -eq 0 ]] || return 0
  local stamp
  stamp="$(date +%Y%m%d-%H%M%S)"
  run cp -p "$path" "${path}.bak-${stamp}"
}

write_file() {
  local path="$1"
  local content="$2"
  if [[ -f "$path" ]] && cmp -s <(printf '%s\n' "$content") "$path"; then
    say "Already up to date: $path"
    return 0
  fi
  backup_file "$path"
  if [[ "$dry_run" -eq 1 ]]; then
    say "Would write $path"
    return 0
  fi
  mkdir -p "$(dirname "$path")"
  local tmp
  tmp="$(mktemp "${path}.tmp.XXXXXX")"
  printf '%s\n' "$content" > "$tmp"
  chmod 0644 "$tmp"
  mv "$tmp" "$path"
  say "Wrote $path"
}

copy_module() {
  local destination="${extras_dir}/panda_breath.py"
  [[ -f "$module_source" ]] || die "Module source not found: $module_source"
  if [[ ! -d "$extras_dir" ]]; then
    if [[ "$dry_run" -eq 1 ]]; then
      say "Would require Klipper extras directory: $extras_dir"
      say "Would copy $module_source -> $destination"
      return 0
    fi
    die "Klipper extras directory not found: $extras_dir"
  fi

  if [[ -L "$destination" && "$(readlink "$destination")" == "$module_source" ]]; then
    say "Module already symlinked: $destination"
    return 0
  fi
  if [[ -f "$destination" && ! -L "$destination" ]] && cmp -s "$module_source" "$destination"; then
    say "Module already installed: $destination"
    return 0
  fi

  backup_file "$destination"
  if [[ "$link_module" -eq 1 ]]; then
    if [[ "$dry_run" -eq 1 ]]; then
      say "Would symlink $module_source -> $destination"
    else
      rm -f "$destination"
      ln -s "$module_source" "$destination"
      say "Symlinked $destination"
    fi
  else
    if [[ "$dry_run" -eq 1 ]]; then
      say "Would copy $module_source -> $destination"
    else
      rm -f "$destination"
      cp -p "$module_source" "$destination"
      say "Copied $destination"
    fi
  fi
}

build_fragment() {
  local device_template
  if [[ "$firmware" == "stock" ]]; then
    device_template="${template_dir}/panda_breath.stock.cfg"
  elif [[ "$firmware" == "esphome" ]]; then
    [[ -n "$mqtt_broker" ]] || die "--mqtt-broker is required with --firmware esphome"
    device_template="${template_dir}/panda_breath.esphome.cfg"
  else
    die "Unknown firmware: $firmware"
  fi

  [[ -f "$device_template" ]] || die "Config template not found: $device_template"
  [[ -f "${template_dir}/panda_breath.heater.cfg" ]] || die "Config template not found: ${template_dir}/panda_breath.heater.cfg"
  if [[ "$with_macros" -eq 1 ]]; then
    [[ -f "${template_dir}/panda_breath.macros.cfg" ]] || die "Config template not found: ${template_dir}/panda_breath.macros.cfg"
  fi

  cat <<EOF
# Panda Breath Klipper integration
# Generated by install.sh. Edit values here, then restart Klipper.

EOF
  render_template "$device_template"
  printf '\n'
  render_template "${template_dir}/panda_breath.heater.cfg"
  if [[ "$with_macros" -eq 1 ]]; then
    printf '\n'
    render_template "${template_dir}/panda_breath.macros.cfg"
  fi
}

escape_sed_replacement() {
  printf '%s' "$1" | sed 's/[\/&|\\]/\\&/g'
}

render_template() {
  local template="$1"
  sed \
    -e "s|@PANDA_BREATH_HOST@|$(escape_sed_replacement "$panda_host")|g" \
    -e "s|@PANDA_BREATH_PORT@|$(escape_sed_replacement "$panda_port")|g" \
    -e "s|@MQTT_BROKER@|$(escape_sed_replacement "$mqtt_broker")|g" \
    -e "s|@MQTT_PORT@|$(escape_sed_replacement "$mqtt_port")|g" \
    -e "s|@MQTT_TOPIC_PREFIX@|$(escape_sed_replacement "$mqtt_topic_prefix")|g" \
    "$template"
}

include_line() {
  local cfg_dir frag_dir frag_abs
  if [[ -d "$(dirname "$printer_cfg")" ]]; then
    cfg_dir="$(cd "$(dirname "$printer_cfg")" && pwd)"
  else
    cfg_dir="$(dirname "$printer_cfg")"
  fi
  if [[ -d "$(dirname "$fragment")" ]]; then
    frag_dir="$(cd "$(dirname "$fragment")" && pwd)"
  else
    frag_dir="$(dirname "$fragment")"
  fi
  frag_abs="${frag_dir}/$(basename "$fragment")"
  case "$frag_abs" in
    "$cfg_dir"/*) printf '[include %s]' "${frag_abs#"$cfg_dir"/}" ;;
    *) printf '[include %s]' "$frag_abs" ;;
  esac
}

ensure_include() {
  local include
  include="$(include_line)"
  if [[ -f "$printer_cfg" ]] && grep -Fxq "$include" "$printer_cfg"; then
    say "printer.cfg already includes $(basename "$fragment")"
    return 0
  fi
  backup_file "$printer_cfg"
  if [[ "$dry_run" -eq 1 ]]; then
    say "Would add $include to $printer_cfg"
    return 0
  fi
  mkdir -p "$(dirname "$printer_cfg")"
  if [[ ! -s "$printer_cfg" ]]; then
    printf '%s\n' "$include" > "$printer_cfg"
  elif grep -q '^#\*# <---------------------- SAVE_CONFIG ---------------------->' "$printer_cfg"; then
    local tmp
    tmp="$(mktemp "${printer_cfg}.tmp.XXXXXX")"
    awk -v include="$include" '
      !inserted && /^#\*# <---------------------- SAVE_CONFIG ---------------------->/ {
        print ""
        print include
        print ""
        inserted = 1
      }
      { print }
      END {
        if (!inserted) {
          print ""
          print include
        }
      }
    ' "$printer_cfg" > "$tmp"
    chmod 0644 "$tmp"
    mv "$tmp" "$printer_cfg"
  else
    printf '\n%s\n' "$include" >> "$printer_cfg"
  fi
  say "Added $include to $printer_cfg"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) panda_host="${2:?}"; shift 2 ;;
    --port) panda_port="${2:?}"; shift 2 ;;
    --firmware) firmware="${2:?}"; shift 2 ;;
    --mqtt-broker) mqtt_broker="${2:?}"; shift 2 ;;
    --mqtt-port) mqtt_port="${2:?}"; shift 2 ;;
    --mqtt-topic-prefix) mqtt_topic_prefix="${2:?}"; shift 2 ;;
    --klipper-dir) klipper_dir="${2:?}"; shift 2 ;;
    --extras-dir) extras_dir="${2:?}"; shift 2 ;;
    --config-dir) config_dir="${2:?}"; shift 2 ;;
    --printer-cfg) printer_cfg="${2:?}"; shift 2 ;;
    --fragment) fragment="${2:?}"; shift 2 ;;
    --module-source) module_source="${2:?}"; shift 2 ;;
    --template-dir) template_dir="${2:?}"; shift 2 ;;
    --link) link_module=1; shift ;;
    --no-include) include_fragment=0; shift ;;
    --with-macros) with_macros=1; shift ;;
    --no-macros) with_macros=0; shift ;;
    --no-backup) no_backup=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    --restart) restart_klipper=1; shift ;;
    --service) service_name="${2:?}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

extras_dir="${extras_dir:-${klipper_dir}/klippy/extras}"
printer_cfg="${printer_cfg:-${config_dir}/printer.cfg}"
fragment="${fragment:-${config_dir}/panda_breath.cfg}"

fragment_content="$(build_fragment)"

copy_module
write_file "$fragment" "$fragment_content"
if [[ "$include_fragment" -eq 1 ]]; then
  ensure_include
else
  say "Skipped printer.cfg include. Add this manually: $(include_line)"
fi

if [[ "$restart_klipper" -eq 1 ]]; then
  if [[ "$(id -u)" -eq 0 ]]; then
    run systemctl restart "$service_name"
  else
    run sudo systemctl restart "$service_name"
  fi
else
  say "Restart Klipper when ready: sudo systemctl restart ${service_name}"
fi
