"""A held Control+M shortcut for user-triggered Codex global dictation.

No transcription endpoint, Codex UI inspection, or automatic task submission.
The emitter is injected so modifier-release failures can be tested safely.
"""
class NativeHold:
    def __init__(self, emit):
        self.emit = emit
        self.down = False

    def release(self):
        try:
            self.emit(46, False, True)
        finally:
            try:
                self.emit(59, False, False)
            finally:
                self.down = False

    def key(self, down):
        if down == self.down:
            return
        if down:
            self.down = True
            try:
                self.emit(59, True, True)
                self.emit(46, True, True)
            except Exception:
                self.release()
                raise
        else:
            self.release()

    def cancel(self):
        try:
            self.emit(53, True, False)
            self.emit(53, False, False)
        finally:
            if self.down:
                self.release()
