"""Probe output must never turn missing sources into a successful zero."""
import unittest
import json
import socket
import struct
import time
import sqlite3
import tempfile
from pathlib import Path
from unittest import mock

try:
    import probe_codex_dashboard as P
except ImportError:
    P = None


class ProbeTests(unittest.TestCase):
    def run_probe_fixture(self, loaded, quota, page, principal=None):
        class Ipc:
            skipped_frames = 0
            def __init__(self, endpoint):
                pass
            def observe(self, expected, subscriptions):
                return P.runtime_report(expected, {}), []
            def close(self):
                pass

        class Daemon:
            def __init__(self, endpoint):
                pass
            def handshake(self):
                pass
            def send(self, value):
                pass
            def close(self):
                pass
            def call(self, request_id, method, params):
                return {"initialize": {}, "thread/loaded/list": loaded,
                        "account/rateLimits/read": quota, "thread/list": page}[method]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sqlite").mkdir()
            (root / ".codex-global-state.json").write_text(json.dumps({
                "environment-catalog-cache-v2": principal or {}}))
            db = sqlite3.connect(root / "sqlite/codex-dev.db")
            db.execute("CREATE TABLE local_thread_catalog (host_id,thread_id,"
                       "missing_candidate,source_updated_at)")
            db.close()
            with mock.patch.object(P, "DesktopIpc", Ipc), mock.patch.object(P, "DaemonWebsocket", Daemon):
                return P.probe(root)

    def test_missing_quota_identity_is_unknown_not_match(self):
        self.assertIsNotNone(P)
        result = self.run_probe_fixture({"data": []}, {}, {"data": []})
        self.assertIsNone(result["quota_account_matches_cached_principal"])

    def test_missing_loaded_data_is_error_not_zero(self):
        self.assertIsNotNone(P)
        result = self.run_probe_fixture({}, {}, {"data": []})
        self.assertNotIn("daemon_loaded_count", result)
        self.assertEqual(result["daemon_error"], "ValueError")

    def test_missing_catalog_data_is_error_not_zero(self):
        self.assertIsNotNone(P)
        result = self.run_probe_fixture({"data": []}, {}, {})
        self.assertNotIn("daemon_catalog_count", result)
        self.assertEqual(result["daemon_error"], "ValueError")

    def test_whole_probe_output_drops_source_secrets(self):
        self.assertIsNotNone(P)
        result = self.run_probe_fixture({"data": []}, {"accountId": "private-account"},
                                        {"data": []}, {"accountId": "private-account",
                                                       "userId": "private-user"})
        self.assertNotIn("private-account", json.dumps(result))
        self.assertNotIn("private-user", json.dumps(result))
        self.assertTrue(result["quota_account_matches_cached_principal"])
        self.assertEqual(result["daemon_loaded_count"], 0)

    def test_large_ipc_frame_is_skipped_without_losing_next_message(self):
        self.assertIsNotNone(P, "read-only probe is not implemented")
        sender, receiver = socket.socketpair()
        reader = object.__new__(P.DesktopIpc)
        reader.sock = receiver
        reader.max_json_bytes = 32
        reader.skipped_frames = 0
        try:
            large = json.dumps({"transcript": "x" * 64}).encode()
            small = json.dumps({"type": "response"}).encode()
            sender.sendall(struct.pack("<I", len(large)) + large +
                           struct.pack("<I", len(small)) + small)
            self.assertEqual(reader.receive(time.monotonic() + 1), {"type": "response"})
            self.assertEqual(reader.skipped_frames, 1)
        finally:
            sender.close()
            receiver.close()

    def test_runtime_report_is_partial_when_remote_missing(self):
        self.assertIsNotNone(P, "read-only probe is not implemented")
        result = P.runtime_report(
            {("local", "a"), ("remote", "b"), ("durable", "c")},
            {("local", "a"): {"type": "active", "activeFlags": []}})
        self.assertEqual(result["running_lower_bound"], 1)
        self.assertFalse(result["complete"])
        self.assertEqual(result["missing_hosts"], ["durable", "remote"])

    def test_unknown_and_waiting_do_not_become_running(self):
        self.assertIsNotNone(P, "read-only probe is not implemented")
        result = P.runtime_report(
            {("local", "a"), ("local", "b"), ("local", "c")},
            {("local", "a"): {"type": "active", "activeFlags": ["waitingOnApproval"]},
             ("local", "b"): {"type": "notLoaded"},
             ("local", "c"): {"type": "idle"}})
        self.assertEqual(result["running_lower_bound"], 0)
        self.assertEqual(result["waiting_lower_bound"], 1)
        self.assertFalse(result["complete"])

    def test_probe_output_does_not_include_conversation_or_identity(self):
        self.assertIsNotNone(P, "read-only probe is not implemented")
        result = P.runtime_report({("secret-host", "private-id")},
                                  {("secret-host", "private-id"): {"type": "active"}})
        self.assertNotIn("private-id", str(result))
        self.assertEqual(result["snapshot_count"], 1)

    def test_only_seven_day_window_is_quota(self):
        self.assertIsNotNone(P, "read-only probe is not implemented")
        self.assertEqual(P.weekly_remaining({"secondary": {"windowDurationMins": 10080,
                                                         "usedPercent": 67}}), 33)
        self.assertIsNone(P.weekly_remaining({"primary": {"windowDurationMins": 300,
                                                          "usedPercent": 20}}))


if __name__ == "__main__":
    unittest.main()
