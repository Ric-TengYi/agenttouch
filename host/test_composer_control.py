import unittest
import threading
from unittest.mock import Mock
from composer_control import ComposerVoice

class ComposerVoiceTests(unittest.TestCase):
    def setUp(self):
        self.row=dict(agent='codex',thread_id='task',host='local')
        self.control=Mock();self.control.lock=threading.RLock();self.control.target.return_value=self.row
        self.focus=Mock(return_value=True);self.begin=Mock(return_value=True)
        self.key=Mock();self.end=Mock();self.cancel_key=Mock()
        self.voice=ComposerVoice(self.control,self.focus,lambda r:True,self.begin,self.key,self.end,self.cancel_key)

    def test_selected_task_records_then_leaves_submission_to_mac(self):
        self.assertTrue(self.voice.start('selected',True))
        self.focus.assert_called_once_with(self.row)
        self.assertTrue(self.voice.stop('selected'))
        self.assertEqual([c.args for c in self.key.call_args_list],[(True,),(False,)])
        self.end.assert_called_once()
        self.assertFalse(self.voice.send('selected'))
        self.assertEqual(self.voice.error,'send_on_mac')

    def test_changed_target_during_navigation_never_starts_shortcut(self):
        def focus(row):self.control.target.return_value=None;return True
        self.focus.side_effect=focus
        self.assertFalse(self.voice.start('selected',True));self.key.assert_not_called()
        self.end.assert_called_once()

    def test_navigation_failure_cleans_audio_and_never_starts(self):
        self.focus.side_effect=RuntimeError('navigation failed')
        self.assertFalse(self.voice.start('selected',True));self.key.assert_not_called()
        self.end.assert_called_once()

    def test_wrong_release_token_cannot_stop_another_utterance(self):
        self.voice.start('selected',True)
        self.assertFalse(self.voice.stop('other'));self.assertTrue(self.voice.down)
        self.assertEqual(self.key.call_count,1)

    def test_cancel_after_release_leaves_codex_draft_or_sent_turn_alone(self):
        self.voice.start('selected',True);self.voice.stop('selected');self.voice.cancel()
        self.cancel_key.assert_not_called();self.assertEqual(self.voice.token,'')

    def test_cancel_while_button_held_releases_native_keys_and_audio(self):
        self.voice.start('selected',True);self.voice.cancel()
        self.cancel_key.assert_called_once();self.end.assert_called_once()
        self.assertFalse(self.voice.down);self.assertFalse(self.voice.pending)

    def test_failed_key_release_closes_audio_and_blocks_delivery(self):
        self.voice.start('selected',True);self.key.side_effect=RuntimeError('release failed')
        self.assertFalse(self.voice.stop('selected'));self.end.assert_called_once()
        self.assertFalse(self.voice.down);self.assertFalse(self.voice.send('selected'))

class DeviceSendTests(ComposerVoiceTests):
    def setUp(self):
        super().setUp()
        self.submit=Mock(return_value=True)
        self.voice=ComposerVoice(self.control,self.focus,lambda r:True,self.begin,self.key,self.end,self.cancel_key,submit=self.submit)

    def test_device_send_requires_release_and_only_submits_once(self):
        self.assertFalse(self.voice.send('selected'));self.submit.assert_not_called()
        self.voice.start('selected',True)
        self.assertFalse(self.voice.send('selected'));self.submit.assert_not_called()
        self.voice.stop('selected')
        self.assertFalse(self.voice.send('other'));self.submit.assert_not_called()
        self.assertTrue(self.voice.send('selected'));self.submit.assert_called_once_with(self.row)
        self.assertFalse(self.voice.send('selected'));self.assertEqual(self.submit.call_count,1)

    def test_task_change_during_send_navigation_never_submits(self):
        self.voice.start('selected',True);self.voice.stop('selected')
        def focus(row):self.control.target.return_value=None;return True
        self.focus.side_effect=focus
        self.assertFalse(self.voice.send('selected'));self.submit.assert_not_called()

    def test_submit_failure_is_not_automatically_retried(self):
        self.voice.start('selected',True);self.voice.stop('selected')
        self.submit.side_effect=RuntimeError('send failed')
        self.assertFalse(self.voice.send('selected'));self.assertFalse(self.voice.send('selected'))
        self.assertEqual(self.submit.call_count,1)

    # The shared base test specifies manual-only mode without submit callback.
    def test_selected_task_records_then_leaves_submission_to_mac(self):
        self.voice.submit=None
        super().test_selected_task_records_then_leaves_submission_to_mac()

class HostSubmitTests(unittest.TestCase):
    def test_wrong_front_app_cannot_receive_device_send(self):
        from unittest.mock import patch
        import agentpet_host as H
        with patch.object(H,'selected_identity',return_value=True), \
             patch.object(H,'_frontmost_app',return_value='Notes|Notes'), \
             patch.object(H,'post_key') as post:
            self.assertFalse(H.submit_codex_composer({'agent':'codex'}));post.assert_not_called()

    def test_matching_front_app_dispatches_once_only_on_explicit_submit(self):
        from unittest.mock import patch
        import agentpet_host as H
        with patch.object(H,'selected_identity',return_value=True), \
             patch.object(H,'_frontmost_app',return_value='ChatGPT|com.openai.codex'), \
             patch.object(H,'post_key') as post:
            self.assertTrue(H.submit_codex_composer({'agent':'codex'}));post.assert_called_once_with('enter')
