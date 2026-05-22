#!/usr/bin/env python3
"""Stock-firmware maintenance CLI for Panda Breath.

This tool talks directly to the Panda Breath WebSocket API using only Python
stdlib modules. Host installation is intentionally handled by install.sh.
"""

import argparse
import base64
import json
import os
import socket
import struct
import sys
from time import sleep


DEFAULT_PANDA_HOST = "PandaBreath.local"
DEFAULT_PANDA_PORT = 80
DEFAULT_REQUIRED_VERSION = "V1.0.3"
DEFAULT_PRINTER_PORT = 80


class CliError(Exception):
    pass


class PandaBreathClient:
    def __init__(self, host=DEFAULT_PANDA_HOST, port=DEFAULT_PANDA_PORT,
                 timeout=10., debug=False):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.debug = debug
        self.sock = None
        self.settings = {}

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _debug_print(self, prefix, text):
        if self.debug:
            print("%s %s" % (prefix, text), file=sys.stderr)

    def open(self, path="/ws"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect((self.host, self.port))
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            "GET {path} HTTP/1.1\r\n"
            "Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).format(path=path, host=self.host, port=self.port, key=key)
        sock.sendall(request.encode())
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
        self.sock = sock
        self.settings = self.recv_json()

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except Exception:
                pass
        self.sock = None

    def send_json(self, obj):
        text = json.dumps(obj)
        self._debug_print(">>", text)
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
        self.sock.sendall(header + mask + masked)

    def recv(self, match=None, timeout=30.):
        def recv_exact(n):
            buf = bytearray()
            while len(buf) < n:
                chunk = self.sock.recv(n - len(buf))
                if not chunk:
                    raise ConnectionError("WS: connection closed mid-frame")
                buf.extend(chunk)
            return bytes(buf)

        self.sock.settimeout(timeout)
        while True:
            header = recv_exact(2)
            opcode = header[0] & 0x0F
            masked = bool(header[1] & 0x80)
            length = header[1] & 0x7F
            if length == 126:
                length = struct.unpack("!H", recv_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", recv_exact(8))[0]
            mask_key = recv_exact(4) if masked else None
            payload = recv_exact(length)
            if masked:
                payload = bytes(b ^ mask_key[i & 3] for i, b in enumerate(payload))
            if opcode == 0x8:
                raise ConnectionError("WS: server closed connection")
            if opcode == 0x1:
                text = payload.decode("utf-8")
                self._debug_print("<<", text)
                if match is None or match(text):
                    return text

    def recv_json(self, match=None, timeout=30.):
        return json.loads(self.recv(
            match=None if match is None else lambda text: match(json.loads(text)),
            timeout=timeout,
        ))


def _detect_local_ip(remote_host, remote_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((remote_host, remote_port))
        return sock.getsockname()[0]
    finally:
        sock.close()


def _parse_fw_version(value):
    parts = value.strip().lstrip("vV").split(".")
    parsed = []
    for part in parts:
        digits = ""
        for char in part:
            if not char.isdigit():
                break
            digits += char
        if digits == "":
            break
        parsed.append(int(digits))
    return tuple(parsed)


def _firmware_at_least(actual, minimum):
    actual_tuple = _parse_fw_version(actual)
    minimum_tuple = _parse_fw_version(minimum)
    if not actual_tuple or not minimum_tuple:
        return actual == minimum
    width = max(len(actual_tuple), len(minimum_tuple))
    actual_tuple += (0,) * (width - len(actual_tuple))
    minimum_tuple += (0,) * (width - len(minimum_tuple))
    return actual_tuple >= minimum_tuple


def unbind(client):
    state = client.settings.get("printer", {}).get("state", 0)
    if state == 0:
        print("Device is already disconnected.")
        return
    print("Disconnecting printer (state=%s)..." % state)
    client.send_json({"printer": {"disconnect": 1}})
    client.recv_json(match=lambda r: r.get("printer", {}).get("state") == 0)
    print("Unbind successful.")


def bind_klipper(client, printer_ip, printer_port, required_version):
    firmware = client.settings.get("settings", {}).get("fw_version", "")
    if required_version and not _firmware_at_least(firmware, required_version):
        raise CliError(
            "Expected firmware %s or newer, got '%s'" % (
                required_version, firmware))
    if required_version:
        print("Firmware OK: %s" % firmware)

    state = client.settings.get("printer", {}).get("state", 0)
    if state in (1, 2, 3, 4, 5, 6):
        print("Disconnecting any existing printer ...")
        client.send_json({"printer": {"disconnect": 1}})
        client.recv_json(match=lambda r: r.get("printer", {}).get("state") == 0)
        sleep(1)

    if client.settings.get("settings", {}).get("printer_type") != 2:
        print("Setting printer type to Klipper...")
        client.send_json({"settings": {"printer_type": 2}})
        resp = client.recv_json(
            match=lambda r: r.get("response", {}).get("type") == "printer_type")
        if resp.get("response", {}).get("ok") != 1:
            raise CliError("printer_type change was not acknowledged")
        sleep(1)

    print("Binding Panda Breath to %s:%s ..." % (printer_ip, printer_port))
    client.send_json({
        "printer": {
            "name": "Klipper",
            "ip": printer_ip,
            "port": printer_port,
        },
    })
    resp = client.recv_json(match=lambda r: (
        "state" in r.get("printer", {}) and r.get("printer", {}).get("state") != 2))
    state = resp.get("printer", {}).get("state")
    if state == 3:
        print("Device reported successful connection.")
        print("Bind successful.")
        return
    if state == 4:
        raise CliError("Printer IP address error")
    if state == 1:
        raise CliError("Invalid printer info")
    raise CliError("Device reported state %s" % state)


def cmd_version(args):
    print("Connecting to ws://%s:%s/ws ..." % (args.host, args.port))
    with PandaBreathClient(args.host, args.port, debug=args.debug) as client:
        print(client.settings.get("settings", {}).get("fw_version", "unknown"))


def cmd_unbind(args):
    print("Connecting to ws://%s:%s/ws ..." % (args.host, args.port))
    with PandaBreathClient(args.host, args.port, debug=args.debug) as client:
        unbind(client)


def cmd_bind_klipper(args):
    printer_ip = args.printer_ip or _detect_local_ip(args.host, args.port)
    print("Connecting to ws://%s:%s/ws ..." % (args.host, args.port))
    with PandaBreathClient(args.host, args.port, debug=args.debug) as client:
        bind_klipper(client, printer_ip, args.printer_port, args.version)


def _add_device_args(parser):
    parser.add_argument("--host", default=DEFAULT_PANDA_HOST,
                        help="Panda Breath host or IP")
    parser.add_argument("--port", type=int, default=DEFAULT_PANDA_PORT,
                        help="Panda Breath WebSocket port")
    parser.add_argument("--debug", action="store_true",
                        help="Log sent/received WebSocket frames to stderr")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Maintain Panda Breath stock-firmware printer binding")
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="Print stock firmware version")
    _add_device_args(version)
    version.set_defaults(func=cmd_version)

    bind = sub.add_parser("bind-klipper", help="Bind stock firmware to Klipper")
    _add_device_args(bind)
    bind.add_argument("--printer-ip",
                      help="Klipper host IP (auto-detected if omitted)")
    bind.add_argument("--printer-port", type=int, default=DEFAULT_PRINTER_PORT)
    bind.add_argument("--version", default=DEFAULT_REQUIRED_VERSION,
                      help="Required Panda Breath firmware version")
    bind.set_defaults(func=cmd_bind_klipper)

    unbind_cmd = sub.add_parser(
        "unbind", help="Disconnect the bound printer from Panda Breath")
    _add_device_args(unbind_cmd)
    unbind_cmd.set_defaults(func=cmd_unbind)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except (CliError, OSError) as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
