import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import provider


class ProviderTests(unittest.TestCase):
    def test_cache_freshness_offline_and_target_isolation(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"ISSUE_PROVIDER_CACHE_DIR": directory}):
            req = {"schema": "issue-provider.request.v1", "operation": "get", "key": "#1", "options": {"repo": "one/repo"}}
            fetch = lambda _: {"issue": {"key": "#1", "title": "Title"}}
            first = provider.cached("github", req, fetch)
            self.assertEqual(first["cache"]["source"], "remote")
            offline = provider.cached("github", dict(req, offline=True), lambda _: self.fail("network called offline"))
            self.assertEqual(offline["cache"]["source"], "cache")
            with self.assertRaises(RuntimeError):
                provider.cached("github", dict(req, options={"repo": "two/repo"}, offline=True), fetch)
            def failed(_):
                raise RuntimeError("session expired")
            with patch("provider.time.time", return_value=first["cache"]["fetchedAt"] + 400):
                stale = provider.cached("github", req, failed)
                self.assertTrue(stale["cache"]["stale"])
                self.assertTrue(stale["cache"]["refreshUnavailable"])
                with self.assertRaises(RuntimeError):
                    provider.cached("github", dict(req, refresh=True), failed)
            content = Path(directory, "snapshots.sqlite3").read_bytes()
            self.assertNotIn(b"session expired", content)

    def test_actionable_auth_and_missing_tool_errors(self):
        from types import SimpleNamespace
        with patch("provider.subprocess.run", return_value=SimpleNamespace(returncode=1, stderr="Please run gh auth login", stdout="")):
            with self.assertRaisesRegex(RuntimeError, "gh auth login"):
                provider.command(["gh", "issue", "view", "1"])
        with patch("provider.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(RuntimeError, "required executable is missing"):
                provider.command(["missing-tool"])
        with patch("provider.subprocess.run", return_value=SimpleNamespace(returncode=1, stderr="session state is expired", stdout="")):
            with self.assertRaisesRegex(RuntimeError, "refresh-session jira-oci"):
                provider.command(["jira-queue", "issue", "view", "EX-1", "--target", "jira-oci"])

    def test_github_argv_and_normalization(self):
        raw = {"id": "I_1", "number": 1, "title": "Test", "body": "Details", "url": "https://github.com/owner/repo/issues/1", "state": "OPEN", "assignees": [{"login": "alice"}], "labels": [{"name": "bug"}]}
        with patch("provider.command", return_value=raw) as command:
            value = provider.github({"operation": "get", "key": "#1", "options": {"repo": "owner/repo"}})
            self.assertEqual(value["issue"]["labels"], ["bug"])
            self.assertEqual(value["issue"]["assignee"], "alice")
            self.assertEqual(command.call_args.args[0][:4], ["gh", "issue", "view", "1"])

    def test_linear_partial_errors_never_become_success(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return json.dumps({"errors": [{"message": "denied"}], "data": {}}).encode()
        with patch.dict(os.environ, {"LINEAR_API_KEY": "test-only"}), patch("provider.urllib.request.urlopen", return_value=Response()) as call:
            with self.assertRaises(RuntimeError):
                provider.linear({"operation": "get", "key": "EX-1"})
            req = call.call_args.args[0]
            self.assertEqual(req.full_url, "https://api.linear.app/graphql")
            self.assertEqual(json.loads(req.data)["variables"]["id"], "EX-1")

    def test_jira_requires_target_and_delegates_cache(self):
        with self.assertRaises(ValueError):
            provider.jira({"operation": "get", "key": "EX-1"})
        with patch("provider.command", return_value={"schema": provider.SCHEMA}) as command:
            provider.jira({"operation": "get", "key": "EX-1", "offline": True, "options": {"target": "jira-oci"}})
            self.assertEqual(command.call_args.args[0], ["jira-queue", "issue", "view", "EX-1", "--target", "jira-oci", "--offline"])


if __name__ == "__main__":
    unittest.main()
