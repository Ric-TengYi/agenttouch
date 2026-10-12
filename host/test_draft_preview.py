import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from test_composer_control import DeviceSendTests

class PreviewGateTests(DeviceSendTests):
    def setUp(self):
        super().setUp()
        self.clock_value=10
        self.snapshot=('', 'empty')
        self.source=Mock()
        self.source.read.side_effect=lambda row:self.snapshot
        self.source.completed.return_value=False
        self.voice.drafts=self.source
        self.voice.clock=lambda:self.clock_value

    def test_release_alone_never_arms_send(self):
        self.voice.start('selected',True);self.voice.stop('selected')
        self.assertFalse(self.voice.send('selected'));self.submit.assert_not_called()

    def prepare(self):
        self.voice.start('selected',True);self.voice.stop('selected')
        self.snapshot=('测试内容', 'new')
        self.source.completed.return_value=True
        self.voice.poll();self.clock_value+=1
        return self.voice.poll()

    def test_complete_stable_draft_is_previewed_before_confirmation(self):
        message=self.prepare()
        self.assertEqual(message['text'],'测试内容')
        self.assertFalse(self.voice.send('selected',revision='wrong'))
        self.assertTrue(self.voice.send('selected',revision=message['revision']))
        self.assertEqual(self.submit.call_count,1)

    def test_changed_mac_draft_blocks_old_preview_send(self):
        message=self.prepare();self.snapshot=('Mac修改后的内容','changed')
        self.assertFalse(self.voice.send('selected',revision=message['revision']))
        self.submit.assert_not_called()

    def test_audio_complete_without_transcript_cannot_enable_send(self):
        self.voice.start('selected',True);self.voice.stop('selected')
        self.snapshot=('新内容','new')
        self.voice.poll();self.clock_value+=2
        self.assertIsNone(self.voice.poll());self.assertFalse(self.voice.ready)

    def test_diagnostics_distinguishes_transcript_from_missing_bound_draft(self):
        self.voice.start('selected',True);self.voice.stop('selected')
        self.source.completed.return_value=True
        self.voice.poll()
        result=self.voice.diagnostics()
        self.assertEqual(result['stage'],'bound_draft_empty')
        self.assertTrue(result['transcript_completed'])
        self.assertEqual(result['draft_chars'],0)
        self.assertNotIn('text',result);self.assertNotIn('token',result)
        self.assertNotIn('thread_id',result)
        self.submit.assert_not_called()

    def test_large_preview_never_truncates_and_enables_send(self):
        self.snapshot=('old','old');self.voice.start('selected',True);self.voice.stop('selected')
        self.snapshot=('"\\\n'*3000,'big');self.source.completed.return_value=True
        self.voice.poll();self.clock_value+=2
        message=self.voice.poll()
        self.assertEqual(message['error'],'preview_too_long');self.assertFalse(self.voice.ready)

    def test_changed_account_or_task_clears_preview_permission(self):
        self.prepare();self.control.target.return_value=None
        message=self.voice.poll()
        self.assertEqual(message['error'],'task_changed');self.assertFalse(self.voice.ready)
        self.assertFalse(self.voice.send('selected',revision=message['revision']))
        self.submit.assert_not_called()

    def test_delayed_draft_arrival_times_out_instead_of_confirming_old_text(self):
        self.voice.start('selected',True);self.voice.stop('selected')
        self.source.completed.return_value=True;self.clock_value+=61
        self.assertEqual(self.voice.poll()['error'],'preview_unavailable')
        self.assertFalse(self.voice.ready)

    def test_mac_edit_gets_new_revision_and_old_revision_stays_invalid(self):
        first=self.prepare();self.snapshot=('修改后的内容','edit')
        changed=self.voice.poll();self.assertEqual(changed['error'],'preview_changed')
        self.voice.poll();self.clock_value+=1;new=self.voice.poll()
        self.assertEqual(new['text'],'修改后的内容')
        self.assertNotEqual(first['revision'],new['revision'])
        self.assertFalse(self.voice.send('selected',revision=first['revision']))
        self.assertTrue(self.voice.send('selected',revision=new['revision']))

    def test_transient_draft_read_failure_recovers_with_new_preview(self):
        self.prepare();self.clock_value+=90;self.source.read.side_effect=OSError('busy')
        self.assertEqual(self.voice.poll()['error'],'preview_unavailable')
        self.assertFalse(self.voice.ready)
        self.source.read.side_effect=lambda row:self.snapshot
        self.voice.poll();self.clock_value+=1
        message=self.voice.poll()
        self.assertEqual(message['text'],'测试内容');self.assertTrue(self.voice.ready)

    # Base tests exercise the compatibility path without the new draft reader.
    def test_device_send_requires_release_and_only_submits_once(self):
        self.voice.drafts=None;super().test_device_send_requires_release_and_only_submits_once()
    def test_task_change_during_send_navigation_never_submits(self):
        self.voice.drafts=None;super().test_task_change_during_send_navigation_never_submits()
    def test_submit_failure_is_not_automatically_retried(self):
        self.voice.drafts=None;super().test_submit_failure_is_not_automatically_retried()

class DraftSourceTests(unittest.TestCase):
    def test_native_dictation_marker_does_not_hide_plain_text(self):
        from draft_preview import DraftSource
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            draft={'prompt':'本次语音', 'pullRequestChecks':[], 'usedDictation':True}
            path=root/'.codex-global-state.json'
            def save():
                path.write_text(json.dumps({'electron-persisted-atom-state':{
                    'composer-prompt-drafts-v2':{'local:task':draft}}}))
            save()
            self.assertEqual(DraftSource(root).read({'thread_id':'task'})[0],'本次语音')
            draft['usedDictation']='invalid';save()
            with self.assertRaises(ValueError):DraftSource(root).read({'thread_id':'task'})
            draft['usedDictation']=True;draft['fileAttachments']=['hidden'];save()
            with self.assertRaises(ValueError):DraftSource(root).read({'thread_id':'task'})

    def test_wrapped_draft_cannot_hide_outer_attachments(self):
        from draft_preview import DraftSource
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'.codex-global-state.json').write_text(json.dumps({
                'electron-persisted-atom-state':{'composer-prompt-drafts-v2':{
                    'local:task':{'draft':{'prompt':'visible','usedDictation':True},
                                  'fileAttachments':['hidden']}}}}))
            with self.assertRaises(ValueError):DraftSource(root).read({'thread_id':'task'})

    def test_actual_bound_draft_and_completion_marker(self):
        from draft_preview import DraftSource
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            draft={'prompt':{'document':{'type':'doc','content':[{'type':'paragraph','content':[{'type':'text','text':'中文测试'},{'type':'hardBreak'},{'type':'text','text':'下一行'}]}]}},'pullRequestChecks':[]}
            state={'electron-persisted-atom-state':{'composer-prompt-drafts-v2':{'local:task':draft}}}
            (root/'.codex-global-state.json').write_text(json.dumps(state))
            history=root/'dictation-history'/'record';history.mkdir(parents=True)
            metadata={'id':'id','createdAtMs':10000,'surface':'composer','status':'completed','text':''}
            (history/'metadata.json').write_text(json.dumps(metadata))
            source=DraftSource(root)
            self.assertEqual(source.read({'thread_id':'task'})[0],'中文测试\n下一行')
            self.assertEqual(source.read({'thread_id':'other'})[0],'')
            self.assertFalse(source.completed(9,11))
            metadata['text']='中文测试';(history/'metadata.json').write_text(json.dumps(metadata))
            self.assertTrue(source.completed(9,11))
            metadata['surface']='global'
            (history/'metadata.json').write_text(json.dumps(metadata))
            self.assertTrue(source.completed(9,11))
            metadata['surface']='unknown'
            (history/'metadata.json').write_text(json.dumps(metadata))
            self.assertFalse(source.completed(9,11))
            metadata['surface']='composer'
            (history/'metadata.json').write_text(json.dumps(metadata))
            self.assertFalse(source.completed(11,12))
            other=root/'dictation-history'/'another';other.mkdir()
            (other/'metadata.json').write_text(json.dumps(dict(metadata,id='other')))
            self.assertFalse(source.completed(9,11))  # two recordings are ambiguous
            state['electron-persisted-atom-state']['composer-prompt-drafts-v2']['local:task']['pullRequestChecks']=['hidden-check']
            (root/'.codex-global-state.json').write_text(json.dumps(state))
            with self.assertRaises(ValueError):source.read({'thread_id':'task'})
            (root/'.codex-global-state.json').write_text('{')
            with self.assertRaises(ValueError):source.read({'thread_id':'task'})
    def test_unknown_rich_node_fails_closed(self):
        from draft_preview import plain_text
        with self.assertRaises(ValueError):plain_text({'type':'doc','content':[{'type':'mention','attrs':{'id':'secret'}}]})
        with self.assertRaises(ValueError):plain_text({'type':'text','text':'label','marks':[{'type':'link','attrs':{'href':'https://example.com'}}]})
