import unittest
import threading
from unittest.mock import Mock
from preview_control import PreviewVoice
from codex_delivery import send_preview, discover, DeliveryError

TID='01a1237e-36c6-7af1-addb-faf4651164a8'

class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.row=dict(agent='codex',host='local',thread_id=TID,title='重命名任务',state='idle')
        self.control=Mock();self.control.lock=threading.RLock();self.control.target.return_value=self.row
        self.preview=Mock();self.preview.call.return_value=dict(active=True,text='语音指令')
        self.valid=Mock(return_value=True);self.begin=Mock(return_value=True)
        self.key=Mock();self.end=Mock();self.sender=Mock(return_value=True)
        self.voice=PreviewVoice(self.control,self.preview,self.valid,self.begin,self.key,self.end,self.sender)

    def test_preview_edit_is_read_at_send_and_exact_id_is_bound(self):
        self.assertTrue(self.voice.start('token',True));self.assertTrue(self.voice.stop('token'))
        self.preview.call.return_value=dict(active=False,text='修改后的指令')
        self.assertTrue(self.voice.send('token'))
        self.assertEqual(self.sender.call_args.args[:2],(self.row,'修改后的指令'))
        self.assertFalse(self.voice.send('token'))
        self.key.assert_any_call(True);self.key.assert_any_call(False)

    def test_account_change_after_microphone_setup_never_invokes_shortcut(self):
        self.begin.side_effect=lambda:self.valid.configure_mock(return_value=False) or True
        self.assertFalse(self.voice.start('token',True))
        self.key.assert_not_called();self.end.assert_called_once()

    def test_focus_loss_during_microphone_setup_never_invokes_shortcut(self):
        self.preview.call.side_effect=[dict(active=False),dict(active=True),dict(active=False)]
        self.assertFalse(self.voice.start('token',True))
        self.key.assert_not_called();self.end.assert_called_once()

    def test_cancel_during_final_preview_read_never_invokes_shortcut(self):
        count = [0]
        def read(*args, **kwargs):
            count[0] += 1
            if count[0] == 3:
                self.control.target.return_value=None
            return dict(active=True,text='指令')
        self.preview.call.side_effect=read
        self.assertFalse(self.voice.start('token',True))
        self.key.assert_not_called()

    def test_selection_invalidated_before_socket_dispatch_does_not_emit(self):
        self.voice.start('token',True);self.voice.stop('token')
        emitted=Mock()
        def sender(row,text,validate,dispatch):
            self.control.target.return_value=None
            dispatch(emitted)
        self.sender.side_effect=sender
        self.assertFalse(self.voice.send('token'));emitted.assert_not_called()

    def test_stale_selection_blocks_send(self):
        self.assertTrue(self.voice.start('token',True));self.assertTrue(self.voice.stop('token'))
        self.control.target.return_value=None
        self.assertFalse(self.voice.send('token'));self.sender.assert_not_called()

    def test_empty_preview_can_be_edited_but_timeout_is_never_retried(self):
        self.voice.start('token',True);self.voice.stop('token')
        self.preview.call.return_value=dict(text='  ')
        self.assertFalse(self.voice.send('token'));self.assertTrue(self.voice.ready)
        self.preview.call.return_value=dict(text='非空')
        self.sender.side_effect=TimeoutError()
        self.assertFalse(self.voice.send('token'));self.assertFalse(self.voice.send('token'))
        self.sender.assert_called_once()

    def test_cancel_releases_mic_and_closes_preview(self):
        self.voice.start('token',True);self.voice.cancel()
        self.key.assert_any_call(False);self.end.assert_called_once()
        self.assertFalse(self.voice.send('token'))

class DeliveryTests(unittest.TestCase):
    def client(self):
        c=Mock()
        c.call.side_effect=[dict(handledByClientId='owner',result=dict(supportsUntrustedAppInput=True)),
                            dict(result=dict(settings=dict(resumeState='resumed'))),
                            dict(method='thread-follower-start-turn',result=dict(result={} ))]
        return c

    def test_idle_preserves_settings_and_exact_thread_id(self):
        c=self.client();row=dict(agent='codex',host='local',thread_id=TID,state='idle')
        self.assertTrue(send_preview(row,'指令',lambda:True,lambda:c))
        args=c.call.call_args.args
        self.assertEqual(args[0:2],('thread-follower-start-turn',2))
        self.assertEqual(args[2]['conversationId'],TID)
        self.assertEqual(args[2]['turnStart']['request']['threadId'],TID)
        self.assertTrue(args[2]['turnStart']['context']['inheritThreadSettings'])
        self.assertEqual(args[3],'owner');c.close.assert_called_once()

    def test_running_uses_steer_without_global_enter(self):
        c=self.client()
        c.call.side_effect=[dict(handledByClientId='owner',result=dict(supportsUntrustedAppInput=True)),
            dict(result=dict(settings=dict(resumeState='resumed'))),
            dict(method='thread-follower-steer-turn',result=dict(result={}))]
        send_preview(dict(agent='codex',host='local',thread_id=TID,state='running'),'指令',lambda:True,lambda:c)
        self.assertEqual(c.call.call_args.args[0:2],('thread-follower-steer-turn',1))
        self.assertEqual(c.call.call_args.args[2]['restoreMessage']['context']['prompt'],'指令')

    def test_identity_changed_after_discovery_never_mutates(self):
        c=self.client()
        with self.assertRaises(DeliveryError):
            send_preview(dict(agent='codex',host='local',thread_id=TID,state='idle'),'指令',lambda:False,lambda:c)
        self.assertEqual(c.call.call_count,2);c.close.assert_called_once()

    def test_unknown_or_waiting_state_is_not_sent(self):
        for state in ('unknown','waiting'):
            c=self.client()
            with self.assertRaises(DeliveryError):
                send_preview(dict(agent='codex',host='local',thread_id=TID,state=state),'指令',lambda:True,lambda:c)
            self.assertEqual(c.call.call_count,2)

    def test_remote_target_is_rejected_before_connection(self):
        factory=Mock()
        with self.assertRaises(DeliveryError):
            send_preview(dict(agent='codex',host='remote',thread_id=TID,state='idle'),'指令',lambda:True,factory)
        factory.assert_not_called()
