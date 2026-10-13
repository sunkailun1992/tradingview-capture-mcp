# 维护者

## English summary

- Maintainer: @sunkailun1992 (repository admin).
- The maintainer and the maintainer's own Claude/Codex sessions may merge to `main` directly after the local checks pass; everyone else needs the maintainer's review and approval.
- Only squash merges; no force pushes or deletions of `main`; agents never change the ruleset or repository permissions.

## 名单

| GitHub | 角色 |
|---|---|
| [@sunkailun1992](https://github.com/sunkailun1992) | 仓库管理员、维护者 |

## 合并规则

- 维护者本人，以及维护者本机用维护者账号运行的 Claude / Codex 会话，可以直接合并到 `main`：合并前本机验证命令全过，合并后看 CI。
- 其他人的 PR：CI 全绿、维护者审核确认是有益的改动并批准、评审对话全部解决之后，由维护者 squash 合并。
- 禁止强推和删除 `main`；任何代理都不得修改 ruleset 或仓库权限。

## 发布

- 版本号用语义化版本；改输出格式或 MCP 工具参数是不兼容改动，升主版本号。
- 每次发布在 `CHANGELOG.md` 写明变化，以及验证过的 TradingView 桌面版版本。
