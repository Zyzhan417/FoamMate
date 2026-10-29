# Adapter 接口契约（M4b 才实现，M4a 只冻结形状）

B 档项目（声明别的 OpenFOAM 版本）**不写进主排名**，只通过 adapter 做命令级替换后做定性对照。
依据：`AGENTS.md` R11（不装第二份 OpenFOAM）、`bench/preregistration.md` §7。

## 契约

每个 adapter 是一个模块，暴露一个函数：

```python
def run_task(task: dict, workdir: str, env: dict) -> dict:
    """执行一个任务，必须自己落盘，不得返回自评。
    返回: {"status": "pass|fail|no_artifact|malformed|blocked|overclaim",
          "artifacts": [相对路径...], "tokens": int|None, "wall_time_s": float,
          "interventions": int, "note": str}
    """
```

硬约束：

1. **adapter 不得自己判 pass/fail 的最终值**——它只能落盘日志与产物，由 `judge` 按 G1–G5 重算。
   返回里的 `status` 仅用于 `blocked`（前置不满足）自述，其余一律由 judge 覆盖。
2. **命令级替换必须登记**：每个 adapter 顶部写 `SUBSTITUTIONS` 列表，逐条记录
   `(原命令, 替换成, 依据)`。例：
   `("docker run -it ... leoyue123/foamagent:v2.0.0 bash", "直接在本机 source /opt/openfoam13/etc/bashrc", "R11：不装第二份 OF")`
3. **凡语义可能已变的地方必须标注** `untested_semantics: [描述]`，该臂结果自动标 `partial`。
4. adapter 不得修改 `references/repos/<arm>/`（R9 只读）；需要改配置就复制到 `bench/runs/` 下再改。
5. 三次尝试仍无法启动 → 返回 `blocked` 并写明卡在哪一步，**不得伪造 log**。

## 已知的替换点（来自 M4a 静态分析）

| arm | 原始命令/约束 | 替换思路 | 风险 |
|---|---|---|---|
| foam-agent | README:35 容器自带 OpenFOAM v10；README:76 `--openfoam_target esi-v2006` | 绕过 docker，直接调本机 v13 `foamRun`；target 参数改为 v13 | 它的模板库与 v10 语法绑定 |
| openfoam-mcp-server | README:257 `apt install openfoam12`；CMake 链系统 OF 库 | 指向 `/opt/openfoam13` 重编 | C++ 层 API 差异可能编译不过 |
| cfd-agent | ReadMe.md:78 必须 v2406，否则与 `database_OFv24/*.json` 不匹配 | 无可行替换（知识库绑版本） | 预计直接判 `blocked` |
| autofoam / deepflow | v2412 | 命令级替换 | 中 |
| metaopenfoam | 知识库由 openfoam10 tutorials 生成 | 用 v13 tutorials 重建库（成本高） | 高，暂不做 |
| nullflux | 推荐 v2306，随仓 sealed 二进制 | 二进制无法替换 | 预计 `blocked` |
