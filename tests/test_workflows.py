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
        with self.appmod.app.app_context():
            self.appmod.seed_demo()
        self.client = self.appmod.app.test_client()
        self.login('employee@example.com')
        self.employee = self.appmod.query_one("SELECT * FROM users WHERE email='employee@example.com'")
        self.approver = self.appmod.query_one("SELECT * FROM users WHERE email='approver@example.com'")
        self.approver2 = self.appmod.query_one("SELECT * FROM users WHERE email='approver2@example.com'")

    def tearDown(self):
        Path(self.tmp.name).unlink(missing_ok=True)
        os.environ.pop('EXPENSE_DB', None)

    def login(self, email):
        self.client.get('/logout')
        return self.client.post('/login', data={'email': email, 'password': 'password'})

    def make_report(self, owner='employee@example.com', title='Trip'):
        self.login(owner)
        self.client.post('/reports/new', data={'title': title, 'start_date': '2026-08-25', 'end_date': '2026-08-27'})
        report_id = self.appmod.query_one('SELECT MAX(id) id FROM reports')['id']
        self.client.post(f'/reports/{report_id}/lines/add', data={'expense_date': '2026-08-25', 'amount': '12.50', 'category': 'Meals', 'description': 'Lunch'})
        return report_id

    def assign(self, report_id, *approver_ids):
        self.login('approver@example.com')
        self.client.post(f'/reports/{report_id}/assign', data=[('approver_ids', str(i)) for i in approver_ids])

    def test_total_is_server_computed(self):
        report_id = self.make_report()
        self.assign(report_id, self.approver['id'])
        self.login('employee@example.com')
        row = self.appmod.query_one('SELECT * FROM reports WHERE id=?', (report_id,))
        self.assertEqual(self.appmod.total_cents(row['id']), 1250)
        self.assertEqual(self.client.get(f'/api/reports/{report_id}/total').json['total_cents'], 1250)

    def test_self_approval_is_refused(self):
        report_id = self.make_report(owner='approver@example.com', title='Approver trip')
        self.assign(report_id, self.approver['id'], self.approver2['id'])
        self.login('approver@example.com')
        self.client.post(f'/reports/{report_id}/submit')
        resp = self.client.post(f'/reports/{report_id}/decide', data={'action': 'approve'}, follow_redirects=True)
        self.assertIn('You cannot approve or reject a report you own', resp.get_data(as_text=True))
        row = self.appmod.query_one('SELECT status FROM reports WHERE id=?', (report_id,))
        self.assertEqual(row['status'], 'Submitted')

    def test_rejection_returns_to_draft_with_reason(self):
        report_id = self.make_report()
        self.assign(report_id, self.approver['id'])
        self.login('employee@example.com')
        self.client.post(f'/reports/{report_id}/submit')
        self.login('approver@example.com')
        self.client.post(f'/reports/{report_id}/decide', data={'action': 'reject', 'reason': 'Missing receipt'})
        row = self.appmod.query_one('SELECT * FROM reports WHERE id=?', (report_id,))
        self.assertEqual(row['status'], 'Draft')
        history = self.appmod.query_all("SELECT old_status,new_status,reason FROM history WHERE report_id=? AND event_type='status_change' ORDER BY id", (report_id,))
        self.assertEqual(history[-2]['old_status'], 'Submitted')
        self.assertEqual(history[-2]['new_status'], 'Rejected')
        self.assertEqual(history[-2]['reason'], 'Missing receipt')
        self.assertEqual(history[-1]['new_status'], 'Draft')

    def test_bulk_reports_each_get_individual_result_for_self_owned_report(self):
        report_id = self.make_report(owner='approver@example.com', title='Own report')
        self.assign(report_id, self.approver['id'])
        self.login('approver@example.com')
        self.client.post(f'/reports/{report_id}/submit')
        resp = self.client.post('/reports/bulk', data=[('action', 'approve'), ('report_ids', str(report_id))], follow_redirects=True)
        self.assertIn('refused: You cannot approve or reject a report you own', resp.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
