import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "fixtures" / "synthetic_messages.json"


class AgenticCrmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.temp.name) / "crm.sqlite")

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, script, *args, expected=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / script), "--db", self.db, *args],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, expected, result.stderr)
        return json.loads(result.stdout) if result.stdout.strip().startswith("{") else result.stdout

    def scalar(self, query, params=()):
        with sqlite3.connect(self.db) as conn:
            return conn.execute(query, params).fetchone()[0]

    def ingest(self):
        return self.invoke("ingest_messages.py", "--adapter", "synthetic", "--input", str(FIXTURE))

    def test_fresh_database_uses_versioned_schema(self):
        result = self.invoke("init_email_crm.py")
        self.assertEqual(result["schema_version"], 2)
        with sqlite3.connect(self.db) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"contacts", "conversations", "messages", "obligations", "action_proposals", "action_audit"} <= tables)

    def test_v1_database_migrates_without_losing_contacts(self):
        migration = (ROOT / "migrations" / "001_email_core.sql").read_text(encoding="utf-8")
        with sqlite3.connect(self.db) as conn:
            conn.executescript(migration)
            conn.execute("INSERT INTO schema_meta VALUES (1, 1, '2026-01-01T00:00:00Z')")
            conn.execute("INSERT INTO contacts (email,email_normalized,source,created_at,updated_at) VALUES (?,?,?,?,?)",
                         ("legacy@example.com", "legacy@example.com", "legacy", "now", "now"))
        result = self.invoke("init_email_crm.py")
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(self.scalar("SELECT email FROM contacts"), "legacy@example.com")

    def test_ingestion_is_normalized_idempotent_and_classified(self):
        first = self.ingest()
        second = self.ingest()
        self.assertEqual((first["imported"], first["duplicates"]), (3, 0))
        self.assertEqual((second["imported"], second["duplicates"]), (0, 3))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM messages"), 3)
        with sqlite3.connect(self.db) as conn:
            states = dict(conn.execute("SELECT subject_normalized, computed_state FROM conversations"))
        self.assertEqual(states["project quote"], "awaiting_me")
        self.assertEqual(states["routing ambiguity"], "needs_review")

    def test_obligation_and_manual_override_take_precedence(self):
        self.ingest()
        conversation_id = self.scalar("SELECT id FROM conversations WHERE subject_normalized='project quote'")
        obligation = self.invoke(
            "upsert_obligation.py", "--conversation-id", str(conversation_id), "--idempotency-key", "quote-v2",
            "--summary", "Wait for revised requirements", "--owner", "them", "--confidence", "0.95",
            "--evidence-json", '[{"message":"synthetic"}]',
        )
        self.assertEqual(obligation["state"]["state"], "awaiting_them")
        override = self.invoke(
            "set_conversation_state.py", "--conversation-id", str(conversation_id), "--state", "closed", "--reason", "Reviewed by operator",
        )
        self.assertTrue(override["manual_override"])
        self.assertEqual(override["state"], "closed")
        cleared = self.invoke("set_conversation_state.py", "--conversation-id", str(conversation_id), "--clear")
        self.assertFalse(cleared["manual_override"])
        self.assertEqual(cleared["state"], "awaiting_them")

    def test_brief_has_json_and_human_modes(self):
        self.ingest()
        machine = self.invoke("brief_email_crm.py", "--json")
        self.assertEqual(machine["count"], 2)
        human = self.invoke("brief_email_crm.py")
        self.assertIn("Email CRM brief", human)
        self.assertIn("Project quote", human)

    def test_action_flow_is_idempotent_audited_and_never_executes(self):
        self.ingest()
        conversation_id = self.scalar("SELECT id FROM conversations WHERE subject_normalized='project quote'")
        args = (
            "--conversation-id", str(conversation_id), "--idempotency-key", "reply-quote-001", "--action-type", "draft_reply",
            "--payload-json", '{"body":"Synthetic draft only"}', "--rationale", "Reply requested",
        )
        first = self.invoke("propose_action.py", *args)
        second = self.invoke("propose_action.py", *args)
        self.assertTrue(first["created"])
        self.assertFalse(second["created"])
        self.assertFalse(first["transport_performed"])
        approved = self.invoke("review_action.py", "--proposal-id", str(first["proposal_id"]), "--approve")
        reconciled = self.invoke("reconcile_action.py", "--proposal-id", str(first["proposal_id"]))
        repeated = self.invoke("reconcile_action.py", "--proposal-id", str(first["proposal_id"]))
        self.assertEqual(approved["status"], "approved")
        self.assertTrue(reconciled["changed"])
        self.assertFalse(repeated["changed"])
        self.assertFalse(reconciled["transport_performed"])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM action_audit"), 3)

    def test_idempotency_key_rejects_changed_action(self):
        self.invoke("propose_action.py", "--idempotency-key", "same", "--action-type", "other", "--payload-json", '{"x":1}', "--rationale", "one")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "propose_action.py"), "--db", self.db, "--idempotency-key", "same",
             "--action-type", "other", "--payload-json", '{"x":2}', "--rationale", "two"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different proposal content", result.stderr)

    def test_excerpt_retention_is_dry_run_by_default(self):
        self.ingest()
        before = self.scalar("SELECT COUNT(*) FROM messages WHERE excerpt IS NOT NULL")
        dry = self.invoke("purge_message_excerpts.py", "--before", "2027-01-01T00:00:00Z")
        self.assertEqual(dry, {"ok": True, "eligible": before, "purged": 0, "applied": False})
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM messages WHERE excerpt IS NOT NULL"), before)
        applied = self.invoke("purge_message_excerpts.py", "--before", "2027-01-01T00:00:00Z", "--apply")
        self.assertEqual(applied["purged"], before)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM messages WHERE excerpt IS NOT NULL"), 0)


if __name__ == "__main__":
    unittest.main()
