# 九、轻量化架构与测试设计（2026-10-28）

> 定位：把 `references/08-condensed-report.md` 的结论落成**可实施的模块划分 + 可判定的测试设计**。
> **与 08 的区别**：08 只压缩已有事实、不产生新判断；本文件**产生设计决策**（模块边界、接口、
> 测试判据、三项用户裁定）。凡引用既有事实处一律带 `path:line`；凡属本文件的设计判断，标「设计决策」。
> 依据顺序：`08`（结论）→ 本文件（设计）→ `bench/preregistration.md`（判据口径，已冻结 v1.0）。
> 第三方代码引用一律 `references/repos/<repo>/<file>:<line>`（R9）。

## 0 用户裁定（2026-10-28，本文件的生效前提）

| # | 裁定 | 落成什么 | 生效条件 |
|---|---|---|---|
| D1 | **G5 范围门进模块契约** | 门禁模块判 G1–G5；退出码扩到 `0–5` | 需同步改两处：退出码表、对 `verify_case.sh` 的描述（原写 G1–G4）。**已完成 2026-10-28**（P3）：现值 `references/00-project-readme.md:231`（退出码含 `5`）、`references/00-project-readme.md:272`（两阶段描述） |
| D2 | **`human_interventions` 口径 = (ii)**：算「替它改字典」+「它停下来问我、我答一句」；不算「重启整轮」 | 模块 F 的测试可以量化「修复需要人帮几次」 | 须写入预注册末尾（见附录 A）。该处不在被哈希的切片内：`bench/freeze_digest.py:28` 的 `SLICES` 只覆盖 §1–§10 / §13–§14 / 冻结记录–变更规则，实测指纹 `1bc8a4008c8a01da…`；正文 §15（`bench/preregistration.md:551`）自身已注明「不在被冻结的章节内」，故追加 §16 **不改指纹、不开新一轮** |
| D3 | **L1/L2 测试放 `tests/`**，不进 `bench/` | `tests/unit/` + `tests/contract/` | `bench/` 受「设计期禁跑」约束（R12），塞进去会让该判定变糊；`references/00-project-readme.md:272` 已明令不建 `docs/`，故本文件放在 `references/` |

**第二批裁定（同日，回答「架构定没定」后拍板）**：

| # | 裁定 | 落成什么 | 连带动作 |
|---|---|---|---|
| D4 | **G1+G5 前置、G2–G4 后置**（项 0 选 C） | E 有 `--stage pre` 与 `--stage post` 两个入口；G1/G5 不跑 OpenFOAM | §1.2 数据流重画；§2 E 契约重写；judge 增加**短路语义**（M-d）；`06:254` 的原始数据流得到遵守 |
| D5 | **6 部件 = 6 文件 + 契约层**（项 1 选 A） | 见 §1 表 | A 的产物必须落盘为 `cases/<id>/spec.json`，否则违反 §1.1 的载体约束 |
| D6 | **退出码 `0–5`，只报第一个失败的门**（项 2 选 A） | `verify_case.sh` 的返回码 | 退出码表加一个 `5`（现 `references/00-project-readme.md:231`）；judge **不读**总退出码，故不受影响 |
| D7 | **`log.gN` = `RC=` 首行 + `G2B=` 次行**（项 3 选 A） | §2 E 的接口段 | `bench/judge.py` 补 g2b 解析（闭合问题 3）；加变异体 J-M7 |
| D8 | **E-lite 先行**（项 4 选 B） | §7 实施顺序重画 | P2 延后到 E-full 之前，不再是「全项目第一步」 |
| D9 | **四元组的字段名与取值域按 `06` 的接口契约**（不是本文件上一版写的） | 第二键 `material` → **`properties`**；`objective` 限定枚举 **`steady` / `transient`** | 见 §2 A 契约。**这一条是纠错**：上一版本文件擅自改了 `06` 的字段定义且未登记，由子代理 A 上报、编排方核实后推翻自己的规格 |
| D10 | **`find_template.sh` 的 `FOUND` 是命中总数，不是输出行数** | 末两行 `FOUND=<总数>` / `SHOWN=<输出行数>`；`--limit` 只改后者 | 规格原文「n = 命中文件数」；首版实现成输出行数，`--limit 3` 时报 `FOUND=3` 而实际 28 个 |
| D11 | **C 用 `cp -a` 派生，不用 `foamCloneCase`** | `new_case.sh` 的复制方式 | **纠错**。本文件上一版写 `foamCloneCase`，实测该脚本有三处隐式行为使 C1 判据无法写成静态规则：①复制集合依赖源内容（只挑 `file` 认得的 shell 脚本，`foamCloneCase:259`–`264`），②对时间目录删 `phi`/`Uf`/`uniform`（`foamCloneCase:80`），③**目标目录已存在直接 error 退出**（`foamCloneCase:215`）——与 C4「同四元组生成两次」直接冲突。R3 明文允许「`foamCloneCase` 或 `cp -r`」（`references/00-project-readme.md:108`），故改走后者 |
| D12 | **D 的日志按 `--mode` 分级产出，不是恒定三件套** | `check`→只有 `log.checkMesh`；`short`→+`log.shortRun`；`full`→三件套 | 本文件上一版的 D2 判据写「三件套都存在」，但 `mode=check` 只跑 `checkMesh`，该判据在 check 模式下必然假红 |
| D13 | **D 的环境探测必须主动，不靠子进程退出码** | 入口先 `command -v foamRun`，失败即退 22；`timeout` 的 124 映射为 21 | 实测：真空环境（`env -i PATH=/usr/bin:/bin`）下 `foamRun` 退出 **127**，与「求解失败」无法区分；而 `command -v` 退出 1 可判定。`timeout 3` 实测退出 **124** |
| D14 | **C 的测试从 L2 改到 L1** | 7 项全放 `tests/unit/`，用伪 tutorial 树 + `FOAM_TUTORIALS` 指过去 | C 只做 `cp -a` + 写 JSON，**一条 OpenFOAM 命令都不调**。上一版排 L2 是照抄「涉及 case 就要 OpenFOAM」的直觉；实测该直觉不成立 |
| D15 | **D3 的「怎么让它超时」不能用 `endTime`** | 用 `nOuterCorrectors` 调大让每步本身变慢（实测 27.1 s / 40000 次 PIMPLE 迭代），`--timeout 3` → 21 | **纠错**。§4-D 的 D3 原写「`endTime=1e9` + `--timeout 3`」，但 short 模式本身就把 `endTime` 改写为 `deltaT*2`，改 `endTime` 对短跑时长**无影响**（实测 2 步 0.1 s）。这是本文件的自相矛盾 |
| D16 | **`full` = 先短跑、再恢复 `endTime` 满跑**（不是「不改 endTime」） | 产出 `log.checkMesh`+`log.shortRun`+`log.run`，跑完把 `endTime`/`writeInterval` 恢复到原值 | §4-D 表里 `full` 行写「同上但不改 endTime」，与 §2-D 契约的「先短跑再恢复」矛盾。取契约版：三件套里 `log.shortRun` 是给 G3 的、`log.run` 是给 G4 的，缺一条就有一个门没输入 |
| D17 | **用法错误统一退 `64`**（全部脚本），不用 `2` | A/B/C/D 的用法错误从 `2` 改为 `64`；E 本来就是 `64` | **纠错**。`2` 在 `verify_case.sh` 里是「G2 网格门失败」（D6 的 `0–5`），用法错误也用 `2` 会让调用方无法区分「我参数写错」与「算例网格没过」——两者处置相反。`64`（`EX_USAGE`）不落在任何模块的业务码内（`0–5`/`10–11`/`12–13`/`20–23`）。由 `tests/unit/test_exit_codes.py` 守 |
| D18 | **G2 只能 grep `Mesh OK.`，绝不能看 `checkMesh` 退出码** | E-full 的 G2 判据；并作为一条 E-full 测试 | 实测：`checkMesh` 在 `Failed 1 mesh checks.`、且不打印 `Mesh OK.` 时**退出码仍是 0**。源码：`$FOAM_SRC/functionObjects/utilities/checkMesh/checkMesh.C:180` 的 `return nFailedChecks == 0` 是**函数对象 `execute()` 的返回值**，不是进程退出码，可执行文件没把它变成 `exit()`。同一文件 `:160`–`163` 才是 `Mesh OK.` 的打印条件（`nFailedChecks == 0`）。若有人把 G2 改成看退出码，**所有不合格网格都会放行** |
| D19 | **`g2b=soft` 是防御性分支，v13 下不可达** | judge / E-full 仍实现四种取值，但不为 `soft` 造"真实样例" | 两条证据：①那 4 项豁免检查不打印 `***`（`checkGeometry.C:902/924/950/978` 各块内 `***` 数=0；全 `meshCheck` 被注释的失败计数仅这 4 处）；②扫描 **208** 个自带 `blockMeshDict` 的 tutorial，`Mesh OK.` 与 `***` 共存 **0 例**（none=182 / hard=8 / 网格未建成=18）。**判据不删**（删了会在真出现时被误记 `malformed`），但不为它编造样例 |
| D20 | **`case.meta` 有两处合法位置；两处都有 → `malformed`** | C 的 `--dest` 是 case 树，meta 写在树内（case 自描述、可单搬）；prereg §12 把它列在 run 根。E-pre 与 judge 都认两处；**同时存在判二义**（不许静默选边） | 集成测试抓到的错位：judge 只读 `run/case.meta`，而 C 写 `run/case/case.meta` → 链上判 `malformed`。另修了一个真 bug：**完全没有 `case.meta` 时 judge 曾判 `pass`**（`meta_raw is None` 时 `meta_missing_source` 保持 False）。R3 要求每个 case 声明 source，判 pass 等于替它担保没说过的来源 |
| D21 | **D 与 E 都接受 `--log <dir>`，缺省 = `--case`** | 三脚本用同一个 `--log` 就能把日志放到 prereg §12 的 run 根 | 原实现：E-pre 忽略 `--log`（写死到 case）、D 写死到 case，于是 judge 读 `run/log.gN` 永远读空 |
| D22 | **F 只改字典，不重跑求解** | F 的输出是 `{changes, written, backup_dir, declined, reason}`，**不含** `log.shortRun`；调用方改完回 E(pre) → 由 D 重跑 | **纠错**。本文件 §2-F 原写「输出 … + 新的 `log.shortRun`」，与 §1.2 数据流的「F → 回 E(pre)（先复查结构，再重跑 D）」矛盾。以 §1.2 为准 |
| D23 | **F 定位不到就 `declined`，不许猜** | 无 `file:` 行的 FATAL（实测 `solvers table is empty`）→ `declined=true`、`changes=[]` | 硬编码猜一个文件名 = 编造（R1）。可判定：declined 时 `changes` 必须为空且 `reason` 非空 |
| D24 | **F 只自动应用「标量 set」；结构修复一律 `declined`** | `Cannot find patchField entry for X`（要加 dict 块）、`Cannot find file "..."`（缺整个文件）→ declined + 定位信息 | `{file, entry, new_value}` 表达不了结构修改；硬套会写坏字典 |
| D25 | **指纹 = `sha256(错误特征串 + "\n" + "file:entry")[:16]`**，其中**错误特征串 = `-->` 之后的前 5 个非空行**（跳过样板与分隔线，压掉连续空白）。落盘 `<run>/attempt_<n>/fingerprint.txt`；locate 模式另记 `<run>/fingerprints.txt` 台账，去重时两处都扫 | 跨 attempt 比对靠扫上述两处 | **2026-10-28 修订**。原文写「FATAL 首行」，但 OpenFOAM 的首行几乎恒为 `--> FOAM FATAL ERROR:` / `... IO ERROR:`，而定位不到时 `file:entry` 为空 → **所有不可定位的错误塌缩成同一指纹**（实测 `solvers table is empty` 与 `cannot find file "..."` 都是 `b10e79556e8a0b5d`）。塌缩后去重守卫把「另一个错误」当成「同一个」拒绝重试，作用与设计相反 |
| D26 | **不建 `tests/contract/test_mutants.py`**；各模块的变异验证保持**就地**（改→红→还原→绿→`diff`） | 删除 §5 与附录 B 对该文件的引用 | 该文件从未存在（`ls` → No such file），却被两处引用并声称「期望 6 passed」；四个模块已各自就地做过变异验证，集中式文件是重复劳动 |

## 1 架构：6 个部件 + 1 个契约层

模块划分直接继承 `08 §2.2` 的 6 部件，不重划——重划会让 08 的锚点失去意义。唯一新增的是契约层 G：
它不是部件，是模块之间唯一的通信面，没有它六个部件的接口不成立。

| # | 模块 | 判定归属 | 输入 → 输出 | 落盘文件 | 是新建还是已有 |
|---|---|---|---|---|---|
| A | 需求→四元组解析 | 模型+脚本校验 | 原话 → `spec.json`（四元组 + `complete` + `missing`） | `scripts/parse_requirement.py`；产物落 `cases/<id>/spec.json` | 新建 |
| B | 知识检索 | **脚本** | 关键词 + 固定搜索根 → `path:line` 列表 | `scripts/find_template.sh` | 新建 |
| C | case 生成 | 模型+脚本校验 | 派生源 + 四元组 → `cases/<id>/` 树 + `case.meta` | `scripts/new_case.sh` | **已实现**（`scripts/new_case.sh`，7 项 L1；README 目录图见 `references/00-project-readme.md:299`） |
| D | 求解执行 | **脚本** | case + 步数 → `log.*` + returncode | `scripts/run_case.sh` | 新建 |
| E | 门禁判定 | **脚本（纯函数）** | ①`--stage pre`：case → G1/G5；②`--stage post`：case+日志 → G2–G4/G2b；合计退出码 `0–5` | `scripts/verify_case.sh` + `bench/judge.py` | **已实现（E-lite 部分）**（`references/00-project-readme.md:272`）；`judge.py` 见 `bench/preregistration.md:354` |
| F | 失败反馈与修复 | 模型+脚本校验 | 失败串 + attempt → 改哪个文件哪个 entry + 备份 | `scripts/fix_case.py` | 新建 |
| G | 契约层 | 脚本 | — | `case.meta` 的 schema + `bench/results.csv` 的固定列 | 部分已有 |

**为什么 C/E 必须沿用已有文件名**：README 目录图（现 `references/00-project-readme.md:299`–`300`）已经把 `new_case.sh` / `verify_case.sh`
写进目录布局，改名会让所有既有文档的锚点失效（这正是 `STATUS.md` N8-1 记的那类事故：
「引用要带行号+值，只写行号的上游值一改就静默过期」）。

### 1.1 模块间只走三种载体

文件树、固定名日志、退出码（`08 §2.4` 零服务）。**没有** RPC、没有消息队列、没有共享内存、
没有 MCP（`references/00-project-readme.md:120` 已否决）。

**每一类跨界传递必须落到这三种之一，不许只存在于内存里**（D5 的连带修正；上一版本条与实际
接口矛盾——A 的 stdout JSON 与 C 的 argv 都不在这三种之内）：

| 跨界传递 | 载体 | 具体位置 |
|---|---|---|
| A → B / A → C 的四元组 | 文件树 | `cases/<id>/spec.json`（不是 stdout 独享；stdout 只是同内容的回显） |
| A → B 的 grep 关键词 | argv（一次进程调用） | `find_template.sh --keyword "..."`；**不入文件**，因为是纯函数入参，无复用价值 |
| B → 调用方（模型/人）的命中 | **stdout**（一次进程调用） | `find_template.sh` 输出每行 `相对路径:行号` + 末两行 `FOUND=`/`SHOWN=`。**不落盘、没有 `sources.txt`** |
| 调用方 → C 的派生源 | argv | `new_case.sh --source <tutorial 相对路径>`；由模型/人从 B 的命中里**选定一个目录**后传入 |
| C → E(pre) 的产物 | 文件树 | `cases/<id>/` 整棵树 + `case.meta` |
| C → E(pre) 的允许改动范围 | 文件树 | `case.meta.allowed_files` |
| D → E(post) 的执行结果 | 固定名日志 | `log.checkMesh` / `log.shortRun` |
| E → 调用方 / judge | 固定名日志 + 退出码 | `log.g1`…`log.g5`（`RC=` 首行）+ 进程退出码 |
| E(post) → F 的失败串 | 固定名日志 | `log.gN` 第 3 行起 |
| F → C 的改动 | 文件树 | 直接改字典 + `attempt_<n>/` 备份 |

argv 只允许承载**纯函数入参**（关键词、路径、模式串），不允许承载需要被后续模块复用的产物——
否则会出现「同一份四元组在两个地方各有一份、改了一处忘了另一处」。

这条约束的收益是测试上的：每个模块都能被单独扔进一个临时目录测，不需要起服务、不需要 mock 网络。
如果某个模块的测试必须起进程间通信才能跑，说明架构已经偏了。

### 1.2 数据流（D4 = G1/G5 前置）

```
用户原话
  └─A→ cases/<id>/spec.json（四元组 + complete + missing[]）
        │                     complete=false → 退出 10，交人（不许填默认值）
        └─B→ stdout（path:line + FOUND/SHOWN；命中为空 → 退出 11，不许凭印象补）
              │   ↑ 模型/人从这里**选定一个 tutorial 目录**，不是自动传递
              ▼
              └─C→ cases/<id>/ 文件树 + case.meta（source / spec / changes / allowed_files）
                    │
                    ├─E(pre)  G1 结构 + G5 范围      ← 纯文件检查，不跑任何 OpenFOAM
                    │   ├─不过 → 退 1 或 5 → 回 C（改字典；**不跑求解**，省掉一次白跑）
                    │   └─过 ──┐
                    ▼         ▼
                    D  blockMesh → checkMesh → foamRun(2–3 步)
                       → log.checkMesh / log.shortRun
                          └─E(post)  G2 网格 / G3 短跑 / G4 产物 + G2b 诊断
                              ├─全过 → 交付（+ log.g1..g5 供 judge 归约）
                              └─不过 → F → 定位 {file, entry} → 改字典 + attempt_<n>/ 备份
                                        → 回 E(pre)（先复查结构，再重跑 D）
                                        （attempt >= max_attempts → 终止，交回用户）
```

**与 `06:254` 原始数据流的关系**：`06:254` 写的是
`[1] → [2]/[3] → [5 G1] → [4] → [5 G2-G4] → …`，即 G1 在求解之前、G2–G4 在求解之后。
上一版本文件把 G1–G5 全放在求解之后，与它不一致（问题 1）。D4 恢复原样，并把**同属纯文件检查的
G5 也一并前置**——`bench/preregistration.md:85` 与 `:89` 的判据列显示：G1 只需
`test -f` + `ls`，G5 只需 `git diff --no-index` 或 mtime 比对，两者都不需要 OpenFOAM。

**短路是合法状态，不是缺数据**（见 §10.1 的 M-d）：G1 或 G5 不过时 G2–G4 根本不会被写。
judge 必须能区分「短路导致的门缺失」与「闸门跑了但没留下结论」。

## 2 模块契约

每个模块的契约只写四件事：**输入类型、输出类型、失败语义、产物路径**。写不清的先不写代码。

### A `scripts/parse_requirement.py`

- 输入：`--text "<原话>" [--out cases/<id>/spec.json]`（argv）
- 输出：①写 `--out` 指定的文件（D5 要求落盘，stdout 只作同内容回显）；②stdout 一行 JSON，字段固定
  `{"geometry": str|null, "properties": str|null, "boundary": str|null, "objective": "steady"|"transient"|null, "complete": bool, "missing": [str]}`
- **字段名与取值域以 `references/06-agent-anatomy.md:57`–`58` 的接口契约为准**（D9）：
  第二键是 `properties` 不是 `material`；`objective` 只取 `steady` / `transient` 两个值。
- `objective` 是**枚举校验**：给了值但不在 `{steady, transient}` 内（例如「层流」）→ 视为没给，
  该键记 `null` 且进 `missing`。理由：不可判定的取值等于没答这个问题，而「不许填默认值」要求
  我们停下问人，不是猜一个。
- 落盘时机：`complete=true` 才写文件；`complete=false` 时**不写**（避免下游误读半成品）
- 失败语义：任一键为空 → `complete=false` 且 `missing` 列出缺的键；**不填默认值**
  （原句在 `references/06-agent-anatomy.md:59`：「四个键任一为空即 `raise RequirementIncomplete`，
  **不许填默认值**——默认值会把『需求没被满足』转成『门全过』」）
- 退出码：`complete=true` → 0；`complete=false` → 10（缺需求，交人，不是错误）
- 不许做的事：不许替用户决定 `objective`；缺几何/物性/边界时停下问人（`AGENTS.md:194`）

### B `scripts/find_template.sh`

- 输入：`--keyword "<词>" [--limit N]`
- 输出：每行一个 `相对路径:行号`，按路径排序；末两行
  `FOUND=<命中总数>` 与 `SHOWN=<实际输出行数>`
- **`FOUND` 不受 `--limit` 影响**（D10）：规格原文是「n = 命中文件数」，首版实现成了
  「输出行数」，于是 `--limit 3` 时报 `FOUND=3` 而实际有 28 个候选——下游选派生源时会误判
  「库里只有 3 个」。`SHOWN` 单独给，两者差就是被截断的条数。
- 搜索根**只有五个**：`$FOAM_TUTORIALS` `$FOAM_SRC` `$FOAM_APP` `$FOAM_ETC` `$FOAM_UTILITIES`（R1）
- 失败语义：命中为空时输出 `FOUND=0` 并退出 11；**禁止**回退到任何记忆、默认值或别的目录
- 确定性要求：同一输入连续两次输出必须逐字相同（反例：`references/repos/cfd-agent/src/database.py:217`
  用 `random.sample` 截断，同一查询两次给不同参考，可复算性被自己毁掉）

### C `scripts/new_case.sh`

- 输入：`--source <tutorial 相对路径或绝对路径> --dest <目录> --spec <四元组 json 文件>`
- 输出：`<dest>/` 文件树 + `<dest>/case.meta`
- 派生方式：**`cp -a`**（D11）。R3/`references/00-project-readme.md:108` 允许「`foamCloneCase` / `cp -r`」两种；
  **不许**从空目录写字典（`references/00-project-readme.md:79` 的 P2「一切 case 从最近的 tutorial 派生，不凭空生成」）
- **B 与 C 之间没有自动传递**：B 的输出是 `path:line` 的**源码坐标**（给模型/人看候选），
  不是 tutorial 目录，也**不落盘**（没有 `sources.txt` 这个东西——上一版本文件的 §1.1/§1.2
  描述过它，实测两个脚本都不碰）。调用方从候选里选定一个目录，作为 `--source` 传给 C。
  硬把二者连起来会把源码路径当成 case 树。
- `source` 校验三条（任一不过 → 退出 12，**不产出任何目录**）：
  ① 目录存在；② 在 `$FOAM_TUTORIALS` 下（R3：只允许从 tutorial 派生）；③ 含 `system/controlDict`
- `case.meta` 必须含**六键**：`source`（相对 `$FOAM_TUTORIALS` 的路径，必须真实存在）、`derived_at`、
  `spec`（四元组原文，D5）、`changes`（改动清单，初始为空数组）、`allowed_files`（G5 的白名单）、
  `schema_version`（常量 `1`，供 G 契约层校验）
- 失败语义：`--dest` 已存在 → 退出 13（**不覆盖**，由调用方决定要不要先删）。这条来自 D11 的实测：
  `foamCloneCase:173` 的行为就是拒绝覆盖，我们把它显式化为一个可判定的退出码
- 成功语义：写完 `case.meta` 才算成功（没有 `case.meta` 的目录不算 case）

### D `scripts/run_case.sh`

- 输入：`--case <dir> --mode check|short|full [--timeout S]`
- 输出（**按 mode 分级**，D12）：

  | mode | 执行的步骤 | 产出的日志 |
  |---|---|---|
  | `check` | 无网格时 `blockMesh`，然后 `checkMesh` | `log.checkMesh` |
  | `short` | 同上 + `endTime` 改小后 `foamRun` | `+ log.shortRun` |
  | `full` | 同上 + 短跑写 `log.shortRun`，**再恢复原 `endTime`/`writeInterval`** 满跑写 `log.run` | 三件套：`log.checkMesh` / `log.shortRun` / `log.run` |

- **`full` 的恢复是硬要求（D16）**：短跑改小过 `endTime`/`writeInterval`，满跑前必须恢复，
  跑完也不许留下被改小的值——否则这个 case 之后被 G4 用时表现为「算例算不完」，而错误早就发生了。
- **网格准备**：`constant/polyMesh` 不存在且有 `system/blockMeshDict` → 先跑 `blockMesh`（R5 只许
  blockMesh 或导入外部网格）。两者都没有 → 退出 23（不是 20：这不是求解失败，是没有网格可跑）
- 退出码约定：`0` 正常 / `20` 求解失败（子进程非 0）/ `21` 超时 / `22` 环境缺失 / `23` 无可用网格
- **环境探测必须主动**（D13）：入口先 `command -v foamRun`，失败即退 `22` 并在 stderr 写
  `OpenFOAM 环境未加载`。**不要**靠子进程退出码兜底——实测真空环境下 `foamRun` 退 `127`，
  与「求解失败」同形，分不出来。反例见 `references/05-cross-project-matrix.md:131`
  （`openfoam-mcp-server` 默认 solver 写死 `simpleFoam`，v13 无此可执行 → 恒 127，
  把「环境错」记成了「求解失败」）
- **超时映射**：`timeout` 命令退出 `124` → 我们的 `21`。实测 `timeout 3 foamRun` 退 `124`
- **写日志的硬要求**：`foamDictionary` 的字典文件是**位置参数**，`-case` 只指定目录。用它改
  `endTime` 必须写 `foamDictionary system/controlDict -case <dir> -entry endTime -set <v>`。
  省掉文件时它会打印 Usage 并在 stderr 报 `FOAM FATAL ERROR: Wrong number of arguments`、
  **退 1**（实测，可以靠退出码发现）。**但真正需要回读校验的是另一件事**：`-set` 对
  **不存在的 entry 会新增并退 0**——拼错键名不会失败，只会悄悄多出一个键。
  所以「改完必须回读」的理由是**防静默新增**，不是防静默失败（原文档写错了，见 §10.8）

### E `scripts/verify_case.sh` + `bench/judge.py`

分两层，别混：`verify_case.sh` 判单个 case 的门；`judge.py` 把多次重复归约成七态。

**E 有两个入口（D4）**：

| 调用 | 判什么 | 需要 OpenFOAM | 写哪些日志 | 可能返回 |
|---|---|---|---|---|
| `verify_case.sh --stage pre --case <dir>` | G1 结构 + G5 范围 | **不需要** | `log.g1`、`log.g5` | `0` / `1` / `5`；用法错误 `64` |
| `verify_case.sh --stage post --case <dir> --log <dir>` | G2 网格 + G3 短跑 + G4 产物（+ G2b 诊断） | 需要（日志由 D 产生，本命令只解析） | `log.g2`、`log.g3`、`log.g4` | `0` / `2` / `3` / `4`；用法错误 `64` |

`--stage pre` 未传 `--allowed` 时，从 `case.meta.allowed_files` 读允许改动范围（契约层 G）。

**`log.gN` 的格式（D7，与 `bench/judge.py` 的唯一接口）**：

```
第 1 行   RC=0                     # 0 = 本门通过，1 = 未通过。缺失或空文件 = 不可判定
第 2 行   G2B=soft:2               # 仅 log.g2 需要；取值 none | soft:N | hard:N | unknown
第 3 行起 自由文本，写失败串        # judge 不解析，供人看
```

**退出码（D6）**：`0` 全过 / `1` G1 / `2` G2 / `3` G3 / `4` G4 / `5` G5；**只报第一个失败的门**
（按门号顺序取最小）。前四码沿用 `references/00-project-readme.md:231`，第五码是 D1 的后果。

**`judge.py`**：对一次 run 的**三次重复**做七态归约，输出 `bench/results.csv` 一行
（规格见 `bench/preregistration.md:354`–`378`）。它**不读进程退出码**，只读
`log.g1`…`log.g5` 的 `RC=` 行、`log.g2` 的 `G2B=` 行、以及 `assert.json`。

门判据（逐字来自 `bench/preregistration.md:85`–`89`，勿改写）：

| 门 | 判据 | 备注 |
|---|---|---|
| G1 | `system/{controlDict,fvSchemes,fvSolution}` 存在；`0/` 非空；`constant/` 有对应物理字典 | 增补：`0/U`、`0/p` 的 patch 集合 == `constant/polyMesh/boundary` 的 patch 集合（`references/01-landscape.md:170`） |
| G2 | `checkMesh` 输出含 `Mesh OK.` | |
| G3 | 缩到 2–3 步，退出码 0，日志无 `FOAM FATAL` | 增补：日志版本行 == 13（`references/01-landscape.md:170`） |
| G4 | 末时刻存在；场可读；无 `nan`/`inf` | 增补：场值有限 + 一个与物理量级挂钩的上限 |
| G5 | 只允许改动 `allowed_files` 内；改 `constant/polyMesh/` 需在 `case.meta` 写理由 | `bench/preregistration.md:89` |
| G2b | **不是门**：数 `***` 行 → `none`/`soft:N`/`hard:N`/`unknown` | 不进 status（`bench/preregistration.md:90`、`:92`） |

### F `scripts/fix_case.py`

**两种互斥模式**（D22/D23/D24 之后）：

| 模式 | CLI | 做什么 | 写盘？ |
|---|---|---|---|
| locate | `--case <c> --error-log <file> --attempt N --max-attempts M` | 读失败日志，用正则表定位到 `{file, entry}` 或 `declined` | **否**（`new_value` 未知，只报位置） |
| apply | `--case <c> --apply '<json>' --attempt N --max-attempts M` | 校验 → 备份 → 写回 → 回读 | 是 |

- **参数名是 `--error-log`（日志文件）不是 `--log`（日志目录）**：项目其余脚本的 `--log` 指目录，
  这里要的是文件，重名会造成误用。
- 输出：stdout 一行 JSON
  `{changes, written, backup_dir, declined, reason, fingerprint}`。
  **不含 `log.shortRun`**（D22：F 不重跑，重跑是 D 的事，调用方改完回 E(pre)）。
- 定位规则表**只覆盖 4 条**，全部由实测得出（见 §10.7）。
  定位不到 → `declined=true` 且 `changes=[]`（D23：不许猜）。
  结构修复（加 dict 块 / 缺整个文件）→ `declined`（D24：`{file, entry, new_value}` 表达不了）。
- 备份：写回前整目录备份到 `<case 的父目录>/attempt_<n>/`；`attempt > max-attempts` 返回 `31`，不许重试
  （`references/06-agent-anatomy.md:149`–`150`）。
- **指纹去重**（D25）：指纹 = `sha256(FATAL 首行 + "\n" + "file:entry")[:16]`，落盘
  `<run>/attempt_<n>/fingerprint.txt`；跨 attempt 比对靠扫 `attempt_*/fingerprint.txt`，
  命中相同指纹 → 退 `32` 且**不建**新的 `attempt_N/`。
- **entry 必须在 file 里恰好命中 1 次**（`references/06-agent-anatomy.md:150`）：
  写前自己数，0 次或 ≥2 次 → 退 `33`，字典文件字节不变。
- 退出码：`0` 正常（含 declined）/ `31` 达到上限 / `32` 指纹重复 / `33` entry 不唯一 / `64` 用法错误。
- **指纹守卫必须有**：同一错误指纹重复出现即终止。反例：`metaopenfoam` 无指纹去重，
  同一错误会烧到 `max_loop=20`（`references/repos/metaopenfoam/src/actions/ReviewerAction.py:456`）；
  `foam-agent` 有守卫，把 25 轮压到 2 轮（`references/repos/foam-agent/src/nodes/reviewer_node.py:23`）

### G 契约层

- 产物：`scripts/check_contracts.py`，两个子命令 `--results <csv>` / `--case-meta <json> [--tutorials <dir>]`；
  退出码 `0` 合规 / `40` 违规 / `64` 用法错误。
  **写成脚本而不是测试辅助**：M2 的 `batch.py` 与 M4b 的 adapter 要复用它。
- `case.meta` schema：**六键**固定（与 §2-C 一致，不是上一版写的四键）：
  `source` / `derived_at` / `spec` / `changes` / `allowed_files` / `schema_version`
  - `source` 非空 str；`derived_at` 可被 `datetime.fromisoformat` 解析；`spec` 是 dict；
    `changes` 是 list；`allowed_files` 非空 list[str]；`schema_version == 1`（**int**，`"1"` 违规）
- `bench/results.csv` 表头**逐字固定**，共 **15 列**：
  `task_id,arm,status,g1,g2,g3,g4,g5,g2b,repeats,unstable,tokens_total,wall_time_s,human_interventions,note`
  （与 `bench/results.csv` 第 1 行逐字一致；`bench/preregistration.md:388`–`389`）
- `status` 取值集合 ⊆ 七态：`pass | fail | no_artifact | malformed | blocked | overclaim | declined`
  （`AGENTS.md:257`）。**常量必须从 `bench/judge.py` 的 `STATES` 导入，不许重写一份**（DRY）
- `g1..g5` 取值 ⊆ `{0,1,unmeasured}`；`human_interventions` 未测时必须是字符串 `unmeasured`
- 判定优先级：`blocked > declined > no_artifact > malformed > overclaim > pass/fail`
  （`bench/preregistration.md:73`）

## 3 测试分层

| 层 | 目录 | OpenFOAM | LLM | 覆盖 | 单次耗时目标 |
|---|---|---|---|---|---|
| L1 | `tests/unit/` | 不需要 | 不需要 | A 的 schema 校验、**E-lite（G1+G5）正反**、G 的列定义 | < 5 秒 |
| L2 | `tests/contract/` | 需要 | 不需要 | B、C、D、**E-full（G2–G4+G2b）正反** | < 120 秒 |
| L3 | `tests/integration/` | 需要 | 需要 | A→C→D→E→F 全链，1 例 × 3 次 | 按需 |
| L4 | `bench/tasks/` 的跑批 | 需要 | 需要 | 12 个任务 × 3 次 | 按批次 |

**硬约束：L1 + L2 必须能在没有 LLM key 的机器上全绿。** 做不到就是模块耦合错了——
某个本该纯脚本的模块偷偷依赖了模型输出。

### 3.1 三条方法论（不是风格，是已付出的代价）

1. **先写「怎样算通过」再写实现**（`references/07-theory-provenance.md:285`）。每个测试文件第一段必须是判定句。
2. **每个判据要证明「会红」**：把 `check()` 改成恒返回 0，测试必须失败（`bench/preregistration.md:483` 的 §14 标题即「冻结前后各跑一轮，证明门禁真的咬人」）。
3. **两个方向都测**：合法输入通过（假阳）+ 非法输入被拦（假阴）。`08 §3.3` 第 5 行的视觉闸就是
   只测了一个方向，判据写成 `"correct" in response.lower()` 而 `"incorrect"` 含 `"correct"`，
   在最该报警的回答形态下判 PASSED。

### 3.2 测试计数基线

写代码前先定，改动需写理由（避免「测试数目随实现漂移」）：

**重算说明（D4/D8 的后果，不是删测试）**：上一版把 E 记成「L1 13 + L2 12」。
D4 把 G1/G5 拆成 `--stage pre`（零 OpenFOAM → 进 L1）、G2–G4+G2b 留 `--stage post`（进 L2）后，
E 的 25 项按门重新分配：G1 2 项 + G5 4 项进 L1，G2/G3/G4 各 2 项 + G2b 1 项 + overclaim 1 项进 L2。
总数从 25 降到 17，差额全部来自「E7 的七态归约 12 项 + E8 优先级 1 项」——
那 13 项**本来就已在 `bench/selftest_judge.py` 里**（`checked=12` + `mapping_checked`），
由 `G-JUDGE-1` 守，不应该在 `tests/unit` 里再算一遍。这是去重，不是删测试。

| 模块 | L1 | L2 | 合计 |
|---|---|---|---|
| A | 16 | 0 | 16 |
| B | 0 | 6 | 6 |
| C | 7 | 0 | 7 |
| D | 0 | 7 | 7 |
| E-lite（G1+G5） | 8 | 0 | 8 |
| E-full（G2–G4+G2b+overclaim） | 0 | 9 | 9 |
| F（locate + apply 两层） | 0 | 8 | 8 |
| G（`check_contracts.py`） | 6 | 0 | 6 |
| **跨模块契约**（入口可执行 + 退出码 64） | 30 | 0 | 30 |
| **端到端集成**（A→C→E-pre→D→E-post→assert→judge） | 0 | 1 | 1 |
| **合计** | **67** | **31** | **98** |

**目标值与当前值的区别（2026-10-28 实测）**：

| | 目标（本表合计） | 当前已实现 | 差在哪 |
|---|---|---|---|
| L1 `tests/unit` | 67 | **67** ✅ | — |
| L2 `tests/contract` | 31 | **31** ✅ | F 的 8 项（含验收补的 F8） |

当前实测（2026-10-28 F+G 验收后）：`tests/unit` → `67 passed`；`tests/contract` → `31 passed`；合计 **98**。

**跨模块契约那一行会自己长**：`test_script_entrypoints.py` 按「类」遍历 `scripts/`，不列举文件名，
所以每新增一个带 shebang 的脚本就自动 +2 项（可执行位 + 能直接启动）。
本轮加 F/G 两个脚本后从 15 → **19**，正是设计意图（§10.3d 缺陷 1 的修法）。
**改基线时记得这一行是动态的**，不要按"上次的数字 + 新增测试"手算。
`bench/selftest_judge.py` → `checked=12 / majority=3 / mapping=3 / g2b=2 / meta=4` 全 0 failed。

**「跨模块契约」这 26 项不是某个模块的测试**，是两个横切不变量：
`test_script_entrypoints.py`（15 项：`scripts/` 下每个带 shebang 的文件必须可直接执行）
与 `test_exit_codes.py`（11 项：用法错误恒退 64 且写 stderr）。它们按**类**遍历而不是按文件列举，
所以新增脚本自动被覆盖，不需要记得加测试。

**跑测试必须用显式解释器**：`<装了 pytest 的解释器> -m pytest ...`。
PATH 上的 `python3` 可能指向**不同环境**（实测同一会话里换过一次，从系统 python 变成某个 venv），
候选里往往只有其中一个装了 pytest。用裸 `python3` 会得到
`No module named pytest`，看起来像「测试坏了」。选法：
`for py in $(which -a python3); do $py -c "import pytest" 2>&1 | head -1; done`。
另有 `bench/selftest_judge.py` 的 `checked=12 / majority_checked=3 / mapping_checked=3 / g2b_checked=2`
（由 `G-JUDGE-1` 守）。

**为什么要把两列分开写**：只写目标值会让接手的人以为「22 比 24 少 2，是不是测试被删了」；
只写当前值会让它读起来像「已经做完」。两个都写才能同时回答「还剩多少」与「没丢东西」。

## 4 逐模块测试设计

### A 需求→四元组解析（L1，16 项）

| 测试项 | 输入 | 期望 |
|---|---|---|
| A1（12 例，参数化） | 完整 / 缺 geometry / 缺 properties / 缺 boundary / 缺 objective / 缺两键 / 全缺 / 键名拼错 / 类型错 / 多余键 / 空串 / 中英混 | 前 1 例 `complete=true`；后 11 例 `complete=false` 且 `missing` 逐项正确 |
| A2 | 「一个方腔，水」（缺顶盖速度） | `boundary=null`；**不许**是 `0.01` 或 `1.0` |
| A3 | 「跑个算例看看」 | `objective=null`，退出码 10 |
| A4（D9 新增） | 「……，层流」（objective 给了非法枚举） | `objective=null` 且进 `missing`；**不许**猜成 `steady` |
| A4b（D9 新增，反向） | `objective` 分别取 `steady` / `transient` | 两者都 `complete=true`。**只测「非法被拦」是单向测试**（§3.1 第 3 条），必须同时证明合法值不被误杀 |

```bash
python3 scripts/parse_requirement.py --text "一个二维方腔，顶盖 1 m/s，水，kOmegaSST，稳态"
# 期望：{"geometry":"二维方腔","properties":"水，kOmegaSST","boundary":"顶盖 1 m/s",
#        "objective":"steady","complete":true,"missing":[]}
python3 scripts/parse_requirement.py --text "跑个算例看看"; echo "exit=$?"
# 期望：objective 为 null，missing 非空，exit=10
python3 scripts/parse_requirement.py --text "一个二维方腔，顶盖 1 m/s，水，层流"; echo "exit=$?"
# 期望：objective=null 且进 missing（「层流」不是 steady/transient），exit=10
```

变异体 A-M1：把校验器改成「缺键填 `""`」→ A2、A3 必须红。
变异体 A-M2（D9 新增）：把 `objective` 的枚举校验去掉（任意字符串照收）→ A4 必须红。

### B 知识检索（L2，5 项）

| 测试项 | 判据 |
|---|---|
| B1 确定性 | 同一查询两次输出 `diff` 为空 |
| B2 搜索根合规 | 每条命中的绝对路径以五个根之一开头；**不得**出现 `~/OpenFOAM/*/src` |
| B3 已知答案集 | 20 条手写 `(查询, 期望相对路径)`，每条至少命中 1 条 |
| B4 空结果不编造 | 查 `kOmegaSSTFoo` → `FOUND=0`、退出 11，无任何回退 |
| B6 `FOUND` 是总数不是截断值（D10） | `--limit 3` 时 `FOUND` 与不带 limit 时一致，且 `SHOWN==3`；截断必须是排序后的前 3 条 |
| B5 命中有效性 | 全部命中 path 存在、行号不越界、**该行非空** |

B3 的 20 条必须在写检索代码之前定（否则会照着实现写测试）。B5 的空行判据不是洁癖：
本项目在这一点上栽过——`references/08-condensed-report.md` 有三条锚点指向空行而门禁全绿。

### C case 生成（**L1**，7 项，零 OpenFOAM）

**为什么能放 L1（D14）**：C 做的是「`cp -a` + 写 JSON + 校验路径」，**一条 OpenFOAM 命令都不调**。
只要测试自己造一棵伪 tutorial 树并把 `FOAM_TUTORIALS` 指过去，就不需要装 OpenFOAM。
上一版把它排在 L2 是照抄了「涉及 case 就要 OpenFOAM」的直觉，实际不成立。

| 测试项 | 判据 |
|---|---|
| C1 派生完整性 | dest 文件集合 == source 文件集合，白名单只有 `case.meta`。**按文件对逐个比内容 sha**，不比 mtime |
| C2 `case.meta` 齐全 | 六键齐（`source`/`derived_at`/`spec`/`changes`/`allowed_files`/`schema_version`）；`$FOAM_TUTORIALS/<source>` 用 `test -d` 通过 |
| C3 `spec` 原样写入 | 写入的 `spec` 与 `--spec` 传入的 JSON **逐键相等**（键名 `properties` 不是 `material`，D9）；不许多键、不许改值 |
| C4 幂等 | 同一 `--spec` 生成到**两个不同 dest**，两树逐文件 sha 相等；`case.meta` 除 `derived_at` 外相等。**不测「同一 dest 跑两次」**——那是 C6 的失败路径 |
| C5 不凭空写 | 源不存在 → 退出 12，且 dest **不存在**（不是空目录） |
| C6 dest 已存在 → 13（D11） | 预置一个同名目录 → 退出 13，且那个目录**内容不被改动** |
| C7 越界源 → 12（R3） | 源存在但不在 `$FOAM_TUTORIALS` 下（如指向 `$FOAM_SRC`）→ 退出 12 |

**注意 C3 的写法**：`case.meta` 是 JSON，用 `json.load` 比较，**不要**对文件做字符串断言
（键顺序、缩进、CJK 转义都会让字符串比较假红）。

### D 求解执行（L2，7 项，需 OpenFOAM 且会真跑）

**这一层是本项目第一次真跑 OpenFOAM**，测试用 tmp_path，**绝不许写 `bench/`**（R12 设计期禁跑）。

| 测试项 | 判据 |
|---|---|
| D1 退出码传播 | 删 `system/fvSolution` 后 `--mode short` → 退出 **20**。实测 `foamRun` 自身退 1 且日志有 `FOAM FATAL ERROR` |
| D2 日志按 mode 分级（D12） | `check` → 只有 `log.checkMesh` 存在且非空，`log.shortRun`/`log.run` **不存在**；`short` → `log.checkMesh` + `log.shortRun` 都非空 |
| D3 超时（D15） | 用 `nOuterCorrectors` 调大让每步变慢（**不是**改 `endTime`——short 模式自己会改写它）+ `--timeout 3` → 退出 **21**，耗时 < 10 s。实测 `timeout` 退 124；实测连跑 4 次 5.12–5.13 s，不随负载漂移 |
| D4 环境缺失 → 22 不是 127（D13） | `env -i PATH=/usr/bin:/bin` 跑 → 退出 **22**，stderr 含 `OpenFOAM 环境未加载`。**同时断言不是 127**：`ret != 127` |
| D5 无网格无 blockMeshDict → 23 | 删 `constant/polyMesh` 和 `system/blockMeshDict` → 退出 **23**。不是 20（那不是求解失败） |
| D6 短跑真的改小了 endTime | `short` 后回读：`readTime`/步数明显小于满跑，且 `log.shortRun` 里最后的时间 <= 改后的 `endTime` + 容差。**这条专门防 `foamDictionary` 静默失败**（用法写错时它退 0 但不改，短跑会跑满 10 s 而测试仍绿） |
| D7 blockMesh 自动准备网格 | 从无 `constant/polyMesh` 的派生 case 起点跑 `--mode check` → 退出 0，且 `constant/polyMesh/` 被生成 |

**D6 的判据为什么必须回读而不是看耗时**：耗时受机器负载影响，不可复算。回读 `/0.01` 这类
时间目录名或 `log.shortRun` 的末行时间戳才是确定性的。

**`full` 的恢复语义（D16）**：短跑改写了 `endTime`/`writeInterval`，满跑前必须恢复原值，
跑完也不许留下被改小的 `endTime`——否则这个 case 之后再被 G5/G4 用时，表现会是「算例算不完」，
而错误发生在很早以前，极难归因。实测验证方式：把 `endTime` 预置成 `0.03`，跑完 `full` 后回读
仍是 `0.03`、`writeInterval` 仍是 `100`，`log.shortRun` 末时间 `0.01`、`log.run` 末时间 `0.03`。

### E 门禁判定（拆成 E-lite / E-full，D4）

七态归约的 12 项**不在这里**——它们在 `bench/selftest_judge.py`，由 `G-JUDGE-1` 守（已完成）。

#### E-lite `--stage pre`（L1，8 项，零 OpenFOAM）

| 测试项 | 正例 | 反例 | 期望码 |
|---|---|---|---|
| E-p1 G1 完整 | `system/{controlDict,fvSchemes,fvSolution}` 齐、`0/` 非空 | — | 0 |
| E-p2 G1 缺文件 | — | 删 `fvSolution` | 1 |
| E-p3 G5 合规 | 只改 `allowed_files` 内 | — | 0 |
| E-p4 G5 越界 | — | 顺手改 `constant/polyMesh/blockMeshDict` 且 `case.meta` 无理由 | 5 |
| E-p5 G5 例外放行 | 改 `constant/polyMesh/` **且** `case.meta.changes` 写了理由 | — | 0 |
| E-p6 双失败取最小码 | 同时缺 `fvSolution` 且越界 | — | 1（不是 5；D6「只报第一个失败的门」） |
| E-p7 mtime 分支（验收补） | 无 `base/`、只改 allowed 内 → 0 | 无 `base/`、改了 allowed 外 → **5** | 证明 mtime 分支真的在工作 |
| E-p7b base 优先于 mtime（验收补） | 有 `base/` 且内容相同、但 mtime 全部更新 → **0** | — | 证明「只要 base 在就绝不走 mtime」（否则 cp/解包会造出假越界） |

```bash
bash scripts/verify_case.sh --stage pre --case tests/unit/fixtures/pre_ok; echo "exit=$?"
# 期望：log.g1=RC=0、log.g5=RC=0，exit=0
bash scripts/verify_case.sh --stage pre --case tests/unit/fixtures/pre_no_fvSolution; echo "exit=$?"
# 期望：log.g1=RC=1，exit=1，且 **不产生** log.g2..log.g4（短路）
```

#### E-full `--stage post`（L2，8 项，需 OpenFOAM）

| 测试项 | 正例 | 反例 | 期望 |
|---|---|---|---|
| E-f1 G2 | 正常网格（`cavity`，`Mesh OK.` 出现 1 次） | 退化块（`aspect=2000`，`Failed 1`、无 `Mesh OK.`） | 码 0 / 2 |
| E-f1b **G2 不看退出码**（D18） | — | **真实日志**：`Failed 1 mesh checks.`、无 `Mesh OK.`，而 `checkMesh` 自身退出码 **0** | 必须 `RC=1`（码 2）。**这条是 E-full 最重要的一条**：把 G2 改成看退出码时它必须红 |
| E-f2 G3 | 正常短跑日志 | 日志含 `FOAM FATAL` | 码 0 / 3 |
| E-f3 G4 | 正常末时刻 | 手改末时刻 `U` 为 `nan` | 码 0 / 4 |
| E-f4 G2b 写出与解析 | 正常网格 → `G2B=none`；退化块 → `G2B=hard:N`（N 与 `grep -c '^\s*\*\*\*'` 相等） | — | `log.g2` 第 2 行格式合法 |
| E-f4b `soft` 分支（D19：**合成日志**，须在 docstring 写明） | 取一段真实 `Mesh OK.` 日志，**注入一行 ` ***...`** 造出"`Mesh OK.` 与 `***` 共存" | — | `G2B=soft:N` 且 **G2 仍 RC=0**。docstring 必须写明：真实 soft 网格在 v13 **不可达**（208 tutorial 全扫 0 例），此例只证明「万一出现，判定器认得」 |
| E-f5 overclaim | — | 声称「已完成」但 G3 不过 | judge 判 `overclaim`，不是 `pass` |
| E-f6 短路合法 | — | pre 阶段 G1 已 fail，post 未运行 | judge 判 `fail`，**不是** `malformed`（M-d） |
| E-f7 空日志 | — | `log.g3` 为空文件 | judge 判 `malformed`（≠ pass） |
| E-f8 G2b 不影响 status | 同一个 case 跑两次：一次 `G2B=none`、一次合成 `G2B=soft:1`（其余日志相同） | — | `g2b` 不同、`status` **相同**（G2b 不是门） |

```bash
bash scripts/verify_case.sh --stage post --case <c> --log <c>; echo "exit=$?"
# 期望：写 log.g2..log.g4，log.g2 第 2 行有 G2B=，exit=0 或 2/3/4
```

### F 失败反馈与修复（L2，7 项）

**测试对象是 locate / apply 两层，不测「模型选什么值」**（§10.7）。

| 测试项 | 判据 |
|---|---|
| F1 定位（可定位类） | 关键字 undefined 的真实 FATAL → `changes[0].file == "system/fvSolution"`、`entry == "PIMPLE"`、`declined=false`、`written=false`（locate 模式不写盘）、`new_value=null` |
| F2 定位（结构类 → declined） | `Cannot find patchField entry for movingWall` → `declined=true`、`changes=[]`、reason 提到 `movingWall`（D24） |
| F3 定位（不可定位 → declined，不猜） | `solvers table is empty` → `declined=true`、`changes=[]`、reason 非空，且**不含任何猜测的文件名**（D23） |
| F4 apply 标量 + 备份 | 把 `system/controlDict` 的 `endTime` 设成 `0.02` → `written=true`、回读 0.02、`attempt_1/` 内容 == 改前快照 |
| F5 entry 必须唯一命中 | 指向不存在的 entry → 退 `33`、`written=false`、字典文件 sha256 **前后相同**（`06:150`） |
| F6 轮数上限 | `--attempt 4 --max-attempts 3` → 退 `31`、`changes=[]`、**不产生 `attempt_4/`** |
| F7 指纹去重 | 同一 FATAL 连调两次（attempt 1 后 attempt 2）→ 第二次退 `32` 且 `attempt_2/` **不存在**（D25） |
| F8 不同错误不同指纹（验收补） | 两个**不同**的不可定位错误 → 指纹必须不同；**同一**错误重复 → 指纹必须相同。正反两向都测，见 §10.8 缺陷 3 |

**F2 与 D2 的可量化口径（D2 裁定的直接后果）**：`human_interventions` 在 L2 里必须恒为 0——
L2 全程无人。它只在 L3/L4 出现，且口径为「改字典 + 答问」两类的合计，不含「重启整轮」。

### G 契约层（L1，6 项）

| 测试项 | 判据 |
|---|---|
| G1 真实 CSV 通过 | 仓库的 `bench/results.csv`（表头 + 0 数据行）→ 退 `0` |
| G2 表头违规被抓 | 4 种坏表头各退 `40`：少一列 / 多一列 / 两列换序 / 列名改大小写 |
| G3 status 取值 | `passed`（非七态）→ 退 `40`；七态各一行 → 退 `0` |
| G4 六键齐 | 六键齐 → 退 `0`；**逐个**缺键（6 次）→ 每次退 `40` 且点名缺的键 |
| G5 类型校验 | `schema_version="1"` / `allowed_files=[]` / `spec=[]` / `derived_at="昨天"` → 各退 `40` |
| G6 与 C 联动 | 用 `scripts/new_case.sh` 真产出的 `case.meta` → 退 `0`（把 G 与 C 钉在一起） |

`bench/results.csv` 的可重算性（删表从 `runs/` 重建得逐字节相同）属 L4，不在此层。

## 5 变异自测（测「门会不会红」）

**变异验证一律就地做，不建集中式的 `test_mutants.py`**（D26：该文件从未存在，
却被本文件与附录 B 引用并声称「期望 6 passed」）。

就地做法（每个模块都这样）：

```bash
cp scripts/<被测脚本> /tmp/<被测脚本>.bak     # 备份
<改一处，实现某个判据失效>
python3 -m pytest <对应测试文件> -q            # 必须红，且只红目标那条
cp /tmp/<被测脚本>.bak scripts/<被测脚本>       # 还原
python3 -m pytest <对应测试文件> -q            # 必须恢复绿
diff -q /tmp/<被测脚本>.bak scripts/<被测脚本>  # 必须无输出
```

**「只红目标那条」是关键**：若一次改动让半个文件的测试变红，说明测试之间互相遮挡，
那个变异体证明不了任何单一判据。

已做的变异体清单见 §4 各模块小节与 §10.3b–e。

| 变异体 | 改法 | 必须变红 |
|---|---|---|
| M1 | G1 的 `test -f` 三连改成只 `test -d system/` | E1 |
| M2 | G2 的 `grep -q "Mesh OK."` 改成恒 `true` | E2 |
| M3 | G3 的 FATAL 检查改成只看退出码 | E3 的「日志含 FATAL 但退出码 0」那条 |
| M4 | G4 的 `nan` 检查删掉 | E4 |
| M5 | G5 的 `allowed_files` 求差改成空集 | E5 |
| M6 | `undeterminable` 映射到 `pass` | E7 / mapping 组 |
| M7 | `g2b` 恒返回 `none`（不解析 `log.g2` 第 2 行） | `mapping` 组的 g2b 解析项（D7 要求） |

> **这张表是设计期的设想，不是执行记录**。实际执行时 M1–M7 都被**就地**做掉了
> （模块 E 的 E-M1/E-M2/E-M3、judge 的 J-M1…J-M8、C 的 C-M1/C-M2、A 的 A-M1/A-M2、
> E-lite 的 mtime 两例、F 的 F-M1..M3、G 的 G-M1/M2）。**M3 尤其重要**：
> 「日志含 `FOAM FATAL` 但退出码 0」这个边界（`bench/preregistration.md:365`）
> 已由 E-full 的 `test_ef1b` 以更强的形式覆盖——`checkMesh` 在网格不合格时**真实退出码就是 0**。

## 6 前置条件（按 D8 重新分配「谁等谁」）

上一版把四项前置都排在「实现之前」，那是把整个项目当成一次大瀑布。D8（E-lite 先行）之后，
四项各有自己的**最近下游**：只在它那个下游开工前做完即可。

| # | 前置 | 必须在谁之前 | 完成判据 | 状态 |
|---|---|---|---|---|
| P1 | **judge 七态归约自测** | 全部（它是判定器的判定器） | `checked=12` + `majority_checked=3` + `mapping_checked=3` + `g2b_checked=2`，**8 个变异体全红** | ✅ 2026-10-28（v2，含 D4 短路 + D7 g2b） |
| P3 | **G5 的门定义进 README** | **E-lite**（G5 是 pre 阶段的判据之一） | 退出码表出现码 `5`（现 `:231`）；目录布局改成说明两阶段（现 `:272`） | ✅ 2026-10-28（G5 已进 §6 门表、退出码 0–5、目录布局写清 `--stage pre/post`） |
| P4a | **G1 增 patch 集合相等** | **E-lite** | `verify_case.sh --stage pre` 能判 `0/U`/`0/p` 的 patch 与 `constant/polyMesh/boundary` 相等 | ✅ 2026-10-28（E-p1 覆盖；boundary 缺失时日志记 `SKIP`） |
| P4b | **G3 版本行 + G4 场值有限+上限** | **E-full** | 两条都体现在 `--stage post` | ❌ **仍未做**（2026-10-28 核实：`grep -n '版本\|version\|上限\|finite' scripts/verify_case.sh` → 0 命中）。E-full 已交付但少这两条，属 E 的缺口，**不在 F/G 范围内** |
| P2 | **G2b soft 分支实测样例** | **E-full 的 E-f4** | 贴出 `blockMesh`+`checkMesh` 输出与 `grep -cE '^\s*\*\*\*'` 的值 | ✅ 2026-10-28 **结案为「不可达」**（D19）：208 个 tutorial 全扫，`Mesh OK.` 与 `***` 共存 0 例；那 4 项豁免检查不打印 `***`。E-f4b 改用合成日志 |

P2 的降级理由是 D8 的直接后果：E-lite 完全不碰 `checkMesh`，所以「必须先从 tutorial 派生一个
soft 缺陷 case」这件事在第一批里没有用处。它只挡 E-f4 一项。

P3 仍是唯一要求改既有文档的前置，只改 README（非冻结件）。

## 7 实施顺序（D8 = E-lite 先行）

```
第一批（可并行，零 OpenFOAM、零 LLM）
  ├─ A   parse_requirement.py 的校验器（L1 14 项）
  ├─ B   find_template.sh（L2 5 项，只 grep）
  └─ E-lite  verify_case.sh --stage pre（G1+G5，L1 6 项）  ← 需 P3 + P4a
                 │
第二批           ▼
  ├─ C   new_case.sh（用 B 的命中 + E-lite 判对）
  └─ D   run_case.sh（用 C 的产物）
                 │
第三批           ▼
  └─ E-full  --stage post（G2–G4+G2b，L2 8 项）  ← 需 P2 + P4b
                 │
第四批           ▼
  └─ F   fix_case.py（用 E 的失败串 + C 的产物）   ✅ 2026-10-28（7 项）
                 │
                 ▼
     G 契约（check_contracts.py，6 项）           ✅ 2026-10-28
                 │
                 ▼
                 │
                 ▼
     L3 单任务 → L4 12 任务跑批
```

**为什么 E-lite 排第一而不是 E-full**：G1/G5 的判据是 `test -f`、`ls`、`git diff --no-index`
（`bench/preregistration.md:85`、`:89`），零 OpenFOAM 依赖。先把它做掉，第一批三个人（A/B/E-lite）
全都能在「无 OpenFOAM、无 LLM key」的机器上跑完 L1/L2，这是 D8 换来的最大好处：
**「要不要现在就跑 OpenFOAM」这个决定被推迟到第三批**。

**为什么 C 不能先于 E-lite**：C 的正确性判据就是「E-lite 判它过」。顺序反了就是用未验证的判定器
验证生成器（上一版 §7 的这条理由仍然成立，只是对象从 E-full 换成 E-lite）。

## 8 与 bench 12 个任务的分工

`bench/tasks/` 的 12 个任务**不属于任何模块的测试**——它们含 LLM、贵、测的是端到端。
模块测试（L1/L2）与它们的关系是：**L1/L2 红的时候，L4 的任何数字都不许写出来**。

| 任务 | 覆盖模块链 | 它证明什么 |
|---|---|---|
| T01–T04（build, D1–D4） | A→C→D→E | 建 case 与改参数 |
| T05（modify, D1） | C→E + `expect_values` | **只过门不够**：不改任何东西也能过 G1–G4，必须靠断言 |
| T06（modify, D2） | A→C→E | 三处联动（PIMPLE + 删 SIMPLE + `ddtSchemes`）只改一处不算过 |
| T07/T08（modify, D3/D4） | C→E | patch 名实测（`movingWall` 非 `topWall`）、无量纲比值 |
| T09–T11（batch, D1–D3） | + 批跑契约 | CSV 汇总、9 例矩阵 |
| T12（batch, D4） | F（拒绝） | 负对照：正确行为是 `declined`，**不进 11 的分母**（`bench/preregistration.md:439`） |

## 9 不做清单（设计时不要留接口）

这 5 件在 `references/08-condensed-report.md` §2.3 已论证过，各有可判定的加回触发条件。
**设计时给它们留接口，就一定会被人填上。**

| 不做 | 加回触发条件（可判定） |
|---|---|
| 阶段状态机 | `runs/<batch>/<case_id>/` 下出现第二份 `log.run` 且不在 `attempt_<n>/` 里 |
| 反思记忆 | 同一 FATAL 首行出现在 ≥3 个不同 case 的 `log.shortRun` |
| 工具接口（MCP/function calling） | 出现第二个消费者且参数形状与现有 CLI 不同 |
| 独立版本断言部件 | `ls -d /opt/openfoam*` 行数 > 1，或换机复跑成为验收要求 |
| 人机停点 | 同一 case 连续 2 次非 0 退出且失败串首行相同 |

## 10 未定项与风险

### 10.1 落地时定下的四处映射（预注册未逐字规定，必须登记）

`bench/judge.py` 的 docstring 里同步写了这四条，改动任一条都要同时改两处：

| 代号 | 决策 | 依据 |
|---|---|---|
| M-a | `case/` 存在但缺 `system/controlDict` → **malformed**（目录半成品）；"根本没有 case 目录"才是 `no_artifact` | `bench/preregistration.md` §4：`no_artifact` = "没有可判定的 case 目录"，`malformed` = "目录半成品"。两处措辞分别支持这两读 |
| M-b | `case.meta` 缺 `source` → **malformed** | 派生来源不可追溯 ⇒ 无法复核 ⇒ 不得记 pass；与 `AGENTS.md:143`「`source` 必须真实存在」同向 |
| M-c | `overclaim` 只在**闸门**未过时成立；"闸门全过但断言 mismatch" 记 `fail` | §4 对 overclaim 的定义是"独立门禁判为未过"，未含断言层 |
| M-d | **短路合法**：若某道门已 `fail`，则序号在它之后的门"缺失"是预期的（G1/G5 不过时 G2–G4 根本不会跑）→ judge 判 `fail`，**不是** `malformed`。判据：所有 `undeterminable` 的门序号都大于第一个 `fail` 的门序号 | D4 把 G1/G5 前置后产生的新状态。没有 M-d，任何 pre 阶段就被拦下的 run 都会被误判成 `malformed`，把「答错了」记成「没法判」——`bench/preregistration.md` §4 明确说这是两类 |

### 10.2 P1 暴露的方法论问题

**样本数够了不等于分支覆盖够了。** 首轮 12 个 fixture 按「7 态 + 5 边界」逐条对齐、`checked=12 failed=0`
全绿，但变异体 J-M1（把 `undeterminable` 改成 `pass`）**存活**——因为 12 个 fixture 里没有
「五门全过但断言 undeterminable」这一例。这正是 `bench/preregistration.md` §11 第 7 条最强调的禁忌。

补法不是「再加一个 fixture 到 12 里」（那会破坏 §11 第 4 条钉死的样本数），而是**另立一组**
`mapping_checked=1` 与本测 `checked=12` 并列打印。判据：
**任何一个变异体能存活，就说明测试集有洞——不管样本数看起来多整齐。**

### 10.3 落盘前自查发现的三个问题（已全部闭合）

这三个问题都是「文档之间互相核对」暴露的，不是通读发现的——值得记住这个发现方式。

| # | 问题 | 怎么发现的 | 处置 |
|---|---|---|---|
| 1 | **G1 的位置错了**：`06:254` 的原始数据流是 `[1]→[2]/[3]→[5 G1]→[4]→[5 G2-G4]`，即 G1 在求解前；上一版把 G1–G5 全放在求解之后 | 为回答「架构定没定」去读 `06:254`，与 §1.2 的图对照 | D4：G1+G5 前置（`--stage pre`），G2–G4 后置（`--stage post`）；§1.2 重画 |
| 2 | **§1.1 的载体定义与模块接口矛盾**：写「只走文件树/日志/退出码」，但 A 的输出是 stdout JSON、C 的输入是 argv | 写 §2 的 A 契约时发现 | §1.1 改为三载体表，逐条列出每类跨界传递的落点；A 的四元组落盘为 `cases/<id>/spec.json`；argv 只许承载纯函数入参 |
| 3 | **`judge.py` 不认 g2b，而 `results.csv` 要 g2b 列**：`grep -c g2b bench/judge.py` → 0，但表头第 9 列是 g2b | 核对 judge 的输入时逐个文件对照 | **已闭合**：D7 + judge v2。`log.g2` 第 2 行 `G2B=`，judge 解析并透传（不参与 status）；`g2b_checked=2` 守两件事（解析 + 缺失记 unknown）；变异体 J-M7 变红。指纹见 `bench/preregistration.md` §17 的 v2 段 |

**教训（与 §10.2 同类）**：三个问题里有两个是「我写的两份文档互相矛盾」，一个是
「我写的代码与预注册的列定义矛盾」。**同一件事在多处出现时，必须逐处核对，不能只核对最新写的那处。**

### 10.3b 第一批验收（不听自报，逐条重跑）发现的问题

三个子代理的自报都通过，但验收时发现 4 处需要修。**没有一处是子代理撒谎**，全是我的规格有问题
或测试覆盖不足。

| # | 问题 | 谁上报的 | 处置 |
|---|---|---|---|
| 1 | **四元组字段名与 `06` 不符**（`material` vs `properties`；`objective` 从枚举变自由文本） | 子代理 A 主动标注 | D9：改 09 + 改代码 + 改测试；新增 A4/A4b 两条（正反两向） |
| 2 | **`FOUND` 语义与规格不符**（规格写「命中文件数」，实现成「输出行数」） | 子代理 B 列为「最可能被挑战」，但没意识到这其实是**违反规格** | D10：`FOUND`=总数 + `SHOWN`=输出行数；新增 B6；变异验证（改回输出行数 → B6 必红） |
| 3 | **mtime 分支零测试覆盖**（5 个 fixture 全带 `base/`，只走 `git diff` 那条） | 子代理 E 主动标注「已知缺口」 | 新增 E-p7 / E-p7b；**两条都做了变异验证**（mtime 恒判无改动 → E-p7 红；忽略 base 强制 mtime → E-p7b 红 + 4 项连带红） |
| 4 | **E 的「理由」判据极宽**（`case.meta.changes` 任意非空即放行 `constant/polyMesh/` 改动） | 子代理 E 主动标注 | **不修**。`bench/preregistration.md:89` 原文只要求「写理由」，未要求理由与改动对得上。预注册是冻结件，改它算新一轮。已在本表登记为**已知放宽**，M4b 出报告时须注明 |

**教训（与 §10.2/§10.3 同族）**：三条「真问题」里，两条是子代理自己标出来的、一条是它们没意识到的。
这说明**自报的疑点列表比自报的结论更有价值**——疑点会被验收捡起，结论会被验收推翻。

### 10.3c 第二批验收（2026-10-28，C+D）

两个子代理自报全绿（C 7 项、D 7 项）。逐条重跑后**结论成立**，但发现 2 处规格自相矛盾、
1 处环境事实我先前说错了。

| # | 问题 | 谁上报的 | 处置 |
|---|---|---|---|
| 1 | **D3「怎么让它超时」机制不成立**：short 模式自己把 `endTime` 改写为 `deltaT*2`，改 `endTime` 对短跑时长无影响（实测 2 步 0.1 s） | 子代理 D 主动说明 | D15：改用 `nOuterCorrectors` 让每步变慢；实测连跑 4 次 5.12–5.13 s 稳定 |
| 2 | **`full` 模式两处定义互斥**：§4 写「不改 endTime」，§2 写「先短跑再恢复」 | 子代理 D 主动说明 | D16：统一为「短跑 + 恢复后满跑」，并实测恢复正确（`endTime` 0.03→0.03、`writeInterval` 100→100） |
| 3 | **`python3` 的 PATH 不稳定**：我先断言「PATH 上的 python3 就是装好依赖的那个」，并据此判三个子代理「是自己沙箱问题」——**这条断言是错的** | 无（我自己弄错） | `tests/unit/README.md` 与本节都改成「必须用绝对路径」。子代理 A 原写的「PATH 上的 python3 未装 pytest」是对的 |

**验收自己做的独立复核**（不复用子代理的变异脚本）：C6 哨兵文件 md5 前后一致、C7 越界源不产目录、
C1 逐文件 sha（13→14，只多 `case.meta`）、`../` 经 realpath 后判得正确、D4 `rc=22` 且不为 127、
D6 注入「字典去位置参数」后回读报 `endTime=0.01 未生效（回读 '10'）`、`full` 恢复语义、
`bench/runs/` 仍为 0。

**教训**：两处「自报与计划不符」都是子代理**主动说明**的，且都揭示我文档内部矛盾。
与第一批同构——**自报的疑点比自报的结论有价值**；而这次连「我自己的环境断言」都该被复核。

### 10.3d 缺陷修复轮（2026-10-28，用户「先修已确认缺陷」）

三个缺陷都是**集成时**才暴露的，都是单模块测试绿的时候测不到的。每条都先写红测试再修。

| # | 缺陷 | 怎么发现的 | 修法 | 守护测试 |
|---|---|---|---|---|
| 1 | `parse_requirement.py` 与 `status_snapshot.py` 有 shebang 但**无执行位**；`./scripts/x.py` → `Permission denied`（126） | 手动串联 A→C 时 `rc=126`。它的 16 项单元测试全绿，因为测试用 `sys.executable` 调用解释器 | `chmod +x`（两个都补） | `tests/unit/test_script_entrypoints.py`（15 项，**按类**遍历 `scripts/`：凡带 shebang 必须可直接执行）。变异：`chmod -x` → 2 条红 |
| 2 | 用法错误退出码**跨模块不一致**：`verify_case.sh` 是 `64`，另四个是 `2`；而 `2` 在 `verify_case.sh` 里是「G2 门失败」 | 逐脚本实测缺参数时的退出码 | 统一为 `64`（`EX_USAGE`）；`parse_requirement.py` 覆盖 argparse 的 `error()`（它默认退 2） | `tests/unit/test_exit_codes.py`（11 项）。变异：改回 `die 2` → 对应项红 |
| 3 | 09 的 §1.1 与 §1.2 描述了 `cases/<id>/sources.txt` 这个**不存在的载体**，而 §2-C 说 C 不解析它 | 集成时发现 B 只往 stdout 写、两个脚本都不碰 `sources.txt` | 改成「B → 调用方（stdout，不落盘）」+「调用方 → C（argv `--source`）」两行 | 无测试可写（是文档），但 §1.1 的载体表现在与 `find_template.sh` 的实际输出一致 |

**这一轮的教训（与前两批同构，但方向相反）**：前两批是子代理自报的问题、我来裁定；
这一轮三个缺陷**全部是我自己的规格/实现留下的**，且都是「单模块绿、合起来才红」的类型。
→ **单模块测试通过不能推出系统可用**，集成测试不是可选项。

### 10.3e E-full 与集成测试轮（2026-10-28，链终于闭环）

这一轮第一次让 `judge` 吃到**真实 run**（此前它只吃合成 fixture）。成果与代价：

**闭环证据**（`tests/contract/test_end_to_end.py`，1 项）：
A（需求→四元组）→ C（派生 case）→ E-pre（写 `log.g1`/`log.g5`）→ D（短跑）→
E-post（写 `log.g2..g4` + `G2B=none`）→ `assert_lib`（写 `assert.json`）→
`judge` 归约出 **`pass`**。全程零人工搬迁，布局按 prereg §12（日志与 `case/` 同级）。

**这条测试一写出来就红了三次**，每次都是真错位：

| # | 症状 | 根因 | 修法 |
|---|---|---|---|
| 1 | E-pre 退 5，`G5 UNJUDGEABLE case.meta 不存在` | E-pre 只在 `<case>/case.meta` 找 meta，且**忽略 `--log`**（写死到 case）；judge 却读 `run/log.gN` 与 `run/case.meta` | D21（E-pre/D 都接受 `--log`）+ D20（meta 两处都认） |
| 2 | `assert_lib` 抛 `TypeError: string indices must be integers` | 我在测试里把 **A 的四元组 `spec.json`** 当成了 **assert_lib 的断言列表**。两者结构无关：前者是 `geometry/properties/boundary/objective`，后者是 `[{kind: ...}]` | 测试里就地构造最小断言（`deltaT=0.005`，short 模式不改它）；并在测试注释里写明两者不是一回事 |
| 3 | 集成测试通过，但**是我在测试里 `shutil.move` 了 `case.meta`** | 测试替实现补了缺口 ⇒ 真实布局没被验证 | 去掉搬运；改为让两端都认两处（D20），由链自己走通 |

**顺带抓到 judge 一个真 bug**：完全没有 `case.meta` 时判 `pass`。
起因是 `if meta_raw is not None:` 分支外没有 else，`meta_missing_source` 保持 `False`。
由新增的 `meta_cases()` 4 项自测咬出来（`meta_checked=4`），并纳入 `G-JUDGE-1`。

**还抓到一条 flaky 测试**：`test_c4_idempotent_two_dests` 在负载下随机红
（`At index 79 diff: b'8' != b'9'`）。原因：逐字节比较把 `case.meta` 也算进去，
而它含 `derived_at`，两次运行跨秒就必然不同。修法：字节比较排除 `case.meta`
（它由后面的 dict 比较负责，已 `pop("derived_at")`）。**这条值得单独记**：
一个只在「跑得慢」时才红的测试，平时全绿会让人以为它可靠。

### 10.4 其余未定项与风险

1. **判定器先行的代价**：P1 已完成，但 P2–P4 未做，E 的 L2 层（G1–G5 正反例）仍写不出来；
   在 P2–P4 完成前，模块 C/D/F 的测试没有判定对象。
2. **`human_interventions` 仍只能测一半**：D2 口径已写入 `bench/preregistration.md` §16，
   但 L2 里它恒为 0（无人），真正的数值只出现在 L3/L4，而 L3/L4 现在 0 条数据行。
3. **G5 的落地依赖 P3**：不把 G5 写进 README，契约里收它就是「实现了文档没有的判据」。
4. **L2 的 fixture 会长期增长**：每个新判据配一对正反例。不设上限，但每次增长必须同时更新 §3.2 的计数基线。
5. **不建议写覆盖率**：本项目测的是「判据会不会红」，不是「代码行有没有被执行」。覆盖率对 M1–M6
   六个变异体没有分辨力（P1 的 J-M1 存活就是现成的反例：当时行覆盖率一定很高）。
6. **`judge.py` 读的 `log.gN` 格式是本文件定的接口**：第一行 `RC=0|RC=1`。E 模块落地时
   `verify_case.sh` 必须照此写，否则 judge 会把所有 run 判成 `malformed`。这条接口约定要随 E 一起冻结。

### 10.5 派单前实测的 OpenFOAM 命令坑（C/D 的实现者必读）

这五条全部是**在没有实际执行前看不出来**的，均于 2026-10-28 实测确认。不写下来，
实现者会踩，而且踩了不会红——只会安静地给出错误结论。

| # | 事实 | 实测证据 | 后果 |
|---|---|---|---|
| 1 | `foamDictionary` 的**字典文件是位置参数**，`-case` 只指定 case 目录。省掉文件时**退 1 并报 FATAL**（不是静默） | `foamDictionary -case $T -entry endTime -set 0.01` → stdout 打 `Usage:`，stderr 打 `--> FOAM FATAL ERROR: Wrong number of arguments, expected 1 found 0`，**`rc=1`** | **本条曾被本文件写错**，见下方 §10.8 的更正说明。真正的静默风险在另一处：`-set` 对**不存在的 entry 会新增并退 0** |
| 2 | 真空环境下 `foamRun` 退 **127**，与「求解失败」同形 | `env -i PATH=/usr/bin:/bin bash -c 'foamRun'` → `127`；`command -v foamRun` → `1` | 必须主动探测（D13）。靠子进程退出码会把环境错记成求解失败 |
| 3 | `timeout` 被杀时退 **124** | `timeout 3 foamRun`（`endTime=1e9`）→ `rc=124`，elapsed=3s | 124 要映射成 21；不映射就会落进「求解失败」 |
| 4 | `cavity` 的 `constant/` 只有 `momentumTransport`+`physicalProperties`，**没有 `polyMesh`** | `ls $FOAM_TUTORIALS/incompressibleFluid/cavity/constant/` | 派生后不能直接 `checkMesh`，必须先 `blockMesh`（D7） |
| 5 | `foamCloneCase` 拒绝已存在目标、只复制 shell 脚本、删 `phi`/`Uf`/`uniform` | `/opt/openfoam13/bin/foamCloneCase:215`（`error "...already exists, delete and re-run"`）、`:259`–`264`（`grep "shell script"` 后逐个 `cp`）、`:80`（`rm -rf "$_tgt/phi" "$_tgt/Uf" "$_tgt/uniform"`） | 已由 D11 改走 `cp -a`，不需要再和它搏斗 |

**已验证可用的最小命令序列**（cavity，实测全绿，可直接作为 D 的骨架）：

```bash
source /opt/openfoam13/etc/bashrc
cp -a $FOAM_TUTORIALS/incompressibleFluid/cavity/. <case>/
cd <case> && blockMesh > log.blockMesh 2>&1     # rc=0
checkMesh > log.checkMesh 2>&1                  # rc=0，含 "Mesh OK."
foamDictionary system/controlDict -entry endTime -set 0.01      # 注意：文件是位置参数
foamDictionary system/controlDict -entry writeInterval -set 2
timeout 120 foamRun > log.shortRun 2>&1         # rc=0
```

### 10.6 g2b 与 checkMesh 退出码：两处被推翻的旧结论（2026-10-28）

这两条都是**文档里写着、但实测不成立**的，且都朝「看起来更省事」的方向撒谎。

| # | 旧说法（错） | 实测事实 | 后果若照旧说法做 |
|---|---|---|---|
| 1 | 「`checkMesh` 打印 `Mesh OK.` 与 `return 0` 是同一个条件，所以『退出码 0 但网格坏』在 v13 不可能发生」 | `checkMesh` 在 `Failed 1 mesh checks.`、不打印 `Mesh OK.` 时**退出码仍是 0**。`:180` 的 `return` 属于函数对象 `execute()`，不是进程退出码 | G2 改成看退出码 → **所有不合格网格放行** |
| 2 | 「4 项豁免检查会打印 `***` 但 `Mesh OK.` 照出，故 `g2b=soft` 可达」 | 那 4 项**不打印 `***`**（块内 `***` 数=0）；208 个 tutorial 全扫，`Mesh OK.` 与 `***` 共存 **0 例** | 为 `soft` 编造样例，或以为自己的网格检测漏了东西 |

**扫描方法**（可复算；R6 要求数字来自命令）：

```bash
source /opt/openfoam13/etc/bashrc
W=${TMPDIR:-/tmp}/g2bscan2
find $FOAM_TUTORIALS -name blockMeshDict -path '*/system/*' | sed 's|/system/blockMeshDict||' | sort -u > $W/list.txt
# 逐个 cp -a → blockMesh → checkMesh，数 Mesh OK. 与 ^\s*\*\*\*
awk -F'\t' 'NR>1 {if($2>=1&&$3>=1)s++; else if($2>=1&&$3==0)n++; else if($2==0&&$3>=1)h++; else o++} \
    END{printf "soft=%d none=%d hard=%d 皆无=%d\n", s,n,h,o}' $W/result.tsv
# 实测输出：soft=0 none=182 hard=8 皆无=18
```

**注意统计脚本本身踩过的坑**：第一版用 `m=$(grep -c ... || echo 0)`，而 `grep -c` 命中 0 时
**退出码是 1 但已经打印了 `0`**，于是 `|| echo 0` 又打一个 0 → 变量含两行 → TSV 列错位 →
`awk` 把路径当成 `***` 计数，得出「soft=3」的假结论。**修法**：`grep -c` 不要带 `|| echo 0`，
或者用 `m=$(grep -c ... 2>/dev/null); [ -z "$m" ] && m=0`。这条与 §10.2 的「用全局量推局部量」同族：
**统计口径本身要先自测一次**。

### 10.7 F 的定位规则为什么只有 4 条：三种真实 FATAL 的实测（2026-10-28）

F1 原写「5 个构造 FATAL，每个都定位到正确的文件 + 正确的 entry」。实测三种真实 FATAL
（cavity 派生，`source /opt/openfoam13/etc/bashrc` 后跑 `foamRun`）后发现**不可能全都定位**：

| 类 | 真实 FATAL（逐字） | 能拿到什么 | F 的行为 |
|---|---|---|---|
| 关键字拼错/缺 | `keyword PIMPLE is undefined in dictionary "<abs>/system/fvSolution"`<br>`file: <abs>/system/fvSolution at line 17.` | `file` + `entry` | 定位成功，`new_value=null` |
| patch 缺条目 | `Cannot find patchField entry for movingWall`<br>`file: <abs>/0/U/boundaryField from line 20 to 35.` | `file` + patch 名 | **declined**（结构修复，D24） |
| solver 名不存在 | `solvers table is empty` | **无 file、无 entry** | **declined**（不可定位，D23） |
| 缺整个文件 | `cannot find file "<abs>/system/fvSolution"` | `file` | **declined**（结构修复，D24） |

**为什么 `new_value` 不由 F 决定**：定位能确定"改哪个文件的哪个键"，但确定不了"该设成什么值"——
后者是物理/语法知识，属模型层（§1 表把 F 标为"模型+脚本校验"）。
所以 F 切成 locate / apply 两层：**locate 只报位置，apply 只执行调用方给的变更**。
接 LLM 时只替换"决定 new_value"这一步，两层与其测试一字不改。

**这也是一条 P-实践类的教训**：`references/06-agent-anatomy.md:150` 说 `changes` 的
「每个 `entry` 必须在 `file` 里恰好命中 1 次」是可被脚本校验的约束——这句话成立，
但它**隐含了"变更必须是标量 set"**。结构修复（加 dict 块）没有"entry 命中 1 次"这回事，
所以必须在契约里显式排除，否则实现者会试图用标量接口去表达加块。

### 10.8 F/G 验收（2026-10-28）：一处我的实测错误 + 三个被实现打出的规格缺陷

两个子代理自报全绿（F 7 项、G 6 项）。逐条重跑后**结论成立**，但验收过程中发现四处问题，
其中**三处是我的规格错**，一处是**我自己实测错并写进了文档**。

| # | 问题 | 谁发现的 | 处置 |
|---|---|---|---|
| 1 | **`foamDictionary` 用法错误的退出码，我测错了**：本文件 §10.5 第 1 条与 `scripts/run_case.sh:24` 的注释都写「只打 Usage 且**退出码仍是 0**，静默不改」。实测是 **`rc=1`** + stderr 的 `FOAM FATAL ERROR: Wrong number of arguments, expected 1 found 0` | 子代理 F 主动报告「与规格不符」 | **根因在我的测量方法**：命令写成 `foamDictionary ... 2>&1 \| head -3; echo rc=$?`，`$?` 拿到的是 `head` 的退出码。**带管道后 `$?` 不再是目标的退出码**——这条与工具里那句「exit_code 是管道最后一个命令的状态」是同一件事，我在文档里犯过、又被自己引用了两轮。已改正 §10.5 与 D18 |
| 2 | **`-set` 对不存在的 entry 会新增并退 0**（真正的静默风险在这里） | 子代理 F 实测 | 子代理实现为「写前自己数 entry 出现次数，0 或 ≥2 次退 33」。**这才是 `06:150`「恰好命中 1 次」要防的东西**：不是防「设置失败」，而是防「拼错键名 → 悄悄多出一个键」 |
| 3 | **指纹塌缩（D25 的规格错）**：原定义用「FATAL 首行」，而首行恒为 `--> FOAM FATAL ERROR:`，导致所有不可定位错误同指纹。实测 `solvers table is empty` 与 `cannot find file "..."` 都是 `b10e79556e8a0b5d` | 我在验收时对比两种错误的指纹发现 | D25 修订为「错误特征串 = `-->` 之后前 5 个非空行」；新增 `test_f8`（正反两向：不同错误不同指纹 + 同一错误同指纹）；变异 F-M4（退回恒定首行）→ F8 必红 |
| 4 | **`Cannot find file` 正则大小写敏感**：OpenFOAM 两种写法都有（blockMesh 侧大写 `Cannot find file "points" in directory "polyMesh"`，字典读取侧小写 `cannot find file "<abs>/system/fvSolution"`）。漏掉小写时结论仍是 `declined`（对），但 `reason` 丢了文件路径，违反 D24「declined 必须带定位信息」 | 我在核对正则时发现 | 加 `re.IGNORECASE`；实测小写现在能给出完整路径 |

**这一轮的教训与前几轮不同向**：前三轮的错误都在「文档之间互相矛盾」，这一轮是
**我的一次命令行测量失误被写进规格，然后被子代理实现、再被另一个子代理质疑**。
它的价值在于：**规格里每一条「实测」都应能被复现**。§10.5 那条若当时附上完整命令
（而不是只写结论 + 一行示意），`\| head` 就会一眼看出来。

**规矩（新增，写文档时执行）**：凡在文档里写「实测：命令 X 退出码是 N」，
命令 X **不得带管道**；若必须带，同时写 `set -o pipefail` 或 `PIPESTATUS`。

## 附录 A 待写入预注册的原文（D2）

**已于 2026-10-28 写入 `bench/preregistration.md` §16**（追加在 §15 之后；实测指纹在追加前后
均为 `1bc8a4008c8a01da…`，未改指纹、未开新一轮）。原文如下，与本附录逐字一致：

```markdown
## 16 human_interventions 计数口径（用户裁定 2026-10-28）

口径 = 上文 §13 N1 的候选 **(ii)**：人工干预次数 = 「我替它改了字典」+「它停下来问我、我答一句」。
三次合计口径下，同一次干预不重复计；「我重启整轮」不计入本列（它记在 `note`）。

- 该列在 L1/L2 层恒为 0（全程无人，见 `references/09-architecture-and-test-plan.md` §4-F）。
- 数值只出现在 L3/L4；`bench/results.csv` 中未测到的行仍写 `unmeasured`。
- **本口径下该列可以进结论句**；但只有 `bench/runs/` 出现 ≥1 条实跑数据行之后才成立。
```

## 附录 B 自检命令

```bash
# 本文件的锚点（G-DOC-1 已覆盖 references/*.md）
source /opt/openfoam13/etc/bashrc
bash scripts/verify_references.sh --frozen | tail -5
# 期望：RESULT: ALL GATES PASS

# 必须用显式解释器（PATH 上的 python3 指向不稳定，可能没装 pytest）
PY=$(command -v python3)          # 换成你装了 pytest 的那个

# L1（无需 OpenFOAM、无需 LLM key）
$PY -m pytest tests/unit -q        # 期望 63 passed（含 F/G 之后）
# L2（需要 OpenFOAM，无需 LLM key）
$PY -m pytest tests/contract -q    # 期望 30 passed
# judge 五组自测（G-JUDGE-1 守）
$PY bench/selftest_judge.py        # 期望 12/3/3/2/4，全 0 failed
# 契约校验器
$PY scripts/check_contracts.py --results bench/results.csv; echo $?   # 期望 0

# 变异验证就地做（D26：没有 test_mutants.py），做法见 §5
```

**数字口径（2026-10-28 实测，不是设计目标）**：L1 63 = A16 + C7 + E-lite8 + 跨模块26 + G6；
L2 30 = B6 + D7 + E-full9 + F7 + 端到端1。
