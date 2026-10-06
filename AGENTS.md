# Agent instructions

- Keep this package generic and public. Never commit live issue contents, credentials, internal identifiers or session state.
- Providers are optional and read-only. Do not install dependencies or start login flows implicitly.
- Use isolated WorkTrunks and Python standard-library facilities. Run `python3 -m unittest -v`.
- Preserve the shared versioned JSON contract with oscm and review-mode.nvim.
- Jira authentication and snapshots belong to jira-queue; never duplicate its cookies or session store.
