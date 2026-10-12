"""User-triggered native dictation into the selected Codex composer.

Submission uses Codex's native draft after an explicit device confirmation.
Reads persisted drafts only; no UI reads or transcription-history replay.

"""
import json
import time
import secrets


class ComposerVoice:
    def __init__(self, control, focus, validate, begin, key, end, cancel_key, submit=None, drafts=None, clock=time.time):
        self.control,self.focus,self.validate=control,focus,validate
        self.begin,self.key,self.end,self.cancel_key=begin,key,end,cancel_key
        self.submit=submit;self.ready=False
        self.drafts=drafts;self.clock=clock
        self.revision='';self.fingerprint='';self.baseline='';self.candidate=None
        self.started=0;self.stopped=0;self.wait_since=0;self.waiting=False;self.preview_error=''
        self.token='';self.voice_id='';self.down=False;self.pending=False;self.error=''
        self.preview_stage='idle'

    def current(self, token):
        row=self.control.target(token)
        return row if row and row['agent']=='codex' and self.validate(row) else None

    def cancel(self):
        try:
            if self.pending:
                self.cancel_key()
                self.pending=False
        finally:
            try:
                if self.down:self.end()
            finally:
                self.down=False;self.pending=False
                self.token='';self.voice_id='';self.ready=False;self.waiting=False;self.revision='';self.candidate=None

    def start(self, token, board_mic):
        began=False
        self.error='composer_unavailable'
        try:
            self.cancel()
            row=self.current(token)
            if not row:return False
            if board_mic:
                began=True
                if not self.begin():return False
            if not self.focus(row):return False
            with self.control.lock:
                current=self.current(token)
                if not current or current['thread_id']!=row['thread_id']:return False
                if self.drafts:self.baseline=self.drafts.read(current)[1]
                self.started=self.clock();self.stopped=0;self.preview_error=''
                self.preview_stage='recording'
                self.key(True)
                self.token=token;self.down=True;self.pending=True
            self.error=''
            return True
        except Exception:
            return False
        finally:
            if began and not self.down:self.end()

    def stop(self, token):
        if token!=self.token or not self.down:return False
        ok=False
        try:
            self.key(False);ok=True
        except Exception:
            self.error='composer_unavailable'
        finally:
            try:self.end()
            except Exception:
                ok=False;self.error='composer_unavailable'
            self.down=False
            # Submission and draft lifetime now belong to Codex. After the
            # user releases the key, future selections must not send Escape
            # into a draft or a turn that may already have been submitted.
            self.pending=False
        if not self.current(token):
            self.error='task_changed';return False
        self.stopped=self.clock();self.wait_since=self.stopped
        self.waiting=ok and self.drafts is not None
        self.ready=ok and self.drafts is None
        self.preview_stage='waiting_for_transcript' if ok else 'release_failed'
        return ok

    def poll(self):
        if not self.drafts or self.down or not (self.waiting or self.ready):return None
        def message(text='', error=''):
            return dict(t='task_status',v=1,agent='codex',token=self.token,
                        phase='preview_ready' if not error else 'preview_wait',voice_id=self.voice_id,
                        text=text,revision=self.revision,error=error)
        try:
            row=self.current(self.token)
            if not row:raise ValueError('task_changed')
            text,fingerprint=self.drafts.read(row)
            if self.ready and fingerprint==self.fingerprint:return None
            if self.ready:
                self.ready=False;self.waiting=True;self.revision='';self.candidate=None;self.wait_since=self.clock()
                return message(error='preview_changed')
            if self.clock()-self.wait_since>60:raise ValueError('preview_unavailable')
            if not self.drafts.completed(self.started,self.stopped):
                self.preview_stage='waiting_for_transcript';return None
            if not text.strip():
                self.preview_stage='bound_draft_empty';return None
            if fingerprint==self.baseline:
                self.preview_stage='bound_draft_unchanged';return None
            self.preview_stage='waiting_for_stable_draft'
            if self.candidate is None or self.candidate[0]!=fingerprint:
                self.candidate=(fingerprint,self.clock());return None
            if self.clock()-self.candidate[1]<.75:return None
            self.revision=secrets.token_hex(8)
            result=message(text)
            if len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode())>3700:
                raise ValueError('preview_too_long')
            self.fingerprint=fingerprint;self.ready=True;self.waiting=False;self.preview_error=''
            self.preview_stage='ready'
            return result
        except Exception as exc:
            if self.ready:self.wait_since=self.clock()
            self.ready=False;self.revision='';self.waiting=True;self.candidate=None
            error=str(exc) if str(exc) in ('task_changed','preview_too_long') else 'preview_unavailable'
            if self.preview_error==error:return None
            self.preview_error=error
            return message(error=error)

    def diagnostics(self):
        """Called on the injection worker; never return text, IDs, or tokens."""
        result=dict(stage=self.preview_stage, recording=self.down, waiting=self.waiting,
                    ready=self.ready, error=self.preview_error,
                    started_at=self.started, stopped_at=self.stopped)
        row=self.current(self.token)
        result['selected_valid']=row is not None
        if self.drafts and row:
            try:
                text,fingerprint=self.drafts.read(row)
                result.update(draft_chars=len(text),draft_changed=fingerprint!=self.baseline,
                              transcript_completed=self.drafts.completed(self.started,self.stopped))
            except Exception as exc:
                result['read_error']='unsupported_draft' if str(exc)=='unsupported_draft' else 'read_failed'
        return result

    def send(self, token, revision=''):
        if self.submit is None:
            self.error='send_on_mac';return False
        self.error='voice_not_ready'
        if token!=self.token or self.down or not self.ready:return False
        if self.drafts and (not revision or revision!=self.revision):return False
        self.ready=False  # consume even on uncertain submission; never retry
        self.error='composer_unavailable'
        try:
            row=self.current(token)
            if not row or not self.focus(row):return False
            with self.control.lock:
                current=self.current(token)
                if not current or current['thread_id']!=row['thread_id']:
                    self.error='task_changed';return False
                if self.drafts and self.drafts.read(current)[1]!=self.fingerprint:
                    self.waiting=True;self.candidate=None;self.revision='';self.wait_since=self.clock()
                    self.error='preview_changed';return False
                self.waiting=False
                self.error='delivery_unconfirmed'
                if not self.submit(current):return False
            self.error=''
            return True
        except Exception:
            return False
