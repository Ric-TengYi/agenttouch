import base64
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

try:
    import dashboard as D
except ImportError:
    D = None


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        claims = {"exp": 2000, "https://api.openai.com/auth": {
            "chatgpt_account_id": "account", "chatgpt_user_id": "user"}}
        token = "header." + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=") + ".sig"
        (self.home / "auth.json").write_text(json.dumps({"auth_mode": "chatgpt",
            "tokens": {"access_token": token, "account_id": "account"}}))
        identity = hashlib.sha256(b'["chatgpt","account","user"]').hexdigest()
        host = "local:" + hashlib.sha256(b'["local","local",null]').hexdigest()
        self.global_state = {"electron-thread-read-state-v1": {"version": 1,
            "unreadByIdentity": {identity: {host: ["a", "b", "child", "archived", "deleted"]}}}}
        self.save_state()
        db = sqlite3.connect(self.home / "state_5.sqlite")
        db.execute("CREATE TABLE threads(id,title,rollout_path,archived,source,creator_account_id,creator_user_id)")
        for tid, archived, source in [("a", 0, "vscode"), ("b", 0, "vscode"),
                                     ("child", 0, '{"subagent":{}}'), ("archived", 1, "vscode")]:
            path = self.home / (tid + ".jsonl")
            path.write_text(json.dumps({"type": "event_msg", "payload": {
                "type": "task_started" if tid == "a" else "task_complete"}}) + "\n")
            db.execute("INSERT INTO threads VALUES(?,?,?,?,?,?,?)",
                       (tid, tid, str(path), archived, source, "account", "user"))
        db.commit()
        db.close()
        (self.home / "sqlite").mkdir()
        db = sqlite3.connect(self.home / "sqlite/codex-dev.db")
        db.execute("CREATE TABLE local_thread_catalog(host_id,thread_id,missing_candidate)")
        db.executemany("INSERT INTO local_thread_catalog VALUES('local',?,0)",
                       [(x,) for x in ["a", "b", "child", "archived"]])
        db.commit()
        db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def save_state(self):
        (self.home / ".codex-global-state.json").write_text(json.dumps(self.global_state))

    def test_native_unread_filters_archived_deleted_and_subagents(self):
        self.assertIsNotNone(D, "dashboard adapter missing")
        snap = D.read_codex(self.home, 1000)
        self.assertEqual(snap["unread"]["value"], 2)
        self.assertEqual(snap["unread"]["quality"], "partial")
        self.assertEqual({t["title"] for t in snap["tasks"]}, {"a", "b"})

    def test_unknown_version_does_not_report_zero(self):
        self.assertIsNotNone(D)
        self.global_state["electron-thread-read-state-v1"]["version"] = 2
        self.save_state()
        self.assertIsNone(D.read_codex(self.home, 1000)["unread"]["value"])

    def test_changed_account_clears_cached_identity(self):
        self.assertIsNotNone(D)
        auth = json.loads((self.home / "auth.json").read_text())
        auth["tokens"]["account_id"] = "different"
        (self.home / "auth.json").write_text(json.dumps(auth))
        snap = D.read_codex(self.home, 1000)
        self.assertIsNone(snap["unread"]["value"])
        self.assertEqual(snap["tasks"], [])

    def test_rollout_lifecycle_and_pending_tool(self):
        self.assertIsNotNone(D)
        self.assertEqual(D.rollout_status(self.home / "a.jsonl", 1000), "running")
        with (self.home / "a.jsonl").open("a") as f:
            f.write(json.dumps({"type": "event_msg", "payload": {"type": "task_complete"}}) + "\n")
        self.assertEqual(D.rollout_status(self.home / "a.jsonl", 1000), "idle")
        (self.home / "b.jsonl").write_text("{broken\n")
        self.assertEqual(D.rollout_status(self.home / "b.jsonl", 1000), "unknown")

    def test_fresh_long_turn_keeps_lifecycle_without_full_subscription(self):
        path = self.home / "a.jsonl"
        with path.open("a") as f:
            f.write(json.dumps({"type": "response_item", "payload": {"type": "custom_tool_call_output", "output": "x" * 300000}}) + "\n")
        self.assertEqual(D.rollout_status(path, 1000), "running")

    def test_expired_credentials_never_show_old_account_data(self):
        self.assertIsNotNone(D)
        self.assertEqual(D.read_codex(self.home, 3000)["tasks"], [])

    def test_quota_fields_and_missing_seven_day(self):
        self.assertIsNotNone(D)
        self.assertEqual(D.parse_quota({"seven_day": {"used_percentage": 67}}, 1000)["remaining_pct"], 33)
        self.assertIsNone(D.parse_quota({"five_hour": {"used_percentage": 20}}, 1000)["remaining_pct"])

    def test_claude_running_and_unread_unknown(self):
        self.assertIsNotNone(D)
        snap = D.read_claude({"a": {"state": "working", "ts": 1000},
                              "b": {"state": "needs_you", "ts": 1000}}, {}, 1000)
        self.assertEqual(snap["running"]["value"], 1)
        self.assertEqual(snap["waiting"]["value"], 1)
        self.assertIsNone(snap["unread"]["value"])

    def test_paging_cursor_epoch_and_utf8_budget(self):
        self.assertIsNotNone(D)
        store = D.DashboardStore()
        snap = D.read_codex(self.home, 1000)
        snap["tasks"][0]["title"] = "任务🙂" * 3000
        store.update("codex", snap, 1000)
        page = store.page("codex", "unread", "", "req", 1000)
        wire = D.encode(page)
        self.assertLessEqual(len(wire), 4000)
        self.assertEqual(json.loads(wire)["request_id"], "req")
        self.assertLessEqual(len(page["list"]), 4)
        old = str(store.get("codex", 1000)["generation"]) + ":1"
        snap["identity"] = "changed"
        snap["tasks"] = []
        store.update("codex", snap, 1001)
        self.assertEqual(store.page("codex", "unread", old, "old", 1001)["error"], "stale_cursor")

    def test_freshness_preserves_observation_time(self):
        self.assertIsNotNone(D)
        store = D.DashboardStore()
        snap = D.read_codex(self.home, 1000)
        snap["quota"] = D.parse_quota({"seven_day": {"used_percentage": 20}}, 1000)
        store.update("codex", snap, 1000)
        result = store.get("codex", 1901)
        self.assertEqual(result["quota"]["quality"], "stale")
        self.assertEqual(result["quota"]["observed_at"], 1000)
        self.assertEqual(result["running"]["quality"], "stale")


if __name__ == "__main__":
    unittest.main()
