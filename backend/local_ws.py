"""Local WebSocket hub — the dev stand-in for API Gateway's WebSocket API.

Implements just enough of RFC 6455 (handshake, text frames, close, ping) to
carry the same payloads the deployed broadcaster sends, with no third-party
dependencies. In AWS none of this runs: API Gateway terminates the socket and
the DynamoDB Streams broadcaster does the fan-out.

The point is that the real-time layer is genuinely exercised during development
instead of being code that only runs after a deploy.
"""
import base64
import hashlib
import json
import logging
import socket
import struct
import threading
from typing import Any, Dict, Set

logger = logging.getLogger(__name__)

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_TEXT = 0x1
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA


def _accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key + GUID).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def _encode(payload: bytes, opcode: int = OP_TEXT) -> bytes:
    """Server-to-client frames are never masked."""
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < (1 << 16):
        header.append(126)
        header += struct.pack(">H", length)
    else:
        header.append(127)
        header += struct.pack(">Q", length)
    return bytes(header) + payload


def _recv_exact(conn: socket.socket, count: int) -> bytes:
    buf = b""
    while len(buf) < count:
        chunk = conn.recv(count - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf += chunk
    return buf


def _read_frame(conn: socket.socket):
    """Returns (opcode, payload). Client-to-server frames are always masked."""
    b1, b2 = _recv_exact(conn, 2)
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(conn, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(conn, 8))[0]
    mask = _recv_exact(conn, 4) if masked else b""
    payload = _recv_exact(conn, length) if length else b""
    if masked:
        payload = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
    return opcode, payload


class Hub:
    """Tracks open sockets and fans payloads out to all of them."""

    def __init__(self):
        self._clients: Set[socket.socket] = set()
        self._lock = threading.Lock()

    def add(self, conn: socket.socket) -> None:
        with self._lock:
            self._clients.add(conn)

    def remove(self, conn: socket.socket) -> None:
        with self._lock:
            self._clients.discard(conn)
        try:
            conn.close()
        except OSError:
            pass

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._clients)

    def broadcast(self, payload: Dict[str, Any]) -> int:
        frame = _encode(json.dumps(payload).encode("utf-8"))
        with self._lock:
            targets = list(self._clients)
        delivered = 0
        for conn in targets:
            try:
                conn.sendall(frame)
                delivered += 1
            except OSError:
                self.remove(conn)
        return delivered

    def send(self, conn: socket.socket, payload: Dict[str, Any]) -> None:
        try:
            conn.sendall(_encode(json.dumps(payload).encode("utf-8")))
        except OSError:
            self.remove(conn)


HUB = Hub()


def _handshake(conn: socket.socket) -> bool:
    request = b""
    while b"\r\n\r\n" not in request:
        chunk = conn.recv(4096)
        if not chunk:
            return False
        request += chunk
        if len(request) > 65536:
            return False

    headers = {}
    for line in request.decode("latin-1").split("\r\n")[1:]:
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()

    key = headers.get("sec-websocket-key")
    if not key or "websocket" not in headers.get("upgrade", "").lower():
        conn.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        return False

    conn.sendall(
        b"HTTP/1.1 101 Switching Protocols\r\n"
        b"Upgrade: websocket\r\n"
        b"Connection: Upgrade\r\n"
        b"Sec-WebSocket-Accept: " + _accept_key(key).encode("ascii") + b"\r\n\r\n"
    )
    return True


def _serve_client(conn: socket.socket, on_hello) -> None:
    try:
        if not _handshake(conn):
            conn.close()
            return
        HUB.add(conn)
        # Mirrors the deployed $connect behaviour: a fresh client gets the
        # current real state immediately, with no REST round-trip.
        HUB.send(conn, on_hello())

        while True:
            opcode, payload = _read_frame(conn)
            if opcode == OP_CLOSE:
                break
            if opcode == OP_PING:
                conn.sendall(_encode(payload, OP_PONG))
                continue
            if opcode == OP_TEXT:
                # Any inbound frame means "resend the snapshot" ($default).
                HUB.send(conn, on_hello())
    except (ConnectionError, OSError, struct.error):
        pass
    finally:
        HUB.remove(conn)


def start(port: int, on_hello, host: str = "127.0.0.1") -> threading.Thread:
    """Start the hub in a daemon thread and wire it up as the broadcast sink."""
    from common import realtime

    realtime.set_local_sink(lambda payload: HUB.broadcast(payload))

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(64)

    def loop():
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                break
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            threading.Thread(target=_serve_client, args=(conn, on_hello), daemon=True).start()

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread
