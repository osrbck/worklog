"""End-to-end tests with synthetic session stores for every adapter.

Run:  python3 -m unittest discover -s tests -v
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "worklog" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from worklog_core import aggregate, config  # noqa: E402
from worklog_core.adapters import ADAPTERS  # noqa: E402
from worklog_core.redact import clean_prompt, redact  # noqa: E402
from worklog_core.timeparse import parse_range  # noqa: E402

T0 = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=3)


def iso(minutes: int) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


def ms(minutes: int) -> int:
    return int((T0 + timedelta(minutes=minutes)).timestamp() * 1000)


def write_jsonl(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_DATE": iso(20), "GIT_COMMITTER_DATE": iso(20)})


class Fixture:
    def __init__(self, home: Path):
        self.home = home
        self.repo = home / "code" / "shop"
        self.repo.mkdir(parents=True)
        git(self.repo, "init", "-q", "-b", "feat/SHOP-42-cart")
        git(self.repo, "config", "user.email", "me@example.com")
        git(self.repo, "config", "user.name", "Me")
        (self.repo / "cart.ts").write_text("x")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "SHOP-42 add cart total")
        self.claude()
        self.codex()
        self.kiro()
        self.opencode_json()
        self.opencode_sqlite()

    def claude(self):
        base = dict(sessionId="c-1", cwd=str(self.repo), gitBranch="feat/SHOP-42-cart")
        write_jsonl(self.home / ".claude/projects/-code-shop/c-1.jsonl", [
            {**base, "type": "user", "timestamp": iso(0),
             "message": {"role": "user", "content": "Fix the cart total rounding, token=sk-abcdefghijklmnopqrstuv"}},
            {**base, "type": "user", "timestamp": iso(1), "isMeta": True,
             "message": {"role": "user", "content": "<system-reminder>ignore</system-reminder>"}},
            {**base, "type": "assistant", "timestamp": iso(5), "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": str(self.repo / "cart.ts")}},
                {"type": "tool_use", "name": "Bash", "input": {"command": "npm test"}}]}},
            {**base, "type": "user", "timestamp": iso(6), "message": {"role": "user", "content": [
                {"type": "tool_result", "content": "ok"}]}},
            {**base, "type": "assistant", "timestamp": iso(8), "message": {"role": "assistant", "content": [
                {"type": "text", "text": "Rounding fixed and tests pass."}]}},
            {**base, "type": "user", "timestamp": iso(9), "message": {"role": "user", "content":
                "<command-name>/worklog</command-name><command-args>today</command-args>"}},
        ])
        # subagent transcript of the same session
        write_jsonl(self.home / ".claude/projects/-code-shop/c-1/subagents/agent-a.jsonl", [
            {**base, "type": "user", "isSidechain": True, "timestamp": iso(3),
             "message": {"role": "user", "content": "explore the repo"}},
            {**base, "type": "assistant", "isSidechain": True, "timestamp": iso(4),
             "message": {"role": "assistant", "content": [
                 {"type": "tool_use", "name": "Write", "input": {"file_path": str(self.repo / "notes.md")}}]}},
        ])

    def codex(self):
        d = self.home / ".codex/sessions" / T0.strftime("%Y/%m/%d")
        name = T0.astimezone().strftime("rollout-%Y-%m-%dT%H-%M-%S")
        write_jsonl(d / f"{name}-x-1.jsonl", [
            {"timestamp": iso(30), "type": "session_meta", "payload": {
                "id": "x-1", "session_id": "x-1", "cwd": str(self.repo), "thread_source": "user",
                "git": {"branch": "feat/SHOP-42-cart"}}},
            {"timestamp": iso(30), "type": "response_item", "payload": {
                "type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>x</environment_context>"}],
                "internal_chat_message_metadata_passthrough": {"content_item_kinds": ["environments.environment_context"]}}},
            {"timestamp": iso(31), "type": "response_item", "payload": {
                "type": "message", "role": "user", "content": [{"type": "input_text", "text": "Add coupon support"}],
                "internal_chat_message_metadata_passthrough": {"content_item_kinds": ["user.text"]}}},
            {"timestamp": iso(35), "type": "response_item", "payload": {
                "type": "custom_tool_call", "name": "exec",
                "input": 'await tools.apply_patch("*** Begin Patch\\n*** Update File: src/coupon.ts\\n*** End Patch")'}},
            {"timestamp": iso(36), "type": "response_item", "payload": {
                "type": "custom_tool_call", "name": "exec", "input": 'text(await tools.exec_command({cmd:"pnpm test"}))'}},
            {"timestamp": iso(40), "type": "event_msg", "payload": {
                "type": "task_complete", "last_agent_message": "Coupons added."}},
        ])
        write_jsonl(d / f"{name}-x-2.jsonl", [
            {"timestamp": iso(32), "type": "session_meta", "payload": {
                "id": "x-2", "session_id": "x-1", "cwd": str(self.repo), "thread_source": "subagent",
                "agent_nickname": "Gauss"}},
            {"timestamp": iso(32), "type": "session_meta", "payload": {"id": "x-1", "session_id": "x-1"}},
            {"timestamp": iso(33), "type": "response_item", "payload": {
                "type": "message", "role": "user", "content": [{"type": "input_text", "text": "inherited"}],
                "internal_chat_message_metadata_passthrough": {"content_item_kinds": ["user.text"]}},
             "metadata": {"inherited_user_message": True}},
            {"timestamp": iso(34), "type": "response_item", "payload": {
                "type": "function_call", "name": "shell",
                "arguments": json.dumps({"command": ["bash", "-lc", "go test ./..."]})}},
            {"timestamp": iso(34), "type": "response_item", "payload": {
                "type": "custom_tool_call", "name": "exec",
                "input": "*** Add File: " + str(self.repo / "src/coupon_test.ts") + "\n"}},
        ])
        write_jsonl(self.home / ".codex/session_index.jsonl", [{"id": "x-1", "thread_name": "Coupons"}])

    def kiro(self):
        base = self.home / ".kiro/sessions/abc"
        for sid, extra, records in [
            ("sess_root", {"title": "Checkout flow"}, [
                {"timestamp": iso(60), "payload": {"type": "user", "content": "Build checkout page",
                                                   "_meta": {"kiro": {"userMessageTag": "p1"}}}},
                {"timestamp": iso(61), "payload": {"type": "user", "content": "Build checkout page",
                                                   "_meta": {"kiro": {"userMessageTag": "p1b"}}}},
                {"timestamp": iso(62), "payload": {"type": "user", "content": "background job finished",
                                                   "_meta": {"kiro": {"notification": {}}}}},
                {"timestamp": iso(70), "payload": {"type": "assistant", "content": "Checkout done."}},
            ]),
            ("sess_child", {"title": "checkout-impl · code #1", "rootConversationId": "sess_root",
                            "_meta": {"kiro": {"workflow": {"workflowName": "checkout-impl"}}}}, [
                {"timestamp": iso(65), "payload": {"type": "tool_call", "toolName": "str_replace", "kind": "edit",
                                                   "args": {"path": str(self.repo / "checkout.tsx")}}},
                {"timestamp": iso(66), "payload": {"type": "tool_call", "toolName": "execute_bash", "kind": "execute",
                                                   "args": {"command": "npm run build"}}},
            ]),
        ]:
            d = base / sid
            d.mkdir(parents=True)
            meta = {"id": sid, "workspacePaths": [str(self.repo)], "createdAt": iso(59),
                    "lastModifiedAt": iso(71), **extra}
            (d / "session.json").write_text(json.dumps(meta))
            write_jsonl(d / "messages.jsonl", records)

    def opencode_json(self):
        st = self.home / ".local/share/opencode/storage"
        (st / "session/proj").mkdir(parents=True)
        (st / "session/proj/oc-1.json").write_text(json.dumps({
            "id": "oc-1", "directory": str(self.repo), "title": "Refactor api",
            "time": {"created": ms(80), "updated": ms(90)}}))
        (st / "message/oc-1").mkdir(parents=True)
        (st / "message/oc-1/m1.json").write_text(json.dumps({"id": "m1", "role": "user", "time": {"created": ms(80)}}))
        (st / "message/oc-1/m2.json").write_text(json.dumps({"id": "m2", "role": "assistant", "time": {"created": ms(85)}}))
        (st / "part/m1").mkdir(parents=True)
        (st / "part/m1/p1.json").write_text(json.dumps({"type": "text", "text": "Refactor the api client"}))
        (st / "part/m2").mkdir(parents=True)
        (st / "part/m2/p1.json").write_text(json.dumps({"type": "tool", "tool": "edit",
                                                        "state": {"input": {"filePath": str(self.repo / "api.ts")}}}))

    def opencode_sqlite(self):
        db = self.home / ".local/share/opencode/opencode.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE session (id TEXT, directory TEXT, title TEXT, time_created INT, time_updated INT)")
        con.execute("CREATE TABLE message (id TEXT, session_id TEXT, time_created INT, data TEXT)")
        con.execute("CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT, data TEXT)")
        con.execute("INSERT INTO session VALUES ('oc-2', ?, 'Docs', ?, ?)", (str(self.repo), ms(100), ms(110)))
        con.execute("INSERT INTO message VALUES ('m9', 'oc-2', ?, ?)", (ms(100), json.dumps({"role": "user"})))
        con.execute("INSERT INTO part VALUES ('p9', 'm9', 'oc-2', ?)",
                    (json.dumps({"type": "text", "text": "Write README for SHOP-43"}),))
        con.commit()
        con.close()


class WorklogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.home = Path(cls.tmp.name)
        cls.old_home = os.environ.get("HOME")
        os.environ["HOME"] = str(cls.home)
        os.environ.pop("XDG_DATA_HOME", None)
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
        os.environ.pop("CODEX_HOME", None)
        cls.fx = Fixture(cls.home)
        cls.cfg = config.load()
        cls.start, cls.end = T0.astimezone() - timedelta(minutes=10), T0.astimezone() + timedelta(hours=3)
        cls.sessions, cls.stats = {}, {}
        for name, mod in ADAPTERS.items():
            root = mod.locate(cls.cfg)
            st = {}
            cls.sessions[name] = list(mod.collect(root, cls.start, cls.end, cls.cfg, st)) if root else []
            cls.stats[name] = st
        cls.report = aggregate.build([s for v in cls.sessions.values() for s in v],
                                     cls.start, cls.end, cls.cfg)

    @classmethod
    def tearDownClass(cls):
        if cls.old_home is not None:
            os.environ["HOME"] = cls.old_home
        cls.tmp.cleanup()

    def project(self):
        self.assertEqual(len(self.report["projects"]), 1)
        return self.report["projects"][0]

    def sessions_of(self, tool):
        return [s for s in self.project()["sessions"] if s["tool"] == tool]

    def test_all_sources_found(self):
        for name in ADAPTERS:
            self.assertTrue(self.sessions[name], f"{name} produced no sessions")
            self.assertNotIn("errors", self.stats[name])

    def test_claude(self):
        (s,) = self.sessions_of("claude")
        self.assertEqual(len(s["prompts"]), 1, "meta, sidechain, tool_result and /worklog are not prompts")
        self.assertIn("[REDACTED]", s["prompts"][0])
        self.assertNotIn("sk-abcdef", s["prompts"][0])
        self.assertEqual(sorted(s["files"]), ["cart.ts", "notes.md"])
        self.assertEqual(s["commands"], ["npm test"])
        self.assertEqual(s["last_reply"], "Rounding fixed and tests pass.")

    def test_codex_subagent_merged(self):
        (s,) = self.sessions_of("codex")
        self.assertEqual(s["title"], "Coupons")
        self.assertEqual(s["prompts"], ["Add coupon support"])
        self.assertEqual(sorted(s["files"]), ["src/coupon.ts", "src/coupon_test.ts"])
        self.assertIn("pnpm test", s["commands"])
        self.assertIn("go test ./...", s["commands"])
        self.assertEqual(s["subagents"], 1)
        self.assertEqual(s["subtasks"], ["Gauss"])

    def test_kiro_workflow_merged(self):
        (s,) = self.sessions_of("kiro")
        self.assertEqual(s["prompts"], ["Build checkout page"], "duplicates and notifications dropped")
        self.assertEqual(s["files"], ["checkout.tsx"])
        self.assertEqual(s["commands"], ["npm run build"])
        self.assertEqual(s["subtasks"], ["checkout-impl"])

    def test_opencode_json_and_sqlite(self):
        titles = {s["title"]: s for s in self.sessions_of("opencode")}
        self.assertEqual(titles["Refactor api"]["files"], ["api.ts"])
        self.assertEqual(titles["Docs"]["prompts"], ["Write README for SHOP-43"])

    def test_project_level(self):
        p = self.project()
        self.assertTrue(p["is_git"])
        self.assertEqual(p["name"], "shop")
        self.assertEqual([c["subject"] for c in p["commits"]], ["SHOP-42 add cart total"])
        self.assertEqual(p["issue_keys"][0], "SHOP-42")
        self.assertIn("SHOP-43", p["issue_keys"])
        self.assertEqual(p["tools"], ["claude", "codex", "kiro", "opencode"])
        self.assertGreater(p["active_minutes"], 0)

    def test_out_of_range_is_ignored(self):
        later = aggregate.build(
            [s for mod in ADAPTERS.values() if mod.locate(self.cfg)
             for s in mod.collect(mod.locate(self.cfg), self.end, self.end + timedelta(days=1), self.cfg, {})],
            self.end, self.end + timedelta(days=1), self.cfg)
        self.assertEqual(later["projects"], [])

    def test_cli_runs(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "worklog.py"), "1d"], capture_output=True,
                             text=True, env={**os.environ, "HOME": str(self.home)})
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["totals"]["projects"], 1)


class UnitTest(unittest.TestCase):
    def test_redact(self):
        self.assertNotIn("ghp_", redact("use ghp_abcdefghijklmnopqrstuvwxyz0123"))
        self.assertEqual(redact("DB_PASSWORD=hunter22"), "DB_PASSWORD=[REDACTED]")
        self.assertIn("https://[REDACTED]@", redact("https://user:pass@host/x"))
        self.assertIn("[REDACTED]", redact("Authorization: Bearer abcdefghijklmnopqrstu"))

    def test_clean_prompt(self):
        self.assertEqual(clean_prompt("<system-reminder>x</system-reminder>  hi\n there"), "hi there")
        self.assertTrue(clean_prompt("a" * 500, 50).endswith("…"))

    def test_ranges(self):
        s, e = parse_range("2026-11-01..2026-11-03")
        self.assertEqual((e - s).days, 3)
        s, e = parse_range("yesterday")
        self.assertEqual((e - s), timedelta(days=1))
        s, e = parse_range("7d")
        self.assertAlmostEqual((e - s).total_seconds(), 7 * 86400, delta=5)

    def test_active_minutes(self):
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        ev = [base, base + timedelta(minutes=10), base + timedelta(minutes=20),  # 20 min burst
              base + timedelta(hours=3)]                                        # isolated event
        self.assertEqual(aggregate.active_minutes(ev, 30, 5), 20 + 2 * 5)


if __name__ == "__main__":
    unittest.main()
