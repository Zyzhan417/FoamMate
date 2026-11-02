# CHANGELOG

本文件记两件不同的事，**不要混算版本号**：

- **规则版本**（`AGENTS.md` 的 1.x）：约束 agent 行为的那套规则改了什么。
- **产品版本**（`VERSION` 里的 0.2.0）：发布给使用者的工具包改了什么。

规则版本原先写在 `AGENTS.md` 头部，占掉 950 字符的注入额度却对 agent 执行毫无用处
（agent 不需要知道 1.2 曾把分母从 12 改成 11），2026-10-29 迁到这里。

---

## 规则版本（`AGENTS.md`）

### 1.6 — 2026-10-29

- 新增 **R14 · 文档维护：一处写值，其余引用**（工程约定）：每类信息只有一个写值处，其它位置只写指针；
  改动按「它改变的事实」更新，不再要求「每次改动同步全部文档」；当前状态只在 `STATUS.md` 表达；
  状态记录固定六字段；局部改动只做局部核验，接口变更 / 模块集成 / 阶段交付才做全局一致性审查。
  细则、维护位置表与已知维护问题见 `references/13-maintenance.md`。**判据一字未改**。
- `specs/001-release-a-harness/tasks.md` 标注为 v0.1 执行记录（原文以删除线保留），当前状态移交 `STATUS.md`。
- R1–R13 正文与编号未动；本轮零代码改动，故无产品版本变化。

### 1.5 — 2026-10-29

- G-R12-2 由「`14/14 OK`」改为「`15/15 OK`」，并把 `scripts/status_snapshot.py` 补进清单描述。
  **规则未变**，是原文与实际清单不符（清单 2026-10-28 已从 14 行扩到 15 行）。
- 同一轮做了一次瘦身（不动任何判据）：版本变更史迁到本文件；R12 的重复段改为指向
  `bench/preregistration.md`；R13 压成「刷新时机 + 一条命令」；两个附录迁到
  `references/07-theory-provenance.md` §7 与 `references/11-delivery-form.md` §14。
  R1–R11 正文与编号未动。

### 1.4 — 2026-10-28

- 新增 R13 与 `scripts/status_snapshot.py`（机器段可重算、可校验）。
- 说明 `AGENTS.md` 的 20000 **字符**注入上限（不是字节），并在 `STATUS.md` 机器段持续报告占用。

### 1.3 — 2026-10-28

- 结果状态由六态扩为**七态**，新增 `declined`（正确拒绝，仅 T12）。
- `success_rate` 分母 12 → **11**（T12 负对照单列，语义相反不能混算）。
- 每任务跑 **3 次**取多数，三次各异记 `malformed` + `unstable=1`。
- 新增 `expect_values` 断言层——G 门只判"能不能跑"，断言判"改对了没有"，两者正交。
- `results.csv` 补 `repeats`、`unstable` 两列。

### 1.2 — 2026-10-28

- `bench/results.csv` 列定义补上 `g5`（范围门，之前漏列）。
- 新增 `g2b` 辅助信号列，并写明它不参与 `status`（v13 有 4 项 `***` 不计失败，见 R12）。

### 1.1 — 2026-10-27

- 新增 R9 第三方参考库只读且不作源码事实来源。
- 新增 R10 单项目体积线 + `registry.csv` 强制登记。
- 新增 R11 不装第二份 OpenFOAM。
- 新增 R12 基准跑预注册、设计期禁跑。
- R7 补一句 `bench/results.csv` 的 `arm` 列。R1–R8 正文与编号未动。

### 1.0 — 2026-10-27

- 首版：R1–R8 + 四条红线。

---

## 产品版本（`VERSION`）

### 0.4.0 — 2026-11-02

- 新增 `scripts/deploy.py`（仓库侧，**不进发布包**）：`--action install` 把仓库克隆到稳定路径
  （缺省 `~/foam-mate`）并跑该副本的 `preflight.sh` 自检；`--action update` 检测远端新提交，
  只在可快进时合并并重新自检；`--action status` 只读报告。退出码 `90`–`94`（见 README
  「部署与更新」一节）。
- 判据：`classify()` 是「要不要自动更新」的唯一判断处，L1 用判据表覆盖五个分支；
  L2 在真 OpenFOAM 上装一次、更新一次，两次 `preflight` 都必须 6/6。
- 不变：发布包仍是 15 个文件（`deploy.py` 依赖 `.git`，登记进 `make_release.sh` 的
  `FORBIDDEN_EXACT`）；`release/*.md` 未改，因为包里没有 `deploy.py`。

### 0.3.0 — 2026-10-31

- 新增 `scripts/dev_lib.py`（二次开发 / 用户库）：四个 stage `prepare` / `check` / `build` /
  `verify`（退出码 `85`–`89`），流程是「派生系统子库副本 → 判改动范围 → `wmake libso` →
  `foamRun -libs` 的 `dlopen` 证明」。**只保证编译与加载，不保证物理正确**；改 `.C`/`.H` 那一步
  仍由人 / 宿主做。规则与判据见 `AGENTS.md` R15、`release/SKILL.md` §11。

### 0.2.0 — 2026-10-29

- 新增 `scripts/batch.py`（批量运行）：`cases.json` 的 base + vary 矩阵 → 逐例派生/改参数/跑/门禁 →
  15 列 `results.csv`。
- 新增 `scripts/msh2d_to_foam.py`（2D 三角形网格导入）：gmsh `-2` 的 ascii `.msh` → 单层三棱柱
  `constant/polyMesh`。
- 工具包自包含化：包内脚本不再引用包外路径（`bench/`、`tests/`）。

### 0.1.0 — 2026-10-28

- 首版：8 个确定性 CLI（`preflight` / `parse_requirement` / `find_template` / `new_case` /
  `run_case` / `verify_case` / `fix_case` / `check_contracts`）+ 三份入口文档。
