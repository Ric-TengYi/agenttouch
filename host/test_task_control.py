import unittest
import dashboard as D
try:
    from task_control import TaskControl, route_matches
except ImportError:
    TaskControl = None
    route_matches = None


def snapshot(now=1000):
    snap = D.empty_snapshot('codex', now)
    snap['identity'] = 'account'
    for index in range(12):
        snap['tasks'].append({'thread_id':str(index),'title':'任务'+str(index),'host':'local',
            'host_label':'Mac','state':'running' if index==0 else 'idle',
            'unread':index==1,'updated_at':100-index})
    return snap

class TaskControlTests(unittest.TestCase):
    def setUp(self):
        self.store=D.DashboardStore();self.store.update('codex',snapshot(),1000)

    def test_catalog_orders_groups_and_adds_five_recent_read(self):
        page=self.store.page('codex','catalog','','req',1000,read_limit=5)
        self.assertEqual([r['kind'] for r in page['list'][:2]],['running','unread'])
        records=page['list'][:]
        while page['next_cursor']:
            page=self.store.page('codex','catalog',page['next_cursor'],'req',1000,read_limit=5)
            records+=page['list']
        self.assertEqual(len(records),7)
        self.assertEqual(sum(r['kind']=='read' for r in records),5)
        first=self.store.page('codex','catalog','','req',1000,read_limit=10)
        self.assertTrue(first['has_more_read'] is False)
        self.assertEqual(first['total'],12)

    def test_more_cursor_is_bound_to_read_limit(self):
        page=self.store.page('codex','catalog','','req',1000,read_limit=5)
        self.assertEqual(self.store.page('codex','catalog',page['next_cursor'],'req',1000,read_limit=10)['error'],'stale_cursor')

    def test_selected_target_survives_native_mark_read_and_reorder(self):
        self.assertIsNotNone(TaskControl)
        control=TaskControl(self.store,clock=lambda:1000)
        handle=self.store.get('codex',1000)['tasks'][1]['handle']
        chosen=control.select('codex',handle)
        new=snapshot();new['tasks'][1]['unread']=False;new['tasks'].reverse()
        self.store.update('codex',new,1001)
        self.assertEqual(control.target(chosen['token'])['thread_id'],'1')

    def test_account_switch_and_removed_task_invalidate_selection(self):
        self.assertIsNotNone(TaskControl)
        control=TaskControl(self.store,clock=lambda:1000)
        token=control.select('codex',self.store.get('codex',1000)['tasks'][0]['handle'])['token']
        new=snapshot();new['identity']='other';self.store.update('codex',new,1001)
        self.assertIsNone(control.target(token))

    def test_failed_focus_never_starts_voice_or_sends(self):
        self.assertIsNotNone(TaskControl)
        calls=[];control=TaskControl(self.store,clock=lambda:1000)
        token=control.select('codex',self.store.get('codex',1000)['tasks'][0]['handle'])['token']
        self.assertFalse(control.run(token,lambda row:False,lambda row:calls.append(row)))
        self.assertEqual(calls,[])
        self.assertTrue(control.run(token,lambda row:True,lambda row:calls.append(row)))
        self.assertEqual(calls[0]['thread_id'],'0')

    def test_route_exact_id_and_local_host_only(self):
        self.assertIsNotNone(route_matches)
        tid='01a1237e-36c6-7af1-addb-faf4651164a8'
        self.assertTrue(route_matches('app://-/local/thread/'+tid,tid))
        self.assertFalse(route_matches('app://-/local/thread/'+tid+'/other',tid))
        self.assertFalse(route_matches('codex://threads/'+tid+'?hostId=remote',tid))
        self.assertFalse(route_matches('app://-/local/thread/other',tid))

    def test_cancelled_or_expired_selection_cannot_send(self):
        self.assertIsNotNone(TaskControl)
        control=TaskControl(self.store,clock=lambda:1040)
        self.assertEqual(control.select('codex',self.store.get('codex',1000)['tasks'][0]['handle'])['error'],'source_unavailable')

class VoiceTests(unittest.TestCase):
    def setUp(self):
        from task_control import SelectedVoice
        self.store=D.DashboardStore();self.store.update('codex',snapshot(),1000)
        self.control=TaskControl(self.store,clock=lambda:1000)
        self.token=self.control.select('codex',self.store.get('codex',1000)['tasks'][0]['handle'])['token']
        self.calls=[];self.focus_ok=True;self.mic_ok=True
        self.voice=SelectedVoice(self.control,lambda row:self.focus_ok,lambda:self.mic_ok,
            lambda down:self.calls.append(('key',down)),lambda:self.calls.append(('end',)),lambda:self.calls.append(('enter',)))

    def test_no_voice_or_enter_when_focus_unverified(self):
        self.focus_ok=False
        self.assertFalse(self.voice.start(self.token,True))
        self.assertFalse(self.voice.stop(self.token));self.assertFalse(self.voice.send(self.token))
        self.assertEqual(self.calls,[])

    def test_failed_board_mic_never_falls_back_to_mac_mic(self):
        self.mic_ok=False
        self.assertFalse(self.voice.start(self.token,True))
        self.assertNotIn(('key',True),self.calls)

    def test_send_requires_finished_utterance_and_consumes_once(self):
        self.assertTrue(self.voice.start(self.token,False))
        self.assertFalse(self.voice.send(self.token))
        self.assertTrue(self.voice.stop(self.token))
        self.assertFalse(self.voice.send('other'))
        self.assertTrue(self.voice.send(self.token));self.assertFalse(self.voice.send(self.token))
        self.assertEqual(self.calls.count(('enter',)),1)

    def test_cancel_stops_fn_and_invalidates_pending_send(self):
        self.voice.start(self.token,False);self.voice.cancel()
        self.assertIn(('key',False),self.calls)
        self.assertFalse(self.voice.send(self.token))

    def test_account_changes_during_focus_refuses_action(self):
        def switch(row):
            new=snapshot();new['identity']='changed';self.store.update('codex',new,1001)
            return True
        self.assertFalse(self.control.run(self.token,switch,lambda row:self.calls.append(('enter',))))
        self.assertEqual(self.calls,[])

    def test_removed_task_invalidates_token(self):
        new=snapshot();new['tasks']=[];self.store.update('codex',new,1001)
        self.assertIsNone(self.control.target(self.token))

    def test_unknown_read_state_never_labelled_read(self):
        new=snapshot();new['tasks'][2]['unread']=None;self.store.update('codex',new,1001)
        page=self.store.page('codex','catalog','','x',1001,read_limit=20)
        rows=page['list'][:]
        while page['next_cursor']:
            page=self.store.page('codex','catalog',page['next_cursor'],'x',1001,read_limit=20);rows+=page['list']
        self.assertEqual(next(r for r in rows if r['title']=='任务2')['kind'],'unknown')

class FocusTests(unittest.TestCase):
    def test_no_focus_key_without_verified_route_and_no_voice_action(self):
        from task_focus import focus_codex
        from unittest.mock import Mock
        tid='01a1237e-36c6-7af1-addb-faf4651164a8'
        ax=Mock();ax.matches.return_value=False;keys=[]
        opener=Mock(return_value=Mock(returncode=0))
        self.assertFalse(focus_codex(dict(thread_id=tid,host='local'),lambda:('com.openai.codex',12),keys.append,'ctrl+shift+i',ax,opener,lambda delay:None))
        self.assertEqual(keys,[])

    def test_foreground_bundle_and_editor_are_required(self):
        from task_focus import focus_codex
        from unittest.mock import Mock
        tid='01a1237e-36c6-7af1-addb-faf4651164a8'
        ax=Mock();ax.matches.return_value=False;keys=[]
        self.assertFalse(focus_codex(dict(thread_id=tid,host='local'),lambda:('com.openai.codex',12),keys.append,'ctrl+shift+i',ax,Mock(return_value=Mock(returncode=0)),lambda delay:None))
        self.assertEqual(keys,[])

class ProtocolTests(unittest.TestCase):
    def test_escaped_titles_stay_below_rx_line_limit(self):
        for title in ('\\'*6000, '\n'*6000, '中'*6000, '"'*6000):
            store=D.DashboardStore();snap=snapshot();snap['tasks'][0]['title']=title;store.update('codex',snap,1000)
            control=TaskControl(store,clock=lambda:1000)
            response=control.select('codex',store.get('codex',1000)['tasks'][0]['handle'])
            response['request_id']='x'*24
            self.assertLessEqual(len(D.encode(response)),4000)
            self.assertTrue(response['title_clipped'])

class FocusRaceTests(unittest.TestCase):
    setUp=VoiceTests.setUp
    def test_mic_preparation_switches_focus_then_start_is_rejected(self):
        def switch():
            self.focus_ok=False
            return True
        self.voice.begin=switch
        self.assertFalse(self.voice.start(self.token,True))
        self.assertNotIn(('key',True),self.calls)
        self.assertIn(('end',),self.calls)

class HostRoutingTests(unittest.TestCase):
    def test_target_voice_and_enter_never_fall_through_legacy_app_focus(self):
        import agentpet_host as H
        import json
        from unittest.mock import patch
        replies=[]
        with patch.object(H,'inject',side_effect=lambda f:f()), patch.object(H.selected_voice,'start',return_value=False), patch.object(H.selected_voice,'send',return_value=False), patch.object(H,'raise_agent_app') as old_focus, patch.object(H,'voice_key') as key, patch.object(H,'post_key') as enter:
            H.handle_board_msg(json.dumps(dict(t='voice',a='start',agent='codex',target='bad',mic=1)),replies.append)
            H.handle_board_msg(json.dumps(dict(t='key',k='enter',agent='codex',target='bad')),replies.append)
            old_focus.assert_not_called();key.assert_not_called();enter.assert_not_called()
        self.assertEqual(len(replies),2)
        self.assertTrue(all(json.loads(r)['error']=='focus_unverified' for r in replies))

    def test_claude_exact_focus_does_not_raise_fallback(self):
        import agentpet_host as H
        from unittest.mock import patch
        with patch.object(H,'sess_adapter',return_value=('warp','warp://missing')), patch.object(H.subprocess,'run') as run:
            run.return_value.returncode=1
            self.assertIsNone(H.focus_session('missing',exact_only=True))
            self.assertEqual(run.call_count,1)
            self.assertEqual(run.call_args[0][0],['open','warp://missing'])

class AccessibilityTests(unittest.TestCase):
    def fake_ax(self, attrs):
        from task_focus import Accessibility
        from unittest.mock import Mock
        reader=Accessibility.__new__(Accessibility)
        reader.ax=Mock();reader.ax.AXUIElementCreateApplication.return_value=1
        reader.cf=Mock()
        reader.attr=lambda obj,key:attrs.get((obj,key))
        reader.text_attr=lambda obj,key:attrs.get((obj,key),'')
        return reader

    def test_sibling_link_and_search_field_cannot_prove_target_composer(self):
        tid='01a1237e-36c6-7af1-addb-faf4651164a8'
        reader=self.fake_ax({(1,'AXFocusedUIElement'):2,(2,'AXRole'):'AXTextField',
            (2,'AXParent'):3,(3,'AXURL'):'app://-/local/thread/'+tid})
        self.assertFalse(reader.matches(12,tid,True))
        reader=self.fake_ax({(1,'AXFocusedUIElement'):2,(2,'AXRole'):'AXTextArea',
            (2,'AXParent'):3,(3,'AXChildren'):[4],(4,'AXURL'):'app://-/local/thread/'+tid})
        self.assertFalse(reader.matches(12,tid,True))

    def test_focused_multiline_editor_requires_ancestor_route(self):
        tid='01a1237e-36c6-7af1-addb-faf4651164a8'
        reader=self.fake_ax({(1,'AXFocusedUIElement'):2,(2,'AXRole'):'AXTextArea',
            (2,'AXParent'):3,(3,'AXURL'):'app://-/local/thread/'+tid})
        self.assertTrue(reader.matches(12,tid,True))
        self.assertFalse(reader.matches(12,'another-thread',True))

class FinalFocusIdentityTests(unittest.TestCase):
    setUp=VoiceTests.setUp
    def test_identity_changes_during_final_focus_never_press_fn(self):
        calls=[0]
        def focus(row):
            calls[0]+=1
            if calls[0]==2:
                snap=snapshot();snap['identity']='switched';self.store.update('codex',snap,1000)
            return True
        self.voice.focus=focus
        self.assertFalse(self.voice.start(self.token,True))
        self.assertNotIn(('key',True),self.calls)
        self.assertIn(('end',),self.calls)

class LegacyApprovalRegressionTests(unittest.TestCase):
    def test_existing_claude_approval_still_focuses_and_presses_key(self):
        import agentpet_host as H
        from unittest.mock import patch
        with patch.dict(H.claude_sessions,{'sid':{'state':'needs_you'}}), patch.object(H,'approve_plan',return_value=('go','sid')), patch.object(H,'sess_adapter',return_value=('warp','warp://sid')), patch.object(H,'inject',side_effect=lambda f:f()), patch.object(H,'focus_session',return_value='warp') as focus, patch.object(H,'post_key') as key, patch.object(H.time,'sleep'):
            self.assertTrue(H.claude_decision('approve','enter','sid'))
            focus.assert_called_once_with('sid')
            key.assert_called_once_with('enter')

class ForegroundRegressionTests(unittest.TestCase):
    def test_selected_focus_queries_fresh_window_owner(self):
        import agentpet_host as H
        import Quartz
        from unittest.mock import patch, Mock
        import sys, types
        app=Mock();app.bundleIdentifier.return_value='com.openai.codex'
        with patch.object(Quartz,'CGWindowListCopyWindowInfo',return_value=[{'kCGWindowLayer':2,'kCGWindowOwnerPID':10},{'kCGWindowLayer':0,'kCGWindowOwnerPID':99}]),patch.dict(sys.modules,{'AppKit':types.SimpleNamespace(NSRunningApplication=Mock(runningApplicationWithProcessIdentifier_=Mock(return_value=app))) }):
            self.assertEqual(H.selected_frontmost(),('com.openai.codex',99))
            sys.modules['AppKit'].NSRunningApplication.runningApplicationWithProcessIdentifier_.assert_called_once_with(99)
