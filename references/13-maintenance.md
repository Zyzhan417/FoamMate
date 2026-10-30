# 13 · 文档维护结构：每类信息只写一处

> 本文回答两个问题：**这类信息该写在哪**、**改了什么才需要动它**。
> 它不是事实来源——规则看 `AGENTS.md`，当前状态看 `STATUS.md`，对外接口看 `release/SKILL.md`。
> 建立于 2026-10-29（依据一次只读维护结构调查 + 本轮局部复核），不占版本号。
> 新会话接续仍看 `STATUS.md`（R13）；本文只在「要改文档 / 要判断该更新哪些记录」时读。

---

## 1 三条不变量

1. **一处写值，其余引用。** 同一事实只在一个文件里写「值」，其它位置写指针（路径 + 章节号），
   不复述。复述的副本不会自己过期，它只会与主位置悄悄分叉。
2. **按影响更新，不按「改了东西」更新。** 只有**改变了某份文档所描述的事实**时才编辑它。
   本项目没有「每次改动同步全部文档」这条规则，也不要发明它。
3. **状态与历史分离。** 当前状态写现在时，且必须带「未验证项」；历史验证记录保持过去时 +
   当时的版本/工作树状态。**今天重跑通过，不改写昨天的失败记录**。

两条可判定的自检（写文档前先过一遍）：

- 想写一个数字 → 先答「哪条命令能重算它、哪道门在守」。答不出就只写指针，不写值（R6）。
- 想在第二份文档里改同一个值 → 说明第一次就写错了位置：先把值移到主位置，另一处改指针。

---

## 2 信息类 → 唯一维护位置

「唯一写值处」= 只在这里写具体值/判据；其它文档只能引用它。

| 信息类 | 唯一写值处 | 其它位置的正确写法 | 守它的检查 |
|---|---|---|---|
| agent 规则（硬规则 / 工程约定） | `AGENTS.md`（R 编号） | 只写「R 号 + 一句话判据」，不复述配方与命令 | 无门（人工）；R12 涉及的仪器在 `bench/tasks/FROZEN.sha256` 里 |
| 对外接口：命令、参数、退出码语义、停点 | `release/SKILL.md` §3–§5；退出码码表同时受 `scripts/check_release_docs.py` 的 `KNOWN_EXIT_CODES` 约束 | README 只写能力概览，不列参数；测试按「类」遍历脚本 | `check_release_docs.py`（引用存在 + 码集合）、`tests/unit/test_exit_codes.py` |
| 产品范围与限制 | `release/SCOPE.md` | README「已知限制」给四条摘要 + 链接 | `check_release_docs.py` |
| 需求约定（v0.1） | `specs/001-release-a-harness/spec.md` | 其它文档引用 `spec §` | 无门；历史件。v0.2 无 spec，见 M-7 |
| 实施计划（v0.1） | `specs/001-release-a-harness/plan.md`、`tasks.md` | `STATUS.md` 只指路 | 无门；2026-10-29 起冻结为历史 |
| **当前任务状态** | `STATUS.md`：`N1`（现在哪一步）/ `N4`（下一步）/ `N11`（轮次记录） | 其它文档不写「现在到哪一步」 | `G-R13-1`（机器段）+ 人工 |
| 冻结方法学与任务集 | `bench/preregistration.md` + `bench/tasks/T*.yaml` | `AGENTS.md` R12 只指章节号 | `G-R12-2` / `G-R12-3` |
| 基准实测数据 | `bench/results.csv`（15 列，唯一数据源） | 报告逐行回切 CSV；缺口清单只引结论 | `G-CONTRACT-1`；`G-R12-1` 的状态多样性 |
| 基准结论与失败归因 | `references/12-bench-report.md` | `STATUS.md` N1 只放头条数与限定 | 无门（靠其 §10 的复现命令） |
| 缺口与待裁定 | `references/10-gap-register.md`（每条带现状命令 / 判据 / 验收命令） | `STATUS.md` N4 只列条目名 | 无门 |
| 二次开发流程与判据 | `references/14-library-dev-flow.md` | 其它文档只引用 §号 | 无门 |
| 测试基线 | `tests/unit/README.md`、`tests/contract/README.md`：判据 `failed=0`，**不记项数** | 其它文档不写「N 项测试」 | 无门（约定） |
| 版本历史 | `CHANGELOG.md`（规则版本 / 产品版本两条轴，不混算） | 其它文档不写「某版本加了什么」 | 无门 |
| 参考库登记 | `references/registry.csv` | 第三方引用写成 `references/repos/<repo>/<file>:<line>`，sha 必须对得上 | `G-R9-1` / `G-R10-1`；`G-DOC-1` |
| 设计依据与调研 | `references/00`–`12`（各文件头部写明范围与用途，部分带日期） | 引用 `path` + `§` | `G-DOC-1`（只判第三方 `:line`） |
| 发布边界（哪些文件不发布） | `.gitignore`（权威表达）+ `scripts/make_export.sh` / `scripts/verify_export.py`（实现） | `references/11-delivery-form.md` §14 解释理由 | 导出树 `E1`–`E6` |
| **文档维护结构（本文）** | `references/13-maintenance.md` | `AGENTS.md` R14 只写规则，不复述本表 | 无门 |

「无门」是事实，不是可以放松：这几类信息过期时**没有任何东西会变红**，只能靠本表的更新判据（§3）
和状态记录里的「未验证项」（§4）。

---

## 3 更新判据（按影响，不按动作）

| 你做了什么 | 必须更新（写值处） | 通常不必更新 | 局部核验 |
|---|---|---|---|
| 改 CLI 参数 / 新增用户面脚本 | `release/SKILL.md` §3–§5；新退出码进 `KNOWN_EXIT_CODES`；对应测试；脚本清单（见 §6 M-1） | README 能力概览（除非能力变了）、`references/00`、`specs/` | `check_release_docs.py` + 该脚本的测试 |
| 只改实现、接口不变（bug fix） | 代码 + 回归测试；已发布 → `CHANGELOG.md` 产品版本；若是坑 → `STATUS.md` N7/N9 | 其它文档一律不动 | 相关测试文件 |
| 新增 / 关闭缺口 | `10-gap-register.md` 该条（保留历史行）；`STATUS.md` N4 一行 | `12-bench-report.md`（历史结论不改写） | 该条自带的「现状命令」 |
| 一轮实跑 / 新基准数据 | `bench/results.csv`；报告；`STATUS.md` N1 摘要 | `tests/*/README.md`（只判 `failed=0`） | `check_contracts.py` + 重算脚本 |
| 里程碑 / 阶段收尾 | `STATUS.md` N1（+N4）+ 六字段记录（§4）；对外发布时才动 `CHANGELOG` | `specs/tasks.md` 的勾选（历史） | `status_snapshot.py --check` + §5 全局 |
| 文档里的数字/事实过期 | **只改那份文档**（主位置） | 不要顺手「全部文档一起改」 | `grep` 该数字的副本，确认只有一处 |
| 新增一份文档 | 文档本身 + 引用它的索引入口（`STATUS.md` N1.1 / README 结构行） | 不要求登记到所有列表 | `grep` 文件名，确认没有硬编码枚举 |
| 改判据 / 冻结件 | **不允许就地改**；按 `bench/preregistration.md` §13 开新一轮 | — | `bash scripts/verify_references.sh --frozen` |

**判据句**：更新一份文档的唯一理由是「它描述的事实变了」。不是「我改了代码」，也不是「它很旧」。
反面例子（本轮实测）：`specs/001/tasks.md` 48/48 全勾完却表达不了 v0.2 的两个脚本——它的问题不是
不新，是**它被当成了当前状态**；处理方式是换主位置（§7），不是把它再改一遍。

---

## 4 状态记录：六字段

每条状态记录都要有这六项，缺任一不算记录（`STATUS.md` N11 是实例）。

| 字段 | 写法 | 反例 |
|---|---|---|
| 任务 | 一句话 + 类型（文档校正 / bug fix / 新功能 / 一轮实跑） | 「继续推进」 |
| 被测版本或工作树状态 | `HEAD <sha>`（提交标题）+ 开始时 `git status --porcelain \| wc -l` 的行数 | 「当前代码」 |
| 实际验证命令 | 可原样复制的命令，一行一条；解释器写**绝对路径** | 「跑了测试」 |
| 结果 | 退出码 + 关键日志行（R6） | 「应该没问题」「基本通过」 |
| 未验证项 | 明确写「未验证」，并点名范围（未提交的树 / 未跑的分支 / 未审的正文） | 省略不写 |
| 下一步 | 指向 `STATUS.md` N4 的条目号或 §6 的登记号 | 重抄一遍下一步的内容 |

放在哪：**跨轮仍有效的**（阶段、决策、下一步）进 `STATUS.md` N1/N4；**一次性轮次记录**进 N11，
旧的不删。同一件事不要同时写在 N1 和 N11——两处必然漂移。

模板（复制后填）：

```text
任务：<一句话；类型>
被测版本或工作树：HEAD <sha>（<标题>）；开始前 `git status --porcelain | wc -l` = <n>
实际验证命令：
  <命令 1>
  <命令 2>
结果：<命令 1 → 退出码 0 / 关键行>；<命令 2 → …>
未验证项：<点名>
下一步：<N4 第 k 条 / §6 M-x>
```

---

## 5 局部核验 vs 全局一致性审查

**局部核验**（每次改动都做，秒级）：

| 改了什么 | 至少跑这些 |
|---|---|
| 任何 `references/*.md` / `bench/*.md` | 整条 `bash scripts/verify_references.sh --frozen`（含 `G-DOC-1`；脚本没有单门开关） |
| `release/*.md` | `python3 scripts/check_release_docs.py` |
| `STATUS.md` | `python3 scripts/status_snapshot.py --check` |
| `AGENTS.md` / `README.md` / `bench/preregistration.md` 等机器段登记的文件 | `python3 scripts/status_snapshot.py --write` 再 `--check` |
| 某个脚本 | 它自己的测试文件；跨模块入口见 `tests/unit/test_script_entrypoints.py` |

**全局一致性审查**只在三种触发下做，不做日常：

1. **接口变更**：CLI 参数、退出码、文件布局、发布白名单。
2. **模块集成**：跨脚本链路（A→C→D→E→judge）、发布包、导出树。
3. **阶段交付**：里程碑收尾、版本发布、一轮基准实跑。

全局命令集（顺序跑；含两层测试）：

```bash
bash scripts/verify_references.sh --frozen        # 11 道门
python3 scripts/status_snapshot.py --check        # STATUS 机器段
python3 scripts/check_release_docs.py             # release/ 契约
python3 scripts/check_contracts.py --results bench/results.csv
python3 -m pytest tests/unit tests/contract -q    # 用装有 pytest 的绝对路径解释器
PYTHON=<同上解释器> bash scripts/make_export.sh --dest dist/export   # 从 HEAD 组树，需先提交
```

**为什么必须分开**：`make_export.sh` 用 `git archive HEAD` 组树，**看不见未提交的工作树**。
所以「全局门全绿」只对它测的那棵树有效；把全局当日常，会得到「绿了但没测到本次改动」的错觉
（本轮就是：导出树 E1–E6 尚未覆盖本轮 7 份文档改动，因为改动未提交）。反过来，单模块测试绿也不能
代替集成——N7 第 12 条（三个缺陷只在集成时暴露）就是这条的代价。

---

## 6 已知维护问题（登记，本轮未修）

每条都带可复现的现状命令；能选的给两种处理与代价，不能选的写明「不改」及理由。**不自行裁定**。

### M-1 脚本清单七处平行登记（另有一处漏项）

现状：加/改一个用户面脚本要同步 `scripts/preflight.sh` 的 `USER_SCRIPTS`（8 个，不含自身）、
`scripts/make_release.sh` 的 `WL_SRC`/`WL_DST`（两数组）、`tests/unit/test_exit_codes.py` 的 `SCRIPTS`、
`tests/unit/test_portability.py` 的 `USER_FACING`、`tests/contract/test_make_release.py` 的
`PACKAGE_SCRIPTS`、`scripts/check_release_docs.py` 的 `KNOWN_EXIT_CODES`（退出码，不是脚本名）、
以及 `scripts/preflight.sh` 里那句「8 个用户面脚本」的三处文字副本
（实测 `grep -n "个用户面脚本" scripts/preflight.sh` → 12 / 74 / 94；同文件 :212 是从数组算的，
不用改）——**同一份清单的文字副本，加脚本时要一起改，没有任何门盯它**。
v0.3 的 `scripts/dev_lib.py` 进上述七处。

```bash
grep -n "USER_SCRIPTS=\|WL_SRC=\|WL_DST=" scripts/preflight.sh scripts/make_release.sh
grep -n "个用户面脚本" scripts/preflight.sh
grep -n "SCRIPTS = \[" tests/unit/test_exit_codes.py
grep -n "USER_FACING = \[" -A12 tests/unit/test_portability.py
grep -n "PACKAGE_SCRIPTS = {" -A12 tests/contract/test_make_release.py
```

已知不一致（本轮复核）：`tests/unit/test_portability.py:40` 的注释写「那 6 个 + P2 才出现的
`preflight.sh`」，紧随的 `USER_FACING` 有 8 项且**没有 `batch.py`**——即「不得写死
`/opt/openfoam13`」这条判据当前不覆盖 `batch.py`。`README.md:123` 说 9 个用户面 CLI。
「七处」的算法：`make_release.sh` 的两个平行数组算一处；第 7 处是上面那句 usage 文字，它只是文字、
没有断言。`README.md:123` 的用户面 CLI 计数是又一处文字、同样无断言（见 M-2）。

- 选项 A：抽一份单一清单（如 `scripts/clis.txt`），七处改为派生 + 断言；代价：一次设计 + 7 处改造 + 4 个测试文件。
- 选项 B：保持现状，把「7 处」写进本文（已写），并给 `test_portability` 补 `batch.py`；代价：仍要改 7 处，其中两处（usage 文字、README 计数）漏改不会被抓红。

### M-2 README 的事实没有任何门盯着

`scripts/check_release_docs.py:146` 用 `doc_dir.glob("*.md")`，只扫 `release/`。根 `README.md` 不在覆盖面；
导出树的 E2 只判「引用能回切 + 行号不越界」，不判陈述真伪 → **路径写错会被抓，事实写旧永远不会被抓**。
2026-10-29 已修掉当时查出的三处（`references` 编号范围、`bench/runs` 为空、测试项数），根因未解决。

- 选项 A：把 README 纳入 `check_release_docs.py`（需要为「陈述」设计可判定判据，不能只判引用）。
- 选项 B：接受无门，改 README 时必须跑 `grep` 自查 + 在 N11 记一条。代价：靠人。

### M-3 P-01：`scripts/batch.py` 用非单调墙钟

`scripts/batch.py:589` / `:598` 用 `time.time()` 测 `wall_time_s`；`tests/contract/test_batch_e2e.py`
断言 `value >= 0`。WSL2 上 `CLOCK_REALTIME` 步进校正时可能写出负值（实测 `-1.7`、`-2.84`），
于是同一行代码在不同运行里给出相反结论。本轮全量契约层跑 **82 passed**，但这不代表已修——是时钟这次没有倒退。

- 选项 A（建议但需批准）：改 `time.monotonic()` + 补一条不依赖时钟的单测（monkeypatch `time.time` 回退）。
- 选项 B：保留并按「已知偶发」登记；代价：契约层随机变红会被训练成「重跑就好」（N7 第 18 条的危害）。

### M-4 `scripts/verify_references.sh` 头部退出码说明与实现不符

`scripts/verify_references.sh:9` 写「0 全过 / 1 R9 / 2 R10 / 3 R11 / 4 R12 / 5 文档引用」，
实现里所有违规都累加到同一个 `fail`，实测只可能退 0 或 1。

- 选项 A：改说明为「0 全过 / 1 有违规（逐门打印）」。
- 选项 B：实装分码；前置是先确认没有下游依赖这组码（它是 11 道门的总闸）。

### M-5 无门计数仍在两处

根 README 的测试项数已在本轮改成定性（§7）；`references/10-gap-register.md` §0 仍写「`98` 项测试」
（本轮实测收集 338：`pytest --collect-only -q` 分别 256 + 82）。`10-gap-register` 是分析文档，
不是状态文档，故未改。判据：出现「N 项测试」的句子都要能被 `--collect-only` 重算，否则降为定性。
同类残留：`STATUS.md` N10 写「`references/00` 有约 50 处下游 `:NNN` 引用」，本轮实测 **97** 处
（命令见 M-6）；N10 是上一轮的记录，按「历史记录保持过去时」不改写，只在此登记。

### M-6 `references/00` §7.1 的文档索引停在 03–11

`references/00-project-readme.md` §7.1 标题即「03–11 各回答什么问题」，不含 12 与 13。
该文件头部已声明「本文是设计阶段的记录，不是现状快照」，**这是设计记录的正确形态**，不要为了「补齐」
去改它（它有 97 处 `references/00-project-readme.md:NNN` 形态的入站引用，实测
`grep -rhoE "references/00-project-readme\.md:[0-9]+" --include=*.md . --exclude-dir=repos --exclude-dir=dist --exclude-dir=.hermes | wc -l`；
插行会静默漂移）。当前索引以 `STATUS.md` N1.1 为准。

### M-7 v0.2 的两个能力没有需求约定文件

现状：`specs/` 只有 `001-release-a-harness`（v0.1 交付形态），v0.2 的 `batch.py`（批量运行）与
`msh2d_to_foam.py`（2D 网格导入）**没有 spec / plan**，其约定实际落在 `release/SKILL.md` §10 与
`CHANGELOG.md` 0.2.0 的两行描述里。

```bash
ls specs/                                   # → 只有 001-release-a-harness
grep -n "## 10 批量运行" release/SKILL.md    # → v0.2 能力的实际契约位置
```

- 选项 A：补一份 `002` spec（那两条能力的需求、退出码、不做清单）；代价：新文档 + 与 SKILL 去重的维护点。
- 选项 B：认定 `release/SKILL.md` §10 就是这两条能力的契约，`specs/` 只覆盖 v0.1 交付形态，
  在 §2 表里写明这一点（已写）。代价：契约与需求没有分离，SKILL 改一次就同时改了「需求」。

**这是记录，不是裁定**：两种都可以自洽，但混用会让「需求变了吗」无法判定。

---

## 7 本轮落地（2026-10-29，不占版本号：只改文档）

| 文件 | 改动 | 依据 |
|---|---|---|
| `references/13-maintenance.md` | 新建（本文） | 维护结构调查的导航表 + 本轮复核 |
| `AGENTS.md` | 追加 R14（**工程约定**，位于 R13 之后、`附` 之前；R1–R13 与行号未动） | 规则要有入口，细节留在本文 |
| `README.md` | 结构行的 `references` 范围 00–12 → 00–13；规则条数改为「14 条（9 硬 + 5 约定）」；两处测试项数改为定性 | 本轮新增 13；`grep -c '^## R' AGENTS.md` |
| `specs/001-release-a-harness/tasks.md` | 头注释：原文「单一事实来源」保留为删除线 + 冻结说明 | 与 R13 冲突，见下 |
| `references/11-delivery-form.md` §10 | 同一处「`tasks.md` 是唯一事实来源」改为指向 `STATUS.md`（状态列标明是当时快照） | 同一冲突的第二处副本（N8 第 6 条：修一条事实错误先 grep 全部副本） |
| `STATUS.md` | N1 里「唯一事实来源是 tasks.md 的勾选框」改为「v0.1 执行记录」；N1.1 索引补 13；新增 N11 | R13 分工 |
| `CHANGELOG.md` | 规则版本 1.6（新增 R14，判据未变）；产品版本不动 | 版本轴分离 |

**冲突登记（按要求只记录、不改变语义）**：`specs/001/tasks.md` 原第 3 行自称「单一事实来源」，
与 `AGENTS.md` R13（`STATUS.md` 是接续点）并存，且该文件 48/48 全勾完、无法表达 v0.2。

- 采用：`STATUS.md` 为当前状态唯一位置；tasks.md 冻结为 v0.1 执行记录（原文以删除线保留，不删）。
  依据：用户本轮明确要求「当前任务状态集中维护」，且 R13 已指定接续点。
- 未采用：把 tasks.md 扩成 v0.2+ 并继续当唯一来源。代价：要给每个新任务补 `[ ]` 与证据行，
  与「少 feature 少文档」相悖，且它无法表达「这一轮只是文档校正」这类不占版本号的工作。

**未改**：`bench/`（冻结件与数据）、`tests/`（无代码变化）、`release/`（对外接口未变）、
`references/00`–`10`、`12` 的正文（设计记录/历史报告，不追新；11 只改了 §10 的指路口径）。

---

## 8 演练：一次小任务完成后该更新哪些记录

**实做的小任务**（本轮真实发生）：新增 `references/13-maintenance.md` 后，根 README 的
「`references/` 00–12」与事实不符（实测 15 个 md）。

| 步骤 | 动作 | 命令/判据 |
|---|---|---|
| 触发 | 发现陈述与事实不符 | `ls references/*.md \| wc -l` → 15 |
| 写值处 | 只改 `README.md` 两行（:128 结构行、:135 段落） | 同行替换，不动行数（根 README 的入站 `:NNN` 引用实测 1 处；`references/00` 才有 97 处） |
| 记录 | `STATUS.md` N11 记一条六字段 | 见 §4 模板 |
| 规则文档 | 本文 §7 记一笔（谁改了什么、依据） | — |
| **不更新** | `CHANGELOG.md`（非版本变化）、`tests/*`（无测试变化）、`bench/*`（冻结件）、`specs/*`（历史）、`release/*`（接口未变） | 按 §3 判据：这些文档描述的事实没变 |
| 核验 | 引用副本只有一处 | `grep -rn "00–12" --include=*.md .`（应只剩历史文件里的过去时记录） |

**一句话**：这类小任务只需要动 **3 处**（值 1 处 + 状态记录 1 处 + 本文 1 处），不是 8 类文档全改。

对照（**未执行**，只给判据）：修 P-01 会动 `scripts/batch.py` + `tests/contract/test_batch_e2e.py`
（或新增单测）+ `STATUS.md` N4/N11 + 发布后的 `CHANGELOG` 产品版本；**不动** `release/SKILL.md`
（接口与退出码未变）、`bench/*`（数据未变）、`references/12-bench-report.md`（历史结论不改写）。

---

## 9 迁移与引用纪律（保留历史）

1. **迁移不删要求**：内容换位置时，原句以删除线或「原…」保留，附日期 + 原因 + 指向新位置。
   2026-10-29 对 `specs/001/tasks.md` 头注释就是这么处理的（§7）。
2. **旧记录保持过去时**：`12-bench-report.md` 里的失败、`10-gap-register.md` §0.1 的「实跑前/后」两列，
   都是历史证据，不因今天重跑通过而改写。
3. **引用优先 `path §章节`**；必须写 `:NNN` 时，同一句要给出被引内容（N8 第 1 条）。插入行会静默移动
   下游 `:NNN`，而门禁只判越界、不判语义漂移（`G-DOC-1` / E2 都是边界检查）。
4. **改被引用文件前先列引用者**：`grep -rn "<文件名>:[0-9]" --include=*.md .`；能同行替换就不插行。
   本轮对 `AGENTS.md` 的处理是**在 R13 之后、`附` 之前插入**：`AGENTS.md:NN` 的 17 处引用最大指向
   257 行（R12 段），插入点在其后，故零位移；改后逐条复核引用目标内容。
5. **改完必须跑该文档对应的检查器**（§5 表），并在状态记录里写「未验证项」——尤其是导出树这类
   依赖提交的动作。
