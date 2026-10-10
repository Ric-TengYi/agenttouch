import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import dashboard as D
from dashboard_service import DashboardService
from claude_statusline import install

class ServiceTests(unittest.TestCase):
    def test_statusline_preserves_command_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); settings=root/'settings.json'; deploy=root/'deploy'
            original={'type':'command','command':'printf original','padding':2}
            settings.write_text(json.dumps({'statusLine':original,'hooks':{'keep':True}}))
            install(settings,deploy); before=settings.read_bytes(); install(settings,deploy)
            self.assertEqual(before,settings.read_bytes())
            self.assertEqual(json.loads((deploy/'claude_statusline_original.json').read_text()),original)
            self.assertEqual(json.loads(before)['hooks'],{'keep':True})

    def test_account_switch_discards_old_quota(self):
        service=DashboardService('/nonexistent')
        service.quota_key='old'; service.quota=D.parse_quota({'seven_day':{'used_percentage':1}},1000)
        snap=D.empty_snapshot('codex',1001); snap['identity']='new'
        with patch('dashboard_service.D.read_codex',return_value=snap), patch('dashboard_service.codex_quota',side_effect=OSError()):
            service.collect({},1001)
        self.assertIsNone(service.store.get('codex',1001)['quota']['remaining_pct'])

    def test_unknown_unread_page_is_not_empty_success(self):
        store=D.DashboardStore(); store.update('claude',D.read_claude({},None,1000),1000)
        self.assertEqual(store.page('claude','unread','','test',1000)['error'],'source_unavailable')

    def test_owner_unknown_excluded(self):
        from test_dashboard import DashboardTests
        fixture=DashboardTests(); fixture.setUp()
        try:
            import sqlite3
            db=sqlite3.connect(fixture.home/'state_5.sqlite')
            db.execute("UPDATE threads SET creator_account_id=NULL,creator_user_id=NULL WHERE id='a'")
            db.commit();db.close()
            self.assertNotIn('a',[r['thread_id'] for r in D.read_codex(fixture.home,1000)['tasks']])
        finally: fixture.tearDown()
