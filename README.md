# FoamMate — A lightweight agent for OpenFOAM

**把一句自然语言 CFD 需求，变成一个人能验证、机器能复算的 OpenFOAM v13 算例。**

这个仓库交付的是一套**确定性的命令行工具 + 一份入口文档**。它不含模型、不含对话、不决定下一步做什么——
模型与调度由调用方提供：**推理在 agent 一侧，FoamMate 提供 agent 缺的那一半**——确定性工具 + 门禁。

```
需求文本 ──► 四元组 ──► grep 定派生源 ──► tutorial 派生 ──► 改字典 ──► 求解 ──► 五道门禁
                │                                                              │
                └────────────────── 失败就回到「改字典」───────────────────────┘
```

它解决的核心问题**不是"生成字典"**（那件事模型做得很好），而是这三件模型做不稳的事：

1. **派生源必须是真的**——从本机 `$FOAM_TUTORIALS` 里 grep 出来的那份 tutorial 派生，不凭印象写字典。
2. **"能跑"必须可判定**——五道门禁的判据是命令输出，不是任何一方的自述。
3. **失败必须可定位**——错误日志被翻译成「改哪个文件的哪个 entry」，且定不到就停下问人，不猜。

---

## 状态

**v0.3**，可运行，已在 OpenFOAM v13 上端到端实测（方腔算例：稳态、192×192、Re=1000、五门全绿）。

| 已验证 | 说明 |
|---|---|
| 单算例闭环 | 派生 → 改字典 → 求解 → 五门门禁 → 失败回修，全程命令行 |
| 批量运行（v0.2 新增） | `cases.json` 参数矩阵 → 逐例跑完 → 汇总 `results.csv`（15 列，结论可从 CSV 重算） |
| 二次开发 / 用户库（v0.3 新增） | 派生系统子库副本 → 判改动范围 → `wmake libso` → `dlopen` 证明（退出码 `85`–`89`）。**只保证编译与加载，不保证物理正确** |
| 陌生用户可用 | 四轮独立验收：只给发布包、不给项目上下文，都能跑通 |
| 测试覆盖 | 两级测试：零 OpenFOAM 依赖的单元层 + 需真求解的契约层；判据都是 `failed=0`（项数随用例变化，`--collect-only` 取当前值） |

| 明确不做 | 原因 |
|---|---|
| 不内置 LLM / 不理解自由文本 | 这是 harness 的定义：模型由调用方提供。提取器是正则+词表，没覆盖就返回"缺需求"停下问人 |
| 不保证物理正确 | 门只判「能跑、边界齐、场可读、无越界」。Re 与网格不匹配时会**警告但不改退出码** |
| 不自动决定物理参数 | 需求说"稳态"不会自动改 `ddtSchemes`；只给诊断 `OBJ=mismatch` 和"去哪 grep 真语法"的清单。批量也只是按你给的值改 |
| 只支持 OpenFOAM v13 | 判据全部按 `/opt/openfoam13` 的真实语法核对过。换版本会同时产生假红与假绿 |
| 不做二次开发的「改 C++」那一步、不做 GUI、不做前处理自动化 | 只有派生/判范围/编译/加载证明在包内（[`release/SKILL.md`](release/SKILL.md) §11）；其余见 [`release/SCOPE.md`](release/SCOPE.md) |

---

## 快速开始

要求：OpenFOAM v13（Foundation 版）、bash、python3 ≥ 3.9；`scripts/deploy.py` 部署时另需 git。**运行脚本无第三方 Python 依赖**（全标准库）；
跑测试另需 `pytest`，见 [`requirements-dev.txt`](requirements-dev.txt)。

```bash
git clone <仓库地址> FoamMate && cd FoamMate
source /opt/openfoam13/etc/bashrc

export HARNESS=$PWD                   # 仓库根：其下同时有 scripts/ 与 release/
bash scripts/preflight.sh             # 6 项环境检查：0 全过 / 50 环境不全 / 51 版本不符
```

> `release/` 里三份文档的命令写成 `$HARNESS/scripts/xxx`。在**发布包**里 `$HARNESS` 是包根
> （三份 md 与 `scripts/` 同级）；在**本仓库**里 `$HARNESS` 是仓库根（`scripts/` 在根下，
> 三份 md 在 `release/` 下）。两种情况下 `$HARNESS/scripts/xxx` 都成立，这也是为什么文档不用相对路径。

前置检查通过后，读 [`release/SKILL.md`](release/SKILL.md)（六步链 + 退出码总表 + 四类停点），
照着 [`release/QUICKSTART.md`](release/QUICKSTART.md) 跑一遍完整例子——那份文档里**每一个输出都是真跑出来的**，
包括一次真实的失败与修法。要把它装到稳定路径、并在远端更新时一键升级，见下文「部署与更新（给 agent 的入口）」。

### 直接调用脚本

```bash
# 1. 需求 → 四元组（缺项就不是 0，不替用户补默认值）
python3 scripts/parse_requirement.py --text "一个二维方腔，顶盖 1 m/s，水，层流，稳态" --out spec.json

# 2. 找派生源（五个搜索根下 grep，输出 FOUND=命中总数 / SHOWN=输出行数）
bash scripts/find_template.sh --keyword cavity --limit 20

# 3. 派生（cp -a，不用 foamCloneCase；写 case.meta 记录来源与改动）
bash scripts/new_case.sh --source incompressibleFluid/cavity --dest ./my-case --spec spec.json

# 3b. 需要三角形网格时：2D gmsh msh → 单层三棱柱 polyMesh（blockMesh 出不了三角形）
#     换网格必须先 rm -rf constant/polyMesh；细节见 release/SKILL.md 步骤 3b
python3 scripts/msh2d_to_foam.py --msh system/triangle2d.msh --out constant/polyMesh --thickness 0.01

# 4. 跑（check 只到 checkMesh；full 内部先跑 2 步短跑再跑完整算例）
bash scripts/run_case.sh --case ./my-case --mode full --timeout 1800

# 5. 门禁（pre 零 OpenFOAM 命令；post 只解析日志）
bash scripts/verify_case.sh --stage pre  --case ./my-case
bash scripts/verify_case.sh --stage post --case ./my-case

# 6. 失败回修（只定位，不改值；改值由你决定）
python3 scripts/fix_case.py --case ./my-case --error-log ./my-case/log.shortRun --attempt 1
```

---

## 五道门禁与四类诊断

**门**决定退出码（`0` 全过 / `1` G1 / `2` G2 / `3` G3 / `4` G4 / `5` G5，只报第一个失败的门）：

| 门 | 判什么 | 注意 |
|---|---|---|
| G1 结构 | 三个 `system/` 字典在、`0/` 非空、patch 名与网格一致 | 纯文件检查，不跑 OpenFOAM |
| G2 网格 | `log.checkMesh` 里有 `Mesh OK.` | **不看 checkMesh 退出码**——网格不合格时它照样退 0 |
| G3 短跑 | `log.shortRun` 退出码 0 且无 `FOAM FATAL` | 2 步就崩的错误最快的探针 |
| G4 产物 | 末时刻目录存在、每个场可读、无 `nan`/`inf` | 场读不出也算失败 |
| G5 范围 | 只改了 `case.meta.allowed_files` 允许的文件 | 求解产物（`log.*`、时间目录）自动排除 |

**诊断**只输出、**不进退出码**（判不了的物理量不该设成门，否则所有人学会忽略它）：

| 诊断 | 含义 |
|---|---|
| `OBJ=<match\|mismatch\|unknown>` | 需求里的 `objective` 与真实 `ddtSchemes` 是否一致 |
| `GEO=cells=… convertToMeters=…` | 网格量取自**磁盘上的真实网格**，不是 `blockMeshDict` 里写的 |
| `RE=<数>` | 由特征速度、几何尺度、`nu` 估的雷诺数 |
| `RES=<coarse\|marginal\|ok\|stale>` | 按 cellRe=Re/√cells 分级的网格充足性；`stale` = 改了 `blockMeshDict` 但没重建网格 |

**一个刻意的取舍：门全绿 ≠ 需求满足。** 实测过的反例——400 个格子算 Re=1e5，五门全绿，但末时刻
最大速度只有顶盖速度的 17%，是数值扩散主导的假解。这个包只把这件事**说出来**（`RES=coarse`），
不替你决定怎么办。

---

## 仓库结构

```
scripts/        10 个用户面 CLI（需求解析 / 检索 / 派生 / 网格转换 / 求解 / 门禁 / 修复 / 前置检查 / 批量 / 二次开发）
                另含 8 个维护侧脚本（打包、导出树、部署更新、文档契约、项目门禁、状态快照…）
release/        对外交付内容源：SKILL.md（入口）+ QUICKSTART.md + SCOPE.md
tests/          两级测试：unit（零 OpenFOAM）+ contract（需真求解），判据 failed=0
bench/          跨任务基准框架：预注册方法学 + 12 个任务定义 + 七态判定器 + 断言库
references/     调研笔记、设计依据与实跑报告（00–14，含文档维护规则）+ 第三方参考库登记表（registry.csv）
AGENTS.md       项目规则：15 条（10 条硬规则 + 5 条工程约定），R1「源码事实必须 grep」是起点
LICENSE         MIT
```

### 关于 `references/`

`references/00`–`14` 是为什么这样设计的完整依据：内部说明、领域调研、逐个项目的架构分析、
证据分级、交叉矩阵、部件清单、理论溯源、交付形态选择、文档维护结构、基准实跑报告、二次开发流程。**它们不是产品的一部分**，
读它们能得到「为什么」，跑起来只需要 `scripts/` + `release/`。

`references/external/` 收录了几篇公开的方法论文章（Anthropic《Building effective agents》与
《Writing effective tools for agents》与《Agent Skills》、OpenAI《A practical guide to building agents》、
HumanLayer《12-Factor Agents》）。它们只作为**方法论证据**引用，不构成本仓库任何代码的来源。

> `references/repos/`（第三方项目的代码副本，约 185 MB）**未包含在本仓库中**。
> 那些项目只用于内部架构调研，登记信息（含每个仓库的 commit sha）见 `references/registry.csv`。
> 文中所有 `references/repos/<仓库>/<文件>:<行号>` 形式的引用都指向那些副本——按 registry 的
> sha 检出对应版本后即可回切到原文。
>
> `references/external/` 下也只有我们自己的索引 `INDEX.md`：那几篇公开方法论文章（Anthropic /
> OpenAI / HumanLayer）的**正文副本不随仓库分发**——它们版权不是我们的，MIT 覆盖不到。
> `INDEX.md` 里给了每篇的 URL、抓取日期与 sha256。
>
> 发布边界可以一条命令自检：`bash scripts/make_export.sh --dest dist/export` 从 `HEAD` 组出
> 公开导出树，再对它跑六道门（结构 / 引用可回切 / 无本机标识 / 代码可运行 / 无第三方源码 / 单文件 ≤1 MB）。

### 关于 `bench/`

一套**先定判据再跑**的跨任务基准：12 个任务各有 `expect_values` 断言层，七态结果归约，
每任务跑 3 次取多数。方法学与任务集已冻结（`bench/tasks/FROZEN.sha256` 钉住了任务文件
**和**测尺本身——只钉任务不钉测尺，等于允许冻结后偷偷放松判据）。

**已有一轮单臂实测**：`bench/results.csv` 12 行（9 pass / 2 fail / 1 declined），被测臂是确定性脚本
`ours_scripted`（不调模型）。**仍是单臂，所以本仓库不含任何跨臂比较结论**——详见 `references/12-bench-report.md`。

---

## 部署与更新（给 agent 的入口）

`scripts/deploy.py` 把这份仓库装到一个**稳定路径**，并在远端有新提交时一键更新。
部署物就是一份 git 克隆：它回答得了「装的是哪个提交」「远端有没有更新」——发布包回答不了，
所以这里不用发布包（代价：目标目录里带着 `tests/ bench/ references/`，约 2 MB）。

```bash
# 1. 首次部署：装到 ~/foam-mate，并跑该副本自己的 preflight 自检
python3 scripts/deploy.py --action install          # 0 成功；94 = 装好了但环境自检没过
export HARNESS=$HOME/foam-mate

# 2. 之后每次：检测 + 更新一步完成（已是最新也退 0）
python3 "$HARNESS/scripts/deploy.py" --action update

# 3. 只查不改（只有 --fetch 才访问远端）
python3 "$HARNESS/scripts/deploy.py" --action status --fetch
```

- `--target` 缺省 `$FOAM_MATE_HOME`，再缺省 `~/foam-mate`；`--repo-url` 缺省 = 本仓库的 origin。
- **装的是提交，不是工作树**：未提交的改动不会进部署（同 `scripts/make_export.sh`）。
- 更新只做**快进**。本地有未提交改动退 `91`、远端历史被重写退 `92`、远端不可达退 `93`，
  三种都不动手；按项目规则 force-push 须由用户明确同意。
- 部署目录不是数据目录：算例放 `$WORK`，别放进去（untracked 不阻止更新，但混在一起会让
  「装的是哪个提交」这件事变难读）。

| 退出码 | 含义 | 下一步 |
|---|---|---|
| `0` | 成功（含 `already_deployed` / `current` / `ahead` 三个幂等态） | 继续 |
| `90` | 目标状态或前置不合法（非空目录、无 origin、detached HEAD、没有部署） | 按 stderr 的 hint 改 `--target`，或先 `install` |
| `91` | 本地已跟踪文件有改动，拒绝更新 | 移走改动，或 `git -C <target> checkout -- <file>` |
| `92` | 远端不是快进（历史被重写 / 分叉） | **停下问人**：`git -C <target> log --oneline HEAD..FETCH_HEAD` 看清再决定 |
| `93` | 远端不可达（clone/fetch 失败或超时） | 查网络与 `--repo-url` |
| `94` | 部署后 `scripts/preflight.sh` 未通过 | 按 preflight 最后一行给的 `source` 命令处理后，重跑 `--action status` |
| `64` | 用法错误 | 改调用，或 `--help` |

`90`–`94` 是自留区间（全仓已用到 `89`）。`deploy.py` **不进发布包**——发布包没有 git 元数据，
更新无从谈起；它只服务「从仓库部署」这条路。

## 设计原则（三条）

1. **LLM 做翻译与决策，脚本做判定与调度。** 写字典是文本工作；但「能否运行」必须由命令输出判定。
2. **一切 case 从最近的 tutorial 派生，不凭空生成。** 凭空写字典是幻觉的主要来源，派生必须记录来源。
3. **源码是唯一权威，用 grep 查。** 网上教程多为旧版本语法；本仓库所有判据都对着本机
   `/opt/openfoam13` 核对过。

---

## 已知限制

完整清单见 [`release/SCOPE.md`](release/SCOPE.md)（12 条）。最需要先知道的四条：

1. **`checkMesh` 通过 ≠ 物理正确。** 门只保证「能跑、边界齐、场可读」。
2. **几何能力上限低。** `blockMesh` 表达不了曲面与复杂装配；需要 STL/CAD 时停下，不要自己生成几何。
3. **诊断行不改变退出码。** 如果你的自动化只看退出码，请自己 grep `OBJ=` / `RES=`。
4. **需求里的几何尺寸不会被校验。** 只说"二维方腔"时边长继承派生源的 `convertToMeters`，
   由此得到的 Re 可能远大于网格能解析的范围——`RES=` 会警告。

---

## 许可

[MIT](LICENSE)。软件按「现状」提供，不附带任何担保。

---

## 报告问题

请附三样东西，缺一无法定位：

1. 完整命令（可复制执行的那种）；
2. 完整退出码；
3. 相关 `log.*` 里的 `FOAM FATAL` 段（原文，不要转述）。

范围之外的需求不是 bug——见 [`release/SCOPE.md`](release/SCOPE.md) §1 的支持清单。
