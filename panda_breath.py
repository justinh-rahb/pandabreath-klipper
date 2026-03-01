# panda_breath.py — Klipper extras module for BIQU Panda Breath
#
# Exposes the Panda Breath as a standard Klipper heater (heater_generic interface).
# Supports two firmware targets via a transport abstraction:
#
#   firmware: stock   — OEM WebSocket JSON protocol (ws://<host>/ws)
#                       Recommended firmware: v0.0.0 (only confirmed stable release)
#   firmware: esphome — ESPHome MQTT protocol (MQTT 3.1.1 over TCP)
#
# No external Python dependencies — stdlib only (socket, struct, hashlib, base64,
# os, json, threading, collections, time, logging).  The module is a single-file
# drop into /home/lava/klipper/klippy/extras/ with no install steps.
#
# printer.cfg — stock firmware:
#   [panda_breath]
#   firmware: stock
#   host: pandabreath.local
#   port: 80
#
# printer.cfg — ESPHome firmware:
#   [panda_breath]
#   firmware: esphome
#   mqtt_broker: 192.168.1.x
#   mqtt_port: 1883
#   mqtt_topic_prefix: panda-breath

import collections
import base64
import hashlib
import json
import logging
import os
import socket
import struct
import threading
import time

logger = logging.getLogger(__name__)

# How long to wait between reconnect attempts (seconds)
RECONNECT_DELAY = 5.
# How often the Klipper reactor timer drains the state queue (seconds)
REACTOR_POLL = 1.
# Log a warning if no temperature update received within this window (seconds)
TEMP_STALE_WARN = 60.


# ─── WebSocket transport (stock OEM firmware) ─────────────────────────────────

class _WebSocketTransport:
    """Minimal RFC 6455 WebSocket client for the Panda Breath OEM firmware.

    Runs a background thread that maintains a persistent connection to
    ws://<host>:<port>/ws, parses incoming JSON settings frames, and
    invokes on_message({'temperature': float}) when a temperature field
    is received.  Reconnects automatically on any error.

    Outbound commands use the {"settings": {...}} envelope the device expects.
    The last-sent command is re-sent on every reconnect so the device is
    always in the desired state after a connection drop.
    """

    def __init__(self, host, port, on_message, on_disconnect):
        self._host = host
        self._port = port
        self._on_message = on_message
        self._on_disconnect = on_disconnect
        self._sock = None
        self._running = False
        self._thread = None
        # Last target degrees — resent on reconnect to keep device in sync
        self._last_target = 0.

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="panda_breath_ws", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    def set_target(self, degrees):
        self._last_target = degrees
        if degrees > 0:
            self._send_settings(
                {"work_mode": 2, "work_on": True, "temp": int(degrees)})
        else:
            self._send_settings({"work_on": False})

    # ── internal ──────────────────────────────────────────────────────────────

    def _send_settings(self, fields):
        """Wrap fields in {"settings": fields} and send as a WebSocket text frame."""
        self._ws_send(json.dumps({"settings": fields}))

    def _ws_send(self, text):
        sock = self._sock
        if sock is None:
            return
        payload = text.encode("utf-8")
        length = len(payload)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
        if length < 126:
            header = struct.pack("!BB", 0x81, 0x80 | length)
        elif length < 65536:
            header = struct.pack("!BBH", 0x81, 0xFE, length)
        else:
            header = struct.pack("!BBQ", 0x81, 0xFF, length)
        try:
            sock.sendall(header + mask + masked)
        except Exception as exc:
            logger.warning("panda_breath: WS send error: %s", exc)

    def _handshake(self, sock):
        """Perform the HTTP/1.1 → WebSocket upgrade handshake."""
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            "GET /ws HTTP/1.1\r\n"
            "Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).format(host=self._host, port=self._port, key=key)
        sock.sendall(request.encode())
        # Read until end of HTTP headers
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(1024)
            if not chunk:
                raise ConnectionError("WS handshake: connection closed")
            buf += chunk
        status_line = buf.split(b"\r\n")[0]
        if b"101" not in status_line:
            raise ConnectionError(
                "WS handshake failed: %s" % status_line.decode(errors="replace"))

    def _recv_exact(self, sock, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("WS: connection closed mid-frame")
            buf.extend(chunk)
        return bytes(buf)

    def _recv_frame(self, sock):
        """Read one WebSocket frame. Returns (opcode, payload_bytes).
        Handles multi-fragment messages by reassembling (rare in practice here).
        """
        header = self._recv_exact(sock, 2)
        # FIN bit and opcode
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(sock, 8))[0]
        mask_key = self._recv_exact(sock, 4) if masked else None
        payload = self._recv_exact(sock, length)
        if masked:
            payload = bytes(b ^ mask_key[i & 3] for i, b in enumerate(payload))
        return opcode, payload

    def _run(self):
        """Background I/O thread: connect, receive, reconnect on any failure."""
        while self._running:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10.)
                sock.connect((self._host, self._port))
                self._handshake(sock)
                sock.settimeout(45.)  # device sends pings; 45 s gives headroom
                self._sock = sock
                logger.info("panda_breath: WebSocket connected to %s:%s",
                            self._host, self._port)
                # Resend desired state so device is in sync after reconnect
                self.set_target(self._last_target)
                while self._running:
                    opcode, payload = self._recv_frame(sock)
                    if opcode == 0x8:   # close
                        break
                    elif opcode == 0x9:  # ping → pong
                        pong = struct.pack("!BB", 0x8A, len(payload)) + payload
                        sock.sendall(pong)
                    elif opcode in (0x1, 0x2):  # text or binary
                        self._dispatch(payload)
            except Exception as exc:
                if self._running:
                    logger.warning(
                        "panda_breath: WS error (%s) — reconnect in %.0fs",
                        exc, RECONNECT_DELAY)
                    self._on_disconnect()
            finally:
                self._sock = None
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass
            if self._running:
                time.sleep(RECONNECT_DELAY)

    def _dispatch(self, payload):
        """Parse a JSON frame and push normalised state to the callback."""
        try:
            msg = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            logger.debug("panda_breath: WS parse error: %s", exc)
            return
        settings = msg.get("settings")
        if not isinstance(settings, dict):
            return
        # Prefer the ADC-calibrated reading; fall back to raw
        temp = settings.get("cal_warehouse_temp", settings.get("warehouse_temper"))
        if temp is not None:
            try:
                self._on_message({"temperature": float(temp)})
            except (TypeError, ValueError):
                pass


# ─── MQTT transport (ESPHome firmware) ────────────────────────────────────────

class _MqttTransport:
    """Minimal MQTT 3.1.1 client for the ESPHome Panda Breath firmware.

    Implements only the packet types needed:
      Send:    CONNECT, SUBSCRIBE, PUBLISH (QoS 0), PINGREQ, DISCONNECT
      Receive: CONNACK, SUBACK, PUBLISH (QoS 0), PINGRESP

    Subscribes to {prefix}/sensor/chamber_temperature/state and calls
    on_message({'temperature': float}) on each retained/incoming value.

    set_target() publishes to climate mode/target topics.
    The last command is re-published on every reconnect.
    """

    _PING_INTERVAL = 30.

    def __init__(self, broker, port, topic_prefix, on_message, on_disconnect):
        self._broker = broker
        self._port = port
        self._prefix = topic_prefix
        self._on_message = on_message
        self._on_disconnect = on_disconnect
        self._sock = None
        self._running = False
        self._thread = None
        self._last_target = 0.

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="panda_breath_mqtt", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        sock = self._sock
        if sock is not None:
            try:
                # Best-effort DISCONNECT
                sock.sendall(b"\xe0\x00")
                sock.close()
            except Exception:
                pass

    def set_target(self, degrees):
        self._last_target = degrees
        if degrees > 0:
            self._publish(
                "%s/climate/chamber/target_temperature/set" % self._prefix,
                "%.1f" % degrees)
            self._publish(
                "%s/climate/chamber/mode/set" % self._prefix, "heat")
        else:
            self._publish(
                "%s/climate/chamber/mode/set" % self._prefix, "off")

    # ── MQTT packet helpers ───────────────────────────────────────────────────

    @staticmethod
    def _encode_remaining_length(n):
        out = bytearray()
        while True:
            byte = n & 0x7F
            n >>= 7
            if n:
                byte |= 0x80
            out.append(byte)
            if not n:
                break
        return bytes(out)

    @staticmethod
    def _mqtt_str(s):
        """UTF-8 string with 2-byte big-endian length prefix (MQTT spec)."""
        encoded = s.encode("utf-8")
        return struct.pack("!H", len(encoded)) + encoded

    def _build_connect(self, client_id="panda_breath_klipper",
                       keepalive=60, username=None, password=None):
        flags = 0x02  # clean session
        if username:
            flags |= 0x80
        if password:
            flags |= 0x40
        vh = (self._mqtt_str("MQTT")     # protocol name
              + b"\x04"                  # protocol level 4 = MQTT 3.1.1
              + bytes([flags])
              + struct.pack("!H", keepalive))
        payload = self._mqtt_str(client_id)
        if username:
            payload += self._mqtt_str(username)
        if password:
            payload += self._mqtt_str(password)
        body = vh + payload
        return b"\x10" + self._encode_remaining_length(len(body)) + body

    def _build_subscribe(self, topic, packet_id=1):
        payload = struct.pack("!H", packet_id) + self._mqtt_str(topic) + b"\x00"
        return b"\x82" + self._encode_remaining_length(len(payload)) + payload

    def _build_publish(self, topic, message):
        # QoS 0, no retain, no DUP
        vh = self._mqtt_str(topic)
        body = vh + message.encode("utf-8")
        return b"\x30" + self._encode_remaining_length(len(body)) + body

    @staticmethod
    def _build_pingreq():
        return b"\xc0\x00"

    # ── socket receive helpers ────────────────────────────────────────────────

    def _recv_exact(self, sock, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("MQTT: connection closed")
            buf.extend(chunk)
        return bytes(buf)

    def _recv_remaining_length(self, sock):
        multiplier, value = 1, 0
        for _ in range(4):
            byte = ord(self._recv_exact(sock, 1))
            value += (byte & 0x7F) * multiplier
            multiplier <<= 7
            if not (byte & 0x80):
                break
        return value

    def _recv_packet(self, sock):
        """Read one MQTT packet. Returns (packet_type_nibble, flags_nibble, body_bytes)."""
        first = ord(self._recv_exact(sock, 1))
        ptype = (first >> 4) & 0xF
        pflags = first & 0xF
        remaining = self._recv_remaining_length(sock)
        body = self._recv_exact(sock, remaining) if remaining else b""
        return ptype, pflags, body

    # ── publish helper (usable from reactor thread too) ───────────────────────

    def _publish(self, topic, message):
        sock = self._sock
        if sock is None:
            return
        pkt = self._build_publish(topic, message)
        try:
            sock.sendall(pkt)
        except Exception as exc:
            logger.warning("panda_breath: MQTT publish error: %s", exc)

    # ── background thread ─────────────────────────────────────────────────────

    def _run(self):
        while self._running:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10.)
                sock.connect((self._broker, self._port))
                sock.sendall(self._build_connect())
                # Expect CONNACK (type 2)
                ptype, _, body = self._recv_packet(sock)
                if ptype != 2:
                    raise ConnectionError(
                        "MQTT: expected CONNACK (2), got %d" % ptype)
                if len(body) >= 2 and body[1] != 0:
                    raise ConnectionError(
                        "MQTT: CONNACK refused, code=%d" % body[1])
                # Subscribe to chamber temperature topic
                temp_topic = "%s/sensor/chamber_temperature/state" % self._prefix
                sock.sendall(self._build_subscribe(temp_topic, packet_id=1))
                # Expect SUBACK (type 9)
                ptype, _, _ = self._recv_packet(sock)
                if ptype != 9:
                    raise ConnectionError(
                        "MQTT: expected SUBACK (9), got %d" % ptype)
                sock.settimeout(self._PING_INTERVAL + 5.)
                self._sock = sock
                logger.info("panda_breath: MQTT connected to %s:%s",
                            self._broker, self._port)
                # Resend desired state after reconnect
                self.set_target(self._last_target)
                last_ping = time.monotonic()
                while self._running:
                    # Send PINGREQ on schedule
                    now = time.monotonic()
                    if now - last_ping >= self._PING_INTERVAL:
                        sock.sendall(self._build_pingreq())
                        last_ping = now
                    try:
                        ptype, pflags, body = self._recv_packet(sock)
                    except socket.timeout:
                        # Use timeout to drive ping; not a fatal error
                        continue
                    if ptype == 3:   # PUBLISH
                        self._dispatch_publish(pflags, body)
                    elif ptype == 13:  # PINGRESP — nothing to do
                        pass
                    elif ptype == 0:   # malformed / connection close
                        break
            except Exception as exc:
                if self._running:
                    logger.warning(
                        "panda_breath: MQTT error (%s) — reconnect in %.0fs",
                        exc, RECONNECT_DELAY)
                    self._on_disconnect()
            finally:
                self._sock = None
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass
            if self._running:
                time.sleep(RECONNECT_DELAY)

    def _dispatch_publish(self, flags, body):
        """Parse an incoming PUBLISH packet and call on_message if it's our topic."""
        # QoS is bits 2-1 of flags; QoS 0 has no packet ID
        qos = (flags >> 1) & 0x3
        offset = 0
        if len(body) < 2:
            return
        topic_len = struct.unpack_from("!H", body, offset)[0]
        offset += 2
        if offset + topic_len > len(body):
            return
        topic = body[offset:offset + topic_len].decode("utf-8", errors="replace")
        offset += topic_len
        if qos > 0:
            offset += 2  # skip packet ID (not used for QoS 0 publishes we send)
        payload = body[offset:].decode("utf-8", errors="replace").strip()
        if topic.endswith("/chamber_temperature/state"):
            try:
                self._on_message({"temperature": float(payload)})
            except (TypeError, ValueError):
                pass


# ─── Klipper heater class ──────────────────────────────────────────────────────

class PandaBreath:
    """Klipper extras module — exposes the Panda Breath as a heater_generic.

    Registers with Klipper's heater system so that:
      SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=45
      TEMPERATURE_WAIT SENSOR=panda_breath MINIMUM=40
    work as expected.  The device manages its own PTC relay duty-cycle and fan
    speed internally; this module only sends on/off + target commands and reads
    the chamber temperature back.
    """

    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.name = config.get_name().split()[-1]

        # Temperature state — only written by reactor timer, so no lock needed
        self._current_temp = 0.
        self._target_temp = 0.
        self._last_temp_time = 0.

        # Thread-safe queue: background I/O thread appends, reactor timer drains.
        # collections.deque is safe for single-producer / single-consumer.
        self._state_queue = collections.deque()

        # Build the appropriate transport
        firmware = config.get("firmware", "stock")
        if firmware == "stock":
            host = config.get("host")
            port = config.getint("port", 80)
            self._transport = _WebSocketTransport(
                host, port,
                on_message=self._enqueue,
                on_disconnect=self._on_disconnect)
        elif firmware == "esphome":
            broker = config.get("mqtt_broker")
            port = config.getint("mqtt_port", 1883)
            prefix = config.get("mqtt_topic_prefix", "panda-breath")
            self._transport = _MqttTransport(
                broker, port, prefix,
                on_message=self._enqueue,
                on_disconnect=self._on_disconnect)
        else:
            raise config.error(
                "panda_breath: unknown firmware '%s' (use 'stock' or 'esphome')"
                % firmware)

        # Register with Klipper's heater manager.
        # This makes SET_HEATER_TEMPERATURE and TEMPERATURE_WAIT work without
        # needing a sensor_type or heater_pin in printer.cfg.
        pheaters = self.printer.load_object(config, "heaters")
        pheaters.available_heaters.append(config.get_name())
        pheaters.available_sensors.append(config.get_name())
        pheaters.heaters[self.name] = self

        # Klipper lifecycle
        self.printer.register_event_handler(
            "klippy:connect", self._handle_connect)
        self.printer.register_event_handler(
            "klippy:disconnect", self._handle_disconnect)
        self.printer.register_event_handler(
            "klippy:shutdown", self._handle_disconnect)
        self._poll_timer = self.reactor.register_timer(
            self._reactor_poll, self.reactor.NEVER)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def _handle_connect(self):
        self._transport.start()
        self.reactor.update_timer(self._poll_timer, self.reactor.NOW)

    def _handle_disconnect(self):
        self._transport.stop()
        self.reactor.update_timer(self._poll_timer, self.reactor.NEVER)

    # ── state queue ───────────────────────────────────────────────────────────

    def _enqueue(self, data):
        """Called from background I/O thread — only appends to deque."""
        self._state_queue.append(data)

    def _on_disconnect(self):
        """Called from background I/O thread on connection loss."""
        # No state mutation from the I/O thread; let the reactor poll notice
        # the temperature going stale via _last_temp_time.
        pass

    def _reactor_poll(self, eventtime):
        """Drain the state queue and update temperature. Runs in reactor thread."""
        while self._state_queue:
            data = self._state_queue.popleft()
            temp = data.get("temperature")
            if temp is not None:
                self._current_temp = float(temp)
                self._last_temp_time = eventtime
        # Warn if temperature data has gone stale
        if (self._last_temp_time > 0.
                and eventtime - self._last_temp_time > TEMP_STALE_WARN):
            logger.warning(
                "panda_breath: no temperature update for %.0fs",
                eventtime - self._last_temp_time)
            self._last_temp_time = eventtime  # suppress repeated warnings
        return eventtime + REACTOR_POLL

    # ── Klipper heater interface ───────────────────────────────────────────────

    def get_temp(self, eventtime):
        return self._current_temp, self._target_temp

    def set_temp(self, degrees):
        self._target_temp = degrees
        self._transport.set_target(degrees)

    def check_busy(self, eventtime, smoothed_temp, extrude_temp):
        # Report busy (not yet at target) while more than 2°C away.
        # This is used by TEMPERATURE_WAIT and the idle-timeout heater check.
        if self._target_temp <= 0.:
            return False
        return abs(self._current_temp - self._target_temp) > 2.

    def get_status(self, eventtime):
        return {
            "temperature": round(self._current_temp, 2),
            "target": self._target_temp,
            # power is not meaningful here (device manages its own relay)
            "power": 0.,
        }


def load_config(config):
    return PandaBreath(config)
