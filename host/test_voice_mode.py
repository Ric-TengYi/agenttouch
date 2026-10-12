import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import agentpet_host as H


class VoiceModeTests(unittest.TestCase):
    def test_system_dictation_mode_is_loaded_from_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'config.json'
            config.write_text(json.dumps({'voice_mode':'fn_double'}))
            with patch.object(H,'CONFIG_OVERRIDE',config), patch.object(H,'VOICE_MODE','hold_fn'):
                H.load_overrides()
                self.assertEqual(H.VOICE_MODE,'fn_double')

    def test_invalid_mode_preserves_existing_shortcut(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'config.json'
            config.write_text(json.dumps({'voice_mode':'bad'}))
            with patch.object(H,'CONFIG_OVERRIDE',config), patch.object(H,'VOICE_MODE','fn_double'):
                H.load_overrides()
                self.assertEqual(H.VOICE_MODE,'fn_double')

    def test_double_fn_start_and_single_fn_finish_do_not_hold_fn(self):
        with patch.object(H,'VOICE_MODE','fn_double'), patch.object(H,'_tap_fn_osascript') as tap, \
             patch.object(H,'_post_fn') as hold, patch.object(H,'voice_down',False):
            H.voice_key(True)
            self.assertTrue(H.voice_down)
            H.voice_key(False)
            self.assertFalse(H.voice_down)
            self.assertEqual([c.args for c in tap.call_args_list],[(2,),(1,)])
            hold.assert_not_called()
