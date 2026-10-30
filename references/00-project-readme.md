# FOAM Agent — 项目内部说明（研发视角；不是仓库首页，首页见根 `README.md`）

**一句话**：agent 把自然语言翻成 OpenFOAM 的字典文本与命令；脚本只负责两件 agent 做不稳的事——
判定「能不能跑」和批量调度。

- 版本：v0.2（脚本层 9 个用户面 CLI，含批量运行与 2D 网格导入；本文保留为设计记录。
  v0.3 增至 10 个：新增二次开发 `scripts/dev_lib.py`（派生 / 判范围 / 编译 / 加载证明），
  本节以下仍是 v0.2 当时的记录，不改写）
- 目标环境：OpenFOAM v13 (Foundation)，`/opt/openfoam13`，`source /opt/openfoam13/etc/bashrc`
- 本机 build：`13-441953dfbb42`
- 规则见 `AGENTS.md`（其中 R1 是硬规则：源码检索强制 grep）

> **本文是设计阶段的记录，不是现状快照**：它停在 v0.2 交付之前，只回答「当初为什么这样设计」。进度与缺口看 `STATUS.md`，对外能力与限制看根 `README.md`；v0.2 的 `batch.py` / `msh2d_to_foam.py` 与基准实跑（`references/12-bench-report.md`）不在本文正文与 §7.1 索引里。

## 0. 环境事实（已实测，勿凭记忆改写）

| 事实 | 值 | 怎么核实的 |
|---|---|---|
| 求解器形态 | **module-based**：一个可执行 `foamRun`，case 在 `system/controlDict` 里写 `solver <module>;` | `ls $FOAM_APP/solvers/` → 5 个（foamRun、foamMultiRun、boundaryFoam、chemFoam、potentialFoam）；`grep -n solver $FOAM_APP/solvers/foamRun/foamRun.C` |
| 两代路径并存 | **主线** = `solver <module>;` + `foamRun`（`controlDict` 有 `solver` 条目）<br>**legacy** = 直接调可执行（`runApplication icoFoam`，`controlDict` **无** `solver` 条目） | `grep -n solver $FOAM_TUTORIALS/incompressibleFluid/cavity/system/controlDict` → 命中<br>`grep -n "application\|solver" $FOAM_TUTORIALS/legacy/incompressible/icoFoam/cavity/cavity/system/controlDict` → **空**；`grep -n icoFoam .../Allrun` → 命中 |
| 求解链已实测 | cavity 上 `blockMesh` (exit 0) → `checkMesh` (**`Mesh OK.`**) → `foamDictionary -entry endTime -set 0.02` → `foamRun` (exit 0，无 FATAL) 全部通过 | 2026-10-27 实跑，见 §6 门禁 |
| 模板库规模 | **252 个** case（含 `system/controlDict`），103 MB；其中主线 **231**、`tutorials/legacy` **21** | `find $FOAM_TUTORIALS -name controlDict -path "*/system/*" \| wc -l` = 252；加 `\| grep -c /legacy/` = 21 |
| 三种运行入口 | `solver <名>;` → `foamRun`（主线 199 例）<br>`regionSolvers` → `foamMultiRun`（`multiRegion/*` 等多区域）<br>两者皆无 → 纯网格 case（`mesh/*`），只跑 `blockMesh` 等 | `grep -n "^solver\|^regionSolvers" <case>/system/controlDict`；`grep -n runApplication <case>/Allrun` |
| 源码规模 | 75 MB | `du -sh $FOAM_SRC` |
| 网格工具 | `checkMesh`、`blockMesh`、`decomposePar`、`topoSet`、`setFields`、`createPatch`、`foamCloneCase` 均在 PATH | `command -v <名>` |
| 外部网格导入 | `$FOAM_UTILITIES/mesh/conversion/`，含 `gmshToFoam`（只读 ascii .msh）、`fluent3DMeshToFoam` 等 | `ls $FOAM_UTILITIES/mesh/conversion/`；`grep -n "ascii msh" .../gmshToFoam.C` |
| 字典改写 | `foamDictionary -entry <name> -set <value> <file>`（另有 `-value/-remove/-add/-merge/-expand`） | `foamDictionary -help` |
| 并行 | `decomposePar` → `foamRun -parallel` → `reconstructPar` | `foamRun -help \| grep parallel` |
| 二次开发输出 | `$FOAM_USER_LIBBIN` = `$WM_PROJECT_USER_DIR/platforms/<platform>/lib` | 目录由首次 `wmake libso` 建出；流程见 skill `openfoam-library-development` |
| 检索工具 | `rg` 15.2.0 可用（`grep -rn` 等价可用） | `rg --version` |

**v13 的 case 骨架**（以 `tutorials/incompressibleFluid/cavity` 为实测样本）：

```
0/            p U k epsilon omega nut ...      （场文件，边界条件写在这里）
constant/     momentumTransport  physicalProperties  polyMesh/
system/       controlDict  fvSchemes  fvSolution  blockMeshDict
```

---

## 1. 能力范围（本版本）

| 任务 | 用户输入 | 产物 | 边界 |
|---|---|---|---|
| **建 case** | 「一个二维方腔，顶盖 1 m/s，水，层流」 | 可 `checkMesh` + 可短跑的 case 目录 | 见 §2 前处理限制 |
| **改 case** | 「把雷诺数提到 1e5」「改成 k-ω SST」「时间步减半」 | 改后的 case + 一个 diff 说明 | 只改字典，不重写物理 |
| **二次开发** | 「给 Dahneke 凝并模型加一个系数」 | 用户目录里的 `.so` + 加载它的 case | 不改 `/opt/openfoam13` |
| **批量运行** | 「D=45/90/120 三组各跑一次」 | `results.csv` + 每例日志目录 | 本机串行或 N 并行 |

### 本版本明确不做

- **自动前处理**：不做 STL/CAD 处理、不做 `snappyHexMesh`、不做网格质量自动优化。
  前处理只允许两条路（§2）。
- **不造检索层**：不建索引、不做向量检索、不做 MCP。
  04_RAG_HMS 已用 36 跑三臂实验实测否决（`reports/.orchestrator/project-conclusion.md`）：
  与 grep 命中打平（各 7/7），token 只省 5.2%，却要多 98 MB 索引并绑死语料版本。
- **不做 GUI / Web**。
- **不自动判定物理正确性**：agent 保证「跑得起来、边界条件齐全、场可读」，
  不保证「结果与实验一致」——那需要用户给参照。

---

## 2. 前处理边界（两条路，其余一律停下问用户）

| 路径 | 适用 | 命令链 |
|---|---|---|
| **A. blockMesh** | 简单几何：长方体/管道/台阶/二维挤出；全部可由 `vertices`/`blocks`/`boundary` 手写 | 写 `system/blockMeshDict` → `blockMesh` → `checkMesh` |
| **B. 外部网格导入** | 用户已有网格文件 | `gmshToFoam <file>.msh`（ascii）或 `fluent3DMeshToFoam` → 用 `read_file` 读 `constant/polyMesh/boundary` 拿真实 patch 名 → `checkMesh` |

判定线：**几何能否用不到 20 行的 blockMesh 描述完**。超出（曲面、多体装配、边界层加密）
→ 停下，告诉用户「本版本不支持，请提供网格文件或降级几何」。

---

## 3. 三条设计原则

**P1 · LLM 做翻译与决策，脚本做判定与调度。**
写字典是文本工作，agent 直接写；但「能否运行」必须由命令输出判定，不能由 agent 声称。

**P2 · 一切 case 从最近的 tutorial 派生，不凭空生成。**
231 个主线 tutorial（另有 21 个 `tutorials/legacy` 不用）是现成的、与 v13 同步的模板。
凭空写字典是幻觉的主要来源。派生必须记录来源（`case.meta`：源路径、派生时间、改了什么）。

**P3 · 源码是唯一权威，用 grep 查。**
网上教程多为 v2012/esiu 语法，与本机 v13 差异大。两个具体后果：

- v13 主线把求解器收成一个 `foamRun` + `controlDict` 里的 `solver <module>`，
  照旧教程写「装 icoFoam 那样用」会写错；虽然 `applications/legacy/` 里还编译了 `icoFoam`
  等旧可执行，`tutorials/legacy/` 也有成套旧 case，但**本项目只用主线路径**
  （理由：主线 tutorials 与 module 同步更新，legacy 目录是历史包袱，且其 case 有
  `cavity/cavity/` 这种双层嵌套，派生时容易踩错层级）。
- 判断一个 tutorial 怎么跑（三步，别猜）：
  `grep -n "^solver" <case>/system/controlDict` → `foamRun`；
  `grep -n "^regionSolvers"` 命中 → `foamMultiRun`；
  两者皆空 → 纯网格 case（`mesh/*`）或 legacy，看 `Allrun` 里的 `runApplication`。

凡涉及源码事实 → `AGENTS.md` R1。

---

## 4. 架构：三层，没有第四层

```
┌─ 知识层 ─────────────────────────────────────────────┐
│ tutorials/（231 主线例，找用法）  src/（75 MB，找定义）  │
│ 取用方式：grep（R1）。无索引、无缓存、无预处理。        │
└──────────────────────────────────────────────────────┘
┌─ 动作层 ─────────────────────────────────────────────┐
│ 建：foamCloneCase / cp -r  → agent 改字典 → blockMesh │
│ 改：agent 编辑 + foamDictionary -entry -set           │
│ 开发：cp 到 $WM_PROJECT_USER_DIR/src → wmake libso    │
│ 批跑：batch.py（见 §5.4）                             │
└──────────────────────────────────────────────────────┘
┌─ 门禁层 ─────────────────────────────────────────────┐
│ G1 结构 · G2 网格 · G3 短跑 · G4 产物可读（见 §6）     │
│ 由 verify 脚本执行，返回退出码。agent 无权跳过。       │
└──────────────────────────────────────────────────────┘
```

**为什么是三层而不是四层**：04 的教训是「多加一层抽象多半是在替 agent 干它本来能干的事」。
检索层被否决；MCP 被否决（`reports/2026-10-25-agent-call-interface-decision.md`）；
向量通道被否决（`reports/2026-10-25-vector-channel-decision-test.md`）。保留的三层各自有
不可替代的职责：知识层是事实来源，动作层是 OpenFOAM 原生命令，门禁层是可判定的失败信号。

---

## 5. 四条任务链

### 5.1 建 case

```
1. 需求 → 抽四元组：几何 / 流体物性 / 边界条件 / 求解目标（稳态|瞬态）
2. grep $FOAM_TUTORIALS 找最接近的 case（grep 配方见 AGENTS.md R1）
3. foamCloneCase <源> <目标>
4. 写 case.meta（源路径、四元组、改动清单）
5. blockMesh（路径 A）或导入（路径 B）
6. verify：G1 → G2 → G3
7. 向用户报告：几何尺寸、网格量、边界条件表、短跑残差
```

### 5.2 改 case

```
1. 把需求翻成「哪个文件、哪个 entry、改成什么值」
2. 对每个 entry：先 grep 确认它在 tutorials/src 里的确切拼写与量纲
3. foamDictionary -entry X -set "Y" <file>（或直接编辑）
4. 重跑 G2（若动了几何）→ G3
5. 输出 diff（内容差异，不是行数）
```

### 5.3 二次开发

完整流程在 skill `openfoam-library-development`（已在 cfd 分类，多次实测）。要点：

```
cp -r $FOAM_SRC/.../<模块> "$WM_PROJECT_USER_DIR"/src/
改 Make/files: LIB = $(FOAM_USER_LIBBIN)/lib<名>Mod
wmake libso -j
case 的 controlDict 里 libs ("lib<名>Mod.so");
```

门禁额外要求：**A/B 对照** —— 同一 case 分别用系统库与用户库跑，
系数取默认值时必须结果一致，改系数才允许有差异。防止改错文件还自我感觉良好。

### 5.4 批量运行

```
cases.json（参数矩阵） → batch.py → cases/<组>_<参数>/ 每例一个目录
                                  → 每例 verify(G1..G3) → foamRun → results.csv
```

`results.csv` 列：`case_id, g1, g2, g3, status, wall_time, key_metrics...`。
**汇总数字一律从 CSV 重算**，不从日志肉眼摘。

---

## 6. 门禁（可判定，退出码语义）

| 门 | 判据 | 命令 |
|---|---|---|
| **G1 结构** | `system/{controlDict,fvSchemes,fvSolution}` 存在；`0/` 非空；`constant/` 有对应物理字典 | `test -f` 三连 + `ls 0/ \| wc -l` |
| **G2 网格** | `checkMesh` 输出含 `Mesh OK.` | `checkMesh -case <c> > log.checkMesh 2>&1; grep -q "Mesh OK." log.checkMesh` |
| **G3 短跑** | 步数缩到 2–3 步跑完，退出码 0，日志无 `FOAM FATAL` | `foamDictionary -entry endTime -set <小值> system/controlDict` → `foamRun -case <c> > log.shortRun 2>&1` → `grep -q "FOAM FATAL" log.shortRun && fail` |
| **G4 产物可读** | 末时刻目录存在；每个场 `foamDictionary` 能读；无 `nan`/`inf` | `foamDictionary -entry internalField -value <末时刻>/U \| head -1` 非空（实测输出 `nonuniform List<vector>`）；`grep -ril "nan\|inf" <末时刻>/` 为空 |
| **G5 范围**（本框架新增，唯一新增门） | 只允许改动 `allowed_files` 内；改动 `constant/polyMesh/` 必须在 `case.meta` 里写理由 | `git diff --no-index --name-status -- base case`（有 `base/` 时）或按 mtime 列改动文件，与 `allowed_files` 求差 |
| **G2b 辅助信号**（**不是门，不参与 pass/fail**） | 数 `log.checkMesh` 里以 `***` 开头的行；配合 G2 结果分类 | `grep -cE '^\s*\*\*\*' log.checkMesh` → `N=0` 记 `g2b=none`；`N>0` 且 G2 过 → `g2b=soft:N`；`N>0` 且 G2 未过 → `g2b=hard:N`；日志缺失 → `unknown` |

**G2b 为什么有用（R1 核实过的机制，2026-10-28 修正）**：

**① `Mesh OK.` 与失败计数一一对应。** `$FOAM_SRC/functionObjects/utilities/checkMesh/checkMesh.C:160`–`163`
是 `if (nFailedChecks == 0) { Info<< "\n    Mesh OK.\n" }`，所以**打印 `Mesh OK.` ⟺ `nFailedChecks == 0`**。
这一层是硬的：G2 用 `grep "Mesh OK."` 判，判的就是 checkMesh 自己的总账。

**② 但退出码不可用。** 同一文件 `:180` 的 `return nFailedChecks == 0` 是**函数对象 `execute()` 的返回值**，
不是进程退出码；可执行文件没有把它变成 `exit()`。实测（`<scratch>/g2bt`，一个为验这条而建的临时算例）：

```
$ checkMesh > cm.log 2>&1; echo $?
0
$ grep -c 'Mesh OK.' cm.log
0
$ grep Failed cm.log
Failed 1 mesh checks.
```

**退出码 0 + 网格不合格 + 没有 `Mesh OK.`** 三者同时成立。所以 G2 **必须** grep `Mesh OK.`，
一旦有人把它"优化"成看退出码，所有不合格网格都会放行。这是本项目最贵的一条教训：
`references/09-architecture-and-test-plan.md` 的 E-full 测试里专门有一条守它。

**③ `g2b=soft` 在 v13 观测不到，是防御性分支。** 原文档称"4 项豁免检查会打印 `***` 但 `Mesh OK.` 照出，
因而 `g2b=soft`"。**这条是错的**：那 4 项**不打印 `***`**。证据两条：

- **源码**：`$FOAM_SRC/meshCheck/checkGeometry.C` 里 `noFailedChecks++` 被注释掉的只有 `:902` checkEdgeLength /
  `:924` checkPointNearness / `:950` checkFaceAngles / `:978` checkFaceFlatness 四处；
  逐块查 `***` 出现次数 = **0**（它们打印的是 `There are N ...` 形式，无星号前缀）。
  且全 `meshCheck` 目录里被注释掉的失败计数**仅此 4 处**。
- **实测**：扫描全部 **208** 个自带 `system/blockMeshDict` 的 tutorial（逐个 `cp -a` →
  `blockMesh` → `checkMesh`，数 `Mesh OK.` 与 `^\s*\*\*\*`）：
  **`Mesh OK.` 与 `***` 共存 0 例**；none=182、仅 `***` 无 `Mesh OK.`=8、两者皆无=18（网格没建成）。

结论：凡是 `***` 都伴随计入失败 → `Mesh OK.` 消失 → `g2b=hard`。`g2b=soft:N` 作为**预注册定义的取值**
保留（判据不能因为"观测不到"就删掉一个状态，否则真出现时会被误记成 `malformed`），
但它在 v13 下**不可达**，出报告时若真出现应先怀疑判定器而不是网格。

实测（2026-10-27 首测，2026-10-28 补扫；本机 v13。前三行产物在
`<scratch>/meshsig`，全库扫描在 `<scratch>/g2bscan2/result.tsv`）：

| 样本 | `***` 行数 | `Mesh OK.` | `Failed N` | 归类 |
|---|---|---|---|---|
| `cavity` 原样 `(20 20 1)` | **0** | 1 | 0 | none |
| 改成 `(2000 1 1)`，aspect ratio 2000 | **1** | 0 | 1 | hard |
| 顶面顶点内推 0.02（边不对齐 400 条） | **1** | 0 | 1 | hard |
| z 厚度压到 1e-4（均匀变薄） | 0 | 1 | 0 | none（阈值按包围盒相对，薄而不算短边） |
| 软分支 | — | — | — | **不存在**：208 个 tutorial 全扫，`Mesh OK.` 与 `***` 共存 0 例（见上文 ③） |

> **不要照抄 ai-cfd-scientist 的白名单。** 它把 `high aspect ratio` 当良性过滤掉
> （`references/repos/ai-cfd-scientist/src/cfd_langgraph/foam_native/loop.py:63`），但在 v13 里
> 该项**会计入失败**：实测 aspect=2000 时 `***High aspect ratio cells found` 伴随
> `Failed 1 mesh checks.`、且 `Mesh OK.` 不再出现。照抄会让 G2 漏判一个真实不合格网格。


> **门只判「能不能跑」，不判「改对了没有」。** 基准框架另有 `expect_values` 断言层
> （`bench/assert_lib.py`），两者正交：G 全过 + 断言 match → pass；G 全过 + 断言 mismatch → fail
> （能跑但改错了）。没有断言层时，「把写盘间隔从 100 改成 50」这类任务里 agent 什么都不改也会 pass。
> 详见 `bench/preregistration.md` §5.5。
>
> **结果状态七态**：`pass | fail | no_artifact | malformed | blocked | overclaim | declined`。
> `declined` 只用于 T12 负对照（正确行为是拒绝，不是交付）。

> 四道门已在 cavity 上逐条实跑通过（2026-10-27）。**patch 完整性不单独设门**：
> 只要 `0/` 里缺某个 patch 的边界条件，G3 一定 FATAL，不必重复检查。
> 注意 `foamDictionary -entry boundary -keywords constant/polyMesh/boundary` 会报
> `Cannot find entry boundary`（boundary 文件是特殊格式），这条命令**不要用**。

G3 是真正抓 bug 的那一道：G1/G2 全过而 solver 因字典缺失启动失败的 case 很常见。

**退出码**：`0` 全过 / `1` G1 / `2` G2 / `3` G3 / `4` G4 / `5` G5；**只报第一个失败的门**。
批跑按码分桶统计。**`64` = 用法错误或前置不满足**（参数非法、case 目录不存在），
不属于门结果。`64` 不用 `2` 的原因：`2` 已经是「G2 网格门失败」，
若用法错误也用 `2`，调用方无法区分「我参数写错了」与「这个算例网格没过」——
两者处置相反。该约定对**全部**脚本统一（`tests/unit/test_exit_codes.py` 守）。

**G1 与 G5 前置**（`--stage pre`，不跑任何 OpenFOAM），G2–G4 后置（`--stage post`）：
结构或范围不对时不必白跑一次网格。依据见 `references/09-architecture-and-test-plan.md` §1.2 与 D4。

---

## 7. 目录布局

```
05_FOAM_Agent/
├── STATUS.md              **接续点**：新会话（清空/压缩后）先读这个（R13）
├── README.md              本文件（框架）
├── AGENTS.md              规则（R1 grep 强制；R9–R13 参考库/下载/版本/预注册/接续点）
├── cases/                 生成的 case，每个带 case.meta
├── runs/                  批跑批次：runs/<批次>/<case_id>/{log.*, results}
├── references/            第三方参考库（只读，见 R9/R10）
│   ├── search-protocol.md   检索式、去重规则、tier 判定、门禁（可复现）
│   ├── registry.csv         project_id/commit_sha/size_mb/declared_of_version/tier/mode…
│   ├── 01-landscape.md      领域调研（论文全池 + GitHub 候选 + 与本项目对照）
│   ├── 02-architectures.md  逐项目架构分析（11 段模板 + 成功判据专项）
│   ├── 03-evidence-audit.md 证据审计：**现在能说什么、不能说什么**（十条禁用主张）
│   ├── 04-harnessfoam-deepdive.md 唯一 v13 原生参照物的代码级解剖（40 条 02 主张逐条验证）
│   ├── 05-cross-project-matrix.md 横向矩阵 + 8 条稳定架构的 K/E/V 三档评级
│   ├── 06-agent-anatomy.md  代码级部件清单（11 部件 + 最小骨架 6 件）
│   ├── 07-theory-provenance.md 理论溯源 + 9 条已排除的形似配对
│   └── repos/               已下载的第三方代码（≤100 MB/项目，只读）
├── bench/                 跨项目基准（设计期禁跑，见 R12）
│   ├── preregistration.md   预注册：**已冻结 v1.0**（指标/七态/判定/作废条件/断言规范/未定项）
│   ├── tasks/               12 个任务定义（T01–T12，含 expect_values）
│   │   └── FROZEN.sha256    冻结清单（15 个文件 = 12 任务 + assert_lib + selftest_expect + status_snapshot）
│   ├── assert_lib.py        断言取值（六种 kind × 三态结局，judge 的唯一取值入口）
│   ├── selftest_expect.py   断言自证（只跑 tutorial 副本，不碰被测臂）
│   ├── judge.py             七态归约（只汇总闸门与断言的结论，零 OpenFOAM 依赖）
│   ├── selftest_judge.py    七态归约的合成自测（12 fixture + 3 多数归约 + 1 断言三态；G-JUDGE-1）
│   ├── adapters/            B 档项目的命令级适配（M4b）
│   ├── runs/                实跑产物（M4a 必须为空）
│   └── results.csv          汇总，比 runs/ 多 arm/repeats/unstable/g2b 列
├── scripts/
│   ├── new_case.sh        从 tutorial 派生 + 写 case.meta（M1）
│   ├── verify_case.sh     执行门禁：--stage pre 判 G1/G5（零 OpenFOAM）、--stage post 判 G2–G4
│   ├── parse_requirement.py  需求→四元组（校验器；LLM 接入时只换提取器）
│   ├── find_template.sh      五根 grep 检索（FOUND=总数 / SHOWN=输出行数）
│   ├── tests/                L1 tests/unit（零 OpenFOAM）+ L2 tests/contract（需 OpenFOAM）
│   ├── batch.py           读 cases.json → 派生 → 跑 → results.csv（M2）
│   ├── status_snapshot.py 生成/校验 STATUS.md 机器段（R13；--write / --check）
│   └── verify_references.sh 九道门一次跑完（R9–R13 + 文档引用 + 断言自证）
├── release/               对外交付内容源：SKILL.md（入口文档）+ QUICKSTART.md + SCOPE.md
├── specs/                 本轮 speckit 产物：001-release-a-harness/{spec,plan,tasks}.md
└── dev/                   二次开发的用户库源码副本（M2）
```

不建 `docs/`、不建 `templates/`（tutorials 就是模板库）、不建 `src/`（不是 Python 项目）。
**`release/` 不是 `docs/`**：前者是对外交付物的**源**（由 `scripts/make_release.sh` 组装进 `dist/`，
只有白名单文件进包），后者是内部文档目录——混在一起会让「什么被发出去」不可判定。

### 7.1 调研与设计文档索引（03–11 各回答什么问题）

`01`–`02` 是「这个领域有什么」，`03`–`07` 是「我们能据此说什么」，`08` 是把 01–07 压成一页的对外交付版，
`09` 是由 08 派生的设计文档（模块划分 + 测试设计，产生设计决策而非领域事实），
`10` 是 `09` 的配套缺口清单（「文档说要、实测没做到」的条目 + 每条的判据与验收命令）。
**引用顺序有依赖**：
先 `03`（许可证）→ 再看 `04`（一手证据）→ 再 `05`（横向）→ 最后 `06`/`07`（综合与溯源）。
逆向引用（例如拿 `06` 的部件去反驳 `03` 的禁用主张）不算证据。

| 文件 | 回答什么 | 不能用来做什么 |
|---|---|---|
| `03-evidence-audit.md` | 五条已知缺口的对账、E0–E4 证据分级、**十条禁用主张黑名单**、三问各自的最高可答级别 | 它不产生新知识，只发许可证；它没有复核 02 的每一条主张 |
| `04-harnessfoam-deepdive.md` | 唯一 v13 原生参照物（tier A）的代码级解剖；**02 的 40 条主张逐条判「证实/证伪/无法验证」** | 它是单项目解剖，不能推广成「行业做法」；「它没做的事」不等于「不需要做」 |
| `05-cross-project-matrix.md` | 12 项目 9 列主表；8 条稳定架构的 **K（收敛度）/ E（证据强度）/ V（版本无关性）** 三档评级，每条带反例 | **不出跨项目比较、不出排名**——A 档只有 1 个，退化路径已在预注册冻结时生效 |
| `06-agent-anatomy.md` | 代码层面的 11 个部件（职责/输入/输出/失败模式/确定性归属）+ 数据流 + 最小骨架 6 件 | 是结构清单，不含「哪个部件更重要」的绩效主张；K=1 的部件不算被验证过 |
| `07-theory-provenance.md` | 每条架构的来源级别（**L1-学术 / L1-工程 / P-实践 / L2 同构**）+ 9 条**已排除**的形似配对 | 只建立「来源关系」，不建立「效果验证」；L3 条目禁止再被引用为论据 |
| `08-condensed-report.md` | 01–07 的**对外精简版**（三节：领域背景与路线 / 最小骨架 / 理论来源 + 可执行结论 + 不能回答什么） | 不产生新事实；要下钻回 01–07，要现状回 `STATUS.md`；它不是新的证据来源 |
| `09-architecture-and-test-plan.md` | **设计文档（非调研）**：6 部件 + 1 契约层的模块划分、接口契约、L1–L4 测试分层、逐模块测试判据、6 个变异体；含用户三项裁定（G5 进契约 / `human_interventions` 口径 (ii) / 测试放 `tests/`） | 它产生**设计决策**，不是领域事实；判据口径以 `bench/preregistration.md` 为准，冲突时以预注册为准 |
| `10-gap-register.md` | `09` 的**配套缺口清单**：9 条缺口逐条给现状证据（可复现命令）、判据、验收命令；另列 6 条「不算缺口的」防止重复发现 | 它不产生新事实，也不排优先级之外的判断；**缺口状态会变**，引用前先跑该条自己的验收命令 |
| `11-delivery-form.md` | **交付形态决策**：A（工具包 + 入口文档）vs B（自带模型的 CLI）的十维对照、失败形状不对称、三个不可逆点、A 的 6 个发布阻塞项；**已裁决先 A、B 为后续目标** | 它是形态选择论证，不含任何绩效数字；外部文献（`references/external/`）只作方法论证据，**不是 OpenFOAM 源码事实来源**（R9 不覆盖该目录） |

**两条跨文件引用纪律**（都是实测踩出来的）：
1. **引上游文档的「可变量」必须写「行号 + 值」**。`05` 的 K 值被改过一次，只写 `05:104` 的文档会静默过期，任何门禁都不会红。
2. **上游文件被编辑后，所有引用它的下游必须逐条重切**（`sed` 比对语义，不是只看行号有没有越界）。`04` 加一节后整体下移 8 行，曾让 `06` 的 9 条引用集体失效而门禁全绿。


---

## 8. 里程碑

| 阶段 | 交付 | 完成判据（可判定） |
|---|---|---|
| **M0 框架** | 本文档 + `AGENTS.md` | 两份文件存在；R1 配方可逐条复制执行 |
| **M1 单例闭环** | cavity 派生 case + `verify_case.sh` | G1–G5 全过，退出码 0；再跑满一个完整算例（不是 2–3 步短跑）并产出末时刻场 |
| **M2 批跑 + 二次开发** | `batch.py` + `new_case.sh`；一个用户库 | 3 例矩阵产出 `results.csv` 且数字可从 CSV 重算；A/B 对照一致 |
| **M3 自然语言端到端** | 把 5.1/5.2 链固化为 skill | 一条新需求（未见过）从零到 G3 通过，全程无人工改字典 |
| **M4a 调研 + 参考库 + 基准设计**（2026-10-27） | `references/`（01/02/registry/search-protocol）、`bench/`（preregistration + 12 任务 + assert_lib + selftest） | 论文全池每条都有条目；`registry.csv` 每个 `full` 行 sha == `rev-parse HEAD` 且 `size_mb` == `du -sm`；`bench/runs/` 为空；12 个任务的 `reference_tutorial` 全部真实存在；`bash scripts/verify_references.sh` 全过；`python3 bench/selftest_expect.py` → `checked=12 failed=0` |
| **M4b 版本适配 + 实跑** | `adapters/` + runner + 真实 `results.csv` | 预注册冻结早于第一个 `log.*`；≥2 个 A 档臂完成 12 任务；结论数字可从 CSV 重算 |


---

## 9. 已知限制与风险

1. **几何能力上限低**：blockMesh 无法表达曲面与复杂装配。这是刻意的取舍，不是待办。
2. **checkMesh 通过 ≠ 物理正确**：G1–G4 只保证「能跑、边界齐、场可读」。
3. **v13 语法与旧教程不兼容**：必须 grep 本机 sources，R1 就是为这条服务的。
4. **网格导入的 patch 名不可预测**：`gmshToFoam` 后必须读 `constant/polyMesh/boundary`，
   按实际 patch 名改 `0/` 里的边界条件，不能假设 `inlet`/`wall` 存在。
5. **并行与内存**：本机内存有限（历史上有 OOM 事故），批跑需限制并发数，默认串行。

---

## 附 · 本文档在开源仓库里的阅读说明

- 这份文件是**项目内部说明（研发视角）**，不是仓库首页。面向使用者的入口是仓库根的 `README.md`。
- 文中引用的 `STATUS.md`、`specs/`、`dist/`、`.hermes/` **不随开源代码发布**，因此那些链接在本仓库里点不开；
  它们只作为历史记录的索引存在（R13 的接续点、本轮 speckit 计划、构建产物、本地进度日志）。
- 文中出现的 `README.md:<行号>` 一律指**本文档**（旧名 `README.md`），已随本次开源改名，
  行号保持不变——这也是为什么本文的既有内容一个字都没有被重排。
- 想知道「现在能做什么」：读根 `README.md` 与 `references/08-condensed-report.md`。
  想知道「怎么用」：读 `release/SKILL.md` 与 `release/QUICKSTART.md`。
