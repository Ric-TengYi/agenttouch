"""Dashboard collection runs outside the host's transport and state locks."""
import copy
from pathlib import Path
import threading
import time
import dashboard as D
from codex_rpc import DaemonWebsocket


def codex_quota(home, now):
    key, account, _ = D.identity(home, now)
    rpc = DaemonWebsocket(home / 'app-server-control/app-server-control.sock')
    try:
        rpc.handshake()
        rpc.call(1, 'initialize', {'clientInfo': {'name': 'agenttouch_dashboard', 'version': '1'},
                                 'capabilities': {'experimentalApi': True}})
        rpc.send({'method': 'initialized'})
        result = rpc.call(2, 'account/rateLimits/read', {})
        if result.get('accountId') != account or D.identity(home, time.time())[0] != key:
            raise ValueError('quota_identity_changed')
        for window in result.get('rateLimits', {}).values():
            if isinstance(window, dict) and window.get('windowDurationMins') == 10080:
                return key, D.parse_quota({'seven_day': {'used_percentage': window.get('usedPercent'),
                           'resets_at': window.get('resetsAt')}}, now)
        return key, D.parse_quota({}, now)
    finally:
        rpc.close()


class DashboardService:
    def __init__(self, home=None):
        self.home = Path(home or Path.home() / '.codex')
        self.store = D.DashboardStore()
        self.lock = threading.Lock()
        self.claude_quota = None
        self.quota_key, self.quota = '', None
        self.last_quota_try = 0

    def accept_claude_quota(self, payload):
        with self.lock:
            self.claude_quota = D.parse_quota(payload, time.time())

    def collect(self, sessions, now):
        snap = D.read_codex(self.home, now)
        if snap['identity'] != self.quota_key:
            self.quota_key, self.quota = snap['identity'], None
            self.last_quota_try = 0
        if snap['identity'] and now - self.last_quota_try >= 300:
            self.last_quota_try = now
            try:
                key, quota = codex_quota(self.home, now)
                if key == snap['identity']:
                    self.quota = quota
            except (OSError, ValueError, KeyError, TypeError, EOFError):
                pass
        try:
            current_key = D.identity(self.home, time.time())[0]
        except (OSError, ValueError, KeyError, TypeError, IndexError):
            current_key = ''
        if current_key != snap['identity']:
            snap = D.empty_snapshot('codex', now)
            snap['error'] = 'identity_changed'
            self.quota_key, self.quota = '', None
        if self.quota:
            snap['quota'] = copy.deepcopy(self.quota)
        self.store.update('codex', snap, now)
        with self.lock:
            quota = copy.deepcopy(self.claude_quota)
        self.store.update('claude', D.read_claude(sessions, quota, now), now)

    def start(self, session_reader, push):
        def run():
            while True:
                try:
                    self.collect(session_reader(), time.time())
                    for agent in ('codex', 'claude'):
                        push(D.encode(self.store.summary(agent, time.time())))
                except Exception:
                    # A failing source must age out, never stop the existing host.
                    pass
                time.sleep(5)
        threading.Thread(target=run, name='dashboard', daemon=True).start()
