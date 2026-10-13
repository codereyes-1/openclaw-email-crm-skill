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
            conn.executemany(
                "INSERT INTO contacts (id,email,email_normalized,source,do_not_contact,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?)",
                [(1, "legacy@example.com", "legacy@example.com", "legacy", 0, "created", "updated"),
                 (2, "dnc@example.com", "dnc@example.com", "legacy", 1, "created", "updated")],
            )
            conn.execute("INSERT INTO email_suppressions VALUES (1,'dnc@example.com','unsubscribe','created')")
            conn.execute("INSERT INTO email_events VALUES (1,1,'sent','{\"synthetic\":true}','occurred')")
        result = self.invoke("init_email_crm.py")
        self.assertEqual(result["schema_version"], 2)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(
                list(conn.execute("SELECT id,email,do_not_contact FROM contacts ORDER BY id")),
                [(1, "legacy@example.com", 0), (2, "dnc@example.com", 1)],
            )
            self.assertEqual(list(conn.execute("SELECT email_normalized,reason FROM email_suppressions")),
                             [("dnc@example.com", "unsubscribe")])
            self.assertEqual(list(conn.execute("SELECT contact_id,event_type,metadata_json FROM email_events")),
                             [(1, "sent", '{"synthetic":true}')])
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_ingestion_is_normalized_idempotent_and_classified(self):
        first = self.ingest()
        second = self.ingest()
        self.assertEqual((first["imported"], first["duplicates"]), (3, 0))
        self.assertEqual((second["imported"], second["duplicates"]), (0, 3))
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM messages"), 3)
        with sqlite3.connect(self.db) as conn:
            states = dict(conn.execute("SELECT subject_normalized, computed_state FROM conversations"))
            source_ref = conn.execute("SELECT source_ref FROM ingestion_runs ORDER BY id LIMIT 1").fetchone()[0]
        self.assertEqual(states["project quote"], "awaiting_me")
        self.assertEqual(states["routing ambiguity"], "needs_review")
        self.assertTrue(source_ref.startswith("content-sha256:"))
        self.assertNotIn(str(FIXTURE), source_ref)

    def test_adapter_boundary_rejects_conflicts_and_sensitive_metadata(self):
        self.ingest()
        original = json.loads(FIXTURE.read_text(encoding="utf-8"))

        conflict_path = Path(self.temp.name) / "conflict.json"
        conflict = {"messages": [dict(original["messages"][0], excerpt="changed duplicate content")]}
        conflict_path.write_text(json.dumps(conflict), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "ingest_messages.py"), "--db", self.db,
             "--adapter", "synthetic", "--input", str(conflict_path)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicting duplicate message identity", result.stderr)

        sensitive_path = Path(self.temp.name) / "sensitive.json"
        sensitive = {"messages": [dict(original["messages"][0], external_id="new-sensitive",
                                         metadata={"nested": {"access-token": "do-not-store"}})]}
        sensitive_path.write_text(json.dumps(sensitive), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "ingest_messages.py"), "--db", self.db,
             "--adapter", "synthetic", "--input", str(sensitive_path)],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("metadata key is not allowed", result.stderr)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM messages"), 3)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM ingestion_runs"), 1)

    def test_timestamps_are_canonical_and_retention_cutoff_fails_closed(self):
        payload = {
            "messages": [{
                "external_id": "time-1", "conversation_external_id": "time-thread",
                "occurred_at": "2026-01-05T01:00:00-08:00", "direction": "inbound",
                "sender": "sender@example.com", "recipients": ["me@example.com"], "excerpt": "synthetic",
            }]
        }
        fixture = Path(self.temp.name) / "timestamp.json"
        fixture.write_text(json.dumps(payload), encoding="utf-8")
        self.invoke("ingest_messages.py", "--adapter", "synthetic", "--input", str(fixture))
        self.assertEqual(self.scalar("SELECT occurred_at FROM messages"), "2026-01-05T09:00:00.000000Z")
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "purge_message_excerpts.py"), "--db", self.db,
             "--before", "not-a-timestamp", "--apply"],
            capture_output=True, text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("before must be an ISO-8601 timestamp with a timezone", result.stderr)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM messages WHERE excerpt IS NOT NULL"), 1)

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
