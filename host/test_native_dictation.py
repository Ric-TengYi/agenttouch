import unittest
from unittest.mock import Mock, patch
from native_dictation import NativeHold

class NativeHoldTests(unittest.TestCase):
    def test_held_shortcut_does_not_repeat_and_releases_control(self):
        emit=Mock();hold=NativeHold(emit)
        hold.key(True);hold.key(True);hold.key(False);hold.key(False)
        self.assertEqual([c.args for c in emit.call_args_list],
            [(59,True,True),(46,True,True),(46,False,True),(59,False,False)])

    def test_failed_m_down_releases_all_synthetic_keys(self):
        calls=[]
        def emit(k,d,c):
            calls.append((k,d,c))
            if k==46 and d:raise RuntimeError('event failed')
        hold=NativeHold(emit)
        with self.assertRaises(RuntimeError):hold.key(True)
        self.assertFalse(hold.down)
        self.assertIn((46,False,True),calls)
        self.assertEqual(calls[-1],(59,False,False))

    def test_release_failure_still_releases_control(self):
        emit=Mock();hold=NativeHold(emit);hold.key(True)
        emit.side_effect=lambda k,d,c: (_ for _ in ()).throw(RuntimeError()) if k==46 and not d else None
        with self.assertRaises(RuntimeError):hold.key(False)
        self.assertFalse(hold.down)
        self.assertEqual(emit.call_args.args,(59,False,False))

    def test_cancel_uses_escape_before_releasing_held_shortcut(self):
        emit=Mock();hold=NativeHold(emit);hold.key(True);emit.reset_mock();hold.cancel()
        self.assertEqual([c.args for c in emit.call_args_list],
            [(53,True,False),(53,False,False),(46,False,True),(59,False,False)])


class HostRoutingTests(unittest.TestCase):
    def test_codex_route_does_not_change_system_input_or_invoke_fn(self):
        import agentpet_host as H
        with patch.object(H,'mic_sink_proc',return_value=object()), \
             patch.object(H,'mic_input_set') as default_input, \
             patch.object(H,'voice_key') as legacy, \
             patch.object(H,'codex_native_hold') as hold, \
             patch.object(H,'mic_sink_open_gate') as gate, \
             patch.object(H.time,'sleep'), patch.object(H,'voice_down',False), \
             patch.dict(H._mic,{'session_board':False,'prev_input':None}):
            self.assertTrue(H.codex_native_begin())
            H.codex_native_key(True);self.assertTrue(H.voice_down)
            H.codex_native_key(False);self.assertFalse(H.voice_down)
            self.assertEqual([c.args for c in hold.key.call_args_list],[(True,),(False,)])
            gate.assert_called_once();legacy.assert_not_called();default_input.assert_not_called()

    def test_cancel_releases_native_keys_and_freeze_even_on_error(self):
        import agentpet_host as H
        with patch.object(H,'codex_native_hold') as hold,patch.object(H,'voice_down',True):
            hold.cancel.side_effect=RuntimeError('failed')
            with self.assertRaises(RuntimeError):H.codex_native_cancel()
            self.assertFalse(H.voice_down)

class GeneralCodexVoiceTests(unittest.TestCase):
    def check_deferred_voice(self, stop_during_focus, focus_failure=False):
        import contextlib
        import json
        import agentpet_host as H
        jobs, events = [], []
        stop_message = json.dumps({'t': 'voice', 'a': 'stop', 'agent': 'claude'})

        def stop():
            H.handle_board_msg(stop_message, lambda _: None)

        def focus(_):
            if focus_failure:
                raise RuntimeError('mock focus failed')
            if stop_during_focus:
                stop()
                # The queued release must leave the active audio route intact.
                self.assertTrue(H._mic['session_board'])

        def open_gate():
            self.assertTrue(H._mic['session_board'])
            H._mic['sink_gate'] = True

        def end_sink():
            H._mic['sink_gate'] = False

        with contextlib.ExitStack() as stack:
            for name, value in [('inject', jobs.append), ('raise_agent_app', focus),
                                ('codex_native_hold', NativeHold(lambda *e: events.append(e))),
                                ('VOICE_SOURCE', 'board'), ('voice_down', False),
                                ('_voice_native', False), ('_voice_board', False),
                                ('_voice_to_front', False)]:
                stack.enter_context(patch.object(H, name, value))
            stack.enter_context(patch.dict(H._mic, {'session_board': False,
                                                  'sink_gate': False, 'prev_input': None}))
            stack.enter_context(patch.object(H, 'mic_sink_proc', return_value=object()))
            gate = stack.enter_context(patch.object(H, 'mic_sink_open_gate', side_effect=open_gate))
            sink_end = stack.enter_context(patch.object(H, 'mic_sink_end', side_effect=end_sink))
            default_input = stack.enter_context(patch.object(H, 'mic_input_set'))
            legacy_key = stack.enter_context(patch.object(H, 'voice_key'))
            send_key = stack.enter_context(patch.object(H, 'post_key'))
            sleep = stack.enter_context(patch.object(H.time, 'sleep'))
            H.handle_board_msg(json.dumps({'t': 'voice', 'a': 'start',
                                          'agent': 'codex', 'mic': True}), lambda _: None)
            if not stop_during_focus and not focus_failure:
                stop()
            self.assertEqual(events, [])
            if focus_failure:
                with self.assertRaisesRegex(RuntimeError, 'mock focus failed'):
                    jobs.pop(0)()
                self.assertEqual(events, [])
                gate.assert_not_called()
                sink_end.assert_called_once()
                self.assertFalse(H._mic['session_board'])
                self.assertFalse(H._mic['sink_gate'])
                self.assertFalse(H.voice_down)
                self.assertFalse(H.codex_native_hold.down)
                default_input.assert_not_called()
                legacy_key.assert_not_called()
                send_key.assert_not_called()
                return
            while jobs:
                jobs.pop(0)()
            self.assertEqual(events, [(59, True, True), (46, True, True),
                                      (46, False, True), (59, False, False)])
            gate.assert_called_once()
            sink_end.assert_called_once()
            self.assertFalse(H._mic['session_board'])
            self.assertFalse(H._mic['sink_gate'])
            self.assertFalse(H.voice_down)
            self.assertFalse(H.codex_native_hold.down)
            self.assertEqual([call.args for call in sleep.call_args_list],
                             [(H.MIC_TAIL_S,), (.5,)])
            default_input.assert_not_called()
            legacy_key.assert_not_called()
            send_key.assert_not_called()

    def test_quick_press_release_queued_before_worker_keeps_audio_and_cleans_up(self):
        self.check_deferred_voice(stop_during_focus=False)

    def test_release_during_focus_does_not_disable_audio_gate(self):
        self.check_deferred_voice(stop_during_focus=True)

    def test_focus_failure_cleans_sink_without_native_shortcut_or_send(self):
        self.check_deferred_voice(stop_during_focus=False, focus_failure=True)

    def run_voice(self, agent='codex', to=None, sink_ok=True):
        import json
        import contextlib
        import agentpet_host as H
        events=[]
        message={'t':'voice','a':'start','agent':agent,'mic':True}
        if to: message['to']=to
        with contextlib.ExitStack() as stack:
            for name, value in [('inject',lambda f:f()),('raise_agent_app',lambda a:None),
                                ('codex_native_hold',NativeHold(lambda *e:events.append(e))),
                                ('voice_down',False),('_voice_to_front',False)]:
                stack.enter_context(patch.object(H,name,value))
            stack.enter_context(patch.object(H,'_voice_native',False,create=True))
            stack.enter_context(patch.object(H,'_voice_board',False))
            stack.enter_context(patch.object(H,'VOICE_SOURCE','board'))
            stack.enter_context(patch.object(H,'_frontmost_app',return_value='test'))
            stack.enter_context(patch.object(H.time,'sleep'))
            stack.enter_context(patch.dict(H._mic,{'session_board':False,'prev_input':None}))
            sink=stack.enter_context(patch.object(H,'mic_sink_proc',return_value=object() if sink_ok else None))
            legacy_begin=stack.enter_context(patch.object(H,'mic_sink_begin',return_value=True))
            legacy_key=stack.enter_context(patch.object(H,'voice_key'))
            default=stack.enter_context(patch.object(H,'mic_input_set'))
            gate=stack.enter_context(patch.object(H,'mic_sink_open_gate'))
            stack.enter_context(patch.object(H,'mic_sink_end'))
            H.handle_board_msg(json.dumps(message),lambda x:None)
            # Release must follow the latched start route, even if the seat changed.
            H.handle_board_msg(json.dumps({'t':'voice','a':'stop','agent':'claude'}),lambda x:None)
            return events,legacy_key.call_args_list,legacy_begin.call_count,default.call_count,gate.call_count

    def test_codex_face_button_holds_native_shortcut_and_release_does_not_send(self):
        events,legacy,begin,default,gate=self.run_voice()
        self.assertEqual(events,[(59,True,True),(46,True,True),(46,False,True),(59,False,False)])
        self.assertEqual(legacy,[]);self.assertEqual(begin,0);self.assertEqual(default,0)
        self.assertEqual(gate,1)

    def test_failed_codex_sink_does_not_start_native_recording(self):
        events,legacy,begin,default,gate=self.run_voice(sink_ok=False)
        self.assertEqual(events,[]);self.assertEqual(legacy,[]);self.assertEqual(gate,0)

    def test_claude_and_front_cursor_keep_existing_voice_route(self):
        for agent,to in [('claude',None),('codex','front')]:
            with self.subTest(agent=agent,to=to):
                events,legacy,begin,default,gate=self.run_voice(agent,to)
                self.assertEqual(events,[])
                self.assertEqual([call.args for call in legacy],[(True,),(False,)])
                self.assertEqual(begin,1)

class NativeQuartzEventTests(unittest.TestCase):
    def test_control_events_keep_device_modifier_bit_for_global_shortcuts(self):
        import agentpet_host as H
        if not H._HAVE_QUARTZ:
            self.skipTest('Quartz only available on macOS')
        # Construct real events but intercept every post: no keys reach any app.
        with patch.object(H.Quartz,'CGEventPost') as post:
            H._emit_codex_native_key(59,True,True)
            event=post.call_args.args[1]
            self.assertEqual(H.Quartz.CGEventGetType(event),H.Quartz.kCGEventFlagsChanged)
            self.assertTrue(H.Quartz.CGEventGetFlags(event) & 0x1)
            H._emit_codex_native_key(46,True,True)
            self.assertTrue(H.Quartz.CGEventGetFlags(post.call_args.args[1]) & 0x1)
            H._emit_codex_native_key(59,False,False)
            flags=H.Quartz.CGEventGetFlags(post.call_args.args[1])
            self.assertFalse(flags & (H.Quartz.kCGEventFlagMaskControl | 0x1))

    def test_native_shortcut_does_not_inherit_other_modifier_combinations(self):
        import agentpet_host as H
        if not H._HAVE_QUARTZ:
            self.skipTest('Quartz only available on macOS')
        event=H.Quartz.CGEventCreateKeyboardEvent(None,46,True)
        H.Quartz.CGEventSetFlags(event,H.Quartz.kCGEventFlagMaskCommand | H.Quartz.kCGEventFlagMaskShift | 0x8 | 0x2)
        with patch.object(H.Quartz,'CGEventCreateKeyboardEvent',return_value=event), \
             patch.object(H.Quartz,'CGEventPost') as post:
            H._emit_codex_native_key(46,True,True)
            self.assertEqual(H.Quartz.CGEventGetFlags(post.call_args.args[1]),
                             H.Quartz.kCGEventFlagMaskControl | 0x1)
