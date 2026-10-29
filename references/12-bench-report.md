# 十二、基准实跑报告（M4b，2026-10-29）

> **本文件是 `bench/results.csv` 的配套报告**。数字口径全部来自冻结件
> `bench/preregistration.md`（§1–§9 + §13）与 `bench/tasks/T01..T12.yaml`；
> 判据由 `bench/judge.py` 归约，取值由 `bench/assert_lib.py` 完成。
> 每个汇总数字都能指到 `bench/results.csv` 的具体行（R7）。
> 批次产物：`bench/runs/m4b-20261029/`（36 个 run 根目录 / 90 个例目录 / 5045 个文件 / 80 MB，`.gitignore` 已排除）。

---

## 1 范围与限定（先说清测的是什么，以及不是什么）

**测的是什么**：12 个冻结任务，一臂（`ours_scripted`），每任务 3 次，端到端
（自然语言需求 → case → 门禁 → 断言 → 归约）。主指标 `success_rate` 的分母是
**11 个正向任务**，T12 是负对照单列。

**三条限定，缺一条就会把结论读大**：

1. **不含「自然语言 → 四元组」这一环。** 本轮臂是确定性脚本（`bench/runners/ours_scripted.py`），
   它把「改哪个文件的哪个 entry 成什么值」写成代码。所以结论只能写成
   **「C→E 脚本链对 12 类任务的回归基线」**，**不是**「agent 的能力」。
   依据：`bench/preregistration.md:275`–`284` 的退化路径（A 档可跑臂 <2 → 只出回归基线）。
2. **`tokens_total` 恒为 0**，因为 A 形态不调模型。这是可测事实，不是未测。
   因此 §8.2 的两臂比较（含「谁更省 token」）**不适用**，本报告不含任何跨臂排序。
3. **单臂**。`harnessfoam` 本轮未派单，CSV 里没有它的行。按 §7 的退化路径，
   主排名本就不成立；「未派单」不等于 `blocked`（后者定义见 `bench/preregistration.md:67`）。

---

## 2 方法与判据

### 2.1 三层归约

| 层 | 输入 | 规则 | 来源 |
|---|---|---|---|
| L1 例级 | 一个 case 的 `log.g1..g5` + `assert.json` + `arm_stdout.txt` | `judge.reduce_run()` → 七态之一 | `bench/preregistration.md:358`–`371` |
| L2 任务一次执行级 | T09 的 3 例 / T10、T11 的 9 例 / 其余 1 例 | 全 match → pass；任一门 fail 或任一断言 mismatch → fail；任一不可判定 → malformed | **本轮新增解释**（见 §9.1） |
| L3 任务级 | 3 次 L2 | `judge.reduce_task()`：≥2 次同态 → 该态；三次互异 → `malformed` + `unstable=1` | `bench/preregistration.md:288`–`296` |

### 2.2 主指标

```
success_rate(ours_scripted) = 9 / 11 = 0.8182
```

分母固定 11，未剔除任何任务（`bench/preregistration.md:45`）。T12 见 §5。

### 2.3 作废条件的逐条核对

| §9 条件 | 实测 | 判定 |
|---|---|---|
| 1 全灭（所有臂 0） | 9/11 | 未触发 |
| 2 全过（所有臂 1） | 2 个正向任务 fail | 未触发 |
| 3 负对照失守（T12 被判 pass） | T12 = `declined` | 未触发 |
| 4 状态退化（`status` 只有两种） | pass=9 / fail=2 / declined=1，共 **3** 种 | 未触发（但见 §9.4 的脆性说明） |
| 5 测量路径漂移 | 仍为端到端 12 任务 | 未触发 |

---

## 3 总表（12 行，逐格可回切 `bench/results.csv`）

| task | 类 | status | g1 | g2 | g3 | g4 | g5 | g2b | repeats | unstable | wall_time_s | 断言 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T01 | 建 | **pass** | 0 | 0 | 0 | 0 | 0 | none | 3 | 0 | 2.62 | match |
| T02 | 建 | **pass** | 0 | 0 | 0 | 0 | 0 | none | 3 | 0 | 5.10 | match |
| T03 | 建 | **pass** | 0 | 0 | 0 | 0 | 0 | none | 3 | 0 | 2.56 | match |
| T04 | 建 | **fail** | 0 | **1** | 0 | 0 | 0 | hard:1 | 3 | 0 | 7.74 | match（模型改对了，网格门不过） |
| T05 | 改 | **pass** | 0 | 0 | 0 | 0 | 0 | none | 3 | 0 | 2.58 | match |
| T06 | 改 | **pass** | 0 | 0 | 0 | 0 | 0 | none | 3 | 0 | 3.56 | match |
| T07 | 改 | **pass** | 0 | 0 | 0 | 0 | 0 | none | 3 | 0 | 2.44 | match |
| T08 | 改 | **pass** | 0 | 0 | 0 | 0 | 0 | none | 3 | 0 | 2.65 | match |
| T09 | 批 | **pass** | 0 | 0 | 0 | 0 | 0 | none | 3 | 0 | 6.99 | match（3 例） |
| T10 | 批 | **pass** | 0 | 0 | 0 | 0 | 0 | none | 3 | 0 | 20.89 | match（9 例，**读法敏感**，见 §9.2） |
| T11 | 批 | **fail** | 0 | 0 | 0 | 0 | 0 | none | 3 | 0 | 23.36 | mismatch（actual=1e-05，expect=2e-05） |
| T12 | 批·负对照 | **declined** | unmeasured ×5 | — | — | — | — | unknown | 3 | 0 | 0.00 | 见 §5 |

`wall_time_s` 合计 80.49 s（12 行求和）。**机时是本轮唯一可比的资源量**：单任务中位数约 2.6 s，
多例任务（T10/T11，各 9 例）约 21–23 s。`unstable` 全为 0：每个任务 3 次结果一致。

---

## 4 按类别得分

| 类 | 任务 | pass | 得分 |
|---|---|---|---|
| 建（build） | T01–T04 | T01 T02 T03 | **3/4** |
| 改（modify） | T05–T08 | 全 pass | **4/4** |
| 批（batch） | T09–T11 | T09 T10 | **2/3** |
| **合计（分母 11）** | | | **9/11 = 0.8182** |

**这个分布本身是结论**：单点修改（4/4）全过；建算例 3/4（唯一失败是"任务自身不可达"，不是能力问题，
见 §6.1）；批处理 2/3（唯一失败是冻结件矛盾，见 §6.2）。
**没有一条失败来自「臂改不动」**——这轮失败的 2 个任务都是**判据侧问题**。

---

## 5 T12 负对照（单列，不进分母）

| arm | status | 理由是否指认 R5 | 是否越界动网格 |
|---|---|---|---|
| `ours_scripted` | `declined` | **yes**（理由原文含「曲面几何」「边界层加密」，落在 `bench/judge.py:43` 的 `R5_MARKERS` 内） | **no**（未派生 case、未调 snappyHexMesh、未生成 STL） |

**必须一起读的一句**：脚本臂的"拒绝"是 `bench/runners/ours_scripted.py` 里写死的行为，
**不是被测系统自己判出来的**。所以 T12 在本轮验证的是
**judge 的 `declined` 判定链在真实 run 上成立**（无 `system/controlDict` + `arm_stdout.txt` 含 R5 关键词
→ `declined`），**不是**「臂懂得守住 R5」。两者不能混说。

---

## 6 失败归因（每条指到门与日志原话）

### 6.1 T04：任务集内部不可达（**不是臂的缺陷**）

`log.g2` 原文（`bench/runs/m4b-20261029/T04/ours_scripted/run1/log.g2`）：

```
RC=1
G2B=hard:1
log.checkMesh 不含 'Mesh OK.'（'***' 行 1 条）⇒ 网格门不过
checkMesh 原话：Failed 1 mesh checks.
```

**独立核验**（本方在 `$TMPDIR` 里对**原生** T3A 副本跑 `blockMesh` + `checkMesh`，未做任何修改）：

```
$ cd $TMPDIR/verify_t04/case && blockMesh && checkMesh
blockMesh rc=0
checkMesh rc=0
$ grep -c 'Mesh OK\.' log.checkMesh
0
$ grep -n 'Failed\|Max aspect' log.checkMesh
71: ***High aspect ratio cells found, Max aspect ratio: 3232.46, number of cells 178
80:Failed 1 mesh checks.
$ grep -n 'cells:' log.checkMesh
33:    cells:            26820
```

即 **T3A 自己的网格就过不了 G2**。而 T04 的断言是 `match`（`actual=kOmegaSST`）——
**臂把需求做的事情做对了**，失败完全来自参考 tutorial。
⇒ 除非臂去改 T3A 的几何/网格（那不是"换湍流模型"，且 `T04.yaml` 的 prompt 从未要求），
**任何臂都不可能 pass T04**。登记为 G-11。

`g2b=hard:1` 与 G2 失败同向，没有出现「`Mesh OK.` 与 `***` 共存」（`bench/preregistration.md:92`–`98`
说明该组合在 v13 不可达，本轮再次印证）。

### 6.2 T11：冻结件内部矛盾（**不是臂的缺陷**）

`T11` 的断言 `actual=1e-05`、`expect=2e-05`，9 例全部 mismatch。三条事实同时成立：

```
$ grep -n 'nu ' $FOAM_TUTORIALS/incompressibleFluid/cavity/constant/physicalProperties
19:nu              1e-05 [m^2/s];                       ← baseline
$ grep -n 'prompt' bench/tasks/T11.yaml
4:prompt: "9 例，汇总 max(U) 与迭代步数到 CSV。"          ← 从未要求改 nu
$ grep -n 'allowed_files' bench/tasks/T11.yaml
6:allowed_files: ["system/*", "0/U"]                    ← 不含 constant/physicalProperties
$ grep -n 'expect' bench/tasks/T11.yaml
13:  - {... "key": "nu", "expect": 2e-05, "tol": 1e-12}
```

**改 nu → G5 越界判 fail；不改 nu → 断言 mismatch 判 fail。** 两条路都是 fail，
所以 T11 在当前冻结件下**不可能 pass**。臂按 prompt 原文做事（只做速度扫描 + 汇总表），
没有为了 pass 而越界改 nu——那是通过违规换取分数。登记为 G-12。

对照：T10 的三处是**一致**的（prompt 要求「动力粘度…3 个值」、`allowed_files` 含
`constant/physicalProperties`、断言 `nu=2e-05`），所以矛盾只在 T11。

---

## 7 每臂预测 vs 实测（§10 的先行性检验）

预测写在 **2026-10-29 14:07:38 CST**，`find bench/runs -type f | wc -l` 时为 **0**
（`bench/preregistration.md` §10 末段记录了该证据）。

| 项 | 预测 | 实测 | 偏差 |
|---|---|---|---|
| `ours_scripted` success_rate | **9/11 = 0.82** | **9/11 = 0.82** | 数值完全一致 |
| 主要失败阶段 | C（改动生成） | **判据侧**（T04 任务不可达 / T11 冻结件矛盾） | **预测错在归因** |
| 结构改动（T03/T06/T08 各留一次做错的机会，预判 2 过 1 不过） | 预期 1 个 fail | **3 个全 pass** | 低估了取证充分的实现 |
| T11 必然 fail（冻结件矛盾） | 已预测 | fail | 一致 |
| T02 需新增 `0/omega` | 已预测（侦察实测） | 实际需要 **7 处**改动才 pass | 低估幅度大 |

**最有价值的偏差是第二行**：我把失败归因到「臂改不动结构」，实测却是「判据/任务集有洞」。
这正是 §10 说的「错的是我们的直觉」——而且这个直觉错误的方向是**对自己不利的**（先怀疑自己，
没先怀疑尺子）。下次遇到「某任务必 fail」时，应先把「任务自身是否可达」当成假设去验，
而不是当成臂的缺陷。证据：§6.1 的原生 T3A 复现。

T02 的 7 处改动（每处都是被一个真实 FATAL 逼出来的，证据在 `bench/runners/ours_scripted.py` 的
`Edit.evidence` 字段）：
`momentumTransport` 换模型 → 新增 `0/omega` → 补 `system/blockMeshDict`（pitzDaily 的 `system/`
里没有，Allrun 用的是共享字典）→ `fvSchemes` 加 `div(phi,omega)` → `fvSolution` 两组
solver 正则补 `omega` → `fvSchemes` 加 `wallDist`。
**这说明「换湍流模型」在 v13 里不是一条改动**，而冻结件把它列为 D2 难度。

---

## 8 诊断（不进结论句，只做解释）

| 诊断 | 实测 | 说明 |
|---|---|---|
| `g2b` 分布 | T04 `hard:1`；其余 11 行 `none`/`unknown` | T12 无网格 → `unknown`（不是 0） |
| `unstable` | 12 行全 0 | 每任务 3 次结果一致；无掷硬币任务 |
| `wall_time_s` 分布 | 2.44–2.79 s（单例）· 6.99 s（3 例）· 20.89/23.36 s（9 例）· 0.00（T12 未派生） | 机时随例数近似线性 |
| `tokens_total` | 12 行全 0 | 确定性脚本臂，可测事实 |
| `human_interventions` | 12 行全 0 | 全自动批跑，**实测的 0**（不是 `unmeasured`；G-06 口径见 §9.5） |

---

## 9 已知放宽与不一致（**这一节是报告可信度的一部分，不要跳过**）

### 9.1 L2 是本轮新增的解释层（预注册未逐字规定）

`bench/preregistration.md` 只定义了 L1（例级）与 L3（3 次归约），**没有定义多例任务怎么合成一次执行**。
本轮按 `T09.yaml` 的 `expect_values_note` 原文「三例全对才算 match」外推为合取语义，
写在 `bench/runners/run_bench.py` 的 `reduce_examples()` 与 `_aggregate()` 里。
**这是解释，不是预注册原文**；要让它成为冻结条款需要开新一轮（§8 末条：判据不得跑完后调整）。

### 9.2 T10 的断言取值是**臂自选**的（读法敏感，本报告最重要的一条保留）

`T10.yaml` 的断言钉的是 `nu=2e-05` 一个值。而 T10 要跑 9 例（nu 取 3 个值），
把同一句断言逐字施加到 9 例，6 例必然 mismatch。runner 的做法是**逐例实例化**：

```
T10_u0.5_nu1e-05  match actual=1e-05 subs={'nu':'1e-05'}
T10_u0.5_nu2e-05  match actual=2e-05 subs={'nu':'2e-05'}
T10_u0.5_nu5e-05  match actual=5e-05 subs={'nu':'5e-05'}
...（9 例同形）
```

**问题**：T10 的 nu 网格是臂自己选的（prompt 只说「各取 3 个值」，没给数值）。
断言于是变成「臂是否写了它自己声明的那个值」——**尺子成了答案的复述**，
这正是 `bench/preregistration.md:127` 明令禁止的（「不得抄 agent 输出」）。

对照 T09：U 的 0.5/1/2 **来自 prompt 原文**，逐例实例化是「按需求判」，合法。

**因此同一批 artifacts 在三种读法下给出三个分数**（重算脚本与明细：
`bench/runs/m4b-20261029/rescoring_sensitivity.json`）：

| 读法 | T09 | T10 | success_rate | 说明 |
|---|---|---|---|---|
| `primary`（已进 CSV） | pass | pass | **9/11 = 0.8182** | 多例逐例实例化（T09/T10 都用臂给出的值） |
| `t10strict`（推荐口径） | pass | **fail** | **8/11 = 0.7273** | 只保留 prompt 派生的实例化（T09 合法），T10 用冻结断言逐字 |
| `strict`（冻结断言逐字） | **fail** | **fail** | 7/11 = 0.6364 | T09 也被判 fail，**这条读法是错的**（T09 的 0.5/1/2 是需求原文） |

**结论必须写成区间**：`success_rate ∈ [0.727, 0.818]`，取决于多例断言取值算不算"臂的经验"。
`strict` 的 0.636 不进区间，因为它连 T09 这种 prompt 明确给了值的任务都判错。
**选哪个当头条口径由用户裁定**——这是判据口径问题，不是实现问题。
登记为 G-13。

### 9.3 T09/T11 的"汇总表"需求无判据

- T09 的 prompt 要求「出汇总表」，`T09.yaml` 的 `expect_values` 里没有任何关于汇总表的断言。
- T11 的 prompt 要求「汇总 max(U) 与迭代步数到 CSV」，`T11.yaml` 的 `expect_values_note`
  原文写「judge 单独查行数」，但 `bench/judge.py` 里 `grep -n 'csv\|行数\|汇总'` **零命中**。

按用户 2026-10-29 裁定（选 (a)）：**不补判据**，登记为已知放宽。
后果：T09/T11 的 pass/fail 完全不含"汇总表"这项需求。T11 恰好因为 §6.2 的矛盾而 fail，
所以这不影响 T11 的判定；但 **T09 的 pass 里，"出汇总表"这一项未被判定**。

### 9.4 G-R12-1「≥3 种状态」这个绿是脆的

本轮 `distinct_status=3` 由 pass(9) + fail(2) + declined(1) 组成，门通过了。
但这个"多样性"里，**2 个 fail 全部来自判据侧缺陷**（G-11 任务不可达、G-12 冻结件矛盾），
不是「七态判据有区分力」的证据。

可判定的检验（独立审计实测）：**把 T11 从任务集里剔掉 → `distinct_status=2` → 门立刻红**；
把 T11 改成 pass → 同样红。也就是说这个绿依赖一个 spec bug 恰好凑出第三种状态。
⇒ 报告不得写「G-R12-1 通过 ⇒ 七态有区分力」。登记为 G-14。

### 9.5 `human_interventions=0` 的口径

`bench/preregistration.md` §16 的口径是「改字典 + 答问」。本轮全自动批跑、无人介入，
所以 0 是**实测值**（不是 `unmeasured`）。但注意：本轮臂**不需要**人介入是因为它是脚本；
这个 0 **不能**外推到任何 LLM 臂。G-06 的判据（`results.csv` 里至少 1 行实测数字）因此被满足，
但它满足的方式（确定性臂）与缺口原意（人工救火次数）不是一回事，见 `references/10-gap-register.md` G-06。

---

## 10 复现命令（逐条可原样跑）

> 下面的 `python3` 在本机必须换成装了 pytest 的那个解释器（`which -a python3` 有 5 个候选，
> 只有一个是 miniforge 的）；**裸 `python3` 会得到 `No module named pytest`**，那看起来像测试坏了
> （`STATUS.md` N7 第 9 条）。

```bash
source /opt/openfoam13/etc/bashrc
cd <仓库根>

# 1 前置门禁：期望 RESULT: ALL GATES PASS
bash scripts/verify_references.sh --frozen

# 2 单元测试（零 OpenFOAM）：期望 70 passed
python3 -m pytest tests/unit/test_bench_runner.py -q

# 3 干跑（不建任何目录；会逐条核对每条改动的 R1 证据）
python3 bench/runners/run_bench.py --dry-run

# 4 实跑（12 任务 × 3 次，约 80 s；本次实际耗时 81 s）
python3 bench/runners/run_bench.py \
  --tasks T01,T02,T03,T04,T05,T06,T07,T08,T09,T10,T11,T12 \
  --repeats 3 --dest bench/runs --batch m4b-20261029 --mode short --jobs 1

# 5 CSV 契约（15 列）
python3 scripts/check_contracts.py --results bench/results.csv

# 6 状态分布（期望 3 种：pass=9 / fail=2 / declined=1）
awk -F, 'NR>1{print $3}' bench/results.csv | sort | uniq -c

# 7 逐格重算（不看 CSV，从 runs/ 重建再比对）：期望 checked=12 行 × 14 列，diffs=0
python3 "$TMPDIR/check_recompute.py" bench/runs/m4b-20261029

# 8 三种断言读法的敏感性：9/11 · 8/11 · 7/11
python3 "$TMPDIR/rescore.py" bench/runs/m4b-20261029

# 9 全套门禁 + 测试
bash scripts/verify_references.sh --frozen
python3 -m pytest tests/unit tests/contract -q
```

> 第 7、8 条的脚本目前放在 `$TMPDIR`（scratch），**不在仓库里**——它们是本轮的一次性核验工具。
> 若要长期可复现，需要把它们移进 `bench/`（那会改动发布白名单的判断，见
> `scripts/make_release.sh` 的 `FORBIDDEN_PREFIX`，N7 第 21 条）。本轮未做，登记在此。
>
> 第 9 条的**已知不稳定项**：`tests/contract/test_batch_e2e.py::test_numbers_are_recomputable_from_csv`
> 会因 `scripts/batch.py` 的负墙钟（P-01）偶发红——全量跑才出现，单独跑全绿。根因与现场见 §11。

---

## 11 本轮发现的缺陷清单（按「会不会让结论假」排序）

| ID | 发现 | 位置 | 会让什么假 | 状态 |
|---|---|---|---|---|
| **G-11** | **T04 任务集内不可达**：原生 T3A 网格 `Failed 1 mesh checks.`，无 `Mesh OK.` | `bench/tasks/T04.yaml` + `$FOAM_TUTORIALS/incompressibleFluid/T3A` | 让「建算例 3/4」被读成能力不足 | 待裁定 |
| **G-12** | **T11 冻结件内部矛盾**：断言 `nu=2e-05`，但 `allowed_files`/prompt 都不允许也没要求改 nu | `bench/tasks/T11.yaml:4/6/13` | 让「批 2/3」被读成能力不足 | 待裁定 |
| **G-13** | **T10 多例断言取值由臂自选**（尺子成答案复述） | `bench/tasks/T10.yaml:13` + runner 的实例化 | **让 success_rate 偏高 1/11** | 待裁定 |
| **G-14** | G-R12-1 的绿依赖 G-12 凑数 | `scripts/verify_references.sh:109`–`140` | 让「状态多样性」被读成「判据有区分力」 | 报内说明（§9.4） |
| **G-10** | `T02.yaml` 的 `expect_values_note` 事实错误：「0/omega 本来就存在」，实测 pitzDaily 的 `0/` 无 omega | `bench/tasks/T02.yaml:13` | 误导下一个实现者，且掩盖了「换模型要 7 处改动」 | 待裁定 |
| **P-01** | `scripts/batch.py` 用非单调的 `time.time()` 测时长 → `wall_time_s` 可为负（实测 `-1.7`） | `scripts/batch.py:589`/`:598` | 交付物里的数字不是测量值（违 R6） | **需授权**（超出本轮范围） |

**P-01 的现场**（本轮抓到的、`STATUS.md` N4 第 4 条那个"未归因偶发红"的真因）：

```
$ pytest tests/unit tests/contract -q     # 全量跑
E  AssertionError: cavity_cm0.1 的 wall_time_s=-1.7 为负
E  assert -1.7 >= 0
1 failed, 299 passed in 116.61s

$ 单独跑同一测试 4 次
1 passed in 6.15s / 6.16s / 5.88s / 6.28s      ← 全绿
```

失败现场 `metrics.json`：`cavity_cm0.1` = `-1.7`，另两例 `0.52` / `0.56`。
**机制**：`started = time.time()` 与 `wall = wall_seconds(time.time() - started)` 之间墙钟倒退了
1.7 s（CLOCK_REALTIME 被步进校正；WSL2 上常见）。耗时必须用 `time.monotonic()`。

**这条同时纠正了一处既有归因**：`STATUS.md` N4 第 4 条把该偶发红归为「判据依赖机器速度」，
并推断「它会把偶发红训练成『重跑就好』」。实测表明 **判据不是速度敏感的**（`value >= 0` 是符号检查），
真因是**被测代码自身产出了负值**。原文的教训（必须抓现场）成立，归因需改。

---

## 12 结论

1. **`success_rate = 9/11 = 0.8182`（primary 读法）**；按更严的 `t10strict` 读法是 **8/11 = 0.7273**。
   两者都是实测，差异只来自 T10 多例断言的取值算不算"臂的经验"（G-13）。**区间 [0.727, 0.818]。**
2. **失败的两个任务都不是"臂改不动"**：T04 是任务集不可达（G-11），T11 是冻结件矛盾（G-12）。
   本报告的主体结论因此是：**这轮实测比分数更有价值的部分，是它把三处冻结件缺陷打出来了。**
3. **可以说的**：本 harness 的确定性链（派生 → 改参数 → 五门 → 断言 → 七态归约）在 12 个任务的
   30 个例子上跑通，产物可逐格重算（diffs=0），3 次重复全部一致（`unstable` 全 0）。
4. **不能说的**：任何"agent 能力"结论（无模型）、任何跨臂排序（单臂）、
   任何"A 比 B 更省"（token 恒 0）、以及「G-R12-1 通过 ⇒ 七态有区分力」（§9.4）。
