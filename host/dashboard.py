"""Local dashboard phase: read-only sources, explicit partial coverage."""
import base64
import copy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading


def metric(value=None, quality="unavailable"):
    return {"value": value, "quality": quality}


def empty_snapshot(agent, now):
    return {"agent": agent, "identity": "", "observed_at": now,
            "running": metric(), "unread": metric(), "waiting": metric(),
            "quota": {"remaining_pct": None, "reset_at": None,
                      "observed_at": 0, "quality": "unavailable"},
            "coverage": {"quality": "partial", "reason": "remote_cloud_unavailable"},
            "tasks": [], "error": ""}


def identity(home, now):
    auth = json.loads((home / "auth.json").read_text())
    if auth.get("auth_mode") != "chatgpt":
        raise ValueError("unsupported_identity")
    tokens = auth.get("tokens", {})
    part = tokens["access_token"].split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    info = claims["https://api.openai.com/auth"]
    account, user = info.get("chatgpt_account_id"), info.get("chatgpt_user_id")
    if (not account or not user or tokens.get("account_id") != account
            or claims.get("exp", 0) <= now):
        raise ValueError("identity_unavailable")
    key = hashlib.sha256(json.dumps(["chatgpt", account, user], separators=(",", ":")).encode()).hexdigest()
    return key, account, user


def rollout_status(path, now):
    try:
        path = Path(path)
        mtime = path.stat().st_mtime
        with path.open("rb") as f:
            size = f.seek(0, 2)
            budget = 8 * 1024 * 1024 if now - mtime <= 30 else 262144
            start = max(0, size - budget)
            f.seek(start)
            data = f.read(budget)
        lines = data.splitlines()[1:] if start else data.splitlines()
        state = "unknown"
        pending = set()
        for line in lines:
            if not any(tag in line for tag in (b'"task_started"', b'"task_complete"', b'"turn_aborted"', b'"request_user_input"', b'"request_permissions"', b'"function_call_output"')):
                continue
            try:
                msg = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            p = msg.get("payload") or {}
            typ = p.get("type")
            if msg.get("type") == "event_msg":
                if typ == "task_started":
                    state, pending = "running", set()
                elif typ in ("task_complete", "turn_aborted"):
                    state, pending = "idle", set()
            elif msg.get("type") == "response_item":
                if typ == "function_call" and p.get("name") in ("request_user_input", "request_permissions"):
                    pending.add(p.get("call_id"))
                elif typ == "function_call_output":
                    pending.discard(p.get("call_id"))
        # A start without an end can survive a crash. Never call an old,
        # unfinished turn actively running from this file alone.
        if state == "running" and now - mtime > 30:
            return "unknown"
        return "waiting" if state == "running" and pending else state
    except (OSError, ValueError, AttributeError, TypeError):
        return "unknown"


def read_codex(home, now):
    home = Path(home)
    snap = empty_snapshot("codex", now)
    try:
        key, account, user = identity(home, now)
        snap["identity"] = key
        state = json.loads((home / ".codex-global-state.json").read_text())
        read = state.get("electron-thread-read-state-v1", {})
        local_key = "local:" + hashlib.sha256(b'["local","local",null]').hexdigest()
        group = read.get("unreadByIdentity", {}).get(key, {})
        unread = group.get(local_key)
        unread_ok = read.get("version") == 1 and isinstance(unread, list) and all(isinstance(t, str) for t in unread)
        db = sqlite3.connect("file:" + str(home / "sqlite/codex-dev.db") + "?mode=ro", uri=True, timeout=1)
        try:
            catalog_columns = {r[1] for r in db.execute("PRAGMA table_info(local_thread_catalog)")}
            display_column = 'display_title' if 'display_title' in catalog_columns else 'NULL'
            visible = dict(db.execute("SELECT thread_id," + display_column + " FROM local_thread_catalog "
                      "WHERE host_id='local' AND missing_candidate=0"))
        finally:
            db.close()
        db = sqlite3.connect("file:" + str(home / "state_5.sqlite") + "?mode=ro", uri=True, timeout=1)
        try:
            columns = {r[1] for r in db.execute("PRAGMA table_info(threads)")}
            updated = "updated_at" if "updated_at" in columns else "0"
            rows = db.execute("SELECT id,title,rollout_path,source,creator_account_id,creator_user_id," + updated + " "
                              "FROM threads WHERE archived=0").fetchall()
        finally:
            db.close()
        for tid, title, path, source, owner_account, owner_user, updated_at in rows:
            if tid not in visible or "subagent" in str(source):
                continue
            if owner_account != account or owner_user != user:
                continue
            if not path or not Path(path).resolve().is_relative_to(home.resolve()):
                status = "unknown"
            else:
                status = rollout_status(path, now)
            snap["tasks"].append({"title": visible.get(tid) or title or "Untitled", "thread_id": tid,
                "host": "local", "host_label": "Mac", "state": status,
                "unread": tid in unread if unread_ok else None, "updated_at": updated_at or 0})
        snap["unread"] = metric(sum(t["unread"] is True for t in snap["tasks"]), "partial") if unread_ok else metric()
        known = [t for t in snap["tasks"] if t["state"] != "unknown"]
        snap["running"] = metric(sum(t["state"] == "running" for t in known), "partial") if known else metric()
        snap["waiting"] = metric(sum(t["state"] == "waiting" for t in known), "partial") if known else metric()
        if not unread_ok:
            snap["error"] = "native_unread_unavailable"
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError, sqlite3.Error):
        # Clear identity and records rather than retaining another account's data.
        snap = empty_snapshot("codex", now)
        snap["error"] = "local_source_unavailable"
    return snap


def parse_quota(payload, now):
    result = empty_snapshot("", now)["quota"]
    window = payload.get("seven_day") if isinstance(payload, dict) else None
    used = window.get("used_percentage") if isinstance(window, dict) else None
    if isinstance(used, (int, float)) and not isinstance(used, bool) and math.isfinite(used):
        reset = window.get("resets_at")
        if not isinstance(reset, (str, int, float)) or isinstance(reset, bool):
            reset = None
        if isinstance(reset, str):
            reset = reset[:80]
        if isinstance(reset, float) and not math.isfinite(reset):
            reset = None
        result.update(remaining_pct=max(0, min(100, 100 - used)), reset_at=reset,
                      observed_at=now, quality="ok")
    return result


def read_claude(sessions, quota, now):
    snap = empty_snapshot("claude", now)
    snap["identity"] = "claude-local"
    snap["quota"] = copy.deepcopy(quota) if quota else snap["quota"]
    for sid, row in sessions.items():
        if row.get("parent_session_id") or now - row.get("ts", 0) > 86400:
            continue
        status = {"working": "running", "needs_you": "waiting", "idle": "idle", "done": "idle"}.get(row.get("state"), "unknown")
        snap["tasks"].append({"title": row.get("title") or row.get("cwd") or "Claude session",
            "thread_id": sid, "host": "local", "host_label": "Mac", "state": status, "unread": None, "updated_at": row.get("ts", 0)})
    snap["running"] = metric(sum(t["state"] == "running" for t in snap["tasks"]), "ok")
    snap["waiting"] = metric(sum(t["state"] == "waiting" for t in snap["tasks"]), "ok")
    snap["coverage"] = {"quality": "ok", "reason": "claude_local_sessions"}
    return snap


def encode(value):
    data = (json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()
    if len(data) > 4000:
        raise ValueError("dashboard_message_too_large")
    return data


class DashboardStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.snapshots = {}
        self.generation = 0

    def update(self, agent, snap, now):
        with self.lock:
            previous = self.snapshots.get(agent)
            signature = (snap["identity"], json.dumps(snap["tasks"], sort_keys=True))
            if not previous or previous["_signature"] != signature:
                self.generation += 1
            new = copy.deepcopy(snap)
            new["generation"] = self.generation if not previous or previous["_signature"] != signature else previous["generation"]
            new["_signature"] = signature
            new["observed_at"] = now
            for index, row in enumerate(new["tasks"]):
                row["handle"] = "%s:%s" % (new["generation"], index)
            self.snapshots[agent] = new

    def get(self, agent, now):
        with self.lock:
            snap = copy.deepcopy(self.snapshots.get(agent, empty_snapshot(agent, now)))
        snap.setdefault("generation", 0)
        snap.pop("_signature", None)
        if now - snap["observed_at"] > 30:
            for name in ("running", "unread", "waiting"):
                if snap[name]["value"] is not None:
                    snap[name]["quality"] = "stale"
        if snap["quota"]["remaining_pct"] is not None and now - snap["quota"]["observed_at"] > 900:
            snap["quota"]["quality"] = "stale"
        return snap

    def summary(self, agent, now):
        snap = self.get(agent, now)
        snap.pop("tasks", None)
        snap.pop("identity", None)
        return dict(snap, t="dashboard", v=1)

    def page(self, agent, filter_name, cursor, request_id, now, read_limit=5):
        snap = self.get(agent, now)
        result = {"t": "tasks", "v": 1, "agent": agent, "generation": snap["generation"],
                  "request_id": str(request_id)[:24], "list": [], "next_cursor": "", "error": ""}
        if filter_name == "catalog":
            return self.catalog(snap, cursor, request_id, now, read_limit)
        if filter_name not in ("unread", "running"):
            result["error"] = "invalid_filter"
            return result
        if snap[filter_name]["value"] is None or snap[filter_name]["quality"] == "stale":
            result["error"] = "source_unavailable"
            return result
        offset = 0
        if cursor:
            try:
                epoch_text, cursor_filter, offset_text = str(cursor).split(":")
                epoch, offset = int(epoch_text), int(offset_text)
                if cursor_filter != filter_name:
                    raise ValueError()
                if epoch != snap["generation"] or offset < 0:
                    raise ValueError()
            except (ValueError, TypeError):
                result["error"] = "stale_cursor"
                return result
        tasks = [t for t in snap["tasks"] if (t["unread"] is True if filter_name == "unread" else t["state"] == "running")]
        for row in tasks[offset:offset + 4]:
            result["list"].append({k: row[k] for k in ("handle", "host_label", "state", "unread")})
            result["list"][-1]["title"] = row["title"][:180]
        if offset + len(result["list"]) < len(tasks):
            result["next_cursor"] = "%s:%s:%s" % (snap["generation"], filter_name, offset + len(result["list"]))
        result["complete"] = snap["coverage"]["quality"] == "ok"
        return result

    def catalog(self, snap, cursor, request_id, now, read_limit):
        result = {"t": "tasks", "v": 1, "agent": snap["agent"], "generation": snap["generation"],
                  "request_id": str(request_id)[:24], "list": [], "next_cursor": "", "error": ""}
        if not snap["identity"] or snap.get("error") == "local_source_unavailable" or now - snap["observed_at"] > 30:
            result["error"] = "source_unavailable"
            return result
        try:
            limit = max(5, min(500, int(read_limit)))
        except (ValueError, TypeError):
            result["error"] = "invalid_limit"
            return result
        offset = 0
        if cursor:
            try:
                generation, kind, cursor_limit, offset_text = str(cursor).split(":")
                offset = int(offset_text)
                if int(generation) != snap["generation"] or kind != "catalog" or int(cursor_limit) != limit or offset < 0:
                    raise ValueError()
            except (ValueError, TypeError):
                result["error"] = "stale_cursor"
                return result
        groups = {"running": [], "unread": [], "read": [], "unknown": []}
        for task in snap["tasks"]:
            kind = "running" if task["state"] == "running" else "unread" if task["unread"] is True or task["state"] == "waiting" else "read" if task["unread"] is False else "unknown"
            groups[kind].append(dict(task, kind=kind))
        for group in groups.values():
            group.sort(key=lambda row: (row.get("updated_at", 0), row["thread_id"]), reverse=True)
        # Claude has no native read-state source. Show recent sessions explicitly
        # as unknown, never invent a read confirmation.
        recent = groups["read"] + groups["unknown"]
        tasks = groups["running"] + groups["unread"] + recent[:limit]
        result.update(total=len(tasks), has_more_read=len(recent) > limit,
                      complete=snap["coverage"]["quality"] == "ok")
        for row in tasks[offset:offset + 4]:
            item = {key: row[key] for key in ("handle", "host_label", "state", "unread", "kind")}
            item["title"] = row["title"][:180]
            result["list"].append(item)
        if offset + len(result["list"]) < len(tasks):
            result["next_cursor"] = "%s:catalog:%s:%s" % (snap["generation"], limit, offset + len(result["list"]))
        return result

    def resolve(self, agent, handle, now):
        return next((t for t in self.get(agent, now)["tasks"] if t["handle"] == handle), None)
