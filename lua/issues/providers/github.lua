local root = vim.fs.dirname(debug.getinfo(1, "S").source:sub(2))
for _ = 1, 3 do
	root = vim.fs.dirname(root)
end
return {
	health = function(config)
		local repo = (config.options or {}).repo or ""
		local host = repo:match("^([^/]+)/[^/]+/[^/]+$") or "github.com"
		local result = vim.system(
			{ "gh", "auth", "status", "--active", "--hostname", host },
			{ text = true, timeout = 10000 }
		)
			:wait()
		return result.code == 0,
			result.code == 0 and ("Existing gh authentication works for " .. host)
				or ("GitHub authentication unavailable for " .. host .. "; run gh auth login --hostname " .. host)
	end,
	requirements = { "python3", "gh" },
	auth_hint = "gh auth login (use --hostname for Enterprise)",
	command = { vim.fs.joinpath(root, "packages", "github", "issue-provider") },
	pattern = "#%d+",
}
