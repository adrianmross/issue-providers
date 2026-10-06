# Optional issue providers

Small, separately installed GitHub Issues, Linear and Jira providers for oscm and review-mode.nvim. Nothing here ships in either base tool. Python 3 is the only shared runtime dependency; no pip packages, daemon or background login are required. Executable entry points use Unix shebangs; Windows users can select Python explicitly through review-mode command configuration.

## Install only the tracker you need

Requires an oscm build with issue-provider extension support:

```sh
oscm extension install adrianmross/issue-providers --name github --subdir packages/github --apply
oscm extension install adrianmross/issue-providers --name linear --subdir packages/linear --apply
oscm extension install adrianmross/issue-providers --name jira --subdir packages/jira --apply
```

Installing clones the package and records its executable. It does not execute provider code, install Python packages, read credentials or activate any project. Upgrade and remove use the existing oscm extension commands. Pin a reviewed commit with `--pin COMMIT`.

For Neovim, install `adrianmross/issue-providers` through your plugin manager and configure `review-mode.nvim` separately:

```lua
require("review_mode").setup({
  issues = {
    projects = {
      ["/path/to/repository"] = {
        provider = "github",
        options = { repo = "owner/repository" },
      },
    },
  },
})
```

This only loads the chosen adapter when an issue command is used. You can also install the Neovim modules with `oscm extension install adrianmross/issue-providers --name issue-plugins --apply`, then append the result of `oscm extension path issue-plugins` to your runtimepath.

## Provider configuration

| Provider | Required tool or authentication | Options | Search |
|---|---|---|---|
| GitHub | Existing authenticated `gh` | `repo`: `OWNER/REPO` or `HOST/OWNER/REPO` | GitHub issue search, up to 20 results |
| Linear | `LINEAR_API_KEY` or `LINEAR_ACCESS_TOKEN` in process environment | Optional `team` key | Case-insensitive title text, up to 20 results |
| Jira | `jira-queue` with issue snapshot support and its existing session store | Explicit `target`: `jira-oci` or `jira-central`; optional local `JIRA_QUEUE_BIN` environment override | JQL, up to 20 results |

GitHub issue keys are numbers or `#number`. Linear and Jira use keys such as `ENG-123`. Linear uses its documented GraphQL endpoint and variables, checks GraphQL errors even on HTTP 200, and delegates neither credential storage nor login to the editor. See https://linear.app/developers/graphql and https://linear.app/developers/filtering.

Use the same provider/options object as `issues` in `.oci-scm.json` for CLI selection. Preserve existing SCM configuration. Never put credentials in project files or provider options. Third-party code runs with your permissions when explicitly invoked; install reviewed repositories and pins.

## Cache behavior

GitHub and Linear snapshots use SQLite under `$XDG_CACHE_HOME/issue-providers` or `~/.cache/issue-providers`. Override with `ISSUE_PROVIDER_CACHE_DIR`. The cache contains normalized issue content, not session state, tokens or raw API responses. Cache files use mode 0600. Keys include provider, repository/team options and request. Use `cacheNamespace` to separate accounts/workspaces, especially after changing credentials. Delete this cache directory to clear snapshots.

Jira delegates caching to jira-queue's existing database and never creates a second Jira cache. Its snapshots are separated by explicit Jira target. `maxAge` defaults to 300 seconds. `--offline` never contacts a tracker. Normal reads fall back to visibly stale snapshots after a refresh failure; `--refresh` instead requires live success. No cache is proof of current remote authorization or issue status. These providers only read issues; they never transition, create, assign or publish them.

## Shared contract

Both hosts invoke an installed executable with `--request JSON`. Example:

```json
{"schema":"issue-provider.request.v1","operation":"get","key":"ENG-123","options":{"target":"jira-oci"},"offline":true,"refresh":false}
```

Search uses operation `search` and `query`. A successful response is exactly one JSON object:

```json
{"schema":"issue-provider.response.v1","issue":{"id":"123","key":"ENG-123","title":"Example","body":"Acceptance criteria","url":"https://tracker.example/issues/ENG-123","status":"Open","assignee":null,"labels":[],"updatedAt":null},"cache":{"source":"cache","fetchedAt":1791244800,"stale":true}}
```

Search returns `items` instead of `issue`. `fetchedAt` is Unix seconds; `stale` and `source` must remain visible to users. Exit nonzero for errors and keep stdout JSON-only. Hosts do not execute a shell string or trigger tracker authentication automatically.

## Validation

```sh
python3 -m unittest -v
```

Tests use fixtures and mock API calls only, covering cache isolation, offline reads, strict refresh behavior, canonical GitHub fields, Linear partial errors, and Jira delegation.
