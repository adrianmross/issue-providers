#!/usr/bin/env python3
"""Optional tracker adapters. Only Python's standard library is required."""
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request

SCHEMA = "issue-provider.response.v1"


def command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=45)
    if result.returncode:
        if "session state is expired" in result.stderr and "--target" in argv:
            target = argv[argv.index("--target") + 1]
            raise RuntimeError(f"Jira session expired; run refresh-session {target}")
        # CLI diagnostics can contain private response bodies; keep them out of caches.
        raise RuntimeError(f"{Path(argv[0]).name} request failed; check its authentication separately")
    return json.loads(result.stdout)


def github(request):
    options = request.get("options") or {}
    repo = options.get("repo", "")
    if not re.fullmatch(r"(?:[A-Za-z0-9.-]+/)?[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("GitHub options.repo must be OWNER/REPO or HOST/OWNER/REPO")
    fields = "id,number,title,body,url,state,assignees,labels,updatedAt"
    if request["operation"] == "get":
        key = str(request.get("key", "")).lstrip("#")
        if not key.isdigit():
            raise ValueError("GitHub issue key must be a number or #number")
        values = [command(["gh", "issue", "view", key, "-R", repo, "--json", fields])]
    else:
        values = command(["gh", "issue", "list", "-R", repo, "--state", "all", "--limit", "20", "--search", request["query"], "--json", fields])
    items = [{"id": v["id"], "key": f'#{v["number"]}', "title": v["title"],
              "body": v.get("body") or "", "url": v["url"], "status": v["state"],
              "assignee": ", ".join(x.get("login", "") for x in v.get("assignees", [])),
              "labels": [x["name"] for x in v.get("labels", [])], "updatedAt": v.get("updatedAt")} for v in values]
    return {"issue": items[0]} if request["operation"] == "get" else {"items": items}


def linear(request):
    token = os.environ.get("LINEAR_API_KEY")
    oauth = os.environ.get("LINEAR_ACCESS_TOKEN")
    if not token and not oauth:
        raise RuntimeError("set LINEAR_API_KEY or LINEAR_ACCESS_TOKEN in the plugin process environment")
    fields = "id identifier title description url updatedAt state { name } assignee { name } labels { nodes { name } }"
    if request["operation"] == "get":
        query = "query($id: String!) { issue(id: $id) { " + fields + " } }"
        variables = {"id": request["key"]}
    else:
        query = "query($filter: IssueFilter!) { issues(first: 20, filter: $filter) { nodes { " + fields + " } } }"
        filters = {"title": {"containsIgnoreCase": request["query"]}}
        team = (request.get("options") or {}).get("team")
        if team:
            filters["team"] = {"key": {"eq": team}}
        variables = {"filter": filters}
    req = urllib.request.Request("https://api.linear.app/graphql", data=json.dumps({"query": query, "variables": variables}).encode(),
                                 headers={"Authorization": token or "Bearer " + oauth, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError("Linear GraphQL returned errors; no partial result was cached")
    values = [result["data"]["issue"]] if request["operation"] == "get" else result["data"]["issues"]["nodes"]
    if any(not v for v in values):
        raise RuntimeError("Linear issue not found")
    items = [{"id": v["id"], "key": v["identifier"], "title": v["title"],
              "body": v.get("description") or "", "url": v["url"], "status": (v.get("state") or {}).get("name"),
              "assignee": (v.get("assignee") or {}).get("name"), "labels": [x["name"] for x in v.get("labels", {}).get("nodes", [])],
              "updatedAt": v.get("updatedAt")} for v in values]
    return {"issue": items[0]} if request["operation"] == "get" else {"items": items}


def jira(request):
    options = request.get("options") or {}
    target = options.get("target")
    if target not in ("jira-oci", "jira-central"):
        raise ValueError("Jira options.target must explicitly select jira-oci or jira-central")
    op = "view" if request["operation"] == "get" else "search"
    argv = [os.environ.get("JIRA_QUEUE_BIN", "jira-queue"), "issue", op, request.get("key") or request["query"], "--target", target]
    for name in ("offline", "refresh"):
        if request.get(name):
            argv.append("--" + name)
    if "maxAge" in options:
        argv += ["--max-age", str(int(options["maxAge"]))]
    return command(argv)


def validate(request):
    if request.get("schema") != "issue-provider.request.v1" or request.get("operation") not in ("get", "search"):
        raise ValueError("unsupported issue-provider request")
    field = "key" if request["operation"] == "get" else "query"
    if not isinstance(request.get(field), str) or not request[field].strip() or len(request[field]) > 8192:
        raise ValueError(f"a nonempty {field} is required")
    if request.get("offline") and request.get("refresh"):
        raise ValueError("offline and refresh are mutually exclusive")
    if request.get("options") is not None and not isinstance(request["options"], dict):
        raise ValueError("options must be an object")


def cached(provider, request, fetch):
    options = request.get("options") or {}
    ttl = int(options.get("maxAge", 300))
    if ttl < 0:
        raise ValueError("maxAge cannot be negative")
    # Cache only normalized issue content, never session state or environment tokens.
    root = Path(os.environ.get("ISSUE_PROVIDER_CACHE_DIR") or Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "issue-providers")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / "snapshots.sqlite3"
    with sqlite3.connect(path) as db:
        os.chmod(path, 0o600)
        db.execute("CREATE TABLE IF NOT EXISTS snapshots (provider TEXT, key TEXT, payload TEXT, fetched_at INTEGER, PRIMARY KEY(provider,key))")
        key = json.dumps({k: request.get(k) for k in ("operation", "key", "query", "options")}, sort_keys=True)
        row = db.execute("SELECT payload,fetched_at FROM snapshots WHERE provider=? AND key=?", (provider, key)).fetchone()
        now = int(time.time())
        stale = row is not None and now - row[1] >= ttl
        if row and (request.get("offline") or (not request.get("refresh") and not stale)):
            value = json.loads(row[0])
            value["cache"] = {"source": "cache", "fetchedAt": row[1], "stale": stale}
        else:
            if request.get("offline"):
                raise RuntimeError("no cached snapshot for this provider and request")
            try:
                value = fetch(request)
            except Exception:
                if not row or request.get("refresh"):
                    raise
                value = json.loads(row[0])
                value["cache"] = {"source": "cache", "fetchedAt": row[1], "stale": True, "refreshUnavailable": True}
            else:
                db.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?)", (provider, key, json.dumps(value), now))
                value["cache"] = {"source": "remote", "fetchedAt": now, "stale": False}
        value["schema"] = SCHEMA
        return value


def main(provider):
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    try:
        request = json.loads(args.request)
        validate(request)
        allowed = {"github": {"repo", "maxAge", "cacheNamespace"}, "linear": {"team", "maxAge", "cacheNamespace"}, "jira": {"target", "maxAge"}}[provider]
        if set(request.get("options") or {}) - allowed:
            raise ValueError("unsupported provider options; credentials belong in the process environment")
        result = jira(request) if provider == "jira" else cached(provider, request, {"github": github, "linear": linear}[provider])
        print(json.dumps(result))
    except Exception as error:
        # Never echo request bodies, auth headers, or token-bearing HTTP errors.
        print(f"issue provider failed: {type(error).__name__}: " + str(error) if isinstance(error, (ValueError, RuntimeError)) else "issue provider request failed; check network/authentication", file=sys.stderr)
        return 1
    return 0
