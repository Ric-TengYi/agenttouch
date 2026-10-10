"""Bound, single-use preview sessions for Codex; legacy Claude stays separate."""
import json
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid


class PreviewWindow:
    def __init__(self):
        self.process = None
        self.responses = queue.Queue()

    def close(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process.stdin.close()
            self.process.stdout.close()
            self.process = None

    def call(self, op, **kwargs):
        if self.process is None or self.process.poll() is not None:
            self.close()
            self.responses = queue.Queue()
            self.process = subprocess.Popen(['/usr/bin/python3', str(Path(__file__).with_name('voice_preview.py'))],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1)
            responses, process = self.responses, self.process
            def read():
                for line in process.stdout:
                    try:
                        responses.put(json.loads(line))
                    except ValueError:
                        pass
                responses.put(None)
            threading.Thread(target=read, daemon=True).start()
        request_id = str(uuid.uuid4())
        self.process.stdin.write(json.dumps(dict(op=op, id=request_id, **kwargs))+'\n')
        self.process.stdin.flush()
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            result = self.responses.get(timeout=max(.001, deadline-time.monotonic()))
            if result is None:
                raise RuntimeError('preview closed')
            if result.get('id') == request_id:
                return result
        raise TimeoutError()


class PreviewVoice:
    def __init__(self, control, preview, validate, begin, key, end, send):
        self.control, self.preview, self.validate = control, preview, validate
        self.begin, self.key, self.end, self.sender = begin, key, end, send
        self.token, self.down, self.ready = '', False, False
        self.error = ''

    def current(self, token):
        row = self.control.target(token)
        return row if row and row['agent'] == 'codex' and self.validate(row) else None

    def cancel(self):
        if self.down:
            self.key(False)
            self.end()
        self.token, self.down, self.ready = '', False, False
        self.preview.close()

    def start(self, token, board_mic):
        self.cancel()
        self.error = 'preview_unavailable'
        row = self.current(token)
        if not row:
            return False
        began = False
        try:
            self.preview.call('show', title=row['title'])
            # Activation is asynchronous; Cocoa needs another event-loop pass.
            time.sleep(.25)
            if not self.preview.call('read')['active']:
                return False
            if board_mic:
                began = True
                if not self.begin():
                    return False
            # Microphone preparation can take time; prove our own editor is
            # still foreground before invoking the dictation shortcut.
            focused = self.preview.call('read')['active']
            with self.control.lock:
                if not focused or not self.current(token):
                    return False
                self.key(True)
                self.token, self.down = token, True
            self.error = ''
            return True
        except Exception:
            return False
        finally:
            if not self.down:
                if began:
                    self.end()
                self.preview.close()

    def stop(self, token):
        if token != self.token or not self.down:
            return False
        self.key(False)
        self.end()
        self.down, self.ready = False, bool(self.current(token))
        self.error = '' if self.ready else 'task_changed'
        return self.ready

    def send(self, token):
        if token != self.token or self.down or not self.ready:
            return False
        self.ready = False  # consume before any IPC; no implicit retry
        self.error = 'delivery_unconfirmed'
        try:
            row = self.current(token)
            text = self.preview.call('read')['text'].strip()
            if not row or not self.current(token):
                self.error = 'task_changed'
                return False
            if not text:
                self.error = 'preview_empty'
                self.ready = True  # no mutation attempted; allow editing
                return False
            def dispatch(emit):
                with self.control.lock:
                    if not self.current(token):
                        raise RuntimeError('target changed before dispatch')
                    emit()
            if not self.sender(row, text, lambda: bool(self.current(token)), dispatch=dispatch):
                return False
            self.error = ''
            self.preview.close()
            return True
        except Exception:
            return False
