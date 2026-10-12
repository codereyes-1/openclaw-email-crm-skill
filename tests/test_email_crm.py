import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class EmailCrmCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "crm.sqlite")

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, script, *args, expected=0):
        result = subprocess.run([sys.executable, str(SCRIPTS / script), "--db", self.db, *args], capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout)

    def test_readiness_and_suppression_are_normalized_and_idempotent(self):
        self.assertEqual(self.invoke("init_email_crm.py")["schema_version"], 1)
        contact = self.invoke("upsert_contact.py", "--email", " Alice@Example.COM ", "--source", "manual-review")
        self.assertEqual(contact["contact_id"], 1)
        self.assertTrue(self.invoke("check_email_readiness.py", "--email", "alice@example.com")["ready"])
        self.invoke("suppress_email.py", "--email", "ALICE@example.com", "--reason", "unsubscribe")
        self.invoke("suppress_email.py", "--email", "alice@example.com", "--reason", "unsubscribe")
        result = self.invoke("check_email_readiness.py", "--email", " alice@example.com ", expected=1)
        self.assertFalse(result["ready"])
        self.assertEqual(set(result["reasons"]), {"contact_do_not_contact", "email_suppressed"})

    def test_event_requires_real_contact(self):
        self.invoke("init_email_crm.py")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "log_email_event.py"), "--db", self.db, "--contact-id", "99", "--event-type", "sent"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_invalid_email_fails_closed(self):
        self.invoke("init_email_crm.py")
        result = self.invoke("check_email_readiness.py", "--email", "not-an-email", expected=1)
        self.assertEqual(result["reasons"], ["invalid_email"])


if __name__ == "__main__":
    unittest.main()
