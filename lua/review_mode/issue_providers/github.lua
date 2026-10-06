local root = vim.fs.dirname(debug.getinfo(1, "S").source:sub(2))
for _ = 1, 3 do
	root = vim.fs.dirname(root)
end
return { command = { vim.fs.joinpath(root, "packages", "github", "issue-provider") }, pattern = "#%d+" }
