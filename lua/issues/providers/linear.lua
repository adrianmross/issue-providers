local root = vim.fs.dirname(debug.getinfo(1, "S").source:sub(2))
for _ = 1, 3 do
	root = vim.fs.dirname(root)
end
return {
	health = function()
		local present = (vim.env.LINEAR_API_KEY or "") ~= "" or (vim.env.LINEAR_ACCESS_TOKEN or "") ~= ""
		return present,
			present and "Linear credential is present; :IssueRefresh verifies API access"
				or "Linear credential is missing; set LINEAR_API_KEY or LINEAR_ACCESS_TOKEN in the editor environment"
	end,
	requirements = { "python3" },
	auth_hint = "Set LINEAR_API_KEY or LINEAR_ACCESS_TOKEN in the Neovim environment",
	command = { vim.fs.joinpath(root, "packages", "linear", "issue-provider") },
	pattern = "%u[%u%d_]+%-%d+",
}
