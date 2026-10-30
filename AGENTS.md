# AGENTS.md — 05_FOAM_Agent 工作规则

适用于任何在本目录工作的 agent（Hermes、Claude Code、Codex 或其他）。
本文件与 `README.md` 冲突时，本文件优先；与用户当次指令冲突时，用户优先。

> 版本：1.5（2026-10-29）。**版本变更史（1.0 → 1.5 逐条）见 `CHANGELOG.md`** ——
> 那是维护者的历史，不是 agent 要执行的规则；本文件只保留当前生效的条款。

规则分两类：**硬规则**（违反 = 结论作废，必须重做）与**工程约定**（违反 = 记录后继续）。
每条都写成可判定的形式——「是否违反」不需要争论。

## 红线（只有四条，任何情况下不破）

1. **查源码事实必须 grep**（R1）。没有 grep 输出的 OpenFOAM 源码陈述 = 编造。
2. **不改 `/opt/openfoam13`**（R2）。二次开发只走 `$WM_PROJECT_USER_DIR`（= `$HOME/$WM_PROJECT/$USER-$WM_PROJECT_VERSION`）。
3. **case 从 tutorial 派生**（R3）。不从空目录凭空写字典。
4. **说「能跑」必须先过 G1–G3**（R4）。agent 自述不算证据。

用户要豁免其中任一条，须在当次对话里明确说「豁免 R<N>」，否则一律按规则执行。

---

## R1 · 源码检索：强制 grep　【硬规则】

**凡涉及 OpenFOAM 源码事实的陈述，必须先 grep，并附命令与输出。没有 grep 证据的源码陈述
一律视为编造，结论作废。**

「源码事实」包括但不限于：类名、函数签名、字典关键字、参数默认值、量纲、边界条件类型名、
湍流/相间模型名、solver module 名、命令行选项、某功能是否存在。

### 为什么是硬规则

- 04_RAG_HMS 的三臂实测（36 跑）：**禁工具的裸问答臂 12 条答案里 5 条编造、5 条弃答**，
  错误形态是「路径根本不存在」和「语义等价的改写」——**人眼审不出来**。
  同一次实验里 grep 臂 24/24 自带逐字引文、23/24 通过区间断言。
- grep 与专门的检索层命中打平（各 7/7），但 grep 零安装零存储、不绑语料版本。
  见 `../04_RAG_HMS/reports/.orchestrator/project-conclusion.md`。
- 本机教程生态混着两代语法：v2012/esiu 的写法与本机 v13 差异大。v13 主线是
  `foamRun` + `controlDict` 里的 `solver <module>`；`applications/legacy/` 与
  `tutorials/legacy/` 里另有旧式可执行（`icoFoam` 等，`controlDict` 不带 `solver` 条目）。
  凭记忆写出的字典在 v13 里常常直接 FATAL，或更糟——悄悄用了 legacy 逻辑。

### 搜索根（唯一允许的根）

```bash
source /opt/openfoam13/etc/bashrc   # 必须先 source，否则 $FOAM_* 全空
echo $WM_PROJECT_DIR                # /opt/openfoam13
```

只允许搜索 `$FOAM_TUTORIALS`、`$FOAM_SRC`、`$FOAM_APP`、`$FOAM_ETC`、`$FOAM_UTILITIES`。
**禁止**搜索 `~/OpenFOAM/*/src` 来回答「系统里怎么做」——那是我们自己的副本。

### 七条配方（可直接复制）

```bash
# ① 找「这个东西在真实 case 里怎么用」——最常用，永远先走这条
grep -rl "<关键词>" $FOAM_TUTORIALS | head -20

# ② 定位到行（先 -l 拿文件，再 -n 拿行；不要一上来 -rn 全库）
grep -n "<关键词>" $FOAM_TUTORIALS/<相对路径>/system/<文件>

# ③ 找类/函数的声明位置
grep -rn "class <类名>" $FOAM_SRC --include=*.H | head

# ④ 找某字典关键字在源码里怎么被读取的（拼写 + 默认值 + 量纲）
grep -rn "lookupOrDefault<scalar>(\"<关键字>\"\|lookupOrDefault(\"<关键字>\"" \
     $FOAM_SRC $FOAM_APP --include=*.C | head
#   实测示例：把 <关键字> 换成 maxCo → 命中 3 处，其中
#   applications/modules/incompressibleFluid/setRDeltaT.C:40
#       pimpleDict.lookupOrDefault<scalar>("maxCo", 0.8)

# ⑤ 找某类体系下的所有可选 type
#    边界条件：目录名就是 type 名（最省事，84 个）
ls $FOAM_SRC/finiteVolume/fields/fvPatchFields/derived | head -30
#    或从注册宏入手（同一个目录体系用 makePatchTypeField，53 处）
grep -rn "makePatchTypeField" $FOAM_SRC/finiteVolume/fields/fvPatchFields --include=*.C | head
#    其他子系统用 addToRunTimeSelectionTable（全库 490 处）
grep -rn "addToRunTimeSelectionTable(" $FOAM_SRC --include=*.C | head -20

# ⑥ 找某个 solver module 读了哪些字典（判断必需项）
ls $FOAM_APP/modules/<module名>/
grep -rn "lookup\|readIfPresent" $FOAM_APP/modules/<module名>/*.C | head -30

# ⑦ 判断一个 case 该用哪个 runner（三步，别猜）
grep -n "^solver"        <case>/system/controlDict   # 命中 → foamRun（单区域主线）
grep -n "^regionSolvers" <case>/system/controlDict   # 命中 → foamMultiRun（多区域，如 multiRegion/CHT）
# 两者都空 → 纯网格 case（$FOAM_TUTORIALS/mesh/*）或 legacy；看 Allrun 里的 runApplication 行
grep -n "runApplication" <case>/Allrun
```

实测分布（2026-10-27）：252 个 case = 主线 231 + `tutorials/legacy` 21。
主线 231 里 199 个有 `solver` 条目，其余 32 个是 `mesh/*`（纯网格）与 `multiRegion/*`（`regionSolvers`）。

### 输出纪律（省 token，也是效率关键）

04 的实测：**87% 的 token 是历史重发**，一次吐 10 KB 会被放大 5–6 倍。所以：

1. `-l` 先拿文件列表 → 选定 1–3 个文件 → `-n` 拿行号 → `read_file` 读 ±20 行上下文。
2. 只用 `head -20`/`head -30` 截断，不要整库 `-rn` 无截断输出。
3. 引用格式固定为 `path:line` + **逐字原文**（不要改写、不要补全、不要纠正拼写）。
4. `rg` 与 `grep` 等价可用（本机 rg 15.2.0）；`rg` 更快，但配方里的 `grep` 必须也能跑通。

### 空结果的处理

grep 返回空 = **这个词在源码里不存在**（或拼写不是这个）。这不是「查不到」，这是有效结论。
**不允许**因为 grep 空就改用自己的记忆补答案。正确动作：
换词（每次只改一个变量）→ 换搜索根（tutorials ↔ src）→ 三次仍空则**告诉用户库里没有**，
并列出试过的词。

---

## R2 · 不修改系统目录　【硬规则】

`/opt/openfoam13` 下任何文件不得修改、不得 `sed -i`、不得 `cp` 覆盖。

二次开发一律走用户目录（流程见 skill `openfoam-library-development`）：

```bash
cp -r $FOAM_SRC/.../<模块> "$WM_PROJECT_USER_DIR"/src/
# 改 Make/files: LIB = $(FOAM_USER_LIBBIN)/lib<名>Mod
wmake libso -j
```

判定（已实测可用）：`/opt/openfoam13` **不是** git 仓库，用编译时间戳当基线：

```bash
find /opt/openfoam13/src /opt/openfoam13/applications \
     -newer /opt/openfoam13/build-stamp -type f | head
```

应输出空（2026-10-27 实测 0 条）。M1 再补一份源码 md5 基线表，作为更强判定。

---

## R3 · case 必须从 tutorial 派生　【硬规则】

231 个主线 tutorial（不含 `tutorials/legacy`）是当前版本同步的模板。**凭空写整套字典是本项目最大的幻觉来源。**

- 新建 case：`foamCloneCase <tutorial> <目标>` 或 `cp -r`，不许从空目录开始写。
- 必须写 `case.meta`：`source=<tutorial 相对路径>`、派生时间、需求四元组、改动清单。
- 派生来源必须用 R1 配方 ① 找到，不能凭印象指定。

判定：每个 `cases/*/case.meta` 里的 `source` 路径必须真实存在。

---

## R4 · 声称「可运行」前必须过门禁　【硬规则】

「可运行」= G1–G3 全过（G4 用于「产物可用」）。**agent 的自述不算证据**，
必须是命令输出：退出码 + 关键日志行。

- G1 结构 / G2 `checkMesh` 含 `Mesh OK.` / G3 短跑无 `FOAM FATAL` 且退出码 0。
- 判定脚本 `scripts/verify_case.sh`（M1 交付）；未实现前逐条手跑并把输出贴进报告。
- **禁止**把「我检查了字典，看起来对」当作通过。

---

## R5 · 前处理边界　【硬规则】

只允许两条路：**blockMesh**（几何可用 <20 行 `vertices`/`blocks`/`boundary` 写清）
或 **导入外部网格**（`gmshToFoam` ascii .msh / `fluent3DMeshToFoam`）。

遇到曲面、多体装配、需要边界层加密、需要 STL → **停下问用户**，不要尝试
`snappyHexMesh`、不要自己生成 CAD、不要写脚本操作 STL。

导入网格后必须读 `constant/polyMesh/boundary` 拿真实 patch 名，再据此写 `0/` 的边界条件。
**禁止假设** `inlet`/`outlet`/`wall` 存在。

---

## R6 · 数字必须实测　【硬规则】

报告中出现的任何数字（网格量、耗时、残差、内存、文件数）必须来自命令输出或落盘文件，
并注明来源命令。**禁止估算、禁止从记忆里取、禁止「大约」。**

批量结果一律从 CSV 重算（R7），不从日志肉眼摘。

---

## R7 · 批量运行产物必须落盘　【工程约定】

- 每例一个目录：`runs/<批次>/<case_id>/`，内含 `log.checkMesh`、`log.shortRun`、`log.run`。
- 汇总写 `runs/<批次>/results.csv`，列固定为 **R12 的 15 列**（R12 是唯一列定义，`task_id` 填 `case_id`）；逐例额外指标写 `runs/<批次>/<case_id>/metrics.json`，**不进 CSV**。
- 默认串行；要并发时显式给 `--jobs N`，本机内存有限（历史 OOM 事故），N ≤ 2 起步。
- 结论必须能从 `results.csv` 重算出来；报告里贴的每个汇总数字要能指到某几行 CSV。
- 跨项目基准用 `bench/results.csv`：同一套 15 列，`arm` 列区分被测对象；列定义见 R12。

---

## R8 · 何时停下问用户　【工程约定】

以下情形不要「先做了再说」：

1. 需求里缺几何尺寸/流体物性/边界条件中的任一项，且 tutorial 里找不到合理默认。
2. 需要超出 R5 的前处理能力。
3. 需要改系统源码才能实现（只能在用户库实现 → 报告可行性再动手）。
4. G1–G3 连续两轮修不好。
5. 用户需求隐含「结果要准」的验收（本版本只保证能跑，物理正确性需用户给参照）。

提问格式：**先说现象与已试过的动作，再给 2–3 个选项，每项附代价**（时间、风险、做不到什么）。
不要只问「怎么办」。

---

## R9 · 参考库只读，且不是源码事实来源　【硬规则】

**凡涉及 OpenFOAM 源码事实，只能来自 R1 的五个搜索根。`references/repos/` 下第三方代码
不得修改，也不得作为源码事实的证据。**

- 引用第三方代码时必须写成 `references/repos/<repo>/<file>:<line>`，并与 `/opt/openfoam13`
  的引用**分列**，不得混在同一段论证里。
- 机制：第三方代码回答「别人怎么实现」，不回答「本机怎么实现」。真实失效模式是把 Foam-Agent
  的 prompt 当 v13 语法证据，而它写的是 v10 语法（实测 README：容器自带 OpenFOAM v10，
  `--openfoam_target esi-v2006`）。混用会让 R1 的 grep 证据悄悄指到非权威树，且看不出来。
- **门禁**：`scripts/verify_references.sh` 的 G-R9-1 —— 登记表里每个 `full` 行的仓库
  `git -C <local_path> status --porcelain` 必须为空。
  （**不要用 mtime 判**：把参考库复制或解包到别的目录后，每个文件都晚于 `registry.csv`，
  实测 1791 个文件全部误红。判据要能表达「没被我们改过」这件事本身，git 自己就能表达。）

---

## R10 · 下载红线与强制登记　【硬规则】

**单项目 ≤100 MB（`du -sm` 实测，不看 GitHub 报的 size）；自研智能体可放宽至 200 MB。**

- 超线只有一条出路：只做文档级分析——`mode=docs_only`、`local_path` 留空、note 写明读了哪些
  文档（README / 论文 / 文档站）。**不得以下载一部分冒充已下载**：缺目录而不自知，会让后面
  所有架构判断建立在「被删掉的目录不存在」这个错觉上。
- 每次下载必须在 `references/registry.csv` 追加一行，列固定：
  `project_id, kind, source_url, commit_sha, size_mb, license, declared_of_version, tier, mode, local_path, note`
- 机制：没有 sha 的下载不可复现，也无法证明没被本地改过；GitHub 的 `size` 是 KB 级打包估算，
  含 notebook 输出与数据时与检出体积可差一个数量级。
- **门禁**：`full` 行的 `commit_sha` == `git -C <local_path> rev-parse HEAD`；`size_mb` == `du -sm`；
  `docs_only` 行的 `local_path` 必须为空且 note 非空。

---

## R11 · 单一 OpenFOAM 版本　【硬规则】

**不安装、不下载、不调用第二份 OpenFOAM**（apt / docker / conda / spack / 源码编译一律不行）。

第三方项目要求别的版本时只有两条路：本阶段只登记 `tier`（A/B/C）不做适配；下阶段做
「命令级适配到本机 v13」并把该臂结果标 `partial`。

- 机制：两个版本共存会让所有「能跑 / 不能跑」的判定失去意义——同一条 README 在两个版本下
  结论相反；且与 R2「系统树是唯一权威」直接冲突。
- **门禁**：`ls -d /opt/openfoam*` 只有 `openfoam13`；`docker images | grep -i openfoam` 为空。

---

## R12 · 基准跑必须预注册；设计期禁跑　【工程约定】

**设计期只写框架、不跑任何被测项目；进入实跑前 `bench/preregistration.md` 必须先冻结。**

- 冻结内容（六项，缺一项不算冻结）：主指标 / 次指标 / 结果状态 / 判定规则 / **作废条件** / 每臂预测。
  **分段冻结允许**（方法学先冻、每臂预测可等实现后补填），但必须在冻结记录里写明，否则后人会误读。
- 结果状态**七态**：`pass | fail | no_artifact | malformed | blocked | overclaim | declined`。
  二值会把「什么都没产出」算成答错；缺 `declined` 则分不清「正确地拒绝」与「崩溃了什么都没交」。
- 主指标分母固定 **11**（T12 负对照不进分母：它的正解是"拒绝"，与"建成 case"语义相反）。
  每任务跑 **3 次**取多数；三次各异 → `malformed` + `unstable=1`。
- **门与断言是两层**：G1–G5 只判"能不能跑、有没有越界"；`expect_values` 判"需求有没有被满足"
  （只有门时，`T05 写盘间隔 100→50` 这类任务什么都不改也能 pass）。断言三态
  `match | mismatch | undeterminable`，`undeterminable` **只能**映射到 `malformed`。
- 结论只能从 `bench/results.csv` 重算，列固定：
  `task_id, arm, status, g1, g2, g3, g4, g5, g2b, repeats, unstable, tokens_total, wall_time_s,
  human_interventions, note`。`g2b` 是**辅助信号不是门**（`none|soft:N|hard:N|unknown`），不参与 `status`。
- **门禁**（`bash scripts/verify_references.sh --frozen`）：
  · `G-R12-1` 预注册 mtime 早于 `bench/runs/` 首个文件；有数据后 `status` 列须 ≥3 种取值
    （只出现两种 = 判定被简化成二值）；0 行数据不算违规（否则冻结当天必红，等于逼人跳过）。
  · `G-R12-2` `sha256sum -c bench/tasks/FROZEN.sha256` 必须 15/15 OK。清单含 12 个任务 yaml
    **以及** `bench/assert_lib.py`、`bench/selftest_expect.py`、`scripts/status_snapshot.py`：
    只钉任务不钉尺子，等于允许冻结后放松判据而门禁不知道。
  · `G-BENCH-1` `bench/selftest_expect.py` 必须 `checked=12 failed=0` —— 抓"文件被动过之后仍然合理"。

> **判据细节不在这里，逐条指到 `bench/preregistration.md`（已冻结，`G-R12-2`/`G-R12-3` 守着它）：**
>
> | 细节 | 在哪 |
> |---|---|
> | 「为什么 R4/R6 管不住跨臂比较」的机制（04 实测：单查询 18% vs 端到端 7/7） | §0 |
> | `***` 被 v13 刻意排除的 4 处源码行（`checkGeometry.C:902/924/950/978`） | §5 |
> | 断言实现的五条硬约束（`-entry` 只解析顶层、顶层标量要 `-value`、剥 `[...]`、不对原始文件做字符串断言、几何用无量纲比值） | §5.5 |
> | 判定规则的非退化守卫（`x <= k*y` 两侧皆 0 时为真，必须显式判 `no_data`） | §8 |
> | judge 的七态归约与 M-d 短路 | §11 |

---

## R13 · 根目录 STATUS.md 是接续点　【工程约定】

**`STATUS.md` 是给新会话（上下文清空 / 自动压缩之后）的接续点。任何会让自己失忆的动作之前必须先刷新它。**

- **刷新时机**（任一触发）：① 用户说「准备清空上下文」；② 察觉已发生压缩；③ 一个阶段收尾。
- **刷新动作**：`python3 scripts/status_snapshot.py --write` + 改写 `NARRATIVE` 段。
  机器段由脚本生成、**禁止手改**（手写数字会腐坏，且腐坏时没有东西会红）。
  分工判据：能被命令测出来的进机器段，需要判断的（在哪一步 / 为什么 / 下一步 / 缺口）进 NARRATIVE；
  **同一句话只许出现在一处**，重复必然漂移。
- **门禁**：`G-R13-1` —— `status_snapshot.py --check` 重算机器段、逐行指出过期项，退出码 0。
  R13 本身是 L0 规则（靠记忆触发，Hermes 没有 pre-compaction hook），**真正的护栏是这道门**：
  「忘了刷新」会在下一次跑门时变红，而不是静默腐烂。

---

## R14 · 文档维护：一处写值，其余引用　【工程约定】

**每类信息只有一个「写值处」，其它位置写指针（路径 + 章节号），不复述值。** 信息类 → 维护位置
的全表与「改了什么才更新哪份」的判据见 `references/13-maintenance.md` §2–§3；本节只写规则。

- **按影响更新**：只有**改变了某份文档描述的事实**时才编辑它。没改变某份文档描述的事实时，
  不要求编辑它；「每次改动同步全部文档」不是本项目的规则。
- **当前状态只在 `STATUS.md`**（N1 现在哪一步 / N4 下一步 / N11 轮次记录）。`specs/001/tasks.md`
  是 v0.1 执行记录、`CHANGELOG.md` 是版本历史——两者都不表达当前进度。
- **状态记录六字段**：任务 / 被测版本或工作树状态 / 实际验证命令 / 结果 / 未验证项 / 下一步。
  缺任一不算记录（模板与实例见 13 §4 与 `STATUS.md` N11）。
- **局部改局部验**：单点改动只跑它自己的检查（13 §5 表）。**接口变更、模块集成、阶段交付**才做
  全局一致性审查；`make_export.sh` 从 `HEAD` 组树，看不见未提交的改动。
- **迁移不删要求**：内容换位置时保留原句与出处（删除线 + 日期 + 指向），旧验证记录保持过去时，
  **不改写成「当前已通过」**。

---

## R15 · 二次开发只能派生 + 最小差异　【硬规则】

**改 OpenFOAM 的类（模型 / 边界条件 / 函数对象 / 子库）只能「派生副本 + 最小差异」，不许从零手写
源文件，也不许改系统树。**

- **派生源**：`cp -a` 自 `$FOAM_SRC` 或 `$FOAM_APP` 下**带 `Make/files` 的最小子库**到
  `$WM_PROJECT_USER_DIR/src/<名>`（R2）；新库名不得与 `$FOAM_LIBBIN` 里已有库同名。
- **改动白名单**：动手前先把「打算改哪几个文件」写进副本根的 `dev.meta.allowed_files`（glob），
  之后再改；落在白名单外的增/删/改一律算越界（判据：`scripts/dev_lib.py --stage check` → `86`）。
- **说「库可用」必须先过四关**：`scripts/dev_lib.py` 的 `prepare / check / build / verify`
  （退 `85`–`89`），证据是命令输出——`.so` 落在 `$FOAM_USER_LIBBIN`、
  `foamRun -libs "lib<名>.so"` 输出里 `dlopen error` 计数为 0、`$WM_PROJECT_DIR` 下没有比
  `build-stamp` 更新的文件。该脚本落地前按同四条判据手工核并贴命令输出（v0.3 开发期条款）。
- **只保证编译与加载**：物理正确性不在本规则范围内（同 `release/SKILL.md` §8「不保证什么」）。

**为什么是硬规则**：`Make/options` 里的相对 `-I` 在副本里指向不存在的目录（实例：
`applications/modules/multiphaseEuler/populationBalance/Make/options:2` 的 `-I../phaseSystem/lnInclude`），
`wmake` 会立刻失败；而「看起来能编译」的手写 C++ 会产出**能编译但语义错**的库，门禁全绿——
比编译失败贵得多。完整流程与判据（S0–S6 / V1–V4）见 `references/14-library-dev-flow.md`。

---

## 附 · 本文件的读者边界

本文件随开源代码发布，但仓库里有一批文件**不发布**（`STATUS.md`、`specs/`、`dist/`、`.hermes/`、
`references/repos/`）。哪些不发布、为什么、以及对使用者有什么实际影响，见
`references/11-delivery-form.md` §14 —— 那份文档是公开的，本文件不再重复一遍表格
（重复的表必然漂移，`.gitignore` 才是权威表达）。

与 04_RAG_HMS 的关系（本项目前一次实验、以及从它继承的两条方法论）见
`references/07-theory-provenance.md` §7。
