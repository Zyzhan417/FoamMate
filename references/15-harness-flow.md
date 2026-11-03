# 从一句话到一个 case：FoamMate 的时间轴

> 读者：会 CFD、但没读过这套 harness 的人。本文只回答一个问题——
> 在「用户说一句自然语言，最后拿到一个能跑的 case」这条真实路径上，
> **每个文件分别在什么时候被触发**。
>
> 事实来源只有两处：脚本头部的契约注释（逐字引用），和本机一次完整探针的实跑记录
> （命令、退出码、落盘文件，见 §6）。退出码的完整语义、五道门的判据、停点规则不在
> 这里重复：`release/SKILL.md` §4 / §3 步骤 6 / §5。

## §0 三句话结论

**一、大脑在宿主一侧。** 这套 harness 没有 `main()`，也没有「一句话进、一个 case 出」的入口。
它只是十个确定性脚本 + 一份文档；谁先跑、跑不跑下一步、什么时候停下问人，全在调用方那边
（人，或读这份文档的另一个 agent）。原话是：「它不含任何模型调用、不决定下一步做什么、
不自己循环」（`release/SKILL.md:15`）。所以下面这张时间轴**不是代码里的调用栈**，
而是宿主照着文档走出来的顺序。

**二、每个文件只在自己那一段被触发。** 一条顺利的链路只碰六个脚本；`fix_case.py` 只在
某道门红了之后才登场，`batch.py` / `dev_lib.py` / `msh2d_to_foam.py` 在多数 case 里一次都不跑。
反过来看（§3）：每个文件都能说清「被谁、在哪一刻、读还是写」。

**三、门绿不等于需求被满足。** 退出码是唯一证据，但退出码只回答「能不能跑」。需求里的
「稳态」不会被翻译成 `ddtSchemes`；「二维方腔」没给边长时，边长静默继承派生源的
`convertToMeters`。这两件事由 `post` 的四条诊断行 `OBJ=` / `GEO=` / `RE=` / `RES=` 摆出来，
而它们**都不进退出码**（`release/SKILL.md:276`）。

## §1 三层触发源

把「谁按下了哪个文件」分三层，是为了让后面那张表可判定：同一行只属于一层。

| 层 | 是谁 | 它决定什么 | 碰哪些时刻 |
|---|---|---|---|
| L1 | 人 | 要什么；字典改成什么值；结果可不可信 | T0（装）、T5（改字典）、T12（结论） |
| L2 | 宿主 agent | 读 `release/SKILL.md`，决定下一个调哪个脚本，什么时候停下问人 | T1–T11 中除 T5 的全部 |
| L3 | 脚本互相调用 | 只有 `batch.py` 会调别的脚本 | B1 |

三层里最容易被想错的是 L3。除了批量入口，**脚本之间零调用**：`parse_requirement.py` 不会
自己去调 `find_template.sh`，`verify_case.sh` 也不会自己去跑 `run_case.sh`。一条可判定
的证据是：仓库里所有「拼出别的脚本路径」的代码都在 `batch.py` 一个文件里
（`grep -rn 'scripts / "' scripts/*.py`，见 §7 第 1 条）。

因此，**同一组输入，两个宿主可能走出两条不同的路**：一个跳过了 `preflight.sh`，
另一个在 `--mode check` 之后就宣称做完了。这不是 harness 的不确定性——每个脚本仍然
是确定性的——而是「顺序不在代码里」的直接后果。

到了 T5 还有一个不对称：`foamDictionary` 不是 harness 的一部分，harness 也不替你翻译
「需求 → 哪个 entry 改成什么值」。这一步只有人能决定，`fix_case.py` 的 `locate` 模式
只肯回答「改哪个文件的哪个 entry」，`new_value` 一律给 `null`（`release/SKILL.md:307`）。

## §2 主链路时刻表 T0–T12

### 2.1 表

| 时刻 | 触发者 | 触发的东西 | 读 | 写 | 频次 | 退出码 |
|---|---|---|---|---|---|---|
| T0 装一次 | 人 | `scripts/deploy.py --action install`（仓库侧，不进包） | 远端仓库（只有 `--fetch`/`update` 走网络） | `~/foam-mate/`（包内 15 个文件） | 1×（每台机器） | 0 / 90 |
| T1 环境自检 | 宿主 | `scripts/preflight.sh` | `$WM_PROJECT_DIR`、PATH、tutorial 计数、同目录脚本 | 无（只 stdout / stderr） | 1×/会话 | 0 / 50 / 51 |
| T2 需求→四元组 | 宿主 | `scripts/parse_requirement.py --text … --out …` | 用户原话（整句，不要自己总结） | `<work>/<名>.spec.json` | 1× | 0 / 10 |
| T3 定派生源 | 宿主 | `scripts/find_template.sh --keyword …` | 五个 `FOAM_*` 搜索根 | 无 | ≥1× | 0 / 11 |
| T4 派生 | 宿主 | `scripts/new_case.sh --source … --dest … --spec …` | tutorial 整树、`spec.json` | case 树（`cp -a` 副本）+ `case.meta` | 1×/case | 0 / 12 / 13 |
| T4b 换网格（条件） | 宿主 | `scripts/msh2d_to_foam.py --msh … --out constant/polyMesh` | `.msh`（msh2 ascii） | `constant/polyMesh/` 五个文件 | 0..1×（只有要三角形网格时） | 0 / 14 / 15 |
| T5 改字典 | **人** | `foamDictionary <文件> -entry <键> -set <值>`（不经 harness） | case 树里的字典 | 就地改字典；`case.meta.changes` 纯手写 | ≥1× | 它自己的码；非 0 自查 |
| T6 建网格 | 宿主 | `scripts/run_case.sh --mode check` | `system/blockMeshDict`（仅当 polyMesh 不存在） | `constant/polyMesh/`、`log.blockMesh`、`log.checkMesh` | 1× | 0 / 22 / 23 |
| T7 前置门 G1+G5 | 宿主 | `scripts/verify_case.sh --stage pre` | case 树、`case.meta.allowed_files`、`base/` 或 mtime | `log.g1`、`log.g5`（写进 `--case` 目录） | 1× | 0 / 1 / 5 |
| T8 短跑 / 长跑 | 宿主 | `scripts/run_case.sh --mode short\|full` | `system/controlDict`（`endTime`/`writeInterval`/`deltaT`） | `log.shortRun`（full 另写 `log.run`）、时间目录、**改写 controlDict** | 1×（full 内含一次短跑） | 0 / 20 / 21 / 22 / 23 |
| T9 后置门 G2+G3+G4 | 宿主 | `scripts/verify_case.sh --stage post` | `log.checkMesh`、`log.shortRun`、`log.run`、`0/`、`constant/polyMesh/owner` | `log.g2`、`log.g3`、`log.g4` | 1× | 0 / 2 / 3 / 4 |
| T10a 回修·定位（条件） | 宿主 | `scripts/fix_case.py --error-log …` | 失败日志 | `<case 父目录>/fingerprints.txt`（仅命中规则时） | 0..n×（只在门红时） | 0（含 declined）/ 31 / 32 |
| T10b 回修·应用（条件） | 宿主定值、脚本动手 | `scripts/fix_case.py --apply '[…]'` | 待改字典 | `<case 父目录>/attempt_<n>/` + 就地改字典 | 0..n× | 0 / 33（另有 31 / 32） |
| T11 重跑（条件） | 宿主 | 回 T6 / T8（可再次 T9） | 同 T6 / T8 | 覆盖同名 log、新时间目录 | 0..n× | 同 T6 / T8 |
| T12 结论 | 人 | 无新命令 | `log.g1`…`log.g5`、四条诊断行 | 结论 | 1× | — |

表里只列**分支需要**的码。其余（`64` 用法错误、维护侧的 `40`/`41`/`60`、二次开发的
`85`–`89`）语义见 `release/SKILL.md` §4 —— 本文不复制那张总表，因为两处写值必然漂移。

### 2.2 红了的边

- **T1**：`50` 只要一条 `source`；`51` 要换环境，重新 `source` 同一个 bashrc 不会把版本变成 13
  （`release/SKILL.md:45` 专门写了这个陷阱）。
- **T2**：`10` 不是错误，是「交人」。不许回头补默认值——那是把「需求没被满足」变成「五门全绿」。
- **T3**：`11` = `FOUND=0`，说明这个词在本机 tutorial 里不存在；换一个词再试，三次空就告诉用户库里没有。
- **T4**：`12` 回 T3 另选派生源，此时 `<dest>` 根本没被创建；`13` 换 `--dest`（它不覆盖任何东西）。
- **T6**：`22` 回 T1 的 `source`；`23` 说明派生源选错了，换一个自带 `blockMeshDict` 的教程。
- **T8**：`20` 进 T10 回修；`21` 既不是失败也不是成功，加 `--timeout` 或先把 `endTime` 压小。
- **T10**：`31`（到上限）/ `32`（同一指纹重现）都**停下问人**；`declined=true` 也不许猜。

### 2.3 每一步为什么长这样

**T3：它是 grep，不是索引。** `find_template.sh` 在五个根上做 `grep -rnI -m1 -F`
（`scripts/find_template.sh:119`），所以它回答「这个关键字在真实 case 里怎么写」，
不回答「哪个目录叫这个名字」——后者要用 `ls -d`。一次全库 grep 的代价是本机实测
6682 ms（`--keyword cavity --limit 5`，命中 `FOUND=28`、输出 5 行）；这个数是数据量的
代价，不是工具的性能指标，别拿它当基准。

**T4：`cp -a`，不是 `foamCloneCase`。** 理由是后者只挑 shell 脚本、删 `phi`/`Uf`/`uniform`、
目标已存在直接 error；而 `cp -a` 保证「派生 = 逐字节副本」，后面的 G5 才有可判定的基线
（`scripts/new_case.sh:162`）。写完 `case.meta` 才算成功，没有 `case.meta` 的目录不算 case。

**T5：harness 唯一主动让位的一步。** 改哪几个 entry 取决于物理判断，脚本不碰。三个实测纪律：
`-set` 对**不存在**的 entry 会新增并退 0（拼错键名不报错，只悄悄多一个键，
`release/SKILL.md:211`）；带量纲的值必须带量纲；改完必须回读——**回读是唯一防线**。
第三条纪律的机器版本就是 T10b 的 `33`：写前校验要求该 entry 在文件里恰好出现 1 次。

**T6：只在没网格时建网格。** `run_case.sh` 的判断是「`constant/polyMesh` 不存在才 `blockMesh`」
（`scripts/run_case.sh:192`）。这条判据带来一个反直觉的后果：改了 `blockMeshDict` 却不删旧网格，
`checkMesh` 照样在旧网格上跑、`Mesh OK.` 照样过。见 §5 第 5 条。

**T8：三条模式，两条支线。** `check` 到 checkMesh 为止并**直接 exit 0**，完全不碰求解；
`short` 跑两步；`full` 内部先跑同样的两步写 `log.shortRun`，恢复原 `endTime` 再跑全时程
（`release/SKILL.md:246`）。所以「跳过 short 直接 full」是允许的——跳过的是「不验证就长跑」
这个动作，不是那条命令。

**★ 但 `short` 会改写字典，而且保留改后的值。** 它把 `endTime` 设成 `deltaT*2`、
`writeInterval` 设成 2（`scripts/run_case.sh:225`），而恢复那两行只在 `full` 分支里
（`scripts/run_case.sh:231`）。实测：派生源原值 `endTime 10` / `writeInterval 100`，
跑过 `--mode short` 之后磁盘上是 `endTime 0.01` / `writeInterval 2`。**这一步会改文件**，
所以「短跑之后直接读字典做断言」必然 mismatch。

**T9：只解析日志，不跑求解。** 它读 T6/T8 写下的 `log.*`，判 G2/G3/G4，并打印四条诊断。
两件事必须记住：① 门禁分两段，`pre` 打 G1+G5、`post` 打 G2/G3/G4，**五道门不是一次调用
全打出来**；② 脚本退出码只报**第一个**失败的门（按门号取最小）。

**T10：回修分两半，中间夹着人。** `locate` 只输出 `{file, entry, new_value: null}`；
`apply` 才动盘，动之前要过写前校验，动之后要回读比对。中间「该改成什么值」是人决定的。
备份是**整个 case 树的完整副本**（`<case 父目录>/attempt_<n>/`），实测一次 170+ 个文件——
成本随时间目录数增长，长跑过的 case 备份会很大。这条备份也是批量入口把 `attempt_1/`
改名成 `base/` 当 G5 基线的由来。

## §3 文件反表

### 3.1 包内 15 个文件

「最小链路」= 一次顺利跑通、不触发任何条件步骤时是否会碰它。十个工具里只有六个被碰到。

| 文件 | 谁触发 | 时刻 | 读 | 写 | 频次 | 最小链路 |
|---|---|---|---|---|---|---|
| `scripts/preflight.sh` | 宿主 | T1 | 环境变量 / PATH / 同目录 9 脚本 | 无 | 1×/会话 | 会 |
| `scripts/parse_requirement.py` | 宿主 | T2 | 用户原话 | `<work>/*.spec.json` | 1× | 会 |
| `scripts/find_template.sh` | 宿主 | T3 | 五个 `FOAM_*` 根 | 无 | ≥1× | 会 |
| `scripts/new_case.sh` | 宿主（B1 代调） | T4 | tutorial + spec | case 树 + `case.meta` | 1×/case | 会 |
| `scripts/run_case.sh` | 宿主（B1 代调） | T6 / T8 / T11 | `blockMeshDict` / `controlDict` | polyMesh、四份 log、改写 controlDict | ≥1× | 会 |
| `scripts/verify_case.sh` | 宿主（B1 代调） | T7 / T9 | case 树 + `log.*` + `case.meta` | `log.g1`…`log.g5` | ≥2× | 会 |
| `scripts/fix_case.py` | 宿主（B1 代调） | T10a / T10b | `log.*`、待改字典 | `fingerprints.txt`、`attempt_<n>/`、字典 | 0..n× | 不会 |
| `scripts/msh2d_to_foam.py` | 宿主 | T4b | `.msh` | `constant/polyMesh/*` | 0..1× | 不会 |
| `scripts/batch.py` | 宿主 | B1 | `cases.json` | `runs/<批次>/**` + `results.csv` | 0..1×/批 | 不会 |
| `scripts/dev_lib.py` | 宿主 + 人 | B2 | 系统子库 + `dev.meta` | 用户库副本、`log.wmake`、`.so` | 0..1× | 不会 |
| `release/SKILL.md` | 宿主 | 全程 | — | 无 | 全程在手 | 会（被读） |
| `release/QUICKSTART.md` | 人 | T0 之后 | — | 无 | 1× | 会（被读） |
| `release/SCOPE.md` | 人 | T0 之前 | — | 无 | 1× | 会（被读） |
| `VERSION` / `LICENSE` | 打包与安装 | T0 | — | 无 | 1× | 会 |

注意最后四行是「被读」，不是「被运行」。它们从不主动做任何事——包括 `SKILL.md`：
**它是宿主的知识，不是 harness 的入口**。这也是为什么「一句话 → case」里没有任何一行代码
读得懂一句话：读得懂的是宿主。

### 3.2 工件（不在包内，但被上表写来写去）

| 工件 | 谁写 | 谁读 | 备注 |
|---|---|---|---|
| `<case>/case.meta` | T4 写六键；T5 手改 `changes`；B1 移位 | T7 / T9（G5 拿 `allowed_files`） | 两个合法位置，见 §5 第 4 条 |
| `<case>/log.g1`…`log.g5` | T7 写 g1/g5；T9 写 g2/g3/g4 | T12（人）；G5 自己按类排除 | 各写各的门，互不覆盖 |
| `<case>/log.blockMesh` … `log.run` | T6 写前两份；T8 写后两份 | T9（只解析） | `full` 一条命令产出短跑与全时程两份 |
| `constant/polyMesh/` | T6 建；T4b 覆盖 | T7 / T9（取 `nCells`） | 换网格必须先删，见 §5 第 5 条 |
| `<case 父目录>/fingerprints.txt` | T10a / T10b | T10a（跨 attempt 去重） | 单例用法下所有 case 共用一份 |
| `<case 父目录>/attempt_<n>/` | T10b | G5（batch 里改名成 `base/`） | 整树副本，不是 diff |
| `runs/<批次>/results.csv` | B1 | 使用者 / `check_contracts.py` | 15 列，固定 |

## §4 三条旁支

### 4.1 batch：把六步折进一个循环（B1，0..1×/批）

`batch.py` 是**唯一**会调别的脚本的脚本：`new_case.sh` → `fix_case.py --apply` →
`verify_case.sh --stage pre` → `run_case.sh` → `verify_case.sh --stage post`
（`scripts/batch.py:482` 起四处子进程调用）。它展开 `cases.json` 里 `base` + `vary` 的
笛卡尔积（上限 50 例），每例一个目录：

```
runs/<批次>/<case_id>/case/        派生的 case 树
                     /case.meta    从 case 树移过来（见 §5 第 4 条）
                     /base/        改参数前的基线（= attempt_1 改名）
                     /log.*        五门 + 四份求解日志
runs/<批次>/results.csv            批次汇总（15 列，与 <case_id>/ 同级）
```

退出码 `0` 全 pass / `70` 跑完但有条目失败 / `71` 批次中止（环境缺失或展开超上限）。
失败策略是四层的：派生失败记 `no_artifact`、参数应用失败记 `malformed`、`pre` 红就跳过求解
省机时、环境缺失中止整批。**它不做智能**：每组参数改成什么值，全由使用者在 `cases.json`
里写全。

### 4.2 dev_lib：改 OpenFOAM 的类（B2，0..1×）

四个阶段 `prepare` / `check` / `build` / `verify`（`scripts/dev_lib.py:55`），
四道码 `85`–`89` 各管一件事：规格不合法 / 改动越界 / 构建失败 / 加载证明失败 / 系统树被改动。
它派生副本、判改动范围、编译、证明 `.so` 能被加载——**但不写也不生成 C++**。
中间的改 `.C` 是人的活，脚本只在事后判范围。`verify` 只判 `dlopen error` 计数，
不判 `foamRun` 的退出码（坏库名实测也退 0）。

### 4.3 治理层：永不进用户流程

`deploy.py`（T0 安装，码 `90`/`91`，见 `scripts/deploy.py:95`）、`make_export.sh` +
`verify_export.py`（组导出树并跑 E1–E6，`80`）、`make_release.sh`（白名单组包，
15 条 = 3 md + 10 脚本 + `VERSION` + `LICENSE`，`60`）、`verify_references.sh`、
`status_snapshot.py`、`check_release_docs.py`、`check_contracts.py`。
它们的共同点是：**使用者遇不到**。唯一贴边的是 `check_contracts.py`——批量跑完
如果仓库里恰好有它，`batch.py` 会顺手调一次（`scripts/batch.py:814`）；发布包里没有这个文件，
所以这条边在用户侧恒为假。

## §5 五个「看着该触发但其实没有」的坑

### 5.1 第十个工具没有被自检

`release/SKILL.md:17` 说「十个确定性的命令行工具」，但 `preflight.sh` 只检查九个：
`USER_SCRIPTS` 数组里是 `parse_requirement.py` … `dev_lib.py` 九条
（`scripts/preflight.sh:75`），**不含 `preflight.sh` 自己**。实跑输出也是
「同目录 9 个用户面脚本均存在且可执行」（`scripts/preflight.sh:213` 打印的正是数组长度）。
差额不是漏检：自己检自己在逻辑上无意义——脚本已经跑到这里了。读者不必怀疑数错了。

### 5.2 `--mode check` 之后跑 `--stage post` 必然红

`check` 只建网格 + checkMesh 就 `exit 0`，所以 `log.shortRun` 不存在；`post` 判 G3 时拿到的是
「MISSING log.shortRun：短跑日志缺失 ⇒ 未判定，不是通过」，退出码 `3`，G4 也红（末时刻目录
不存在）。**这是设计，不是 bug**：主链路其实是两条支线，`check` 只到 G2，
`short`/`full` 才到 G3/G4。把流程画成一条直线的人，一定会在这里撞上一次假失败。

同一段里还有个更隐蔽的：**还没有网格时 G1 也 RC=0**。G1 只查三件事——`system/` 三字典在、
`0/` 非空、`constant/` 有物理字典——加上一项 patch 集合比对；而 patch 比对在
`constant/polyMesh/boundary` 不存在时只写一行 `SKIP`（`scripts/verify_case.sh:655`），
不改 RC。所以 `pre` 通过**不说明网格对**，甚至不说明网格存在。

### 5.3 门禁不是只读的

`pre` 会往 case 树里写 `log.g1` 与 `log.g5`（脚本头自己写着「本脚本不建/改/删 case 里的
任何文件，唯一写操作是 `<dir>/log.g1`、`log.g5`」，`scripts/verify_case.sh:46`）。
所以「门禁只读、可以随时重跑」这句话要打个折：它写，但它按类把自己的产物从 G5 的改动集里
排除掉——否则第二次跑会把自己上次的日志判成越界。判据现在是**按类**：名字以 `log.` 开头
一律算产物，纯数字的时间目录（`0/` 除外）也算；枚举清单 `RUN_ARTIFACTS` 仍然保留，
但它只用来兜 `case.meta` / `assert.json` 这类无模式可判的名字。按类之前是枚举式的，
漏过 `log.blockMesh`，实测让「先求解、后跑 `pre`」的人看到假红。

`fix_case.py` 的 `locate` 也不是纯只读：命中定位规则时会写 `fingerprints.txt`，
而它落在 `<case 父目录>` 而不是 case 里（`scripts/fix_case.py:459`）。单例用法下，
所有 case 共用一份台账，于是「这个失败以前修过」是跨 case 去重的。

### 5.4 同一个 `case.meta` 被判成「两处都有」

`verify_case.sh` 认 `case.meta` 的两个合法位置：case 树内，或 run 根。而 `--log` 缺省
等于 `--case`（`scripts/verify_case.sh:121`），单 case 用法下 `LOG_DIR == CASE_DIR`，
同一个文件自然「两处都有」，于是每次都打印一条
「注意 case.meta 同时存在于 case 树与 run 根」（`scripts/verify_case.sh:135`）。
**这是无害噪声**，不是出现了两份。批量的布局不同（`run/` 与 `run/case/` 真的分开了），
所以 `batch.py` 派生完就把 `case.meta` 移到 run 根，并写明理由（`scripts/batch.py:65`）。

### 5.5 改了 `blockMeshDict` 不删 `polyMesh`，门会全绿

`run_case.sh` 只在 `constant/polyMesh` 不存在时才跑 `blockMesh`（`scripts/run_case.sh:192`）。
不删旧网格的后果是四连：求解仍在旧网格上；G2 读的还是上一次的 `log.checkMesh`，`Mesh OK.`
照样过；五门可能全绿；只有 `post` 的 `RES=stale` 会把这件事说出来。
正确动作是先 `rm -rf constant/polyMesh` 再重跑（`release/SKILL.md:221` 给了同样的结论）。
换外部网格（T4b）同理，转换器在输出目录非空时退 `15` 拒写，就是为了不让旧网格混进来。

## §6 一次实测运行的时间线

一台 WSL2 + OpenFOAM v13 的机器上，用 `incompressibleFluid/cavity` 走了一遍；
下表的 rc 与耗时是**本机实测**，命令列可按原样复跑。耗时单位 ms。

| # | 命令（简写） | rc | ms | 关键输出 / 落盘 |
|---|---|---|---|---|
| T1 | `preflight.sh` | 0 | 379 | `6/6 项通过` |
| T2 | `parse_requirement.py --text … --out` | 0 | 98 | `complete=true`，落 `cavity.spec.json` |
| T3 | `find_template.sh --keyword cavity --limit 5` | 0 | 6682 | `FOUND=28`、`SHOWN=5` |
| T4 | `new_case.sh --source … --dest cavity-01` | 0 | 91 | `DERIVED=…/cavity-01` |
| T5 | `foamDictionary … -entry simulationType -set laminar` | 0 | — | 回读 `laminar` |
| T7 | `verify_case.sh --stage pre`（**先在没有网格时跑一次**） | 0 | 219 | 新增 `log.g1`、`log.g5`；G1/G5 皆 `RC=0` |
| T6 | `run_case.sh --mode check` | 0 | 789 | `constant/polyMesh/` 五个文件、`log.blockMesh`、`log.checkMesh` |
| T8 | `run_case.sh --mode short --timeout 120` | 0 | 869 | `SHORT_END=0.01`、`log.shortRun`、时间目录 `0.01/` |
| T9 | `verify_case.sh --stage post` | 0 | 192 | G2/G3/G4 皆 `RC=0`；诊断 `OBJ=mismatch`、`RES=marginal` |
| T8 | `run_case.sh --mode full --timeout 300` | 0 | 4136 | `log.run`、`0.5…10` 共 21 个时间目录；controlDict 恢复 |
| T9′ | `verify_case.sh --stage post`（**在只跑过 check 的 case 上**） | **3** | 103 | `MISSING log.shortRun ⇒ 未判定，不是通过` |
| T10a | `fix_case.py --error-log log.shortRun`（日志含 `Unknown patchField type`） | 0 | 120 | `declined=true`、`changes=[]`、不写台账 |
| T10a | 同上（日志含 `keyword nu is undefined`） | 0 | — | `changes=[{file, entry:nu, new_value:null}]`，台账加一行 |
| T10b | `fix_case.py --apply …`（但 `nu` 在文件里 0 次命中） | **33** | — | 写前校验未过 ⇒ 不备份、不写 |
| T10b | `fix_case.py --apply …`（`nu` 恰好 1 次） | 0 | — | `attempt_1/`（整树副本 + `fingerprint.txt`），回读 `2e-05 [ m^2 / s]` |

读这张表要注意三处：

1. **T7 那一行是故意提前跑的**，为的是验证「没有网格时 G1 会怎样」——结论是 `RC=0`
   （§5.2）。正常顺序里 `pre` 在 T6 之后。
2. **T9′ 那一行是负对照**：同一个 `post` 命令，在有 `log.shortRun` 的 case 上退 0，
   在只有 `log.checkMesh` 的 case 上退 3。它不是偶发失败，是「门禁只判它拿到的日志」这条设计的
   直接体现。
3. **T10 的两行 `33`/`declined` 是两种拒绝**，都不写盘：`declined` 是「定位不到 file+entry，
   不猜」；`33` 是「定位到了，但文件里这个 entry 命中 0 次（要求恰好 1 次），所以不改」。
   两种拒绝都不是崩溃——退出码 `0` 的那次里 `written=false`，读 JSON 才看得见。

两条耗时的口径：T3 的 6682 ms 是全库 grep 的代价（数据量，不是性能）；其余步骤从百毫秒到四秒
不等，最大的那一项是真跑求解的 `full`（4136 ms）。

## §7 本页事实怎么复核

每条先写它验证哪条断言，再给命令。全部在仓库根执行；带 `$WORK` 的几条需要先按 §2 建一个 case。

**① 断言「除批量入口外，脚本之间零调用」**

```bash
grep -rn 'scripts / "' scripts/*.py
```

期望：只有 `batch.py` 的 482 / 499 / 511 / 593 四处（另有一处 814 是可选的
`check_contracts.py`，发布包里不存在）。

**② 断言「harness 自己声明不控流程」**

```bash
sed -n '15,21p' release/SKILL.md
```

期望：`它不含任何模型调用、不决定下一步做什么、不自己循环`，以及「调度权、裁决权在调用方那边」。

**③ 断言「包内 10 个脚本，`preflight` 只自检 9 个」**

```bash
sed -n '/^WL_SRC=(/,/^)/p' scripts/make_release.sh | grep -c 'scripts/'
sed -n '75,85p' scripts/preflight.sh | grep -cE '\.(sh|py)$'
```

期望：`10` 与 `9`。

**④ 断言「实跑输出也报 9」**

```bash
source /opt/openfoam13/etc/bashrc && bash scripts/preflight.sh | grep 'OK scripts'
```

期望：`OK scripts 同目录 9 个用户面脚本均存在且可执行`。

**⑤ 断言「退出码原文只存在于脚本头部，本文没有另造总表」**

```bash
grep -nE "退出码" scripts/preflight.sh scripts/parse_requirement.py \
  scripts/find_template.sh scripts/new_case.sh scripts/run_case.sh \
  scripts/verify_case.sh scripts/fix_case.py scripts/batch.py \
  scripts/msh2d_to_foam.py scripts/dev_lib.py
```

期望：每个文件一到十行不等（`verify_case.sh` 最多），那些行就是 §2 表里各个码的出处。

**⑥ 断言「`short` 改写 controlDict，恢复只在 `full` 分支里」**

```bash
sed -n '225,226p;231,234p' scripts/run_case.sh
```

期望：先是 `set_entry endTime "$SHORT_END"` / `set_entry writeInterval 2`，
然后是 `if [ "$MODE" = "full" ]` 里的两行恢复。两段之间没有任何「无论如何都恢复」的出口。

**⑦ 断言「`--log` 缺省等于 `--case`，所以单例用法必然出现那条提示」**

```bash
grep -n 'LOG_DIR="\$CASE_DIR"\|同时存在于' scripts/verify_case.sh
```

期望：`121`（缺省赋值）与 `135`（那条提示）。

**⑧ 断言「`pre` 会写 case 树」**

```bash
grep -n '唯一写操作' scripts/verify_case.sh
ls "$WORK"/cavity-01/log.g*
```

期望：脚本头那一行自述；以及 `log.g1`、`log.g5` 两个文件确实躺在 case 根。

**⑨ 断言「指纹台账落在 case 的父目录」**

```bash
grep -n 'run_dir = case_dir.parent' scripts/fix_case.py
```

期望：`459` 与 `579` 两处。

**⑩ 断言「没有网格时 G1 只是跳过 patch 比对，不改 RC」**

```bash
sed -n '655p' scripts/verify_case.sh
```

期望：`SKIP constant/polyMesh/boundary 不存在，patch 集合子项未判定`。

**⑪ 断言「只在没有 polyMesh 时才 blockMesh」**

```bash
grep -n 'if \[ ! -d constant/polyMesh \]' scripts/run_case.sh
```

期望：`192`。

**⑫ 断言「`find_template.sh` 是五个根上的全库 grep」**

```bash
grep -n 'ROOT_VARS\|grep -rnI' scripts/find_template.sh
time bash scripts/find_template.sh --keyword cavity --limit 5
```

期望：`37` 与 `97` 的五个根、`119` 的 `grep -rnI`；实跑 `FOUND=28`，
本机耗时 6.7 s 量级。

**⑬ 断言「派生只是整树复制 + 一个 `case.meta`」**

```bash
grep -n 'cp -a -- ' scripts/new_case.sh
find "$FOAM_TUTORIALS"/incompressibleFluid/cavity -type f | wc -l
```

期望：`162` 的 `cp -a`；教程本身 13 个文件，派生后加 `case.meta` 是 14 个。

**⑭ 断言「`check` 之后 `post` 必然红」**

```bash
bash scripts/run_case.sh --case "$WORK/cavity-01" --mode check
bash scripts/verify_case.sh --stage post --case "$WORK/cavity-01"; echo "rc=$?"
```

期望：第一条 `rc=0` 且 `LOGS=log.checkMesh`；第二条 `rc=3`，失败串含
`MISSING log.shortRun`。

**⑮ 断言「`foamDictionary -set` 对不存在的 entry 会新增并退 0」**

```bash
cd "$WORK/cavity-01"
foamDictionary constant/physicalProperties -entry noSuchKey -set 1; echo "rc=$?"
foamDictionary constant/physicalProperties -entry noSuchKey -value
```

期望：`New entry noSuchKey 1;` 与 `rc=0`，回读也拿得到 `1`——所以「改成功了」这个判断
不能只看退出码。

**⑯ 自检：本文没有本机标识与家目录绝对路径**

```bash
grep -nE "/home/[a-z]|/mnt/[a-z]/" references/15-harness-flow.md
```

期望：0 行。
