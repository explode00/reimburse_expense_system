import os
import tempfile
import unittest
from pathlib import Path

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False)
        self.tmp.close()
        os.environ['EXPENSE_DB'] = self.tmp.name
        import importlib
        import app as appmod
        self.appmod = importlib.reload(appmod)
        self.appmod.init_db()
        self.appmod.seed_demo()
        self.client = self.appmod.app.test_client()
        self.client.post('/login', data={'email':'employee@example.com','password':'password'})
        self.employee = self.appmod.query_one("SELECT * FROM users WHERE email='employee@example.com'")
        self.approver = self.appmod.query_one("SELECT * FROM users WHERE email='approver@example.com'")
        self.approver2 = self.appmod.query_one("SELECT * FROM users WHERE email='approver2@example.com'")

    def tearDown(self):
        Path(self.tmp.name).unlink(missing_ok=True)
        os.environ.pop('EXPENSE_DB', None)

    def login(self, email):
        self.client.get('/logout')
        return self.client.post('/login', data={'email':email,'password':'password'})

    def make_report(self):
        r=self.client.post('/reports/new', data={'title':'Trip','start_date':'2026-08-25','end_date':'2026-08-27'}, follow_redirects=True)
        self.client.post('/reports/1/lines/add', data={'expense_date':'2026-08-25','amount':'12.50','category':'Meals','description':'Lunch'})
        return r

    def test_total_is_server_computed(self):
        self.make_report()
        row=self.appmod.query_one('SELECT * FROM reports WHERE id=1')
        self.assertEqual(self.appmod.total_cents(row['id']),1250)
        self.assertEqual(self.client.get('/api/reports/1/total').json['total_cents'],1250)

    def test_self_approval_is_refused(self):
        self.make_report(); self.client.post('/reports/1/submit')
        self.login('approver@example.com')
        self.client.post('/reports/1/assign', data={'approver_ids':str(self.approver['id'])})
        resp=self.client.post('/reports/1/decide', data={'action':'approve'}, follow_redirects=True)
        self.assertIn('You cannot approve or reject a report you own', resp.get_data(as_text=True))

    def test_rejection_returns_to_draft_with_reason(self):
        self.make_report(); self.client.post('/reports/1/submit')
        self.login('approver@example.com')
        self.client.post('/reports/1/assign', data={'approver_ids':str(self.approver['id'])})
        self.client.post('/reports/1/decide', data={'action':'reject','reason':'Missing receipt'})
        row=self.appmod.query_one('SELECT * FROM reports WHERE id=1')
        self.assertEqual(row['status'],'Draft')
        h=self.appmod.query_one("SELECT * FROM history WHERE report_id=1 AND event_type='status_change' ORDER BY id DESC")
        self.assertEqual(h['reason'],'Missing receipt')

    def test_bulk_reports_each_get_individual_result(self):
        self.make_report(); self.client.post('/reports/1/submit')
        self.login('approver@example.com')
        self.client.post('/reports/1/assign', data={'approver_ids':str(self.approver['id'])})
        # Create a second report owned by employee is not needed: selected report must still be processed individually.
        resp=self.client.post('/reports/bulk', data=[('action','approve'),('report_ids','1')], follow_redirects=True)
        self.assertIn('refused: You cannot approve or reject a report you own', resp.get_data(as_text=True))

if __name__ == '__main__':
    unittest.main()
