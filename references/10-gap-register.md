# 十、缺口清单（可判定版，2026-10-28）

> **定位**：本文件**不产生新事实**，只把「已经声称要做、但当前实测没做到」的条目逐条列出，
> 每条给**现状证据**（命令 + 真实输出）、**判据**（怎样算补齐）、**验收命令**（补齐后跑什么、期望什么）。
> 它是 `09-architecture-and-test-plan.md` 的配套件：`09` 说**该做成什么样**，本文件说**还差什么、怎么验**。
>
> **「缺口」的判定口径**（避免这个词被滥用）：
> 一条算缺口，必须同时满足 ①**某个文档或冻结件声明了它**（给出 `path:line`）②当前**实测**不满足它。
> 只是「可以更好」的，不算缺口，列在 §4「不算缺口的」里。
>
> 证据分级沿用 `references/03-evidence-audit.md:12`（`E0` 行：本机命令输出）：本文件的每条现状都是 **E0**，
> 复现命令都写在条目里。
>
> **基线（2026-10-28 22:04 实测）**：`tests/unit` 67 passed · `tests/contract` 31 passed ·
> `judge` 自测 12+3+3+2+4 全 0 failed · `selftest_expect` `checked=12 failed=0` ·
> `bash scripts/verify_references.sh --frozen` → `RESULT: ALL GATES PASS`（**11 道门**：
`G-R9-1` `G-R10-1` `G-R11-1` `G-R12-1` `G-R12-2` `G-R12-3` `G-BENCH-1` `G-JUDGE-1` `G-R13-1`
`G-DOC-1` `G-CONTRACT-1`。注：`grep -c '^head1'` 得 12，因为第 22 行是 `head1()` **函数定义**——
按 `head1` 行数报门数会多算一道）。

## 0 三句话

1. **测试框架本身完整，被测系统的覆盖有 9 处缺口**：`98` 项测试 + `24` 项声明式自测 +
   `12` 道门，但 **L3/L4 零数据**、**七态里六态没有真实 run 覆盖**、**LLM 层未接**。
2. **只有 1 条是「文档说要做、代码没做」**（G-01）；其余 8 条都是「**还没到那一步**」——
   它们是里程碑未开工，不是实现缺陷。两类混淆会让人把「进度」当成「bug」。
3. **最该先做的不是 G-01**（它甚至可能该被删掉），而是 **G-02/G-03**：
   一条真实任务跑通，能同时揭穿其余缺口里的假设（含 G-04 的六态、G-06 的计数口径）。

## 0.1 M4b 实跑之后的缺口状态（2026-10-29，**本节覆盖 §1/§2 里对应的"零数据"描述**）

实跑报告：`references/12-bench-report.md`；数据：`bench/results.csv`（12 行）+ `bench/runs/m4b-20261029/`。

| ID | 实跑前的状态 | 实跑后 | 判据证据 |
|---|---|---|---|
| G-02 | L3 零数据：无任何测试读 `bench/tasks/` | **部分补齐** | 12 个任务已被 runner 实跑（36 个 run 根目录 / 90 个例目录），`bench/runners/ours_scripted.py:load_task()` 逐条读 `bench/tasks/T01..T12.yaml`；但**没有 pytest 测试**走完 A→C→D→E→assert→judge。`grep -rln 'bench/tasks/T0' tests/ --include=*.py` 仍只命中一处注释。**不把"runner 跑过"冒充"测试覆盖"** |
| G-03 | L4 零数据；`results.csv` 可重算性从未验证 | **已补齐** | `awk -F, 'NR>1{print $3}' bench/results.csv \| sort -u \| grep -c .` → **3**；逐格从 `runs/` 重算 → `checked=12 行 × 14 列，diffs=0`（脚本见报告 §10 第 7 条） |
| G-04 | 七态里 6 态只有合成 fixture | **部分补齐** | 真实 run 覆盖：`pass`=9 行、`fail`=2 行、`declined`=1 行。仍只有合成 fixture 的：`no_artifact` / `malformed` / `blocked` / `overclaim`（本轮 12 个任务没有产生这四态） |
| G-06 | `human_interventions` 无真实值 | **形式上补齐，实质退化** | 12 行全是实测 `0`（`awk -F, 'NR>1 && $14!="unmeasured"…'` → 实值 12 行）。但 0 的原因是**臂是确定性脚本、不需要人介入**，与「人工救火次数」的原意不是一回事；**不得外推到任何 LLM 臂** |
| G-08 | `bench/adapters/` 只有 README | **未变（本轮范围外）** | `ls bench/adapters/` → `README.md` |
| G-07 | `prereg:267` B=9 vs 实测 B=10 | **未变，仍待裁定** | 本轮未触碰冻结切片 |

**新增 5 条（全部由本轮实跑或独立审计打出）**：G-10 ~ G-14 见 §2 末尾。

---

## 1 总表

| ID | 缺口 | 类别 | 阻塞什么 | 依据 |
|---|---|---|---|---|
| **G-01** | `P4b` 的两条判据（G3 版本行、G4 场值上限）既无实现、**也无冻结件依据** | 文档说要做、代码没做 | E 模块能否声称「按 spec 完成」 | `references/09-architecture-and-test-plan.md:569`；`bench/preregistration.md:87`–`88`（原文无此要求） |
| **G-02** | L3 单任务层**零数据**：没有任何测试引用 `bench/tasks/` 的 12 个任务 | 里程碑未开工 | 端到端可信度、M4b 实跑 | `09` §3 的 L3 定义；`grep` 实测 0 引用 |
| **G-03** | L4 12 任务层**零数据**：`bench/runs/` 0 文件、`results.csv` 0 数据行；`results.csv` 的可重算性从未验证 | 里程碑未开工（R12 刻意禁跑） | 任何跨臂结论 | `bench/preregistration.md:387`–`390`；R12 |
| **G-04** | 七态里 **6 态没有真实 run 覆盖**（只有合成 fixture） | 覆盖缺口 | 判定器在真实输入上的行为 | `bench/selftest_judge.py`（合成）+ `tests/contract/test_end_to_end.py`（只有 pass） |
| **G-05** | **LLM 层完全未接**：A/C/F 三处的「模型」侧都是空的 | 里程碑未开工（M3） | 自然语言端到端 | `09` §1 表把 A/C/F 标为「模型+脚本校验」；`grep` 实测 0 处 LLM 调用 |
| **G-06** | `human_interventions` 口径已冻结但**无任何真实值** | 依赖 G-03 | 该列能否进结论句 | `bench/preregistration.md` §16；`09` §10.4 第 2 条 |
| **G-07** | `prereg:267` 的 **B=9** 与实测 **B=10** 矛盾（冻结切片内） | 冻结件自身矛盾 | 参考库统计的可引用性 | `bench/preregistration.md:267` |
| **G-08** | `bench/adapters/` **只有 README**，没有任何 adapter 实现 | 里程碑未开工（M4b） | B 档项目的定性对照 | `bench/adapters/README.md:1`（自称 M4b 才实现） |
| **G-09** | `bench/adapters/README.md` 的 adapter 返回约定只列 **6 态**，漏 `declined` | 文档与实现不一致（可当场修） | adapter 实现者会漏掉一个合法状态 | `bench/adapters/README.md:13` vs `bench/judge.py:39` |
| **G-10** | `T02.yaml` 的 note 声称「`0/omega` 本来就存在」，**实测不存在** | 冻结件事实错误 | 照它实现的臂会 FATAL；且掩盖「换模型要 7 处改动」 | `bench/tasks/T02.yaml:13`；§2 G-10 |
| **G-11** | **T04 在任务集内不可达**：原生 T3A 网格 `Failed 1 mesh checks.`、无 `Mesh OK.` | 冻结件设计缺陷 | 任何臂都不可能 pass T04；`success_rate` 上限被压到 10/11 | §2 G-11（含原生副本复现命令） |
| **G-12** | **T11 断言与其 prompt / allowed_files 矛盾**：断言要 `nu=2e-05`，但两者都不允许也没要求改 nu | 冻结件设计缺陷 | T11 不可能 pass（改则越界、不改则 mismatch） | §2 G-12 |
| **G-13** | **多例任务的断言取值由臂自选**（T10 的 nu 网格），尺子成了答案的复述 | 判据设计缺陷 | `success_rate` 在 9/11 与 8/11 之间浮动 | `bench/preregistration.md:127`；§2 G-13 |
| **G-14** | **G-R12-1「≥3 态」的绿依赖 G-12 凑数** | 门与结论的耦合 | 会让「门绿」被读成「七态有区分力」 | §2 G-14 |

**严重度不是「都重要」**：G-01、G-07、G-09 是**文档层**（可判定、工作量小）；G-02/G-03/G-05 是**里程碑**（大）；
G-04/G-06 是**派生物**（依赖 G-03 先有数据）。

---

## 2 逐条

### G-01 `P4b` 的两条判据：无实现，且无冻结件依据

**声明在哪**：`references/09-architecture-and-test-plan.md:569`

```
| P4b | **G3 版本行 + G4 场值有限+上限** | **E-full** | 两条都体现在 `--stage post` | ❌ **仍未做** …
```

**现状证据**：

```bash
$ grep -cE 'version|上限|isfinite' scripts/verify_case.sh
0
```

E-full 的 G3 实际判据（`scripts/verify_case.sh` 的 G3 段注释）是
「`log.shortRun` 存在且非空、不含 `FOAM FATAL`、含 `End`」；G4 是
「末时刻目录存在（名字可解析为 float 的最大目录，排除 `0`）+ 至少一个场文件
`foamDictionary <file> -entry internalField -value` 非空 + 该目录 `grep -rilE 'nan|inf'` 为空」。
**两者都不含「版本行」与「值上限」**。

**关键发现（必须先看这条再决定做不做）**：**冻结件的 G3/G4 定义里没有这两条**。

```bash
$ sed -n '87,88p' bench/preregistration.md
| G3 短跑 | 缩到 2–3 步，退出码 0，日志无 `FOAM FATAL` | `foamDictionary -entry endTime -set <小值> …; foamRun -case <c> > log.shortRun 2>&1` |
| G4 产物可读 | 末时刻存在；场可读；无 `nan`/`inf` | `foamDictionary -entry internalField -value <末时刻>/U \| head -1` 非空 |
```

即 `P4b` 是 `09` **自己加的前置项**，既不来自预注册，也没有引用任何上游。
所以它有两种合法去向，**二选一，都必须留痕**：

| 选项 | 动作 | 代价 |
|---|---|---|
| **(a) 实现** | 在 `--stage post` 加两条：G3 检查 `log.shortRun` 里含可解析的版本行（v13 实测形如 `Build  : 13-...`，需先 grep 确认原文）；G4 检查末时刻场值落在给定上限内 | 需新增 2 项 L2 测试 + 2 个变异体；且**要给上限定义一个来源**（上限写在哪？任务 yaml？），否则不可判定 |
| **(b) 删掉** | 从 `09` §6 删 `P4b` 行，并在 §10 记一句「原 P4b 无上游依据，已删」 | 零代码；但若将来真需要「值上限」，要重新论证 |

**不建议「先实现再说」**：`G4 场值上限` 的「上限」目前**没有定义**——
任务 yaml 里没有这个字段，预注册也没有。没有定义的上限写进代码，就是让实现者自己编一个数，
这与 R6「数字必须实测」相抵触。

**判据（补齐后成立）**：
- 选 (a)：`grep -c 'version' scripts/verify_case.sh` ≥ 1 **且** `pytest tests/contract/test_verify_case_post.py -q` 的项数
  从 9 变 11 **且** 新增 2 个能变红的变异体；并且**上限的来源**在 `09` 里写成可判定的（哪个文件的哪个字段）。
- 选 (b)：`grep -c 'P4b' references/09-architecture-and-test-plan.md` 为 0 或仅出现在「已删」的记录里。

**验收命令**：

```bash
# 选 (a)
grep -c 'version' scripts/verify_case.sh                  # 期望 >= 1
python3 -m pytest tests/contract/test_verify_case_post.py -q                      # 期望 11 passed
# 选 (b)
grep -n 'P4b' references/09-architecture-and-test-plan.md  # 期望只命中"已删"记录
```

---

### G-02 L3 单任务层：零数据

**声明在哪**：`09` §3 的分层表把「L3 单任务（1 个 task yaml × 1 个臂）」列为独立层；
`09` §8 的对照表把 12 个任务映射到模块链。

**现状证据**：命名空间里**没有任何测试读 `bench/tasks/`**。

```bash
$ grep -rl 'bench/tasks\|T01.yaml\|expect_values' tests/ --include=*.py
tests/contract/test_end_to_end.py
# ↑ 唯一命中是 test_end_to_end.py:161 的一行注释：「不读 `bench/tasks/`，避免与 R12 搅在一起」
$ grep -c 'bench/tasks' tests/contract/test_end_to_end.py
1        # 注释而已，不是读取
```

**为什么这是缺口而不是选择**：12 个任务 yaml 里带 `expect_values`（断言层），而
`assert_lib.py` 已经能取值（`selftest_expect.py` 实测 `checked=12 failed=0`）——
**尺子造好了，但从没量过任何一个任务**。端到端测试用的是我自己现造的
一条最小断言（`deltaT=0.005`），不是 12 个任务里的任何一条。

**判据**：存在至少 1 项测试满足：①读 `bench/tasks/T01.yaml` ②经 A→C→D→E→assert→judge
③断言 `status` 为预期值。**且该测试不写 `bench/runs/`**（R12 未解冻前只能写 `tmp_path`）。

**验收命令**：

```bash
grep -rln 'bench/tasks/T0' tests/ --include=*.py       # 期望非空
ls bench/runs/ | wc -l                                 # 期望仍为 0（R12）
```

**依赖**：G-05（任务 yaml 的 prompt 需要模型来解析；也可先用人工填好的 `spec.json` 绕过，那样只测 C→E 段）。

---

### G-03 L4 12 任务层：零数据（R12 刻意）

**声明在哪**：`bench/preregistration.md:387`–`390`（run 目录布局与 `results.csv` 列定义）。

**现状证据**：

```bash
$ ls bench/runs/ | wc -l
0
$ echo $(( $(wc -l < bench/results.csv) - 1 ))
0
```

`results.csv` 目前**只有表头**，故其「可重算性」（删表从 `runs/` 重建得逐字节相同）
**从未被验证过**——它需要 ≥1 条真实数据行才谈得上重算。

**判据**：`bench/runs/` 出现 ≥1 条实跑数据行，且
①`results.csv` 的 `status` 列出现 ≥3 种取值（R12-1 的判据，七态下只出现两种 = 判定被简化成二值）
②从 `runs/` 重建 `results.csv` 得逐字节相同。

**验收命令**：

```bash
bash scripts/verify_references.sh --frozen   # G-R12-1 会开始真正检验（现在 checked=0）
awk -F, 'NR>1{print $3}' bench/results.csv | sort -u | grep -c .   # 期望 >= 3
```

**前置条件（三条全过才允许解冻）**：见 `STATUS.md` N4 与 `bench/preregistration.md` §10 的每臂预测补填。

---

### G-04 七态里六态没有真实 run 覆盖

**声明在哪**：`bench/preregistration.md` §4（七态定义）+ §11 第 4 条（合成自测要求）。

**现状证据**（合成 fixture 数 vs 真实 run 数）：

```bash
$ for s in pass fail no_artifact malformed blocked overclaim declined; do
    printf '%-12s 合成=%s 真实=%s\n' "$s" \
      "$(grep -c "\"$s\"" bench/selftest_judge.py)" \
      "$(grep -c "\"$s\"" tests/contract/test_end_to_end.py)"; done
pass         合成=12  真实=1
fail         合成=9   真实=0
no_artifact  合成=2   真实=0
malformed    合成=9   真实=0
blocked      合成=2   真实=0
overclaim    合成=2   真实=0
declined     合成=2   真实=0
```

**这条缺口的性质要说清**：合成 fixture 证明的是「**判定器认得这种输入**」，
不是「**系统真会产出这种输入**」。两者差一层：比如 `overclaim` 要求 `arm_stdout.txt`
里有「已完成」字样且某门不过——除了造样本，没人验证过真实臂会不会那么写。

**判据**：至少 `fail` 与 `declined` 各有 1 条**由真实脚本链产出**的 run（不是手写 fixture）。
`fail` 最容易：拿 `--mode short` 跑一个删了 `fvSolution` 的 case，`log.g3` 会 RC=1，
judge 应判 `fail`；`declined` 需要臂真的拒绝（可先用 `fix_case.py` 的 declined 输出模拟）。

**验收命令**：

```bash
# 期望新增端到端用例，且它们不写 bench/
python3 -m pytest tests/contract/test_end_to_end.py -q --collect-only | grep -c '::'
# 期望 >= 3（现在是 1：只有 pass）
```

**依赖**：可独立于 G-03 做（用 `tmp_path` 即可）。

---

### G-05 LLM 层完全未接（M3）

**声明在哪**：`09` §1 的模块表把 A/C/F 标为「模型+脚本校验」；
`09` §2-A 明确「接 LLM 时只换 `extract_quad`」。

**现状证据**：

```bash
$ grep -rln 'openai\|anthropic\|api_key\|requests.post' scripts/ bench/
# （无输出）
```

三个部件的**确定性半边**都已落地（A 的 `validate_quad`、F 的 locate/apply 两层），
**模型半边**是空的。这意味着「自然语言 → case」目前**跑不通**：
A 用正则是从固定词表里抽，遇到没覆盖的表述就返回 `complete=false` 停下问人（这是设计好的行为，
不是缺陷），C/D/E/F 全链本身不需要模型。

**判据**：A 的提取器可被替换为 LLM 实现，且
①`tests/unit/test_parse_requirement.py` 的 16 项**一行不改**仍全绿（校验器契约稳定）；
②新增的模型层有「输出过不了校验器」的负例（模型胡说时必须被判 `complete=false`，不许放行）。

**验收命令**：

```bash
python3 -m pytest tests/unit/test_parse_requirement.py -q                        # 期望仍 16 passed
grep -c 'def extract_quad' scripts/parse_requirement.py                               # 期望 >= 1（替换点存在）
```

**注意**：接 LLM 会引入 R12 之外的成本问题（token/网络/不确定性），
`bench/preregistration.md` §11 的「每任务跑 3 次取多数」就是为它准备的。

---

### G-06 `human_interventions` 无真实值

**声明在哪**：`bench/preregistration.md` §16（口径已冻结：算「改字典」+「答问」）。

**现状证据**：L1/L2 全程无人，故该列恒应为 0 而**当前没有任何一列**（`results.csv` 0 行）。
`09` §10.4 第 2 条已登记这一点。

**判据**：`results.csv` 里至少 1 行的 `human_interventions` 是**实测数字**而非 `unmeasured`，
且该行的 `note` 能指出干预发生在哪一步（否则无法复核计数）。

**验收命令**：

```bash
awk -F, 'NR>1 && $14!="unmeasured" && $14!="" {print; n++} END{print "实值行数="n+0}' bench/results.csv
# 期望 >= 1
```

**依赖**：G-03（必须先有实跑）。

---

### G-07 `prereg:267` 的 B=9 与实测 B=10 矛盾

**声明在哪**：`bench/preregistration.md:267`（**在冻结切片内**）

```
> **实测 tier 分布**（`references/registry.csv`，2026-10-27）：A=1、B=9、C=1。
```

**现状证据**：

```bash
$ awk -F, 'NR>1 && $8=="B"' references/registry.csv | wc -l
10
```

**这条为什么不能顺手改**：该行在 `bench/freeze_digest.py:28` 的 `SLICES` 覆盖范围内，
改它会让 `G-R12-3`（冻结章节指纹）变红，按 prereg 变更规则算**新一轮**。

**两种合法处置**（`STATUS.md` N5.2 已列为待用户裁定）：

| 选项 | 动作 | 代价 |
|---|---|---|
| (a) 开新一轮 | 改 §7 正文 → 重算 `bench/freeze_digest.py` 指纹 → 在「轮次记录」追加一行 → 旧轮 `results.csv` 标 `void` | 当前 `results.csv` 0 行、`runs/` 空，**此刻代价最低**；之后有数据了代价会陡增 |
| (b) 出报告时脚注 | 不改冻结件，M4b 报告脚注写明「本报告用 B=10，冻结文档 §7 正文写 B=9 是笔误」 | 零成本，但**每次引用都要带脚注**，容易漏 |

**判据**：
- 选 (a)：`G-R12-3` 变红后按流程重算并记录；`grep -c 'B=10' bench/preregistration.md` ≥ 1；
  `bash scripts/verify_references.sh --frozen` 恢复 `ALL GATES PASS`；「轮次记录」多一行。
- 选 (b)：M4b 报告里出现该脚注（可 grep 到）。

**验收命令**：

```bash
sed -n '267p' bench/preregistration.md | grep -c 'B=10'   # 选 (a) 时期望 1
awk -F, 'NR>1 && $8=="B"' references/registry.csv | wc -l  # 期望 10（两边一致）
```

---

### G-08 `bench/adapters/` 只有 README

**声明在哪**：`bench/adapters/README.md:1`「Adapter 接口契约（**M4b 才实现**，M4a 只冻结形状）」。

**现状证据**：

```bash
$ ls bench/adapters/
README.md
```

**这不是缺陷**——README 自己声明了 M4b 才实现。列出来是因为它**阻塞 G-03**：
B 档项目（10 个里的多数）要进 L4 必须经 adapter 做命令级替换。

**判据**：至少 1 个 `bench/adapters/<arm>.py` 满足 README 的 `run_task(task, workdir, env) -> dict` 契约，
且**不 import 任何 LLM SDK**（B 档只做命令级适配，见 `AGENTS.md` R11）。

**验收命令**：

```bash
ls bench/adapters/*.py 2>/dev/null | wc -l        # 期望 >= 1
grep -L 'def run_task' bench/adapters/*.py        # 期望无输出（都有该函数）
```

---

### G-09 `adapters/README.md` 只列 6 态，漏 `declined`

**声明在哪**：`bench/adapters/README.md:13`

```
    返回: {"status": "pass|fail|no_artifact|malformed|blocked|overclaim",
```

**现状证据**：`bench/judge.py:39` 是**七态**，含 `declined`：

```bash
$ python3 -c "import sys;sys.path.insert(0,'bench');from judge import STATES;print(STATES)"
('pass', 'fail', 'no_artifact', 'malformed', 'blocked', 'overclaim', 'declined')
```

**为什么这是真缺口**：T12 是负对照，正解就是 `declined`（`bench/preregistration.md:69` 的 `declined` 行原文：
「**正确拒绝**：不产出 case，且给出了可指认的理由（指向 R5 的限制）」，并注明「只有 T12 会出现」）。
adapter 实现者照 README 的六态写，会把 `declined` 当成非法值丢弃或抛异常——
**恰好丢掉唯一一个「正确拒绝」的状态**。

**判据**：`bench/adapters/README.md` 的返回约定含 `declined`，
且与 `bench/judge.py` 的 `STATES` **逐字一致**（顺序不做要求）。

**验收命令**：

```bash
grep -c 'declined' bench/adapters/README.md         # 期望 >= 1
# 更好：让 G 的校验器也管这条（见下"顺手可做"）
```

**处置**：`bench/adapters/README.md` **不在** `bench/tasks/FROZEN.sha256` 里（实测 `grep -c adapters` → 0），
所以**可以直接改，不触冻结**。

---

### G-10 `T02.yaml` 的 note 是事实错误：pitzDaily 根本没有 `0/omega`

**声明在哪**：`bench/tasks/T02.yaml:13`（`expect_values_note`）

```
  baseline model=kEpsilon（momentumTransport:21）。0/omega 本来就存在，不能拿它当判据。
```

**现状证据（实测，命令可原样跑）**：

```bash
$ source /opt/openfoam13/etc/bashrc
$ ls $FOAM_TUTORIALS/incompressibleFluid/pitzDaily/0/
U  epsilon  k  nuTilda  nut  p
$ ls $FOAM_TUTORIALS/incompressibleFluid/pitzDaily/0/ | grep -c '^omega$'
0
```

**为什么它是缺口**：note 告诉实现者「omega 本来就存在，不用管它」。照做的人会得到
一次 `FOAM FATAL`（kOmegaSST 要读 omega）。实测正确解法需要 **7 处**改动
（`momentumTransport` + 新增 `0/omega` + 补 `system/blockMeshDict` + `div(phi,omega)` +
两组 solver 正则 + `wallDist`），见 `references/12-bench-report.md` §7。

**判据**：`sed -n '13p' bench/tasks/T02.yaml` 不再声称 omega 存在，且与实测一致。

**处置**：该文件在 `FROZEN.sha256` 内，改它算**新一轮**（§8 末条）。**本轮不改**，只在报告里
记下「臂按实测做法实现了 7 处改动并 pass」，note 保留原样作为证据。

---

### G-11 T04 任务集内不可达：原生 T3A 的网格过不了 G2

**声明在哪**：`bench/tasks/T04.yaml`（`reference_tutorial: incompressibleFluid/T3A`）

**现状证据（本方独立复现，未修改任何文件）**：

```bash
$ W=$TMPDIR/verify_t04 && cp -a $FOAM_TUTORIALS/incompressibleFluid/T3A $W/case
$ cd $W/case && blockMesh > ../log.blockMesh 2>&1; echo $?      # 0
$ checkMesh > ../log.checkMesh 2>&1; echo $?                     # 0（注意：退出码 0，见 N3 #19）
$ grep -c 'Mesh OK\.' ../log.checkMesh
0
$ grep -n 'Max aspect\|Failed' ../log.checkMesh
71: ***High aspect ratio cells found, Max aspect ratio: 3232.46, number of cells 178
80:Failed 1 mesh checks.
```

**为什么它是缺口**：G2 的唯一判据是「`log.checkMesh` 含 `Mesh OK.`」。
原生 T3A 不打印它 ⇒ **任何臂都不可能 pass T04**，除非它去改 T3A 的几何/网格——
那不是「换湍流模型」，`T04.yaml` 的 prompt 也从未要求。
实跑结果与之吻合：T04 的**断言 match**（`actual=kOmegaSST`，臂做对了），**G2 = RC=1**。

**代价**：`success_rate` 的上限被压到 10/11，而这不是能力问题。

**判据（补齐后成立）**：要么换参考 tutorial（一个 G2 能过的 kOmegaSSTLM 算例），
要么在 `T04.yaml` 里显式声明「本任务的 G2 按 mesh 自定义判据」。两者都要开新一轮。

**处置**：本轮不改冻结件；报告 §6.1 写明，**不得**把 T04 的 fail 读成能力不足。

---

### G-12 T11 冻结件内部矛盾：断言要 `nu=2e-05`，但既不允许也没要求改 nu

**声明在哪**：`bench/tasks/T11.yaml:4`（prompt）/ `:6`（allowed_files）/ `:13`（断言）

```bash
$ grep -n 'prompt\|allowed_files\|expect' bench/tasks/T11.yaml
4:prompt: "9 例，汇总 max(U) 与迭代步数到 CSV。"
6:allowed_files: ["system/*", "0/U"]
13:  - {... "key": "nu", "expect": 2e-05, "tol": 1e-12}
$ grep -n 'nu ' $FOAM_TUTORIALS/incompressibleFluid/cavity/constant/physicalProperties
19:nu              1e-05 [m^2/s];
```

**为什么它是缺口**：改 nu → G5 越界（`constant/physicalProperties` 不在白名单）→ fail；
不改 nu → 断言 mismatch → fail。**两条路都 fail**，故 T11 在当前冻结件下不可能 pass。
实跑 9 例全部 `actual=1e-05 / expect=2e-05`。
对照 T10：prompt 要求改 nu、`allowed_files` 含 `constant/physicalProperties`、断言 `nu=2e-05`，三处一致。

**判据**：`T11.yaml` 的断言与其 prompt/allowed_files 不再矛盾。

**处置**：本轮不改（冻结件）；臂按 prompt 原文只做速度扫描 + 汇总表，
**没有为了 pass 而越界改 nu**。报告 §6.2 写明。

---

### G-13 多例任务的断言取值由臂自选（尺子成了答案的复述）

**声明在哪**：`bench/preregistration.md:127`（「不得抄 agent 输出（尺子变成答案的复述）」）
vs `T09.yaml` / `T10.yaml` 的 `expect_values_note`（「三例全对才算 match」/「9 例逐个施加」）

**现状证据**：`T10.yaml` 只钉 `nu=2e-05` 一个值，而任务是 9 例（nu 取 3 值）。
runner 的做法是**逐例实例化**，于是断言变成「臂是否写了它自己声明的那个值」：

```
T10_u0.5_nu1e-05  match actual=1e-05 subs={'nu':'1e-05'}
T10_u0.5_nu5e-05  match actual=5e-05 subs={'nu':'5e-05'}
```

**与 T09 的区别（关键）**：T09 的 U 取 0.5/1/2 **来自 prompt 原文**，逐例实例化是「按需求判」，合法。
T10 的 nu 网格是**臂自己选的**（prompt 只说「各取 3 个值」），实例化就等于让臂定义判据。

**代价（实测）**：同一批 artifacts 三种读法给出三个 success_rate
（`bench/runs/m4b-20261029/rescoring_sensitivity.json`）：

| 读法 | success_rate |
|---|---|
| `primary`（已进 CSV，T09/T10 都实例化） | 9/11 = 0.8182 |
| `t10strict`（只保留 prompt 派生的实例化） | 8/11 = 0.7273 |
| `strict`（冻结断言逐字） | 7/11 = 0.6364（T09 也被判 fail，**这条读法本身是错的**） |

**判据**：多例任务的 `expect_values` 要么由 prompt 钉死取值（像 T09），
要么改成「网格形状」断言（9 例、3 个 U、3 个 nu、笛卡尔积齐全）。后者是新判据 → 新一轮。

**处置**：报告 §9.2 把区间 [0.727, 0.818] 写清，**头条口径由用户裁定**；本轮不改冻结件、不改判据。

---

### G-14 G-R12-1 的「≥3 种状态」这个绿依赖 G-12 凑数

**声明在哪**：`scripts/verify_references.sh:109`–`140`（G-R12-1）

**现状证据**（独立审计实测，`$TMPDIR/critic/sim_g_r12_1.py` 一类的模拟）：

- 本轮 `distinct_status=3` = pass(9) + fail(2) + declined(1) → 门绿。
- **把 T11 剔掉 → `distinct_status=2` → 门立刻红**；把 T11 改成 pass → 同样红。

**为什么它是缺口**：门绿的原因是「一个冻结件缺陷恰好造出第三种状态」，
**不是**「七态判据有区分力」。这两件事在报告里必须分开写，否则会得出
「G-R12-1 通过 ⇒ 判定层可信」的错误推论——而判定层的真实覆盖见 G-04（还有 4 态只有合成 fixture）。

**判据**：G-R12-1 通过时，报告能指出「第三种状态来自哪个任务的哪种真实失败」，
且该失败**不是**判据侧缺陷。做不到时，报告必须显式声明这个绿是脆的。

**处置**：本轮在 `references/12-bench-report.md` §9.4 显式声明。**不改门**（改门槛会让它更弱）。

---

### P-01 `scripts/batch.py` 用非单调时钟测时长 → `wall_time_s` 可为负（**需授权才能修**）

**位置**：`scripts/batch.py:589`（`started = time.time()`）/ `:598`（`wall_seconds(time.time() - started)`）

**现状证据（本轮抓到的现场，正是 `STATUS.md` N4 第 4 条那个"未归因偶发红"）**：

```bash
$ python3 -m pytest tests/unit tests/contract -q       # 全量
E  AssertionError: cavity_cm0.1 的 wall_time_s=-1.7 为负
E  assert -1.7 >= 0
1 failed, 299 passed in 116.61s

$ python3 -m pytest tests/contract/test_batch_e2e.py::test_numbers_are_recomputable_from_csv -q   # 单跑 4 次
1 passed in 6.15s / 6.16s / 5.88s / 6.28s
```

现场（`$TMPDIR/pytest-fail/m20/runs/m2test/`）：三例 `wall_time_s` = **-1.7 / 0.52 / 0.56**。

**机制**：`CLOCK_REALTIME` 可被 NTP/虚拟化层步进校正（WSL2 常见）。测时长必须用
`time.monotonic()`。**这不是「判据依赖机器速度」**——`value >= 0` 是符号检查，
与机器快慢无关；真凶是被测代码产出了非法值。

**为什么本轮没修**：`scripts/` 下 15 个文件全在禁止清单（`AGENTS.md` R2 之外的自设边界，
见计划 §3.4）。修法一行 + 一条测试，但需要用户批准。

**判据（补齐后成立）**：`scripts/batch.py` 的差值来自 `time.monotonic()`；
`tests/unit/test_batch.py` 有一条断言「负 delta 不得写进 CSV」且能变异自证变红。

---

## 3 其他须知

**本文件刻意不进 `STATUS.md` 的「D 文档规模」机器段**。那张表由 `scripts/status_snapshot.py` 的
`DOCS` 列表生成，而该脚本**在 `bench/tasks/FROZEN.sha256` 里**（第 20 行）——改它会让
`G-R12-2`（15 文件 sha 校验）变红，属于「为了让文档更整齐而破坏冻结件」，不值得。
所以这份清单的规模不进机器段，`STATUS.md` 里只留一句指针。
**注意**：这意味着本文件的字节数/行数**没有任何门禁会盯着它腐坏**，改它时自己复核。

## 3.1 顺手可做（一行改动，已授权范围外先登记）

- **G-09 的机械化守护**：`scripts/check_contracts.py` 可加一条「`STATES` 与 adapters README 的
  状态串一致」的检查。目前靠人眼，改了 README 也没人红。
- **`tests/contract/README.md`** 已存在，记录了 L2 的跑法与变异口径。

## 4 不算缺口的（防止下一个人重新「发现」一遍）

| 现象 | 为什么不算缺口 | 依据 |
|---|---|---|
| `g2b=soft` 在 v13 观测不到 | 已结案为**不可达**：208 个 tutorial 全扫，`Mesh OK.` 与 `***` 共存 0 例。判据保留但用合成日志测 | `09` §10.6、D19 |
| G5 的「理由」判据极宽（`changes` 任意非空即放行 `polyMesh/` 改动） | 预注册原文只要求「写理由」，未要求理由与改动对得上。**已登记为已知放宽**，改它算新一轮 | `bench/preregistration.md:89`、`09` §10.3b 第 4 条 |
| 没有 `tests/contract/test_mutants.py` | 该文件从未存在；变异验证一律**就地**做（改→红→还原→绿→`diff`） | `09` D26、§5 |
| `checkMesh` 网格不合格时退出码仍是 0 | 这不是缺口而是**事实**；G2 已按「必须 grep `Mesh OK.`」实现 | `09` D18、§10.6 |
| E 的 `--stage pre` 不判 G2–G4 | D4 的设计：G1/G5 前置、G2–G4 后置。短路是合法状态，judge 有 M-d 语义 | `09` D4、§10.1 M-d |
| `09` 附录 B 的期望值曾是 29/31 | 已改为实测值（67/31），并注明「必须用绝对路径的解释器」 | 本文 §0 基线 |

## 5 建议顺序（按「一条动作能揭穿多少假设」排）

```
1. G-01 决策（实现 or 删）     ← 半天内能定；不定会一直挂在那里
2. G-09 修 README 六态→七态     ← 一行；不修会害下一个写 adapter 的人
3. G-04 补 fail / declined 的真实 run 用例（tmp_path，不碰 bench/）
4. G-05 接 A 的模型层          ← M3 的起点，A 的 16 项测试一行不改是硬判据
5. G-07 处理 B=9（现在代价最低）
6. G-08 写 1 个 adapter + G-03 解冻实跑 → 同时让 G-06 有值
```

**为什么不先做 G-03**：解冻实跑要补 `prereg` §10 的每臂预测（六项冻结内容之一），
那是「先定判据再跑」的硬流程；在 G-01/G-04 未定时跑，等于用未定稿的尺子量。

## 6 自检

```bash
cd <repo>
source /opt/openfoam13/etc/bashrc

# 本文件的每条现状都能复现（挑三条最容易漂的）
grep -cE 'version|上限|isfinite' scripts/verify_case.sh      # G-01：0
ls bench/runs/ | wc -l                                        # G-03：0
awk -F, 'NR>1 && $8=="B"' references/registry.csv | wc -l     # G-07：10

# 全套门禁（本文件在 references/*.md 下，会被 G-DOC-1 扫锚点）
bash scripts/verify_references.sh --frozen | grep RESULT      # 期望 ALL GATES PASS
```
