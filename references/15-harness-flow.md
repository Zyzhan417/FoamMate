# 一句话之后发生了什么：接口、入口与函数级调用链

> 本文回答三个具体问题，其余一概不答：
> **① 入口文件在哪里？ ② 脚本和 agent 怎么交互？ ③ 一句话输入之后，实际经过哪些函数？**
>
> 证据只有两类：`python3 -m trace --trace` 与 `bash -x` 抓下来的**真实运行时序列**（不是读源码推断），
> 以及本机一次完整探针的 rc / 落盘记录。每个函数序列都标注了采集方式。
> 退出码完整语义、五道门判据、停点规则不在本文重复 → `release/SKILL.md` §4 / §3 步骤 6 / §5。

---

## §0 三个问题，三句话

**① 入口文件是 `release/SKILL.md`，不是任何可执行文件。**

```
$ grep -n "input()\|sys.stdin.read\|/dev/stdin" scripts/*.py scripts/*.sh
(空 —— 十个脚本没有一个读 stdin)
```

对操作系统来说，**十个脚本各自就是入口**（`main()` + argparse，或 bash 直接执行）。
对 agent 来说，入口是那份文档：它的前 4 行是 YAML frontmatter，

```yaml
name: openfoam-v13-case-harness
description: Use when 要把一句自然语言 CFD 需求变成一个能在本机 OpenFOAM v13 上跑通的 case 目录…
```

agent 会话开始时扫所有 skill 的 `description`，命中「要建 case」这个意图，就把 `SKILL.md` 全文读进
上下文（563 行，含 6 步命令块、退出码表、四条停点规则），然后**照着走**。

所以准确的说法是：**harness 没有 agent，agent 有 harness。**

**② 交互只有三个通道，其中两个是单向的。**

| 方向 | 通道 | 形态 |
|---|---|---|
| agent → 脚本 | **argv** + 环境变量 | `bash $HARNESS/scripts/new_case.sh --source … --dest … --spec …` |
| 脚本 → agent | **stdout** / **stderr** / **退出码** | `DERIVED=/path`、一行 JSON、`FAIL version …`、`rc=0` |
| 脚本 ↔ 脚本 | **磁盘** | case 树、`case.meta`、`log.checkMesh`、`log.g1…g5`、`attempt_1/` |

没有 stdin、没有 socket、没有 API、没有共享内存。每一步都是「从磁盘读状态 → 干活 → 往磁盘写状态
→ 吐一个退出码」。进程随时死掉都不影响下一步，因为**上下文不在内存里，在文件系统里**。

agent 判断下一步看的是**退出码**，不是 stdout 文字：读到 `0` 继续，读到 `10` 停下问人，
读到 `50` 去执行它给的那条 `source`。stdout 是给人看的，退出码是契约。

**③ 一句话之后是 8 个独立进程、约 40 次函数进入、0 次跨进程函数调用。**

进程之间不共享任何内存，唯一通过磁盘传递状态的是文件。下面 §2 逐个展开。

---

## §1 一屏看完：8 个进程

按 `release/QUICKSTART.md` 的顺序（§6 前置门禁在 §7 跑之前）：

```
用户说："一个二维方腔，顶盖 1 m/s，水，层流，稳态"
   │
   ├─[agent 侧]  扫 skill description → 命中 → 读 release/SKILL.md 全文进 context
   │             ↑ 这是唯一一次"入口"动作，它不是可执行文件
   │
   ├─进程 1  bash    scripts/preflight.sh                          → rc=0   6 项检查
   ├─进程 2  python3 scripts/parse_requirement.py --text … --out … → rc=0   spec.json
   ├─进程 3  bash    scripts/find_template.sh --keyword cavity     → rc=0   FOUND=28
   ├─进程 4  bash    scripts/new_case.sh --source … --dest …       → rc=0   case 树 + case.meta
   ├─进程 5  foamDictionary <文件> -entry <键> -set <值>            → rc=0   ← 人决定改什么值
   ├─进程 6  bash    scripts/verify_case.sh --stage pre            → rc=0   log.g1 / log.g5
   ├─进程 7  bash    scripts/run_case.sh --mode full               → rc=0   polyMesh + 4 份 log
   └─进程 8  bash    scripts/verify_case.sh --stage post           → rc=0   log.g2 / log.g3 / log.g4
```

红了的边会插入进程 9（`fix_case.py` 定位）与进程 10（`fix_case.py` 应用），然后回到进程 7。

> **⚠ 两份对外文档给的顺序不一样**（实测，2026-11-03）：
> `QUICKSTART.md` 是 派生(§4) → 改字典(§5) → **前置门禁(§6)** → 跑(§7) → 后置门禁(§8)；
> `SKILL.md` 是 派生(步骤3) → 改字典(步骤4) → **跑(步骤5)** → 门禁(步骤6，pre 与 post 在同一节)。
> 差别不是笔误：`pre` 零 OpenFOAM 命令、设计意图就是「结构不对就不必白跑网格」，所以它应该在校验前；
> 但 G1 的 patch 一致性检查读 `constant/polyMesh/boundary`，**没有网格时只能 SKIP**。
> 两条顺序都能跑通，代价不同。agent 读哪份文档，就走哪条顺序——这就是「控制流不在代码里」的具体代价。

---

## §2 函数级调用链（真实运行时序列）

采集方式：`python3 -m trace --trace <脚本> <参数>` 与 `bash -x`（`PS4` 里带 `FUNCNAME`）。
标注 **[trace]** = 实际跑出来的进入顺序；**[ast]** = 静态解析出的事实（无法或不值得真跑时用）。

### 2.1 进程 1 · `preflight.sh` —— 2 次函数进入 + 6 次 ok [trace]

```
main → resolve_bash_rc → ok ×6
```

`bash -x` 实测：进入 `main`，先跑 `resolve_bash_rc`（`scripts/preflight.sh:41`）推导 bashrc 路径
——**这一步不能复用别的脚本的实现**，因为它必须能在「同目录没有任何其他脚本」时单独跑通
（它就是陌生用户的第一条命令）。然后 `ok`（`scripts/preflight.sh:132`）/ `fail`（`scripts/preflight.sh:136`）各打一行，共 6 次。
下表省略文件名，**全部指 `scripts/preflight.sh`**：

| # | 检查 | ok 行 | fail 行 |
|---|---|---|---|
| 1 | bashrc 已 source | `:150` | `:152` |
| 2 | 四个命令在 PATH | `:161` | `:163` |
| 3 | tutorial 数 ≥ 100 | `:172` | `:174` / `:177` |
| 4 | 版本字面等于 13 | `:185` | `:183` / `:188` |
| 5 | python3 ≥ 3.9 | `:195` | `:199` / `:201` |
| 6 | 同目录 9 个脚本可执行 | `:213` | `:215` |

顺序是刻意的：**#1 必须排在 #4 之前**。没 source 时 `$WM_PROJECT_VERSION` 为空，先判版本会把
「环境没加载」误报成「版本不对」(51)，处置方向完全相反（一个只要一条 `source`，一个要换安装）。

### 2.2 进程 2 · `parse_requirement.py` —— 11 次函数进入 [trace]

真跑 `--text "一个二维方腔，顶盖 1 m/s，水，层流，稳态"` 抓到：

> 下表行号均指 `scripts/parse_requirement.py`。

```
_UsageParser → main → run → extract_quad → _first_match → _extract_properties
             → _first_match → validate_quad → _normalize_value → exit_code_for → to_json
```

| 函数 | 行 | 干什么 |
|---|---|---|
| `main` | `:256` | 解析 argv，调 `run`，把 JSON 打到 stdout，`complete=true` 且给了 `--out` 才落盘 |
| `run` | `:228` | 三行流水线：`validate_quad(extract_quad(text))` + `exit_code_for` |
| `extract_quad` | `:197` | **纯函数、纯标准库**，正则 + 关键词表，四个字段各猜一次；猜不到给 `None` |
| `_first_match` | `:161` | 单字段的匹配器（`extract_quad` 与 `_extract_properties` 都调它，所以出现两次） |
| `_extract_properties` | `:179` | `properties` 字段特殊：要同时认出流体名与湍流模型 |
| `validate_quad` | `:79` | **不关心猜的来源**：只查四个键、值必须非空 `str`、缺的记 `None` |
| `_normalize_value` | `:66` | 去空白、统一口径 |
| `exit_code_for` | `:98` | `complete` → 0，否则 10（**唯一**推退出码的地方，CLI 与测试共用） |
| `to_json` | `:234` | 一行 JSON，中文不转义 |

**这 11 次进入里没有一次碰到文件系统**（除了最后 `main` 里的 `write_text`）。
所以「需求 → 四元组」这一步可以在完全没有 OpenFOAM、没有网络的机器上单独测——事实上它就是这么被测的。

接 LLM 时只替换 `extract_quad` 一个函数，`validate_quad` 与 `exit_code_for` 一行都不用改。

### 2.3 进程 3 · `find_template.sh` —— 1 次函数进入 [trace]

```
main → resolve_bash_rc
```

> 本段行号均指 `scripts/find_template.sh`。

之后是纯 bash 循环：`for var in "${ROOT_VARS[@]}"`（`:97`），每个根跑一次
`grep -rnI -m1 -F -- "$KEYWORD" "$root"`（`:119`），结果排序去重后截断到 `--limit`，
末两行打 `FOUND=<总数>` 与 `SHOWN=<输出行数>`。

**没有函数封装**，因为它的全部逻辑就是一次 grep。它不建索引、不缓存、不猜。

### 2.4 进程 4 · `new_case.sh` —— 1 次函数进入，5 个外部命令 [trace]

> 本段行号均指 `scripts/new_case.sh`。

```
main（无内部函数调用）
  ├─ :112  command -v $PYTHON        → 找不到退 64（写 case.meta 需要 python3）
  ├─ :136  realpath -e -- $src       → 失败退 12
  ├─ :142  realpath -e -- $FOAM_TUTORIALS
  ├─ :158  dirname -- $DEST + mkdir -p（父目录不存在时）
  ├─ :162  cp -a -- "$src_real/." "$DEST/"
  └─ :168–195  python3 <<'PY'         写 case.meta 六键（内嵌 heredoc，失败即回滚 dest 退 64）
```

校验全在 `main` 里顺序执行，**没有拆函数**——因为每条校验都是「不满足就 `die`」，
拆成函数不会降低复杂度。source 校验（`:134`–`:151`，含 exists / realpath / 在 `$FOAM_TUTORIALS` 下 /
有 `system/controlDict` 四条）任一条不过退 12 且 **`$DEST` 完全没被创建**；
`:154`/`:155` 判 `$DEST` 已存在（含符号链接）退 13。

`:162` 用 `"$src_real/."` 而不是 `"$src_real"`：前者把内容铺进 dest，后者会多一层同名子目录。

### 2.5 进程 5 · `foamDictionary` —— 不是 harness 的一部分

```
foamDictionary constant/physicalProperties -entry nu -set "1e-06 [m^2/s]"
foamDictionary constant/physicalProperties -entry nu -value     # 回读
```

这是 OpenFOAM 自带的工具，agent 直接调。**harness 不提供「需求 → 哪个 entry 改成什么值」的翻译**
——那需要物理判断。`fix_case.py locate` 只肯说「改哪个文件的哪个 entry」，`new_value` 恒为 `null`。

实测一条坑：`-set` 对**不存在**的 entry 会新增并退 0（`-entry noSuchKey -set 1` → `New entry noSuchKey 1;` rc=0）。
所以回读是唯一防线。

### 2.6 进程 6 · `verify_case.sh --stage pre` —— 2 次函数进入 + 2 个 python 块 [trace]

> 本段行号均指 `scripts/verify_case.sh`。

```
main → write_log     （+ 2 个内嵌 python3 heredoc 块：:581-690 判 G1 的 patch 集合，:724-882 求 G5 改动集）
```

`bash -x` 实测：进入 `main`，两个内嵌 python 块各被调一次（trace 报在块的结束行 690 / 882），
然后 `write_log`（`:143`）写 `log.g1`、`log.g5`。

**「门禁只读」是错的**：`pre` 会往 `--case` 目录里写这两个文件。所以 G5 必须按类把它们排除，
否则第二次跑会把自己上次的日志判成越界（`:801`–`:816` 的注释记着这次实测）。

### 2.7 进程 7 · `run_case.sh` —— 5 个内部函数，按模式分两支 [trace]

> 下两段与下方函数表的行号均指 `scripts/run_case.sh`。

**`--mode check`**（只建网格 + checkMesh）：

```
main → run_capped(:194, blockMesh) → handle(:195) → run_capped(:202, checkMesh) → handle(:203)
```

**`--mode short`**（在上面基础上加短跑，并**改写字典**）：

```
main → run_capped(blockMesh) → handle → run_capped(checkMesh) → handle
     → read_entry(:214 deltaT) → read_entry(:215 endTime) → read_entry(:216 writeInterval)
     → set_entry(:225 endTime=$SHORT_END) → set_entry(:226 writeInterval=2)
     → run_capped(:228 foamRun) → handle(:229)
```

**`--mode full`**：先跑一遍上面的 short，再在 `if [ "$MODE" = "full" ]`（`:231`）里
`set_entry` 把原值恢复（`:233`/`:234`），然后跑全时程写 `log.run`。

| 函数 | 行 | 干什么 |
|---|---|---|
| `run_capped` | `:149` | 跑一条 OpenFOAM 命令，`timeout` 包住，返回 0/20/21 |
| `handle` | `:161` | 把 0/20/21 翻译成退出码 + 人话 |
| `read_entry` | `:171` | 回读 `controlDict` 顶层标量的裸值（剥空白） |
| `set_entry` | `:177` | 设置 + **立刻回读校验**（不符按失败处理） |
| `is_number` | `:187` | 校验 `endTime` 是数字，否则退 20 |

**★ 实测结论**：`--mode short` 把 `endTime` 改成 `deltaT*2`、`writeInterval` 改成 2，
**并且保留**——恢复只在 `full` 分支里。派生源原值 `endTime 10` / `writeInterval 100`，
跑过 short 之后磁盘上是 `endTime 0.01` / `writeInterval 2`。所以「短跑之后直接读字典做断言」必然 mismatch。

### 2.8 进程 8 · `verify_case.sh --stage post` —— 2 次函数进入 + 3 个 python 块 [trace]

> 本段行号均指 `scripts/verify_case.sh`。

```
main → write_log     （+ 3 个内嵌 python3 heredoc 块，trace 报在结束行 250 / 328 / 499；
                      分别判 G3 短跑日志、G4 产物、G2 的 patch 名一致性）
```

然后 `write_log` 写 `log.g3`（`:214`）、`log.g4`（`:276`）、`log.g2`（`:193`，第 2 行带 `G2B=`）。

**只解析日志，不跑求解。** 这带来一个必然结果：在只跑过 `--mode check` 的 case 上跑 post，
G3 拿到的是「MISSING log.shortRun ⇒ 未判定，不是通过」，**退出码 3**。这是设计，不是 bug。

### 2.9 进程 9/10 · `fix_case.py` —— 12 与 25 次函数进入 [trace]

> 下两段与下方函数表的行号均指 `scripts/fix_case.py`。

`locate` 模式（真跑，日志含 `keyword nu is undefined`）：

```
_UsageParser → main → _build_parser → _allowed_globs → _run_locate
             → fatal_first_line → locate → fingerprint_of → error_signature → _payload → _emit
```

`apply` 模式（真跑，成功路径）：

```
main → _build_parser → _allowed_globs → _run_apply → parse_apply_payload → fingerprint_for_apply
     → _is_allowed → _safe_rel_path → seen_fingerprints → _ledger_path → validate_changes
     → _count_entry → _foam_dictionary → _backup_case → _set_entry → _read_entry
     → _values_equal → _norm_scalar → record_fingerprint → _ledger_path → _payload → _emit
```

关键几个：

| 函数 | 行 | 干什么 | 实测事实 |
|---|---|---|---|
| `locate` | `:276` | 只有 4 条规则（3 正则 + 1 兜底），匹配不到就 `declined` | 日志含 `Unknown patchField type` → `declined=true`，**不写盘** |
| `validate_changes` | `:437` | 写前校验：entry 必须**恰好命中 1 次** | 命中 0 次 → 退 33，**不备份、不写** |
| `_backup_case` | `:457` | 备份 | ★备份的是**整个 case 树**，实测 `attempt_1/` 有 170+ 文件 |
| `_set_entry` / `_read_entry` | `:476` / `:485` | 写 + 回读 | `_values_equal` 会剥掉后置量纲（`1e-5 [m^2/s]` vs `1e-05 [ m^2 / s]`） |
| `record_fingerprint` | `:344` | 指纹台账 | ★写在 `run_dir = case_dir.parent`（`scripts/fix_case.py:459` 与 `scripts/fix_case.py:579`）——**case 的父目录**，单例用法下所有 case 共用一份 |

### 2.10 旁支 · `batch.py` —— 唯一「脚本调脚本」的文件 [ast + dry-run trace]

> 本段行号均指 `scripts/batch.py`。

```
main(:709) → parse_cases(:237) → expand(:313) → print_expansion / [Runner]
           → write_results(:640) → _self_check_csv(:667)

Runner.one(:526) → _derive(:467) → _apply(:491) → _verify(:509) → read_gate(:389) → run(:377)
                → wall_seconds(:429) → _verify → parse_diagnostics(:415) → read_gate ×2
```

它用 `subprocess.run`（`:380`、`:516`）起四个兄弟脚本：`new_case.sh`（`:482`）、
`fix_case.py`（`:499`）、`verify_case.sh`（`:511`）、`run_case.sh`（`:593`）。
**全仓库唯一拼别的脚本路径的地方**（可判定：`grep -rn 'scripts / "' scripts/*.py` 只有这几处）。

### 2.11 旁支 · `dev_lib.py` —— 按 `--stage` 分派 [ast]

> 本段行号均指 `scripts/dev_lib.py`。

```
main(:707) → handlers[args.stage] = stage_prepare(:238) / stage_check(:386) / stage_build(:486) / stage_verify(:617)
```

四个 stage 各自是长函数，内部有 `sha256_tree`(:165)、`meta_self_sha`(:178)、`diff_manifest`(:191)、
`first_error`(:464)、`system_tree_newer`(:569) 等。**脚本不改 C++、不生成 C++**，中间改 `.C` 是人的活。

### 2.12 旁支 · `msh2d_to_foam.py` —— 8 次函数进入 [ast]

> 本段行号均指 `scripts/msh2d_to_foam.py`。

```
main(:362) → read_msh(:97) → convert(:215) → render(:171) → write_polymesh(:343)
```

`read_msh` 内部调 `_block` ×3（解析三个 msh 段），`convert` 调 `_cells_for_edges`，
`render` 调 `_head` ×4（写 polyMesh 头）。**它不生成网格**：拓扑全部来自 gmsh。

---

## §3 每个文件在什么时候被碰（反查表）

同一个问题反过来问：**我要改这个文件，会影响哪几步？**

| 文件 | 被谁、在进程几 | 读 / 写 | 频次 |
|---|---|---|---|
| `scripts/preflight.sh` | agent，进程 1 | 读环境变量；不写盘 | 1×/会话 |
| `scripts/parse_requirement.py` | agent，进程 2 | 写 `<work>/*.spec.json` | 1× |
| `scripts/find_template.sh` | agent，进程 3 | 不写盘 | ≥1× |
| `scripts/new_case.sh` | agent，进程 4；`batch` 代调 | 写 case 树 + `case.meta` | 1×/case |
| `scripts/run_case.sh` | agent，进程 7；`batch` 代调 | 写 `polyMesh`、4 份 log、**改写 `controlDict`** | ≥1× |
| `scripts/verify_case.sh` | agent，进程 6/8；`batch` 代调 | 写 `log.g1…g5` | ≥2× |
| `scripts/fix_case.py` | agent，进程 9/10；`batch` 代调 | 写 `fingerprints.txt`、`attempt_<n>/`、字典 | 0..n× |
| `scripts/msh2d_to_foam.py` | agent，条件进程 | 写 `constant/polyMesh/*` | 0..1× |
| `scripts/batch.py` | agent，旁支 | 写 `runs/<批次>/**` | 0..1×/批 |
| `scripts/dev_lib.py` | agent，旁支 | 写用户库副本、`.so` | 0..1× |
| `release/SKILL.md` | agent，**全程在手** | 只读 | 全程 |
| `release/QUICKSTART.md` / `SCOPE.md` | 人，装完 / 装前 | 只读 | 1× |
| `<case>/case.meta` | 进程 4 写六键；进程 5 手改 `changes`；6/8 读 | 读+写 | 1× |
| `<case>/log.g1…g5` | 进程 6 写 g1/g5；进程 8 写 g2/g3/g4 | 写后被读 | 各 1× |
| `<case>/log.blockMesh` … `log.run` | 进程 7 写 | 写后被进程 8 读 | 1× |
| `constant/polyMesh/` | 进程 7 写；`msh2d` 覆盖 | 读+写 | 1× |
| `<case 父目录>/attempt_<n>/` | 进程 10 写 | 整树副本 | 0..n× |
| `<case 父目录>/fingerprints.txt` | 进程 9/10 写 | 一行一条指纹 | 0..n× |
| `runs/<批次>/results.csv` | `batch` 写 | 15 列 | 0..1×/批 |

**不是「每个文件都会在某个时刻被触发」**：一次顺利跑通只碰 6 个脚本，
`fix_case.py` / `batch.py` / `dev_lib.py` / `msh2d_to_foam.py` 在多数 case 里**一次都不跑**。

---

## §4 十二条实测事实（与既有说法不一致的部分）

前 11 条是 2026-11-03 一次完整探针打出来的，第 12 条来自核对两份文档的顺序。

| # | 事实 | 证据 |
|---|---|---|
| F1 | **没有自然语言入口，没有 `main()` 驱动六步** | `release/SKILL.md:15`「不决定下一步做什么、不自己循环」；`grep` 十个脚本零 stdin |
| F2 | 文档说「十个工具」，`preflight` 只自检 **9** 个（不检自己） | `release/SKILL.md:17` vs `scripts/preflight.sh:75`；实跑打「9 个用户面脚本」 |
| F3 | **`--mode check` 之后跑 `--stage post` 必然 `rc=3`** | 实跑：G3 报 `MISSING log.shortRun ⇒ 未判定，不是通过` |
| F4 | **`pre` 门禁会往 case 树写 `log.g1`/`log.g5`** | 实跑 `find` 差集；脚本头 `scripts/verify_case.sh:46` 自述 |
| F5 | **`--mode short` 改写 `controlDict` 并保留**（`endTime` 10→0.01、`writeInterval` 100→2） | 实跑后 `grep`；恢复只在 `scripts/run_case.sh:231` 的 `full` 分支 |
| F6 | `fix_case.py locate` 也会写盘：命中规则时写 `fingerprints.txt`，落在 **case 的父目录** | `run_dir = case_dir.parent`（`scripts/fix_case.py:459` 与 `scripts/fix_case.py:579`）；实跑新增 |
| F7 | `fix_case.py --apply` 的备份是**整个 case 树的副本**（实测 170+ 文件） | 实跑 `attempt_1/` 文件清单；成本随 time 目录数增长 |
| F8 | 单 case 用法下**每次** `verify_case.sh` 都打一条必然触发的假警报 | `--log` 缺省 = `--case`（`scripts/verify_case.sh:121`），同一个 `case.meta` 被判成「两处都有」（`scripts/verify_case.sh:135`） |
| F9 | **还没有网格时 G1 也 `RC=0`** | 实跑；patch 比对在无 `boundary` 时只写 `SKIP`（`scripts/verify_case.sh:655`） |
| F10 | `foamDictionary -set` 对不存在的 entry **新增并退 0** | 实跑 `-entry noSuchKey -set 1` → `New entry noSuchKey 1;` rc=0 |
| F11 | `find_template.sh` 单次 6.7 s 是**全库 grep 的数据量代价**，不是工具性能 | 实测 6682 ms（`--keyword cavity --limit 5`，`FOUND=28`） |
| F12 | **两份对外文档的步骤顺序不一致**（前置门禁在跑之前 vs 之后） | `QUICKSTART.md` §6/§7/§8 vs `SKILL.md` 步骤 5/6 |

---

## §5 面试问答

**30 秒版**

> 这套东西不是 agent，是 agent 的工具层。它没有程序入口——入口是一份 SKILL.md，
> agent 靠 frontmatter 的 description 匹配到「建 case」这个意图，把文档读进上下文，然后按里面的
> 命令块逐个调脚本。每个脚本是独立进程，协议就三条：argv 进，stdout + 退出码出，状态全落盘。
> 所以控制流不在代码里，在 agent 的循环里；脚本只保证每一步可判定——同一输入同一输出，失败有独立退出码。
> 一句话进来之后是 8 个进程、约 40 次函数进入、零次跨进程函数调用。这是 tool-use 的最原始形态，
> MCP 只是把这个契约标准化了。

| 追问 | 答法 |
|---|---|
| 「你的 agent 在哪？」 | 诚实答：这一版 agent 是外部的（Claude Code / 人）。接 LLM 的那一层我明确没做，因为要先证明工具层确定性。 |
| 「为什么不写成一个 main？」 | 判定权必须外置。合成一个程序后，失败时无法区分「模型判断错」还是「工具实现错」。现在边界很硬：`parse_requirement` 只猜（猜不到退 10 交人），`fix_case locate` 只肯说改哪儿、值恒为 null。 |
| 「怎么测？」 | 每个脚本 5 个左右退出码，能写变异测试：把判据改哑，测试必须红。守 G2 那条最有说服力——只认 `Mesh OK.` 那行，**绝不看 checkMesh 退出码**，因为实测网格不合格时它仍退 0。 |
| 「脚本之间不共享状态，不慢吗？」 | 多几次进程启动（毫秒级），换来每步可单独重跑、单独测、单独替换。实测最小链路 8 步合计 < 10 秒，其中 6.7 秒是一次全库 grep。 |
| 「和让 LLM 直接写 shell 命令有什么区别？」 | 区别是**判据**。LLM 写的命令没有退出码契约，成功失败靠猜；这里每个码都有测试和文档，失败时 agent 拿到的是一个确定的数字。 |
| 「怎么防止 agent 乱来？」 | 三道：停点规则写进 SKILL.md（缺项必须停下问人，不许补默认值）；G5 只允许改 `allowed_files`；派生只允许 `cp -a` 自 `$FOAM_TUTORIALS`。 |
| 「换一个 agent 还能用吗？」 | 能，而且已经验证过——同一批脚本被 `batch.py` 用 `subprocess` 驱动，跑完了 12 任务 × 3 次的基准。换宿主只换读文档的那一半。 |
| 「为什么不用 MCP？」 | 那时还没这需求。MCP 解决「工具怎么被发现和授权」，我这套用「一份带 frontmatter 的文档」解决了同一件事，代价是没有结构化 schema、不能跨进程复用连接。要接 MCP 的话，十个脚本各自的 argv 就是现成的 tool schema。 |

---

## §6 本页事实怎么复核

每条先写它验证什么，再给命令。全部在仓库根执行。

**① 断言「没有 stdin 入口」**

```bash
grep -n "input()\|sys.stdin.read\|/dev/stdin" scripts/*.py scripts/*.sh
```

期望：无输出。

**② 断言「入口是 SKILL.md 的 frontmatter」**

```bash
sed -n '1,4p' release/SKILL.md
```

期望：`name:` 与 `description:` 两行。

**③ 断言「脚本之间零调用，除 batch.py」**

```bash
grep -rn 'scripts / "' scripts/*.py
```

期望：只有 `scripts/batch.py` 的 482 / 499 / 511 / 593 / 814 五行。

**④ 复现进程 2 的函数序列（trace 实测）**

```bash
python3 -m trace --trace scripts/parse_requirement.py \
  --text "一个二维方腔，顶盖 1 m/s，水，层流，稳态" --out /tmp/x.json 2>&1 \
  | grep -oE "modulename: parse_requirement, funcname: [A-Za-z_]+" \
  | sed 's/.*funcname: //' | awk '!s[$0]++'
```

期望（逐行，去掉连续的重复进入后正好 10 个）：`_UsageParser` `main` `run` `extract_quad`
`_first_match` `_extract_properties` `validate_quad` `_normalize_value` `exit_code_for` `to_json`。

> 必须带 `modulename: parse_requirement` 这个前缀过滤：`trace` 会把标准库的每一次函数进入
> 也打出来，只按 `funcname` 抓会得到几百个 `_find_and_load` / `add_argument` 之类的噪音。

**⑤ 复现进程 7 的函数序列（bash -x）**

```bash
export PS4='+FN=${FUNCNAME[0]:-main}: '
bash -x scripts/run_case.sh --case <某个已派生的 case> --mode short 2>&1 \
  | grep -oE "FN=[a-z_]+" | awk '!s[$0]++'
```

期望：`main` → `run_capped` → `handle` → `read_entry` → `is_number` → `set_entry`。

**⑥ 断言「pre 会写 case 树」**

```bash
grep -n '唯一写操作' scripts/verify_case.sh
ls <case>/log.g1 <case>/log.g5
```

**⑦ 断言「short 会改写并保留 controlDict」**

```bash
sed -n '225,226p;231,234p' scripts/run_case.sh
grep -nE "^(endTime|writeInterval)" <case>/system/controlDict
```

期望：先是 `set_entry endTime "$SHORT_END"` / `set_entry writeInterval 2`，
然后 `if [ "$MODE" = "full" ]` 里的两行恢复；跑过 short 的 case 里是 `0.01` 与 `2`。

**⑧ 断言「10 个工具 vs 自检 9 个」**

```bash
sed -n '/^WL_SRC=(/,/^)/p' scripts/make_release.sh | grep -c 'scripts/'
sed -n '75,85p' scripts/preflight.sh | grep -cE '\.(sh|py)$'
source /opt/openfoam13/etc/bashrc && bash scripts/preflight.sh | grep 'OK scripts'
```

期望：`10`、`9`、以及实跑那行「同目录 9 个用户面脚本均存在且可执行」。

**⑨ 断言「备份是整个 case 树」**

```bash
grep -n "run_dir = case_dir.parent" scripts/fix_case.py
find <case 父目录>/attempt_1 -type f | wc -l
```

期望：`459` 与 `579` 两处；文件数远大于「只备份一个字典」。

**⑩ 断言「退出码原文只在脚本头部，本文没有另造总表」**

```bash
grep -n "退出码：" scripts/preflight.sh scripts/parse_requirement.py scripts/find_template.sh \
  scripts/new_case.sh scripts/run_case.sh scripts/verify_case.sh scripts/fix_case.py scripts/dev_lib.py
```

期望：每文件一行头部契约；本文只引用它们，不复述整表。

**⑪ 断言「两份文档顺序不一致」（F12）**

```bash
grep -n "^## [0-9]" release/QUICKSTART.md
grep -n "^### 步骤" release/SKILL.md
```

期望：QUICKSTART 的 §6 是前置门禁、§7 才是跑；SKILL.md 的步骤 5 是跑、步骤 6 才是门禁。

**⑫ 自检：本文没有本机标识与家目录绝对路径**

```bash
grep -nE "/home/[a-z]|/mnt/[a-z]/" references/15-harness-flow.md
```

期望：0 行。
