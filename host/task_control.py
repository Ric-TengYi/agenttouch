"""Selection tokens bind device actions to an identity and stable conversation ID."""
import json
import secrets
import threading
import time
from urllib.parse import urlparse, parse_qs


def route_matches(url, thread_id):
    try:
        route = urlparse(url)
        if parse_qs(route.query).get('hostId', ['local']) != ['local']:
            return False
        return ((route.scheme == 'app' and route.netloc == '-' and route.path == '/local/thread/' + thread_id)
                or (route.scheme == 'codex' and route.netloc == 'threads' and route.path == '/' + thread_id))
    except (TypeError, ValueError):
        return False


class TaskControl:
    def __init__(self, store, clock=time.time):
        self.store, self.clock = store, clock
        self.lock = threading.RLock()
        self.selected = None

    def clear(self):
        with self.lock:
            self.selected = None

    def select(self, agent, handle):
        with self.lock:
            self.selected = None
            now = self.clock()
            snap = self.store.get(agent, now)
            result = dict(t='task_selected', v=1, agent=agent, token='', error='')
            if not snap['identity'] or now - snap['observed_at'] > 30:
                return dict(result, error='source_unavailable')
            row = next((r for r in snap['tasks'] if r['handle'] == handle), None)
            if not row:
                return dict(result, error='task_changed')
            token = secrets.token_hex(16)
            self.selected = (token, agent, snap['identity'], row['thread_id'])
            # UTF-8 limit keeps the entire response below the board's 4096 B line.
            title = row['title'].encode('utf8')[:3200].decode('utf8', 'ignore')
            response = dict(result, token=token, title=title, state=row['state'], title_clipped=title != row['title'])
            # Measure escaped JSON, not only raw UTF-8: quote/newline-heavy
            # titles can double in size. Leave room for the echoed request ID.
            while len(json.dumps(response, ensure_ascii=False, separators=(',', ':')).encode('utf8')) > 3700:
                title = title[:max(0, len(title) - 100)]
                response.update(title=title, title_clipped=True)
            return response

    def target(self, token):
        with self.lock:
            if not self.selected or not token or token != self.selected[0]:
                return None
            _, agent, identity, thread_id = self.selected
            now = self.clock()
            snap = self.store.get(agent, now)
            if snap['identity'] != identity or now - snap['observed_at'] > 30:
                return None
            row = next((r for r in snap['tasks'] if r['thread_id'] == thread_id and r['host'] == 'local'), None)
            return dict(row, agent=agent) if row else None

    def run(self, token, focus, action):
        row = self.target(token)
        if row is None or not focus(row):
            return False
        # Opening a conversation can change its read-state and catalogue order.
        # Revalidate the stable ID and identity, never the old row number.
        with self.lock:
            current = self.target(token)
            if current is None or (current['thread_id'], current['agent']) != (row['thread_id'], row['agent']):
                return False
            action(current)
            return True


class SelectedVoice:
    """Called on the existing serial injection worker; one utterance per token."""
    def __init__(self, control, focus, begin, key, end, enter):
        self.control, self.focus = control, focus
        self.begin, self.key, self.end, self.enter = begin, key, end, enter
        self.token, self.down, self.ready = '', False, False

    def cancel(self):
        if self.down:
            self.key(False)
            self.end()
        self.token, self.down, self.ready = '', False, False

    def start(self, token, board_mic):
        self.cancel()
        def start(row):
            if board_mic and not self.begin():
                self.end()
                return
            if self.control.target(token) is None or not self.focus(row) or self.control.target(token) is None:
                if board_mic: self.end()
                return
            self.key(True)
            self.token, self.down = token, True
        self.control.run(token, self.focus, start)
        return self.down

    def stop(self, token):
        if token != self.token or not self.down:
            return False
        self.key(False)
        self.end()
        self.down, self.ready = False, True
        return True

    def send(self, token):
        if token != self.token or self.down or not self.ready:
            return False
        self.ready = False  # single use even if focus fails
        return self.control.run(token, self.focus, lambda row: self.enter())
