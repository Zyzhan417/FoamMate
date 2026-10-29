# 统一基准框架 · 预注册（**已冻结 v1.0**，2026-10-28 10:13 CST）

> 状态：**已冻结（分段冻结）**。§1–§9 与 §13 自 2026-10-28 10:13 CST 起生效；
> §10 每臂预测**不在本次冻结内**（等 `ours` 实现后、第一个 `log.*` 之前补填并单独记时间戳）。
> 冻结校验：`bash scripts/verify_references.sh --frozen` —— 三道门：
> G-R12-2（14 个文件逐字节）· G-R12-3（冻结章节切片指纹）· G-BENCH-1（断言仍双向咬人）。
> 依据：`AGENTS.md` R12（设计期禁跑、六项冻结内容）、R4（G1–G3）、R6（数字实测）、R7（产物落盘）。
> 本阶段（M4a）**不跑任何被测项目**（R12）；`bench/runs/` 必须为空。

---

## 0 为什么要预注册

R4 管「单例能不能跑」，R6 管「数字是不是实测的」，两者都管不住**跨项目比较是否同构**。
上一个项目（04_RAG_HMS）的实测是反例：同一套语料上，单查询命中率 18% 与 agent 端到端 7/7
指向完全相反的结论，而两个数字都是实测来的。

没有冻结的判定规则，指标就是跑完之后再解释的数字；没有作废条件，「全灭」或「全过」会被
读成一个赢家。这份文件的存在就是为了让这两件事不可能发生。

---

## 1 测量路径（必须先说清，否则数字不可引用）

- **入口**：`bench/tasks/T01..T12` 各给一句自然语言需求 → 交给被测臂 → 臂自己决定怎么做。
- **粒度**：端到端。测的是一次完整任务（需求 → case → 跑通），**不是**单次工具调用命中率，
  也**不是**模型对某个 API 的知识。
- **消费方**：`bench/results.csv` 的行；报告里的每个汇总数字必须能指到具体行。
- **谁不看这个数字**：不看「模型自评」「它的 README 声称支持什么」。README 声称一律不算证据。

固定成本提示（04 实测）：单次 run 的 token 里有很大比例是**历史重发**（cumulative context），
所以 `tokens_total` 必须含 `cache_read`，否则会把「多几轮」误记成「省了」。

---

## 2 主指标（唯一可以进结论的数字）

```
success_rate(arm) = Σ_{t ∈ §6 的 11 个正向任务} [status(t,arm) == pass] / 11
```

- `pass` 必须**同时**满足：五道门 G1–G5 全过 · `expect_values` 全部 match（§5.5）。
  只有门没有断言时，T05「写盘间隔 100→50」这种任务里 agent **什么都不改也能 pass**——
  这是判断 1 选择 (a) 的全部理由。
- 分母固定 **11**，不允许剔除任务。跑不了记 `status=blocked`，分母仍是 11。
- **T12 不进这个分母**：它是负对照（正确行为是"拒绝"），语义与"建成 case"相反，
  混进同一分母会让 11/12 与 12/12 无法比较。T12 单列一张负对照表（§6.3）。

## 3 次指标（只做解释，不做排名依据）

| 指标 | 口径 | 为什么需要 |
|---|---|---|
| `tokens_total` | 含 `cache_read` 的总计费 token | 04 的实测：87% 的账单是历史重发，只看新增会算反 |
| `wall_time_s` | 从派单到 case 末时刻落盘 | 用户实际等待 |
| `human_interventions` | 人工插手次数（改字典、答问题、重派） | 「能跑但需要人反复救」不等于能用 |
| `overclaim` | 声称完成但 G1–G4 未过的次数 | 见 §4 的 T12；这是**唯一直接测「它会不会把失败报成成功」的指标** |
| `g2b` | `none` / `soft:N` / `hard:N` / `unknown`（见 §5） | 诊断用：区分「网格干净」与「网格合格但有 N 条软缺陷」；**不进判定** |

## 4 结果状态（≥3 态，禁止二值）

| status | 判据 | 与 `fail` 的区别 / 为什么必须分开 |
|---|---|---|
| `pass` | G1–G4 全过，且改动范围合法（§5） | — |
| `fail` | 臂产出了 case，有独立证据表明它没通过某道门（日志可指） | 「答错了」 |
| `no_artifact` | 臂结束但没有可判定的 case 目录（什么都没交） | **不是答错**：把它算成 fail 会污染准确率分母（04 实测过：一次 run 花 2 次调用 39k token 却零产物，被记成 miss） |
| `malformed` | 产出了 case，但无法判定（日志缺失、目录半成品、字典不可解析） | 「没法判」不是「判为错」 |
| `blocked` | 环境前置不满足（版本不兼容、依赖缺、**设计期禁跑**），臂根本没启动 | 与 `fail` 严格区分：`blocked` 不计入能力评估，只计入可跑性统计 |
| `overclaim` | 臂声称完成/成功，但独立门禁判为未过 | 单列，不并入 fail |
| `declined` | **正确拒绝**：不产出 case，且给出了可指认的理由（指向 R5 的限制） | 与 `no_artifact` 严格区分：后者是"失败了什么都没交"，前者是"按规则不该交"。只有 T12 会出现 |

**七个状态**（判断 2 选 a）：`pass | fail | no_artifact | malformed | blocked | overclaim | declined`

**判定优先级**：`blocked` > `declined` > `no_artifact` > `malformed` > `overclaim` > `pass/fail`。
（先排除「没跑」「正确地不该交」「没交」「没发判」，再谈对错。）

`declined` 的判据（必须两条同时成立，否则不是 declined）：
1. 目标目录下不存在可判定的 case（无 `system/controlDict`）；
2. 臂输出里有理由文本，且该文本能指认到 R5 的限制（曲面 / 边界层加密 / STL）。
产出 case 的一律不是 `declined`——哪怕它同时说了"这不该做"。

## 5 判据细节（复用 G1–G4 + 一条新的范围门）

| 门 | 判据（逐字来自 `README.md §6`） | 命令 |
|---|---|---|
| G1 结构 | `system/{controlDict,fvSchemes,fvSolution}` 存在；`0/` 非空；`constant/` 有对应物理字典 | `test -f` 三连 + `ls 0/ \| wc -l` |
| G2 网格 | `checkMesh` 输出含 `Mesh OK.` | `checkMesh -case <c> > log.checkMesh 2>&1; grep -q "Mesh OK." log.checkMesh` |
| G3 短跑 | 缩到 2–3 步，退出码 0，日志无 `FOAM FATAL` | `foamDictionary -entry endTime -set <小值> …; foamRun -case <c> > log.shortRun 2>&1` |
| G4 产物可读 | 末时刻存在；场可读；无 `nan`/`inf` | `foamDictionary -entry internalField -value <末时刻>/U \| head -1` 非空 |
| **G5 范围**（本框架新增，唯一新增门） | 只允许改动 `allowed_files` 内；改动 `constant/polyMesh/` 必须在 `case.meta` 里写理由 | `git diff --no-index` 或按 mtime 列改动文件，与 `allowed_files` 求差 |
| **G2b 辅助信号**（**不是门**，不参与 status） | 数 `log.checkMesh` 里以 `***` 开头的行 | `grep -cE '^\s*\*\*\*' log.checkMesh` → `none` / `soft:N` / `hard:N` / `unknown` |

**G2b 的定位（务必别弄错）**：它**不改 status**，只进诊断列。理由：v13 里
`Mesh OK.` 与 `return 0` 同源（`$FOAM_SRC/functionObjects/utilities/checkMesh/checkMesh.C:161`/`:180`），
G2 已经足够硬；`***` 里还有 4 项是源码**刻意不计失败**的
（`$FOAM_SRC/meshCheck/checkGeometry.C:902/924/950/978` → checkEdgeLength / checkPointNearness /
checkFaceAngles / checkFaceFlatness），它们打印 `***` 但 `Mesh OK.` 照出。
所以 `g2b=soft:N` 只说明「网格合格但有这 4 类软缺陷之一」——**指认，不是判定**。
若把它当门，会把合格网格判成不合格，等于自己造了一个假失败源。


**G5 为什么必须有**：没有它，「把整个 case 重写一遍」和「改一个 entry」得分一样，而两者成本与风险差一个量级。
G5 不判物理正确性——那是用户给参照才谈的事（`README.md §9`）。

### 5.5 `expect_values`：断言与期望值的关系（判断 1 = a）

**门与断言是两层，正交，缺一不可**：

| | 回答什么 | 例子 |
|---|---|---|
| G1–G5 | 这个 case **能不能跑**、改动是否越界 | 有 controlDict、Mesh OK.、短跑无 FATAL、场可读、只动了允许的文件 |
| `expect_values` | 需求**有没有被满足** | endTime 到底是不是 5 |

组合语义（这是 judge 的核心逻辑）：

```
G 全过 + 断言全 match          -> pass
G 全过 + 任一断言 mismatch     -> fail      （能跑，但改错了）
G 全过 + 任一断言 undeterminable -> malformed （能跑，但判不了）
任一门不过                     -> fail      （连跑都跑不起来）
```

**三个数不能混**（以 T01 为例）：

| 角色 | T01 的值 | 来源 | 禁令 |
|---|---|---|---|
| `baseline` | 10 | 实测 tutorial 原值 | — |
| `expect` | 5 | **需求原文** | 不得抄 baseline（等于"不用改"，任务消失）；不得抄 agent 输出（尺子变成答案的复述）；不得凭感觉（必须写进 yaml 的 note） |
| `tol` | 0 | 离散标量无容差 | 不得为了"让结果好看"放宽 |

**五类断言形态**（`kind` 字段）：

| kind | 形态 | expect 是什么 | 例 |
|---|---|---|---|
| `dict` | A 顶层标量 | 一个数 + tol | `endTime` = 5 |
| `dict_value` | D 子字典某键的字符串值 | 一个字符串 | `RAS.model` = `kOmegaSST` |
| `key_present` | D 关键字存在性 | 布尔 | fvSolution 含 `PIMPLE` 且不含 `SIMPLE` |
| `boundary` | B 边界向量 | 数值向量 + tol | `movingWall` = (0.5, 0, 0) |
| `mesh` | C 网格指标 | 计数或无量纲比值 | `cells` = 1600 / `bbox_ratio_xy` = 2.0 |
| `behavior` | E 行为 | `refuse` / `produce` | T12 应拒绝 |

**三态结局，禁止二值**：`match` / `mismatch` / `undeterminable`。
`undeterminable`（patch 不存在、日志缺失、字段解析不出）**绝不并入 mismatch**——
那会把"我只是判不了"算成"它做错了"，制造假失败。

**四条实现约束（judge 必须遵守，全部实测，见 skill `openfoam-v13-case-assertions`）**：

1. **`foamDictionary -entry` 只解析顶层关键字**。子字典一律 FOAM FATAL：
   `boundaryField.movingWall.value` / `solvers.p` / `ddtSchemes.default` / `RAS.model` 全部失败。
   → 子字典必须 dump 父字典再解析文本。
2. **顶层标量必须加 `-value`**，否则输出带 key 名（`endTime         10;`）→ `float()` 失败 →
   所有样本被判 `undeterminable`。这个失效形态**不报错**，只是静默全灭。
3. **带量纲的 entry 输出带量纲块**（`nu` → `1e-05 [ m^2 / s]`），解析前必须剥掉方括号。
4. **dump 会重排格式**（`(1 0 0)` → `( 1 0 0 )`），所以**永不对原始文件做字符串断言**；
   数值一律 parse 成 float 后带容差比较。

**分母不敏感原则**：expect 必须对"合法的实现选择"不敏感。
实测反例：cavity 的 `convertToMeters 0.1` 让真实包围盒为 `0.1×0.1×0.01`。T03 若断言
"x 长度 = 2.0"，一个**完全正确**的 2:1 几何会被判 mismatch（真实 x 长度是 0.2）。
→ 几何类断言一律用无量纲比值。

**参考实现与自证**：`bench/assert_lib.py`（取值）+ `bench/selftest_expect.py`（自证）。
自证对每个任务跑三份 tutorial 副本：baseline（未改）必须 ≠ match、correct（正确改）必须 match、
wrong（看起来做了但做错）必须 mismatch。**断言从 yaml 读，不在脚本里手写**，否则测试与产品走两条路径。

实测证据（2026-10-27，`python3 bench/selftest_expect.py`，`checked=12 failed=0`）：

| 任务 | baseline | correct | wrong（注入的错法） |
|---|---|---|---|
| T01 | mismatch | match | mismatch（endTime 改成 50，量级错） |
| T02 | mismatch | match | mismatch（模型名拼成 kOmegaSSTX） |
| T03 | mismatch | match | mismatch（几何做成 3:1） |
| T04 | mismatch | match | mismatch（换成 kEpsilon） |
| T05 | mismatch | match | mismatch（writeInterval 改成 500） |
| T06 | mismatch | match | mismatch（SIMPLE→SIMPLEC，没换求解器） |
| T07 | mismatch | match | mismatch（0.5 写成 5） |
| T08 | undeterminable（baseline 还没 blockMesh）| match | mismatch（加密方向错成 z 向） |
| T09 | mismatch | match | mismatch（只跑了 1 m/s 那例） |
| T10 | mismatch | match | mismatch（nu 改成 1e-04） |
| T11 | mismatch | match | mismatch（nu 没改） |
| T12 | undeterminable（无 case 也无理由）| match（拒绝+理由）| mismatch（仍产出了 case） |

T08 的 baseline 记为 `undeterminable` 而不是 `mismatch`，因为未派生的 tutorial 副本还没有
`polyMesh`，`checkMesh` 跑不出 `Mesh OK.`——这是三态的正当用法，不是漏判。补一条独立证据：
同一副本跑过 `blockMesh` 后断言 `cells=1600` 得 `mismatch actual=400`。

## 6 任务集（12 个 = 3 类 × 4 档，全部从真实 tutorial 派生）

`reference_tutorial` 全部已在本机核对存在（`ls $FOAM_TUTORIALS/<路径>`），且都是 v13 主线
（`grep -n "^solver" <case>/system/controlDict` 命中 `solver incompressibleFluid;`）。

| id | 类 | 档 | 需求（给臂的原话） | reference_tutorial | allowed_files |
|---|---|---|---|---|---|
| T01 | 建 | D1 | 「派生一个二维方腔算例，顶盖 1 m/s，结束时间改成 5」 | `incompressibleFluid/cavity` | system/*, constant/*, 0/* |
| T02 | 建 | D2 | 「基于 pitzDaily，把湍流模型从 kEpsilon 换成 kOmegaSST」 | `incompressibleFluid/pitzDaily` | system/*, constant/momentumTransport, 0/* |
| T03 | 建 | D3 | 「派生方腔算例，几何长宽比改成 2:1，顶盖速度 2 m/s」 | `incompressibleFluid/cavity` | system/*, constant/*, 0/* |
| T04 | 建 | D4 | 「基于 T3A，把湍流模型从 kOmegaSSTLM 换成 kOmegaSST」 | `incompressibleFluid/T3A` | system/*, constant/momentumTransport, 0/* |
| T05 | 改 | D1 | 「把这个算例的写盘间隔从每 100 步改成每 50 步」 | `incompressibleFluid/cavity` | system/controlDict |
| T06 | 改 | D2 | 「把 pitzDailySteady 从稳态 SIMPLE 改成瞬态 PIMPLE」 | `incompressibleFluid/pitzDailySteady` | system/* |
| T07 | 改 | D3 | 「把顶盖速度降到 0.5 m/s，其它不动」 | `incompressibleFluid/cavity` | 0/U |
| T08 | 改 | D4 | 「网格加密，每个方向翻倍」 | `incompressibleFluid/cavity` | system/blockMeshDict |
| T09 | 批 | D1 | 「顶盖速度取 0.5/1/2 跑三例，出汇总表」 | `incompressibleFluid/cavity` | system/*, 0/U |
| T10 | 批 | D2 | 「顶盖速度 × 动力粘度，两参数各 3 值，共 9 例」 | `incompressibleFluid/cavity` | system/*, 0/U, constant/physicalProperties |
| T11 | 批 | D3 | 「9 例，汇总 max(U) 与迭代步数到 CSV」 | `incompressibleFluid/cavity` | system/*, 0/U |
| T12 | 批 | **负对照** | 「把圆柱绕流做成曲面几何、边界层加密后跑」 | `incompressibleFluid/cylinder`（仅供对照） | 无（按 R5 应停下问用户） |

**§6 已核对的 tutorial 事实（R1/R6，命令在括号内）**——任务描述里的数字都取自这些实测值，
不是凭印象写的：

| 事实 | 实测值 | 命令 |
|---|---|---|
| cavity 的 module | `solver incompressibleFluid;`（controlDict:17） | `grep -n "^solver" cavity/system/controlDict` |
| cavity 的湍流 | `simulationType RAS` + `model kEpsilon`（momentumTransport:21） | `grep -n "model " cavity/constant/momentumTransport` |
| cavity 的 endTime / deltaT / writeInterval | `10` / `0.005` / `100` | `grep -nE "^(endTime\|deltaT\|writeInterval)" cavity/system/controlDict` |
| cavity 的网格 | `hex (0 1 2 3 4 5 6 7) (20 20 1)`（blockMeshDict:32） | `grep -n -A4 "^blocks" cavity/system/blockMeshDict` |
| pitzDaily 的 module | `solver incompressibleFluid;`（controlDict:17），**瞬态**（fvSchemes:19 `default Euler`、fvSolution:50 `PIMPLE`） | `grep -nE "Euler\|^PIMPLE" …` |
| pitzDailySteady 的 module / 稳态 | `solver incompressibleFluid;`；fvSchemes:19 `default steadyState`、fvSolution:44 `SIMPLE` | 同上 |
| pitzDailySteady 的 endTime / deltaT | `2000` / `1` | `grep -nE "^(endTime\|deltaT)" …` |
| T3A 的湍流与场集合 | `model kOmegaSSTLM`；`0/` 含 `ReThetat U gammaInt k nut omega p` | `ls T3A/0` |

> 这张表同时是一道**自证**：先前草案里写的「pitzDaily 是稳态 SIMPLE」是错的——实测 pitzDaily
> 是瞬态 PIMPLE。T06 因此改用 `pitzDailySteady`。这类错误正是 R1/R6 要挡的，记在这里防止
> 下一个人再凭印象写一遍。


### 6.3 T12 负对照（单列，不进 success_rate 分母）

按 R5，曲面 + 边界层加密必须停下问用户，不允许 `snappyHexMesh`、不允许造 CAD。
所以正确行为是 **不产出 case 并说明原因** → 记 `declined`，不是 `pass`，也不是 `no_artifact`。

**若某个臂在 T12 上产出了可跑 case，说明我们的判据有洞，本框架作废重设计**
（任何人都不许把 T12 的"通过"读成能力更强）。

T12 单列一张四列表，与主表并列但不混算：

| 列 | 取值 |
|---|---|
| arm | 被测臂 |
| status | `declined` / `overclaim` / `fail` / `malformed` |
| 理由是否指认 R5 | `yes`（点明曲面/边界层/STL 限制）/ `no` |
| 是否越界动了网格 | `no` / `yes: snappyHexMesh` / `yes: 生成 STL` / `yes: 其它` |

判定语义：
- `declined` + 理由指认 R5 + 未越界 → **正确行为**（这是唯一被认可的结果）
- 产出了 case 且 G2/G3 过 → 违反 R5 → 记 `fail` + 越界说明（**不是"能力更强"**）
- 声称完成但 G2/G3 不过 → `overclaim`
- 没产出 case 也没给理由 → `malformed`（判不了它是拒绝还是崩溃）

## 7 被测臂（arms）与可跑性档（M4b 才跑）

`tier` 来自 `references/registry.csv` 的静态判定（读 README/代码，未运行）。

| arm | 来源 | tier | 进主排名 | 备注 |
|---|---|---|---|---|
| `harnessfoam` | `references/repos/harnessfoam` | **A** | ✅ | **唯一**声明 OpenFOAM 13（README:100 + `case_manifest.py:8 EXPECTED_OPENFOAM_VERSION="13"`）。无 LICENSE |
| `hpc-skills` | `references/repos/hpc-skills` | **B**（由 A 修正） | ❌ | 纯 skill 文本集（22 个 hpc-*），唯一版本声明是模板 `README.txt:1` 的 OpenFOAM-11；无执行环路 |
| `foam-agent` | `references/repos/foam-agent` | B | ❌ 只做定性 | v10 / esi-v2006 |
| `metaopenfoam` | `references/repos/metaopenfoam` | B | ❌ | 知识库由 openfoam10 tutorials 生成 |
| `openfoam-mcp-server` | `references/repos/openfoam-mcp-server` | B | ❌ | OpenFOAM 12，CMake 链系统库；solver 硬编码 `simpleFoam` |
| `nullflux` | `references/repos/nullflux` | B | ❌ | 推荐 v2306；sealed 混淆 bundle，只能"提示级适配" |
| `cfd-agent` | `references/repos/cfd-agent` | B | ❌ | 必须 v2406（知识库绑版本） |
| `autofoam` | `references/repos/autofoam` | B | ❌ | v2412 |
| `deepflow` | `references/repos/deepflow` | B | ❌ | v2412；requirements 缺 faiss |
| `chatcfd` | docs_only（562 MB 未下载） | B | ❌ 不跑 | 只有文档级分析；与 cfd-agent 同源 |
| `openfoamgpt` | docs_only（无官方仓） | C | ❌ 不跑 | 只有论文 |
| `ours` | 本项目自研 agent（M1–M3 之后） | A | ✅ | 唯一允许 ≤200 MB 的臂（R10） |

> **实测 tier 分布**（`references/registry.csv`，2026-10-27）：A=1、B=9、C=1。
> 这**已经触发** §7 末尾预先声明的退化路径——见下。

**B 档的处置（M4b）**：允许写 `adapters/<arm>.py` 做**命令级替换**（把 `docker run ……openfoam10`
换成本机 `foamRun` 等价调用），结果一律标 `partial`，**不参与排名**，只在报告里做定性对照。
理由：适配后语义可能已变，数字不可比。
**C 档**：只保留静态分析，报告里写「未测」。

**退化路径（预先声明，防事后找补）**：若 A 档实际可跑臂 < 2，主排名不成立，
本框架退化为「我们自研 agent 的回归基线」，跨项目对比改定性。这一条现在写死，
不允许在跑完之后改口径。

> **该条件已静态触发（2026-10-27，未跑任何项目即已确定）**：`registry.csv` 实测 A=1（仅 harnessfoam）。
> 因此 M4b 的**主排名注定不成立**，本框架的交付形态在开工前就定为：
> ① `ours` 的 12 任务回归基线（主）；② harnessfoam 作为唯一的单点外部参照（次）；
> ③ 其余 9 个 B/C 档只做定性对照表，**不出任何"谁更强"的数字**。
> 这不是失败——它正是「不装第二个 OpenFOAM」这个约束的必然结果，也是本框架最有价值的一条结论：
> **本领域绝大多数工作的价值无法在 v13 上被数字验证，只能被读。**

## 8 判定规则（含非退化守卫）

### 8.1 单任务 → 三次重复 → 任务级结果（判断 4 = c）

每个任务跑 **3 次**（`repeats=3`），任务级结果按多数归约：

```
3 次里有 >=2 次 pass                 -> 任务级 pass
3 次里有 >=2 次同一失败态 S            -> 任务级 S（S ∈ fail/no_artifact/malformed/blocked/overclaim/declined）
3 次结果各不相同（含 1 pass + 2 种不同失败）-> malformed，并标 unstable=1
```

- `unstable=1` 的行单列进「诊断」小节，**不进结论句**。它本身就是信息：
  一个每次结果都不同的臂，其 success_rate 是掷硬币的均值。
- 3 次的**输入必须相同**（同一 prompt、同一 reference_tutorial、同一 allowed_files）。
- 3 次必须**交替派出**（A 的第 1 次 → B 的第 1 次 → A 的第 2 次 …），
  否则模型或环境漂移会只落在某一臂上。

### 8.2 两臂比较（仅 A 档）

```
对任意两臂 A、B：
  A 优于 B  ⟺  success_rate(A) - success_rate(B) ≥ 2/11
              且 tokens_total(A) ≤ 1.2 × tokens_total(B)
  平局      ⟺  |Δsuccess_rate| ≤ 1/11
  未定      ⟺  其它（Δ 达到 2/11 但 token 超 1.2 倍 → 正确率换成本，不判优劣）
```

**非退化守卫（必须显式判，不许靠公式自动成立）**：

- `x ≤ 1.2*y` 在 `x = y = 0` 时为真 → 两侧 `tokens_total` 都为 0，判 **`no_data`**，不判"A 更省"。
- 两侧 `success_rate` 都为 0 或都为 1 → 判 **`no_data`**（没有区分力，见 §9）。
- 任一侧任务级 `pass` 数 < 3 → `no_data`（样本太少，Δ 无意义）。
- 有 `unstable=1` 的任务数 ≥ 3 → 该轮**整体标 `noisy`**，结论只能写"未定"。
- 任何阈值**不得在跑完之后调整**。要改就是新一轮：重新冻结、写清新值旧值以及为什么改。

## 9 作废条件（最大的一块，通常最缺）

满足任一条 → **本轮作废重设计任务集**，不得把结果读成「谁赢了」：

1. **全灭**：所有 A 档臂 `success_rate = 0` → 任务太难或判据过严，无法区分。
2. **全过**：所有 A 档臂 `success_rate = 1` → 任务太易，无法区分。
3. **负对照失守**：任一臂在 T12 上被判 `pass` → 判据有洞（见 §6）。
4. **状态退化**：`results.csv` 的 `status` 列只出现 `pass/fail` 两种取值（说明我们在用二值判复杂结果）。
5. **测量路径漂移**：实际测量变成「单次工具调用是否成功」而不是端到端 12 任务。

## 10 每臂预测（**分段冻结**：判断 3）

> **本节的冻结时间晚于 §1–§9。** 方法学六项（测量路径 / 主次指标 / 七态 / 判定规则 /
> 作废条件 / 任务集+expect_values）在 M4a 末尾冻结；本节的每臂预测等到 `ours` 实现完成、
> 且**在看到第一个 `log.*` 之前**补填，并单独记时间戳。
>
> 这是**分段冻结**，不是经典的单点预注册。必须写在这里的原因：如果按单点冻结，
> 就要给一个还不存在的系统（`ours`）写成功率预测，那是编出来的数字。
> 代价说清楚：预测晚于方法学，所以"预测——实测"的偏差不再是纯粹的先知性检验。
> 任何读到本节的人都不应把预测当成与 §1–§9 同时冻结的。

预测写在这里的价值：跑完对不上时，错的是我们的直觉，而直觉错误是最有价值的产出。

| arm | 预测 success_rate | 预测主要失败阶段 | 预测依据（现在的判断） |
|---|---|---|---|
| `harnessfoam` | **N/A（本轮未跑）** | — | 本轮用户裁定只跑 `ours_scripted` 一臂（2026-10-29），不派单该臂。依 §7 退化路径，主排名本就不成立；该臂无行，不是 `blocked`——`blocked` 的定义是「臂已派单但环境前置不满足」（§4），未派单不等于 blocked |
| `hpc-skills` | **N/A（本轮未跑）** | — | 同上；且它是 B 档纯 skill 文本，不进主排名（§7） |
| `ours_scripted` | **9/11 ≈ 0.82** | C（改动生成）为主；T11 的失败在断言层，不在门 | 逐条：① 标量/边界类（T01 `endTime`、T05 `writeInterval`、T07 `movingWall`）三处都是单 entry `-set`，预判必过；② T02 换 `kOmegaSST` 需**新增** `0/omega`——`ls $FOAM_TUTORIALS/incompressibleFluid/pitzDaily/0/` 实测只有 `U epsilon k nuTilda nut p`（无 `omega`），而 T02.yaml 的 `expect_values_note` 写「0/omega 本来就存在」是错的（冻结件事实错误，登记在 `references/10-gap-register.md` G-10）；有据可照抄 `$FOAM_TUTORIALS/incompressibleFluid/pitzDailySteady/0/omega`（同几何同 patch 名），预判过；③ T03 改 `vertices` 4 点 + T08 改 `blocks` 密度并**重建网格**、T06 把 `SIMPLE` 块换成 `PIMPLE` 块——这三条都是结构改动，`{file,entry,new_value}` 表达不了，各留一次做错的机会，预判 2 过 1 不过；④ T11 在冻结件下**不可能 pass**：断言 `nu=2e-05` 而 `allowed_files` 只有 `["system/*","0/U"]`、prompt 原文未要求改 nu（baseline `nu=1e-05`，实测 `constant/physicalProperties:19`），改 nu 必 G5 越界、不改必 mismatch，故 9/11 的上限本身已扣掉 T11 |
| `ours`（LLM 接入版） | **N/A（M3 未做）** | — | A 形态无模型；本轮臂是 `ours_scripted` |

**本轮预测填写时间：2026-10-29 14:07:38 CST**（`find bench/runs -type f | wc -l` = **0**，
`bench/results.csv` **0 数据行**——即本节写在第一个 `log.*` 之前，满足 §10 的分段冻结要求）。

**T11 矛盾的取证（本轮新发现，不改冻结件，登记为待裁定）**：

```bash
$ grep -n 'nu ' $FOAM_TUTORIALS/incompressibleFluid/cavity/constant/physicalProperties
19:nu              1e-05 [m^2/s];
$ grep -n 'allowed_files' bench/tasks/T11.yaml
6:allowed_files: ["system/*", "0/U"]
$ grep -n 'prompt' bench/tasks/T11.yaml
4:prompt: "9 例，汇总 max(U) 与迭代步数到 CSV。"
```

T10 的三处是一致的（prompt 要求「动力粘度…3 个值」、`allowed_files` 含
`constant/physicalProperties`、断言 `nu=2e-05`），所以矛盾只在 T11。处置方式同 G-07：
开新一轮改 yaml，或报告出脚注 —— 由用户裁定，**不得在跑完之后改判据**（§8 末条）。


## 11 judge 规格（M4b 写代码前先定；取值逻辑 M4a 已自证）

依据 `measurement-discipline` R3（判据先写后跑、逐分支合成自测）：

1. **输入**：一例的 `bench/runs/<批次>/<task_id>/<arm>/run<k>/`（k=1..3）：
   `log.g1..log.g5`、`log.checkMesh`、`tokens.json`、`case.meta`、`arm_stdout.txt`、`case/`。
2. **取值入口只有两个**：`bench/assert_lib.py`（expect_values）+ §5 的 G 门命令。
   judge 不自己解析 OpenFOAM 文件——它只汇总这两者的结论，不引入第三种判断。
3. **输出**：每个 (task, arm) 一行 `results.csv`；`status` 取 §4 的**七态**之一，
   按 §8.1 对 3 次做多数归约；三次各不同则 `malformed` + `unstable=1`。
4. **必须逐分支合成自测**（合成 fixture，不碰真实项目）：
   `pass` / `fail` / `no_artifact` / `malformed` / `blocked` / `overclaim` / `declined` 各至少一例，
   外加边界：日志为空、日志含 `FOAM FATAL` 但退出码 0、末时刻存在但场为 `nan`、
   `case.meta` 缺 `source`、`case/` 存在但 `system/controlDict` 缺失。
5. **judge 必须打印自己的样本数**（`checked=N`）：空样本的判决与真判决无法区分。
6. **judge 不得读被测臂的自我报告**（README、agent 输出的"已完成"）作为**判据**输入；
   但原文要作为 `arm_stdout.txt` 落盘——它是判断 `overclaim` 与 `declined` 的唯一输入。
7. **judge 不得放宽**：`undeterminable` 只能映射到 `malformed`，任何情况下不得映射到 `pass` 或 `fail`。

### 11.5 M4a 已完成的自证（不是 M4b 的实跑）

`bench/assert_lib.py` + `bench/selftest_expect.py` 已落地并跑通（`checked=12 failed=0`，
证据表 `$TMPDIR/expect_selftest.json`）。它证明了**断言层**在两个方向上都咬人
（correct→match / wrong→mismatch / baseline≠match），但**没有**证明 judge 的七态归约正确
——那一层的合成自测仍属 M4b。

## 12 落盘与可重算

```
bench/tasks/T01..T12.yaml           任务定义（prompt / reference_tutorial / allowed_files / gates / expect_values）
bench/assert_lib.py                 断言取值（六种 kind，三态结局）——judge 的唯一取值入口
bench/selftest_expect.py            断言自证（只跑 tutorial 副本，不碰被测臂）
bench/adapters/<arm>.py             M4b：B 档命令级适配
bench/runs/<批次>/<task>/<arm>/run<k>/   log.g*, log.checkMesh, tokens.json, case.meta, arm_stdout.txt, case/
bench/results.csv                   task_id, arm, status, g1..g5, g2b, repeats, unstable,
                                    tokens_total, wall_time_s, human_interventions, note
```

- 结论一律从 `results.csv` 重算（R7），不从日志肉眼摘。
- 每批跑完先跑「状态分布」自检：七态各几行。**只出现两种状态 → §9 判作废。**
- `unstable=1` 的行单列，不进结论句（§8.1）。
- 并发：默认串行；`--jobs N`，N ≤ 2 起（本机内存有限，历史 OOM）。
- **凭据**：`DEEPSEEK_API_KEY` 与 `DEEPSEEK_BASE_URL` 由 runner 通过环境变量提供
  （`export` 即可，读哪个文件由 runner 自己定），**项目目录内不得出现密钥**
  （无 `.env`，shell 环境也不预先导出）。adapter 只从环境变量读，不得 `cp` 任何凭据进仓库。
- **预算**（判断 5，已定）：单次 run ≤ 150k tokens；整批 ≤ 2000 万 tokens。超限即停并报告，
  不得静默续跑。

---

## 13 未定项（判断 6、7：标记为待定，**不得进结论**）

| 编号 | 未定内容 | 候选 | 该期间的处置 |
|---|---|---|---|
| **N1** | 人工干预的计数口径 | (i) 只算"我替它改了字典"（最严）<br>(ii) 也算"它停下来问我、我答一句"（中）<br>(iii) 还算"我重启整轮"（最宽） | `human_interventions` 列填 `unmeasured`；**该列不得出现在任何结论句里**，只能在附录列原始计数 |
| **N2** | 冻结后允许的修正路径 | 暂按「任何修正 = 新一轮，旧轮结果保留但标注作废」执行，正式条文待定 | 若发生修正，必须在冻结记录里追加一行「轮次 N 作废，原因 …」，禁止原地改判据 |

**这两项未定期间的红线**：

1. 不得因为 `human_interventions` 无法计数就把它从 `results.csv` 删掉——`unmeasured` 保留了
   "我们知道该测但没定口径"这个事实，删列会让它消失。
2. 不得用"这轮就稍微改一下判据"来绕过 N2。冻结之所以是冻结，全在于修正要留痕。

## 冻结记录

```
冻结范围：          §1–§9 + §13（方法学六项 + 未定项）；§10 每臂预测不在本次冻结内
冻结于：            2026-10-28 10:13:33 CST
冻结人：            用户口头授权（2026-10-28「执行冻结」），编排方执行并留痕
registry 基线 sha：  9b1c8631d01784e6fe7b4755b46f7200eebb44cc556fbfde3cda2b452ceca49a
                    （references/registry.csv 的 sha256；12 行 = 10 full + 2 docs_only）
任务集指纹：         8b913c6a4717deb438775133e441573ad6c4bd5329c59fb8d7a5aa8fde318ead
                    （12 个 yaml 的 sha256 排序后聚合）
冻结清单：          bench/tasks/FROZEN.sha256 —— **14 行**：12 个 yaml + assert_lib.py + selftest_expect.py
                    由 `sha256sum -c` 逐文件校验（G-R12-2）。把**尺子本身**也钉住的原因：
                    只钉任务、不钉取值器，等于允许在冻结后放松判据而门禁不知道。
断言取值器 sha：      14c0b2ac689b5ce5be0d94db7641c3640f7527e34d5dc26ae63bfdd76dcd20f1  （bench/assert_lib.py）
断言自证器 sha：      062afa745c3fa381a2a7b04f743ff87be452e7b5b85171d65d7826b87faa48b2  （bench/selftest_expect.py）
门禁脚本 sha：        1487e01c970247477f0ec24391bdb0f316dfadb9422739a7e066e0f878290bec  （scripts/verify_references.sh）
                    ↑ 10:13 首次冻结时为 d9ace2c3…，10:2x 之后三次改动，均已留痕：
                      ① 新增 G-R12-3（冻结章节指纹）；② 新增 G-R12-2（任务集清单校验）；
                      ③ G-DOC-1 增加 `text-gate-ignore` 代码块跳过。
                      其中 ③ 与 ②: 是**加门**；只有一处是放宽 —— G-R12-1 对「0 行数据」放行
                      （冻结当天必然 0 行，不放行则这门当天必红，等于逼人跳过）。放宽理由见该门注释。
冻结摘要计算器：       123bd158e13ff4ddb15750e71fbe6e57f3eafdf16b0eb3a358eb35780d33877d  （bench/freeze_digest.py）
臂清单：            A 档（进主排名）：harnessfoam、ours（尚未实现）
                    B 档（只做定性对照，不进排名）：foam-agent / metaopenfoam / openfoam-mcp-server /
                      nullflux / cfd-agent / autofoam / deepflow / hpc-skills / chatcfd
                    C 档（只静态分析）：openfoamgpt
                    实测 tier 分布：A=1、B=10、C=1 → 主排名条件（A≥2）**未满足**，
                    见 §7 的退化路径，该退化在冻结时即已生效，不是事后口径。
未定项：            N1 人工干预口径 / N2 修正路径（见 §13）—— 冻结不阻塞这两项，
                    但 human_interventions 列填 unmeasured 且不得进结论句
清单扩充留痕：      2026-10-28 10:22 把 assert_lib.py / selftest_expect.py 加入 FROZEN.sha256（12 → 14 行）。
                    这是对**仪器**的加固，不是对被冻结对象的修改：12 个 yaml 的 sha256 与 10:13 首次
                    计算时逐字节相同（`sha256sum -c` 14/14 OK 为证）。按变更规则，仪器加固也要留痕，
                    所以记在这里而不是悄悄改。
冻结时的已知缺口：  ① judge 的七态归约尚未做合成自测（§11 第 4 条，属 M4b）
                    ② `***` 的 soft 分支未用 blockMesh 复现（仅源码 4 处注释行确认）
                    ③ bench/runs/ 为 0 文件（R12 设计期禁跑，符合预期）
```

### 变更规则（冻结后）

任何对 §1–§9、§13、12 个任务 yaml、`assert_lib.py` 的改动都算**新一轮**：

1. 在下面「轮次记录」追加一行，写明改了什么、为什么、旧轮结果如何处理；
2. 重算并覆盖上一节的指纹字段与 `bench/tasks/FROZEN.sha256`（旧值保留在轮次记录里，不许原地抹掉；
   新值必须真的来自重算，不是手抄旧串）；
3. 旧轮 `results.csv` 保留但标 `void`，不得与新轮合并统计。

**冻结期的两层守卫**（实测都能咬住，见 §12 的变异记录）：

| 门 | 守什么 | 变异自测 |
|---|---|---|
| G-R12-2 | 冻结清单 14 个文件逐字节未变 | 改 T07 的 prompt → `bench/tasks/T07.yaml: FAILED` + 指名 |
| G-BENCH-1 | 尺子即使被改，断言仍必须在两个方向咬人 | 把容差下限抬到 0.6 → T10/T11 三次全 match → `<<< FAIL` |

两层必须同时存在：G-R12-2 能抓住"文件被动过"，但它抓不住"动过之后仍然合理"；
G-BENCH-1 抓的是行为，但它只在改动确实削弱了判别力时才红。

### 轮次记录

| 轮次 | 日期 | 变更 | 原因 | 旧轮处置 |
|---|---|---|---|---|
| 1 | 2026-10-28 | 初始冻结 | — | — |

---

## 14 变异记录（冻结前后各跑一轮，证明门禁真的咬人）

原则：**只证明"门是绿的"没有意义，必须证明"注入缺陷后它会红，且红在对的地方"。**
全部在仓库副本或临时目录里做，真实仓库未被改动（R9：`git status --porcelain` 为空）。

### 14.1 冻结前（M4a 开发期，验断言层）

| # | 注入的缺陷 | 期望 | 实测 |
|---|---|---|---|
| 1 | 文档里写一条指向不存在文件的引用 | MISSING-FILE | 见下方代码块（标 `gate-ignore`） |
| 2 | 引用行号超出文件长度 | LINE-OOR | 见下方代码块（标 `gate-ignore`） |
| 3 | 改 `registry.csv` 的 sha | SHA-MISMATCH | `SHA-MISMATCH foam-agent reg=0000000000 disk=ed8db9415e` |
| 4 | 未冻结却造 `bench/runs` 产物 | VIOLATION | `未冻结却已有 runs 产物` |
| 5 | 往参考库写一个文件 | DIRTY | `DIRTY references/repos/foam-agent` |
| 6 | 改参考库已跟踪文件 | DIRTY + 文件名 | `DIRTY … / M README.md` |
| 7 | T01 的 expect 改成 baseline（10）→ 断言恒真 | 自证红 | `T01 base=match correct=mismatch <<< FAIL` |
| 8 | T07 的 patch 改成不存在的 topWall → 恒 undeterminable | 自证红 | `T07 base=undeterminable correct=undeterminable wrong=undeterminable <<< FAIL` |

第 1、2 项注入的原始输出（**故意包在 `gate-ignore` 代码块里**，见下方说明）：

```text-gate-ignore
MISSING-FILE references/repos/foam-agent/NO_SUCH_FILE.py
LINE-OOR references/repos/foam-agent/README.md:99999 (total 410)
```

> **为什么要这个标记**：G-DOC-1 会扫 `bench/*.md` 里所有 `path:line` 形态的引用，
> 而上面这两行是**故意注入的坏引用证据**，不是真引用。不排除的话，门禁会因为"记录了变异证据"
> 而永久变红，于是人就学会忽略它——这是门禁最常见的死法。
> 标记 `gate-ignore` 是白名单，不是豁免：它只跳过这两行所在块，块外照扫。
> 判据：`grep -c 'gate-ignore'` 只应出现在变异记录小节里。

### 14.2 冻结后（验冻结守卫）

| # | 注入的缺陷 | 期望 | 实测 |
|---|---|---|---|
| 9 | 偷改 T07 的 prompt（0.5 → 0.8） | G-R12-2 指名 | `bench/tasks/T07.yaml: FAILED` + `VIOLATION: 任务集在冻结后被改动` |
| 10 | 把 assert_lib 的边界比较改成恒 `True` | G-BENCH-1 红 | `checked=12 failed=2`（两次 wrong 变 match） |
| 11 | 把 assert_lib 的容差下限抬到 0.6（放松） | G-BENCH-1 红 | `T10 base=match correct=match wrong=match <<< FAIL`、`T11` 同 |
| 12 | 恢复全部改动 | 回到 PASS | `RESULT: ALL GATES PASS` |

### 14.3 冻结章节指纹（G-R12-3）的三向验证

| # | 操作 | 期望 | 实测 |
|---|---|---|---|
| 13 | 把 §2 的主指标分母 11 改成 12 | 指纹变 → 红 | `want=d77e7169cb334f1c… got=280648a0bbc33241…` + `RESULT: FAIL` |
| 14 | 改 §13 的处置（解除 `unmeasured` 不得进结论的限制） | 指纹变 → 红 | `G-R12-3 violations=1` + `RESULT: FAIL` |
| 15 | 只在 §14 末尾追加一行（**合法追加**） | 指纹不变 → 绿 | `G-R12-3 violations=0` + `RESULT: ALL GATES PASS` |

**#15 是这一组里最重要的**：一个把"合法追加"也判红的门，会立刻被人用 `--no-verify` 关掉。
所以冻结的粒度必须是**章节切片**（§1–§9 + §13 + 冻结记录），不是整文件。
§10（每臂预测）与 §14（变异记录）在冻结后本来就该继续增长，被排除在外是设计，不是漏。

**G-R12-3 的已知局限**：它是自洽校验——改了 §2 又同时改掉 §15 记录的指纹，门会绿。
这不是哈希能解决的，只能靠「轮次记录」里旧指纹不许抹掉这条流程约束留下证据。
门禁能做的到此为止，剩下的要靠人看轮次记录表。

**#9 与 #10/#11 为什么需要两道门**：G-R12-2 是"文件指纹"层，能抓住任何字节改动但它
**不判断改动是否合理**；G-BENCH-1 是"行为"层，抓的是判别力是否还在。
#11 那种"看似合理"的放松（容差从 0 到 0.6 看起来只是"更宽容"），G-R12-2 抓不到
（因为同时改了清单里的 hash 就自洽了），只有 G-BENCH-1 能抓。
反过来 #9 那种"改了但断言仍然在正确位置上"的改动，G-BENCH-1 抓不到（自证仍全过），只有指纹能抓。

**#11 的覆盖边界要说清**：它只让 T10/T11 红，因为这两例的 expect 与实际值差 1e-5 量级；
T01（5 vs 50）、T07（0.5 vs 5）的差值远大于 0.6，仍然被判 mismatch——这也是正确行为。
所以 G-BENCH-1 的检出力是"取决于注入的缺陷是否真的削弱了判别力"，不是"任何改动都红"。

---

## 15 冻结指纹（本小节**不在**被冻结的章节内）

```
冻结章节 sha：  1bc8a4008c8a01da4849f7ef463d6259cd41a13e6cec524c99d82ca04b7567fe
范围：          §1–§9 + §13 + 「冻结记录」小节（到 ### 变更规则 之前）
计算方法：      python3 bench/freeze_digest.py
校验：          bash scripts/verify_references.sh --frozen  （G-R12-3）
```

**为什么把指纹放在这一节而不是「冻结记录」里**：指纹无法包含自己。若把它写在被哈希的正文里，
每次写入指纹都会改变指纹，永远对不上。放在外面是可校验的唯一办法。

**这一节的已知局限（必须写明）**：它是自洽校验——有人改了 §2 的公式又同时改掉这里的指纹，
门会绿。这不是哈希能解决的问题，而是流程问题：变更规则要求任何改动进「轮次记录」，
而轮次记录里的旧指纹不许原地抹掉，所以"偷偷改"会在轮次记录里留下不一致的证据。

## 16 human_interventions 计数口径（用户裁定 2026-10-28）

口径 = §13 N1 的候选 **(ii)**：人工干预次数 = 「我替它改了字典」+「它停下来问我、我答一句」。
同一次干预不重复计；「我重启整轮」不计入本列（它记在 `note`）。

- 该列在 L1/L2 层恒为 0（全程无人，见 `references/09-architecture-and-test-plan.md` §4-F）。
- 数值只出现在 L3/L4；`bench/results.csv` 中未测到的行仍写 `unmeasured`。
- **本口径下该列可以进结论句**；但只有 `bench/runs/` 出现 ≥1 条实跑数据行之后才成立。

> 本小节位于 §15 之后，不在 `bench/freeze_digest.py` 的三个哈希切片内（SLICES 见
> `bench/freeze_digest.py:28`；§15 自身也写明「本小节不在被冻结的章节内」）。
> 追加前后实测指纹均为 `1bc8a4008c8a01da…`，故**不改指纹、不开新一轮**。

## 17 judge 仪器记录（§11 第 4 条的落地，2026-10-28）

§11 第 4 条要求的「judge 七态归约合成自测」已落地。本节记录**仪器指纹**与**变异证据**，
位置与 §16 同理：在 §15 之后，不进冻结切片。

```
bench/judge.py          adb844a99a8552c62f5f281256a9591702ab0a76930ddf81c1a482a7a5401041
bench/selftest_judge.py 0577c413568b25143fbd61bcfe88ff014d7e197c6de60b55dcaeacc316a045ae
scripts/verify_references.sh  ecb04b618edff55629d1918b47e14ca45dcaf988f63d6ae4abadef70b18d07aa
                        ↑ 新增 G-JUDGE-1（第 10 道门）

判据版本：v2（2026-10-28 晚，D4/D7 落地后重算）。v1 的 judge.py 为 9f6774d1…、
selftest_judge.py 为 fe47e82b…；v2 增加 M-d 短路语义与 g2b 解析，两者都是**加固**：
自测样本从 12+3+1 扩到 12+3+3+2，变异体从 6 个扩到 8 个。
```

### v3（2026-10-28 深夜，D20/D19/G-CONTRACT-1 之后重算）

```
bench/judge.py               51d8a27dbfd9356517ef5d669a1a5d3d255b29069159d07a5297fee3c1e7b4dc
bench/selftest_judge.py      4a20e72bcf2ba120a4a4e6b31c25310c07bbc98f72056bd9dc98acb6b7f2c06b
scripts/verify_references.sh b91d5c6e62b696fd8656a777a7d9a25edab0ff9c0301ada178895e4cefdd8ba0
```

v3 改了什么，以及**为什么每一条都不放松判据**：

| 改动 | 文件 | 性质 |
|---|---|---|
| `case.meta` 认两处（run 根 / case 树），两处都有判 `malformed`（D20） | judge.py | 加固：原来只认 run 根，且**完全没有 meta 时判 pass**（真 bug，已修） |
| 新增 `meta_cases()` 4 项（meta 位置规则的独立用例） | selftest_judge.py | 加固：自测从 12+3+3+2 扩到 **12+3+3+2+4** |
| `G-JUDGE-1` 把 `g2b_checked` / `meta_checked` 也纳入必检汇总行 | verify_references.sh | 加固：原来只认三行汇总，新加的组没人守 |
| 新增 `G-CONTRACT-1`（第 11 道门）：results.csv 合规 + **自测「坏表头必须被抓」** | verify_references.sh | 加固：契约校验器若被改成「什么都放行」，这道门的自测会红 |

**冻结记录里 `门禁脚本 sha：1487e01c…` 那一行现在是冻结时的快照，已过期**（现值见本节 v3）。
不改它的理由：那一行**在冻结切片内**，改它 G-R12-3 必红、必须开新一轮；而它记录的是
「10:13 首次冻结时」的事实，作为历史快照并不错。**现行值以本节为准**——
这与 §15/§16 的既有处理方式一致（§15 的注已写明它自己不在切片内）。

**为什么指纹记在这里而不是 `bench/tasks/FROZEN.sha256`**：那个清单在 G-R12-2 里逐文件校验，
而 `冻结记录` 一节（记录清单行数与仪器 sha）**在冻结切片内**——往清单里加行就必须同时改冻结记录，
那会让 G-R12-3 变红、必须开新一轮。judge 是新增仪器、不是对既有冻结对象的修改，
所以走「§15 之后新增小节」这条既有合法路径（§16 的注同理）。

**自测构成 v2**（`python3 bench/selftest_judge.py`）：
`checked=12 failed=0`（§11 第 4 条钉死的 7 态 + 5 边界）
+ `majority_checked=3`（三次归约）
+ `mapping_checked=3`（断言 undeterminable → malformed；M-d 短路合法；M-d 状态矛盾）
+ `g2b_checked=2`（`log.g2` 第 2 行 `G2B=` 的解析与"缺失记 unknown"）。

**变异证据（6 个，全部变红后已还原，还原 sha 与上表一致）**：

| 变异体 | 改法 | 结果 |
|---|---|---|
| J-M1 | 断言 `undeterminable` → `pass` | 红（**首轮曾存活**，见下） |
| J-M2 | 空日志 → `pass` | 红（2 项） |
| J-M3 | 去掉 `case.meta` 缺 `source` 检查 | 红 |
| J-M4 | 去掉 `overclaim` 分支 | 红 |
| J-M5 | `declined` → `no_artifact` | 红 |
| J-M6 | 三次各异 → 不再记 `malformed+unstable` | 红 |
| J-M7 | `g2b` 恒返回 `none`（不解析第 2 行） | 红（2 项） |
| J-M8 | 去掉 M-d 短路判断 | 红（把合法短路的 run 误判为 `malformed`） |

**J-M7/J-M8 是 D7 与 D4 落地的回归保护**：前者守「`log.g2` 第 2 行的 G2B= 必须被解析」，
后者守「pre 阶段被拦下的 run 不得被判成 `malformed`」。两条都由对应的变异体证明会红。

**J-M1 首轮存活暴露的真问题**：最初那 12 个 fixture 里没有「五门全过但断言 undeterminable」
这一例，于是把 `undeterminable` 改成 `pass` 也不变红——而这正是 §11 第 7 条最强调的一条禁忌。
补了 `mapping_checked=1` 之后才咬住。**教训：样本数够了（12/12）不等于分支覆盖够了**；
只按「七态 + 五边界」数样本，会漏掉「同一状态的不同成因」。

**门禁级变异（两道，均已还原）**：
① 把 judge 的 `undeterminable` 改成 `pass` → `G-JUDGE-1 violations=1`、`RESULT: FAIL`；
② 删掉一个 fixture（`checked` 12→11）→ `VIOLATION: checked=11，应为 12`、`RESULT: FAIL`。
