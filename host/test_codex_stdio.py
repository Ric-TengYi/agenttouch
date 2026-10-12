import subprocess
import unittest
from unittest.mock import Mock
from codex_stdio import StdioReadOnly

class StdioSafetyTests(unittest.TestCase):
    def test_mutating_methods_never_reach_process(self):
        rpc=StdioReadOnly.__new__(StdioReadOnly);rpc.process=Mock()
        with self.assertRaises(ValueError):rpc.send({'method':'turn/start','params':{}})
        rpc.process.stdin.write.assert_not_called()
    def test_unresponsive_process_is_killed_and_pipes_closed(self):
        rpc=StdioReadOnly.__new__(StdioReadOnly);rpc.selector=Mock();rpc.process=Mock()
        rpc.process.wait.side_effect=[subprocess.TimeoutExpired('codex',2),0]
        rpc.close()
        rpc.process.terminate.assert_called_once();rpc.process.kill.assert_called_once()
        rpc.process.stdin.close.assert_called_once();rpc.process.stdout.close.assert_called_once()
