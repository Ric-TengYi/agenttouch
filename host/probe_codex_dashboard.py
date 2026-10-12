#!/usr/bin/python3
"""Read-only feasibility probe. Does not install, start, resume or edit tasks.

Only count/coverage diagnostics are printed. IPC snapshots are discarded after
extracting runtime status. This is not the production dashboard adapter.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import plistlib
import socket
import sqlite3
import struct
import time
import uuid


def runtime_report(expected, statuses):
    known = {key for key, value in statuses.items()
             if value.get("type") in ("active", "idle")}
    running = waiting = 0
    for key in known & expected:
        status = statuses[key]
        if status["type"] == "active":
            if status.get("activeFlags"):
                waiting += 1
            else:
                running += 1
    return {"running_lower_bound": running, "waiting_lower_bound": waiting,
            "snapshot_count": len(known & expected),
            "complete": expected.issubset(known),
            "missing_hosts": sorted({h for h, _ in expected - known})}


def weekly_remaining(rate_limits):
    for window in rate_limits.values():
        if (isinstance(window, dict) and window.get("windowDurationMins") == 10080
                and isinstance(window.get("usedPercent"), (int, float))):
            return max(0, min(100, 100 - window["usedPercent"]))
    return None


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


class DesktopIpc(Reader):
    max_json_bytes = 16 * 1024 * 1024
    skipped_frames = 0

    def send(self, value):
        payload = json.dumps(value, separators=(",", ":")).encode()
        self.sock.sendall(struct.pack("<I", len(payload)) + payload)

    def receive(self, deadline):
        while time.monotonic() < deadline:
            size = struct.unpack("<I", self.take(4, deadline))[0]
            if not 0 < size <= 268435456:
                raise ValueError("invalid ipc frame size")
            if size > self.max_json_bytes:
                self.skipped_frames += 1
                while size:
                    chunk = min(size, 65536)
                    self.take(chunk, deadline)
                    size -= chunk
                continue
            return json.loads(self.take(size, deadline))
        raise TimeoutError()

    def initialize(self):
        request_id = str(uuid.uuid4())
        self.send({"type": "request", "requestId": request_id,
                   "sourceClientId": "initializing-client", "version": 0,
                   "method": "initialize", "params": {"clientType": "agenttouch"},
                   "timeoutMs": 5000})
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = self.receive(deadline)
            if result.get("requestId") == request_id:
                if result.get("resultType") != "success":
                    raise ValueError("ipc initialization failed")
                self.client_id = result["result"]["clientId"]
                return
        raise TimeoutError()

    def observe(self, expected, subscriptions=None):
        self.initialize()
        # Snapshot subscriptions can transmit the entire conversation. The
        # diagnostic deliberately samples rather than subscribing to a catalog.
        for host, thread in (subscriptions if subscriptions is not None else expected):
            self.send({"type": "broadcast", "sourceClientId": self.client_id,
                       "version": 1, "method": "thread-stream-following-changed",
                       "params": {"hostId": host, "conversationId": thread,
                                  "following": True}})
        statuses, versions = {}, set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                value = self.receive(deadline)
            except TimeoutError:
                break
            if value.get("method") != "thread-stream-state-changed":
                continue
            versions.add(value.get("version"))
            if value.get("version") != 11:
                continue
            params = value.get("params", {})
            change = params.get("change", {})
            state = change.get("conversationState", {})
            key = (params.get("hostId"), params.get("conversationId"))
            if change.get("type") == "snapshot" and key in expected:
                statuses[key] = state.get("threadRuntimeStatus") or {}
        return runtime_report(expected, statuses), sorted(versions)


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


def probe(home=None):
    home = Path(home or Path.home() / ".codex")
    result = {"probe_version": 1, "product_adapter": False}
    global_state = json.loads((home / ".codex-global-state.json").read_text())
    env = global_state.get("environment-catalog-cache-v2", {})
    principal = ["chatgpt", env.get("accountId"), env.get("userId")]
    identity = hashlib.sha256(json.dumps(principal, separators=(",", ":")).encode()).hexdigest()
    unread = global_state.get("electron-thread-read-state-v1", {})
    result["cached_principal_matches_unread"] = identity in unread.get("unreadByIdentity", {})
    db = sqlite3.connect("file:" + str(home / "sqlite/codex-dev.db") + "?mode=ro", uri=True)
    try:
        rows = [(host, thread) for host, thread in db.execute(
            "SELECT host_id,thread_id FROM local_thread_catalog "
            "WHERE missing_candidate=0 ORDER BY source_updated_at DESC")
                if not host.startswith("chatgpt:")]
        expected = set(rows)
    finally:
        db.close()
    cloud = global_state.get("electron-persisted-atom-state", {}).get(
        "cloud-thread-prototype-threads-by-account-v1", {}).get(env.get("accountId"), {})
    expected.update(("durable", thread) for thread in cloud)
    subscriptions, per_host = set(), {}
    for host, thread in rows + [("durable", thread) for thread in cloud]:
        if per_host.get(host, 0) < 2:
            subscriptions.add((host, thread))
            per_host[host] = per_host.get(host, 0) + 1
    result["cached_catalog_count"] = len(expected)
    result["cached_catalog_complete"] = False  # cache alone cannot prove live full coverage
    ipc = None
    try:
        ipc = DesktopIpc(home / "ipc/ipc.sock")
        result["desktop_runtime"], result["ipc_stream_versions"] = ipc.observe(expected, subscriptions)
        result["ipc_skipped_large_frames"] = ipc.skipped_frames
    except (OSError, ValueError, EOFError) as exc:
        result["ipc_error"] = type(exc).__name__
    finally:
        if ipc:
            ipc.close()
    daemon = None
    try:
        daemon = DaemonWebsocket(home / "app-server-control/app-server-control.sock")
        daemon.handshake()
        daemon.call(1, "initialize", {"clientInfo": {"name": "agenttouch_probe", "version": "0.1"},
                                      "capabilities": {"experimentalApi": True}})
        daemon.send({"method": "initialized"})
        loaded = daemon.call(2, "thread/loaded/list", {})
        if not isinstance(loaded, dict) or not isinstance(loaded.get("data"), list):
            raise ValueError("loaded catalog schema mismatch")
        result["daemon_loaded_count"] = len(loaded["data"])
        quota = daemon.call(3, "account/rateLimits/read", {})
        quota_account, cached_account = quota.get("accountId"), env.get("accountId")
        valid_accounts = all(isinstance(v, str) and v.strip()
                             for v in (quota_account, cached_account))
        result["quota_account_matches_cached_principal"] = (
            quota_account == cached_account if valid_accounts else None)
        result["seven_day_remaining_pct"] = weekly_remaining(quota.get("rateLimits", {}))
        count, cursor, request_id = 0, None, 4
        while True:
            page = daemon.call(request_id, "thread/list", {
                "limit": 100, "cursor": cursor, "archived": False, "useStateDbOnly": True})
            if not isinstance(page, dict) or not isinstance(page.get("data"), list):
                raise ValueError("thread catalog schema mismatch")
            count += len(page["data"])
            cursor = page.get("nextCursor")
            if not cursor:
                break
            request_id += 1
            if request_id > 100:
                raise ValueError("catalog paging limit")
        result["daemon_catalog_count"] = count
    except (OSError, ValueError, EOFError) as exc:
        result["daemon_error"] = type(exc).__name__
    finally:
        if daemon:
            daemon.close()
    result["gate"] = "blocked"  # live complete remote/cloud coverage not proven by these caches
    return result


if __name__ == "__main__":
    try:
        info = plistlib.loads(Path("/Applications/ChatGPT.app/Contents/Info.plist").read_bytes())
        output = probe()
        output["desktop_version"] = info.get("CFBundleShortVersionString")
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, sqlite3.Error) as error:
        print(json.dumps({"gate": "blocked", "error_type": type(error).__name__}))
