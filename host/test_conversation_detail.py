import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import threading
import conversation_detail as C

class ConversationDetailTests(unittest.TestCase):
    def test_latest_question_and_response_ignore_tools_children_and_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log.jsonl'
            def event(kind,**kw):return {'type':'event_msg','payload':dict(type=kind,**kw)}
            def message(role,text,phase=None):return {'type':'response_item','payload':dict(type='message',role=role,phase=phase,content=[{'type':'input_text' if role=='user' else 'output_text','text':text}])}
            rows=[message('developer','internal'),event('task_started',turn_id='root',root_turn_id='root'),
                  message('user','old'),message('assistant','old answer','final_answer'),
                  message('user','<environment_context>hidden</environment_context>question'),
                  message('assistant','working','commentary'),
                  event('task_started',turn_id='child',root_turn_id='root',turn_attribution={'parent_turn_id':'root'}),
                  message('assistant','child secret','final_answer'),event('task_complete',turn_id='child',root_turn_id='root'),
                  message('assistant','answer','final_answer')]
            p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            self.assertEqual(C.read_exchange(p),{'question':'question','answer':'answer'})
            with p.open('a') as f:f.write(json.dumps(message('user','next'))+'\n')
            self.assertEqual(C.read_exchange(p),{'question':'next','answer':''})
    def test_wire_budget_even_escaped_content(self):
        msg=C.detail_message('codex','token',{'question':'"\\\n中'*5000,'answer':'好'*5000})
        self.assertLessEqual(len(json.dumps(msg,ensure_ascii=False,separators=(',',':')).encode())+1,4000)
        self.assertTrue(msg['clipped'])

    def test_selected_detail_rejects_outside_home_and_changed_identity(self):
        class Control:
            lock=threading.RLock()
            selected=('token','codex','identity','thread')
            def clock(self):return 1000
            def target(self,token):return {'rollout_path':'/tmp/unrelated.jsonl'}
        with tempfile.TemporaryDirectory() as tmp:
            with patch('dashboard.identity',return_value=('identity','account','user')):
                self.assertEqual(C.selected_detail(Control(),tmp)['error'],'source_unavailable')
            with patch('dashboard.identity',return_value=('other','account','user')):
                self.assertEqual(C.selected_detail(Control(),tmp)['error'],'source_unavailable')

    def test_claude_ignores_tools_and_subagent_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'claude.jsonl'
            rows=[{'type':'user','message':{'content':'question'}},
                  {'type':'assistant','isSidechain':True,'message':{'content':[{'type':'text','text':'child'}]}},
                  {'type':'user','message':{'content':[{'type':'tool_result','content':'internal'}]}},
                  {'type':'assistant','message':{'content':[{'type':'text','text':'answer'}]}}]
            p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            self.assertEqual(C.read_exchange(p,'claude'),{'question':'question','answer':'answer'})

    def test_overlapping_children_and_identified_parent_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log.jsonl'
            def event(kind,turn,root):return {'type':'event_msg','payload':{'type':kind,'turn_id':turn,'root_turn_id':root}}
            def answer(turn,text):return {'type':'response_item','payload':{'type':'message','role':'assistant','internal_chat_message_metadata_passthrough':{'turn_id':turn},'content':[{'type':'output_text','text':text}]}}
            rows=[event('task_started','root','root'),{'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'question'}]}},
                  event('task_started','a','root'),event('task_started','b','root'),event('task_complete','a','root'),
                  answer('root','parent progress'),answer('b','child final')]
            p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            self.assertEqual(C.read_exchange(p),{'question':'question','answer':'parent progress'})

    def test_internal_citations_removed_before_clipping_but_code_kept(self):
        text='Answer\n```python\nprint(1)\n```\n<oai-mem-citation><citation_entries>internal path</citation_entries><rollout_ids>internal id</rollout_ids></oai-mem-citation>'
        self.assertEqual(C.display_text(text),'Answer\n```python\nprint(1)\n```')
        self.assertEqual(C.display_text('Answer<oai-mem-citation>partial'),'Answer')
        self.assertEqual(C.display_text('Answer</oai-mem-citation>'),'Answer')
        msg=C.detail_message('codex','token',{'question':'Q','answer':text})
        self.assertNotIn('oai-mem',msg['answer'])
