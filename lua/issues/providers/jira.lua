local root = vim.fs.dirname(debug.getinfo(1, "S").source:sub(2))
for _ = 1, 3 do
	root = vim.fs.dirname(root)
end
return {
	requirements = { "python3", vim.env.JIRA_QUEUE_BIN or "jira-queue" },
	auth_hint = "refresh-session jira-oci or refresh-session jira-central, matching your configured target",
	command = { vim.fs.joinpath(root, "packages", "jira", "issue-provider") },
	pattern = "%u[%u%d_]+%-%d+",
}
