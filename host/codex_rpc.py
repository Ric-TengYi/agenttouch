"""Bounded read-only RPC transport to the existing local Codex daemon."""
import base64, hashlib, json, os, socket, struct, time

class Reader:
    def __init__(self, endpoint):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        self.sock.connect(str(endpoint))

    def take(self, size, deadline):
        if size > 16 * 1024 * 1024:
            raise ValueError("frame limit exceeded")
        parts = bytearray()
        while len(parts) < size:
            self.sock.settimeout(max(0.001, deadline - time.monotonic()))
            if time.monotonic() >= deadline:
                raise TimeoutError()
            chunk = self.sock.recv(size - len(parts))
            if not chunk:
                raise EOFError()
            parts.extend(chunk)
        return bytes(parts)

    def close(self):
        self.sock.close()


class DaemonWebsocket(Reader):
    def handshake(self):
        key = base64.b64encode(os.urandom(16)).decode()
        request = ("GET /rpc HTTP/1.1\r\nHost: codex-app-server\r\n"
                   "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                   "Sec-WebSocket-Key: " + key + "\r\n"
                   "Sec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(request.encode())
        headers, deadline = b"", time.monotonic() + 5
        while not headers.endswith(b"\r\n\r\n"):
            if len(headers) > 8192:
                raise ValueError("header limit")
            headers += self.take(1, deadline)
        accept = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if not headers.startswith(b"HTTP/1.1 101 ") or accept not in headers:
            raise ValueError("websocket handshake failed")

    def send(self, value, opcode=1):
        data = value if isinstance(value, bytes) else json.dumps(value).encode()
        size, mask = len(data), os.urandom(4)
        header = bytes([128 | opcode, 128 | size]) if size < 126 else (
            bytes([128 | opcode, 254]) + struct.pack("!H", size))
        self.sock.sendall(header + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(data)))

    def receive(self, deadline):
        while time.monotonic() < deadline:
            header = self.take(2, deadline)
            size, opcode = header[1] & 127, header[0] & 15
            if size == 126:
                size = struct.unpack("!H", self.take(2, deadline))[0]
            elif size == 127:
                size = struct.unpack("!Q", self.take(8, deadline))[0]
            if header[1] & 128 or not header[0] & 128:
                raise ValueError("unsupported websocket frame")
            data = self.take(size, deadline)
            if opcode == 9:
                self.send(data, opcode=10)
            elif opcode == 8:
                raise EOFError()
            elif opcode == 1:
                return json.loads(data)
        raise TimeoutError()

    def call(self, request_id, method, params):
        if method not in ("initialize", "thread/list", "thread/loaded/list",
                          "account/rateLimits/read"):
            raise ValueError("probe permits read-only methods")
        self.send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.receive(deadline)
            if result.get("id") == request_id:
                if "error" in result:
                    raise ValueError("rpc query rejected")
                return result["result"]
        raise TimeoutError()

