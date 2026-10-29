---
name: openfoam-v13-case-harness
description: Use when 要把一句自然语言 CFD 需求变成一个能在本机 OpenFOAM v13 上跑通的 case 目录（派生 tutorial、改字典、跑求解、过五道门禁）。本 harness 只提供九个确定性命令行工具与一份文档：不含模型、不控流程，模型与循环由调用方提供。仅支持 OpenFOAM v13。
---

# OpenFOAM v13 case harness

## 1 这是什么（以及它不是什么）

**v13-only。** 本 harness 的每条判据、每个字典关键字都按本机 `/opt/openfoam13` 的真实语法核对过。
其它版本（v2012、esi 系、v11/v12、任何 OpenFOAM.com 版本）**一律不支持**：换版本会同时出现假红
（判据失效）和假绿（旧语法被接受，跑不起来却没人报警）。版本不对时前置检查会直接拦住
（退 51），不会让你在半路才发现。

**这是一个 harness，不是 agent。** 它不含任何模型调用、不决定下一步做什么、不自己循环：

- 它提供的东西：**九个确定性的命令行工具** + 这份文档。同样的输入永远给同样的输出。
  （一个前置检查 `preflight.sh` + 八个功能工具：需求解析 / 检索 / 派生 / 网格转换 / 求解 / 门禁 / 修复 / 批量）
- 谁决定流程：**调用方**——人，或者读这份文档的另一个 agent。调度权、裁决权、什么时候停下问人，
  都在调用方那边。
- 因此"跑通了"这句话的**证据是退出码**，不是任何一方的自述。harness 只回答"能不能跑"，
  不回答"结果对不对"（见 §8）。

一句话：你（宿主）负责想和决定，harness 负责把每一步做成可判定的。

## 2 前置检查（第一条命令，永远先跑）

```bash
export HARNESS=/path/to/foam-mate-0.2.0            # 本包根目录，里面有 scripts/
export WORK=$HOME/foam-work                        # 你的工作目录，随便选
mkdir -p "$WORK"
bash "$HARNESS/scripts/preflight.sh"                # 无参数 = 跑检查
```

它做 6 项检查（bashrc / 命令 / tutorial 数 / 版本 / python3 / 脚本完整性），每项一行。
**只有三种结局**：

| 退出码 | 输出长什么样 | 下一步 |
|---|---|---|
| `0` | 6 行 `OK ...` 在 stdout，末行 `preflight: 6/6 项通过，环境就绪。` | 直接进 §3 |
| `50` | **stderr** 里有 `FAIL bashrc ...` / `FAIL commands ...`，末行 `下一步：source <前缀>/etc/bashrc` | **环境没加载**。逐字执行那条 `source`，再跑一次前置检查 |
| `51` | **stderr** 里有 `FAIL version WM_PROJECT_VERSION='12'(期望字面值 13)`，汇总行以 `preflight: 本包只支持 OpenFOAM v13` 开头 | **装错版本**。不要改脚本、不要降级判据：这个包只对 v13 负责，换环境或停在这里 |

`50` 与 `51` 分开是为了处置方向：`50` 只要一条命令，`51` 要换安装。
**注意 `51` 的末行提示也是 `下一步：source ...`——那条对 `51` 不适用**（重新 source 同一个 bashrc
不会把版本变成 13），它是脚本给所有非 0 结局统一加的一句。看到 `51` 就看 `FAIL version`，别照抄末行。

前置检查之外的任何脚本也都会自己判环境，缺环境时退 22 或 64，不会假装跑过。

## 3 六步链（每步都可直接复制）

后面的命令都假设你已经 `source` 过 bashrc 并 `export HARNESS WORK`。**所有路径用绝对路径**。

### 步骤 1 · 需求 → 四元组

把用户原话整句丢进去，不要自己总结：

```bash
python3 "$HARNESS/scripts/parse_requirement.py" \
  --text "一个二维方腔，顶盖 1 m/s，水，层流，稳态" \
  --out "$WORK/cavity-01.spec.json"
```

输出一行 JSON：`geometry / properties / boundary / objective`，外加 `complete` 与 `missing`。
它**只负责猜，猜不到就记 null**，绝不填默认值。

- 退 `0` + `"complete": true` → 进步骤 2。
- 退 `10` → `missing` 里列出的键用户没说。**停下问人**（§5 第 1 条），不要替用户补默认值：
  默认值会把"需求没被满足"变成"五道门全过"，这是本 harness 最贵的失败形状。

> **`objective` 是这一格的特殊情况，必须读完这一段再用。**
> `objective` 只会被**解析和存档**（进 `case.meta.spec`），**本 harness 不做任何翻译**：
> 它不会因为你要"稳态"就去改 `ddtSchemes`，也不会替你挑求解器。派生来的 case 是瞬态还是稳态，
> 完全取决于那份 tutorial 自己怎么写。
> 因此：**门全绿不代表 `objective` 被满足**。判据在步骤 6 —— 后置门禁会打一行
> `OBJ=<match|mismatch|unknown>`，把"你要的"与"实际的 `ddtSchemes`"摆在一起。看到 `mismatch`
> 时要么自己改字典（改哪些 entry 由你按物理决定），要么把它作为已知偏差写进你的结论。

> **同样的问题也存在于"几何尺寸"上，而且更隐蔽。** 你说"二维方腔"但没给边长：
> `parse_requirement.py` 照样会报 `"complete": true`（`geometry` 字段只要有文字就算给了），
> 边长于是静默继承派生源 tutorial 的 `convertToMeters`（实测 `0.1`，即 0.1 m）。
> 配合 `nu=1e-6` 就是 Re=1e5，而网格只有 20×20=400 cells —— 那样跑出来的结果**没有物理意义**，
> 尽管五门全绿。
> 所以后置门禁还会打 `GEO=`（网格量与尺度）、`RE=`（估出来的雷诺数）、`RES=<coarse|ok>`
> （网格量是否明显不够）。`RES=coarse` 不是判定，是提醒：要么加密网格，要么在结论里写明
> "本次仅演示流程"。

> **要真做稳态，语法去哪抄（不要凭记忆写）。** 这三处是 v13 里 `steadyState` 的完整写法，
> 直接 grep 就能拿到，别自己发明：
>
> ```bash
> bash "$HARNESS/scripts/find_template.sh" --keyword steadyState --limit 20
> ls -d "$FOAM_TUTORIALS"/incompressibleFluid/*[Ss]teady*
> ```
>
> 参考实现是 `$FOAM_TUTORIALS/incompressibleFluid/pitzDailySteady`（同一 solver module，
> `solver incompressibleFluid`），三处需要同步改：
>
> | 文件 | 改什么 | 该 tutorial 里的值 |
> |---|---|---|
> | `system/fvSchemes` | `ddtSchemes { default steadyState; }` | `steadyState` |
> | `system/fvSolution` | `SIMPLE { residualControl { p 1e-2; U 1e-3; } }` + 顶层 `relaxationFactors { equations { U 0.9; ".*" 0.9; } }` | 见该 case |
> | `system/controlDict` | `deltaT` 与 `endTime` 变成**迭代计数**，不再有物理时间含义 | `deltaT 1; endTime 2000` |
>
> **闭腔（无进出口，比如方腔）还要多一步**：压力没有唯一解，必须把原来的
> `pRefCell 0; pRefValue 0;` 从 PIMPLE 块**搬进新的 SIMPLE 块**。
> `pitzDailySteady` 是有进出口的后台阶算例，没有这两项——直接照抄会漏，然后跑出一个
> 压力漂移的解。
>
> 改完必须重跑 G3/G4（`run_case.sh --mode full` 再 `verify_case.sh --stage post`）。
> 跑成功时 `log.run` 里会出现这两行（**逐字，前缀是 `SIMPLE:` 不是 `PIMPLE:`**）：
>
> ```
> SIMPLE: Operating solver in steady-state mode with 1 outer corrector
> SIMPLE: Operating solver in SIMPLE mode
> ```
>
> **抄语法，别抄收敛阈值。** `pitzDailySteady` 的 `p 1e-2 / U 1e-3` 对后台阶够用，
> 对 Re=1000 的方腔不够——实测照抄会在 162 次迭代就宣称 `SIMPLE solution converged`，
> 而中线速度剖面还是错的（u(y/H=0.5) 报 −0.099，收紧后是 −0.059）。阈值要按你自己的
> 算例调，且**不能比 `fvSolution.solvers` 里对应场的 `tolerance` 更严**（更严就永远满足不了，
> 只能靠 `endTime` 停）。
>
> **harness 不会替你改这些**：改哪几项、残差收到多少，取决于你的物理判断。上面给的是语法出处，不是模板。

### 步骤 2 · grep 定派生源（不许凭印象指定 tutorial）

```bash
bash "$HARNESS/scripts/find_template.sh" --keyword cavity --limit 20
ls -d "$FOAM_TUTORIALS"/*/cavity*        # 按目录名找，见下面的说明
```

- `find_template.sh` 搜的是**文件内容**（等价 `grep -F`），所以它回答"这个关键字在真实 case 里
  怎么写"，不回答"哪个目录叫这个名字"。要找目录名用第二行那种 `ls -d`。
- 输出每行 `相对路径:行号`，末两行 `FOUND=<总数>` 与 `SHOWN=<实际输出行数>`。
- 退 `11` = `FOUND=0`，**这个词在本机 tutorial 里不存在**。这是有效结论，不是"没查着"：
  换一个词再试（每次只改一个词），三次都空就告诉用户库里没有，并列出试过的词。
- 选派生源的三条硬要求：① 必须真的命中；② 必须是 `$FOAM_TUTORIALS` 下的（`legacy/` 除外，
  那是旧语法）；③ 它的 `system/controlDict` 里要有 `solver` 条目（v13 主线用 `foamRun`），
  有 `regionSolvers` 的是多区域（要用 `foamMultiRun`，本包不覆盖）。

### 步骤 3 · 派生（cp -a，不是从空目录写字典）

```bash
bash "$HARNESS/scripts/new_case.sh" \
  --source incompressibleFluid/cavity \
  --dest "$WORK/cavity-01" \
  --spec "$WORK/cavity-01.spec.json"
```

成功时 stdout 两行 `DERIVED=<绝对路径>` 与 `SOURCE=<相对路径>`，并在 `<dest>/case.meta` 里写六个键
（`source / derived_at / spec / changes / allowed_files / schema_version`）。

- 退 `12` = source 不合法（不存在、不在 `$FOAM_TUTORIALS` 下、或缺 `system/controlDict`），
  **此时 `<dest>` 完全没被创建**。回去做步骤 2。
- 退 `13` = 目标目录已存在。**它不会覆盖任何东西**（这是保护你的数据）。换个 `--dest`，
  或自己确认后删掉旧目录再派生。

### 步骤 3b · 网格：blockMesh 还是导入外部网格（需求要非六面体时才读）

`blockMesh` 是结构化六面体生成器，**出不了三角形或四面体**，没有选项能改这一点。
`$FOAM_TUTORIALS/fluid/prism` 的 "prism" 只是 patch 名 `prismWall`，`blocks` 段全是 `hex`——
别从目录名推断生成器能力，读 `blocks` 段。

需求要求三角形网格时走导入这条路：

```bash
# 1. 2D 三角面网格：geo 里写 `Mesh 2;`，每个壁面一条 Physical Curve
gmsh -2 system/triangle2d.geo -format msh2 -o system/triangle2d.msh
# 2. 2D msh → 单层三棱柱 polyMesh（换网格必须先删旧网格）
rm -rf constant/polyMesh
python3 "$HARNESS/scripts/msh2d_to_foam.py" --msh system/triangle2d.msh \
        --out constant/polyMesh --thickness 0.01
# 3. 判网格（G2 只认这一行 Mesh OK.）
checkMesh > log.checkMesh; grep -E "prisms|Mesh OK\.|\*\*\*" log.checkMesh
```

三条别踩的：

- **2D 只能是棱柱。** OpenFOAM 的 2D 判据要求 `empty` 面数 == 2×cells，且所有边垂直或平行于
  非空方向。单层四面体两条都不满足：实测 2832 tet 得 `Failed 1 mesh checks`（1888 empty faces、
  1456 条斜边），求解在 `t=0.04 s` 就 `Floating point exception`（Co max 33、残差 1e+297）。
  而 `gmsh -3` 把三角面挤出后**一定给四面体**——这就是中间必须有那一步的原因。
- **`gmshToFoam` 收不了纯 2D msh**（`No cells read … Does your file specify any 3D elements`）。
- **转换器在输出目录非空时退 `15` 拒写**，这不是刁难：混进旧网格会得到一份"看着建好、其实
  跑在旧网格上"的算例。

转换器**不生成网格**：拓扑全部来自 gmsh，它只搬格式，落盘前做五项自检（msh2 ascii / 共面 /
逆时针 / 非流形 / 每条边界边能定位到 patch 名），任一条不过退 `14` 且**一个文件都不写**。
它零 OpenFOAM 依赖，所以能在没装 OpenFOAM 的机器上判。

导入后 patch 名一定变了：读 `constant/polyMesh/boundary` 拿真名，再把 `0/` 里**每个**场的边界块
改过来（漏一个场就是求解时 `Cannot find patchField entry for …`）。

### 步骤 4 · 改字典（只改字典，不重写物理）

先看教程原值和需求差在哪，改完**必须回读**。`foamDictionary` 的字典文件是**位置参数**，
`-case` 不能代替它：

```bash
cd "$WORK/cavity-01"
foamDictionary constant/momentumTransport -entry simulationType -set laminar
foamDictionary constant/momentumTransport -entry simulationType -value   # 回读：应打印 laminar
foamDictionary constant/physicalProperties -entry nu -set "1e-06 [m^2/s]"
foamDictionary constant/physicalProperties -entry nu -value              # 回读：应打印 1e-06 [ m^2 / s]
```

三条实测纪律（每条都是踩过的坑）：

1. **`-set` 对不存在的 entry 会新增并退 0**，拼错键名不会报错，只会悄悄多一个键。所以回读是
   唯一防线；`run_case.sh` 里也一律回读，不符按求解失败处理。
2. **带量纲的值要带上量纲**：`1e-06` 与 `1e-06 [m^2/s]` 不是一回事，前者在需要量纲的 entry 上会
   FATAL。
3. 改完把改动记到 `case.meta` 的 `changes` 里（人看的部分）。G5 会按 `allowed_files` 判你有没有
   越界改文件——默认只允许 `system/*`、`constant/*`、`0/*`。
   `changes` **没有命令行入口**，是纯手写的 JSON 数组；门禁**不要求**它非空（只有你在
   `constant/polyMesh/` 里动过东西时，它才被当作"为什么可以动"的理由读一次）。没写不影响过门，
   但写了对下一个人有用。

**改网格的纪律（最容易上当的一条）**：`run_case.sh` 只在 `constant/polyMesh` **不存在**时才跑
`blockMesh`。所以改了 `system/blockMeshDict` 之后，**必须删掉 `constant/polyMesh` 再重跑**，
否则：

- 求解用的仍是旧网格；
- `G2` 读的还是上一次的 `log.checkMesh`，`Mesh OK.` 照样过（门会绿）；
- 只有 `post` 里的 `RES=stale` 会把这件事说出来。

```bash
rm -rf constant/polyMesh        # 想换网格就必须删，否则等于没改
bash "$HARNESS/scripts/run_case.sh" --case "$WORK/cavity-01" --mode full --timeout 1800
```

> **顺带一条 `foamDictionary` 纪律**：`-entry` **不认点路径**。`-entry SIMPLE.residualControl`
> 会 `FOAM FATAL IO ERROR: Cannot find entry` 并退 `2`（注意这个 `2` 与"G2 网格门失败"同号，
> 别混）。子字典要么 `-entry SIMPLE` 整块 dump，要么用 `-set "{ ... }"` 整块替换。

### 步骤 5 · 跑

```bash
bash "$HARNESS/scripts/run_case.sh" --case "$WORK/cavity-01" --mode check   # 只建网格+checkMesh
bash "$HARNESS/scripts/run_case.sh" --case "$WORK/cavity-01" --mode short --timeout 300
bash "$HARNESS/scripts/run_case.sh" --case "$WORK/cavity-01" --mode full  --timeout 1800
```

三种模式的差别只有一项：`check` 到 checkMesh 为止，`short` 跑 2 步，`full` 先跑 2 步再恢复原
`endTime` 跑完整算例。日志固定落 `log.blockMesh / log.checkMesh / log.shortRun / log.run`。
**别跳过 `short` 直接 `full`**——这里的意思不是"要跑两次命令"：`full` **内部已经先跑了一遍 2 步
短跑**（那份 `log.shortRun` 就是它写的，G3 判的就是它）。所以只跑 `full` 一条命令是允许的，
跳过的是"不验证就直接长跑"这个动作，不是那条命令。想单独看 2 步结果时才用 `--mode short`。

| 退出码 | 含义 | 下一步 |
|---|---|---|
| `0` | 正常（`STATUS=ok`） | 进步骤 6 |
| `20` | 求解失败（FATAL，或改字典后回读不符） | 读 `log.run`/`log.shortRun` 的 `FOAM FATAL` 段，进步骤 6 的回修 |
| `21` | 超时（`--timeout` 到点） | 不是失败也不是成功：加 `--timeout`，或把 `endTime` 改小先看能不能跑起来 |
| `22` | 环境缺失（PATH 里没有 `foamRun`） | 回 §2，`source` bashrc |
| `23` | 没有可用网格（既无 `constant/polyMesh` 也无 `system/blockMeshDict`） | 派生源选错了：换一个自带 `blockMeshDict` 的 tutorial |
| `64` | 用法错误 / `--case` 不存在 | 改调用，不要改算例 |

### 步骤 6 · 门禁，失败就回修

门禁分两个入口。`pre` 只做文件检查、**一行 OpenFOAM 命令都不跑**（结构不对就不必白跑网格）；
`post` 只解析上一步写下的日志、也不跑求解：

```bash
bash "$HARNESS/scripts/verify_case.sh" --stage pre  --case "$WORK/cavity-01"
bash "$HARNESS/scripts/verify_case.sh" --stage post --case "$WORK/cavity-01"
```

五道门**不是**一次调用全打出来：`pre` 打 G1 与 G5（零 OpenFOAM 命令），`post` 打 G2 / G3 / G4
（只解析日志）。两段加起来是五道门。
每个门的输出形如 `G<n> RC=<0|1>`；脚本的退出码是**第一个失败的门**（`0` 全过 / `1` G1 / `2` G2 /
`3` G3 / `4` G4 / `5` G5）。

`post` 还会多打几行**诊断**（都不是门、都不进退出码）：

| 诊断行 | 含义 |
|---|---|
| `OBJ=<match\|mismatch\|unknown>` | 需求里的 `objective` 与真实的 `ddtSchemes` 是否一致（见步骤 1） |
| `GEO=cells=… convertToMeters=…` | 这个算例实际有多大：网格量与几何尺度。`cells` 一律取**磁盘上的真实网格**（`constant/polyMesh/owner` 的 `nCells`），不是 `blockMeshDict` 里写的 |
| `RE=<数>` | 由 `U_ref`（`0/U` 里最大的 `fixedValue`）、`L`（按 `convertToMeters` 的量级）、`nu` 估的雷诺数 |
| `RES=<coarse\|marginal\|ok>` | **量级启发式**（按 cellRe=Re/√cells 分级）：网格量是否明显小于该 Re 所需。<1000 以下才可能可靠 |
| `RES=stale` | **`blockMeshDict` 改了但网格没重建**——见步骤 4 末尾。出现这一行时不会再有别的 `RES=` 结论 |

看到 `mismatch` / `coarse` / `marginal` / `stale` 时：门仍然可能是绿的，但**"能跑"与"结果可信"是两件事**。处置见步骤 1 与步骤 4。

| 门 | 判什么 | 不过时先看哪里 |
|---|---|---|
| G1 结构 | 三个 `system/` 字典在、`0/` 非空、`constant/` 有物理字典、`0/` 的 patch 名与网格一致 | 少哪个文件；patch 名是否照抄了别的算例 |
| G2 网格 | `log.checkMesh` 里有 `Mesh OK.`（**不看 checkMesh 的退出码**，它不合格也退 0） | `log.checkMesh` 的 `Failed N mesh checks` 与 `***` 行 |
| G3 短跑 | `log.shortRun` 退出码 0 且无 `FOAM FATAL` | 第一个 `FOAM FATAL` 段，它直接指出缺哪个 entry |
| G4 产物 | 末时刻目录存在、每个场能读、无 `nan`/`inf` | 是不是发散了；`deltaT` 是否过大 |
| G5 范围 | 只改了 `case.meta.allowed_files` 允许的文件 | 你是不是动了 `constant/polyMesh/` 或别的算例 |

回修只有两种动作，都**不猜值**：

```bash
# ① 从失败日志定位到「改哪个文件的哪个 entry」（不写盘）
python3 "$HARNESS/scripts/fix_case.py" --case "$WORK/cavity-01" \
  --error-log "$WORK/cavity-01/log.shortRun" --attempt 1
# ② 按你决定的改动备份→写回→回读（备份在 <case 父目录>/attempt_1/）
python3 "$HARNESS/scripts/fix_case.py" --case "$WORK/cavity-01" \
  --apply '[{"file":"system/fvSolution","entry":"PIMPLE","new_value":"..."}]' --attempt 1
```

`locate` 只给 `{file, entry, new_value: null}`——"能确定改哪儿"不等于"知道该改成什么值"，
后者依赖需求与物理判断。改完回步骤 5 重跑，再回步骤 6。

## 4 退出码总表

| 退出码 | 含义 | 下一步 |
|---|---|---|
| `0` | 全过 / 正常完成 | 继续下一件 |
| `1` | G1 结构门失败 | 补齐 `system/` 字典、`0/`、`constant/`；核对 patch 名 |
| `2` | G2 网格门失败 | 看 `log.checkMesh` 的 `Failed N`；改 `blockMeshDict` 或换派生源 |
| `3` | G3 短跑门失败 | 读 `log.shortRun` 的 `FOAM FATAL`，按它说的 entry 改 |
| `4` | G4 产物门失败 | 场读不出或含 `nan`/`inf`：先压 `deltaT` 再看 |
| `5` | G5 范围门失败 | 你改了 `allowed_files` 之外的文件；撤销或写进 `case.meta` 的 `changes` |
| `10` | 需求四元组不全 | **停下问人**（§5 第 1 条） |
| `11` | `FOUND=0`，关键字在 tutorial 里搜不到 | 换一个词再搜，三次空就告诉用户库里没有 |
| `12` | 派生源不合法 | 回步骤 2，选一个 `$FOAM_TUTORIALS` 下带 `controlDict` 的目录 |
| `13` | 目标目录已存在（不覆盖） | 换 `--dest`；确认后自己删旧目录 |
| `14` | 网格转换：msh 不合规或自检不过 | 看 stderr 的 `[bad-input]` 段；改几何或 msh，不要改脚本 |
| `15` | 网格转换：输出目录非空且未给 `--force` | 先 `rm -rf constant/polyMesh`（推荐）；确认后加 `--force` |
| `20` | 求解失败 | 读日志的 `FOAM FATAL` 段，回修后重跑 |
| `21` | 超时 | 加 `--timeout`，或先把 `endTime` 改小 |
| `22` | 环境缺失（找不到 `foamRun`） | `source` bashrc 后重跑 |
| `23` | 没有可用网格 | 换一个自带 `blockMeshDict` 的派生源 |
| `31` | 修复尝试次数到上限 | **停下问人**（§5 第 2 条） |
| `32` | 同一个失败指纹重复出现 | **停下问人**（§5 第 2 条）——你上一轮的改动没起作用 |
| `33` | 写前校验或回读不符（字典没变） | 数一下 entry 在文件里是否恰好出现 1 次；0 次或多次都会被拒 |
| `50` | 前置检查：环境不全 | 执行它给的那条 `source <前缀>/etc/bashrc` |
| `51` | 前置检查：版本不是 v13 | 换环境或停在这里，本包不给别的版本兜底 |
| `64` | 用法错误或前置不满足（参数非法、`--case` 不存在） | 改你的调用；`64` 不是业务结果，别和 `1`–`5` 混 |
| `40` / `41` / `60` | 维护侧（打包与文档契约检查），**不在交付包里**，使用者遇不到 | 与你无关；维护者见 §9 |

**只报第一个失败的门**（按门号取最小），所以 `RC=3` 时 G4/G5 也可能红——先去修 G3。

## 5 停点：必须停下问人的四种情形

1. **需求四元组不全（退 10）**，或需求里缺几何尺寸 / 物性 / 边界条件中的任一项，而 tutorial
   里找不到合理默认。**不要**用"看起来合理"的值填上：那会把需求问题变成"门全过"。
2. **修复已经到上限（退 31）或同一失败指纹重复（退 32）**——`--max-attempts` 默认 3。
   同一指纹重现 = 上一轮的改动没生效，再试一次只是浪费一轮。
3. **同一道门连续两轮失败**。第二轮仍红说明问题不在细节而在方向（选错派生源、选错求解器），
   继续改字典只会把算例越改越远。
4. **需求超出前处理能力**：曲面、多体装配、STL/CAD、需要边界层加密、需要 `snappyHexMesh`。
   本包只走两条路——`blockMesh`，或导入外部网格（`gmshToFoam` / `fluent3DMeshToFoam`）。
   这两条都不合适时停下，不要自己生成几何。

问的时候给出：现象 + 已试过的动作 + 2–3 个选项（每个附代价：时间、风险、做不到什么）。
不要只问"怎么办"。

## 6 宿主必须遵守的三条硬规则

1. **不从空目录写整套字典，必须从 tutorial 派生。**
   *为什么*：v13 的字典项多、默认值藏得深，凭空写的字典通常直接 FATAL，更糟的是"看起来跑通了
   但用的是别的物理"。派生保证基线是真实存在的、本版本同步的模板。
2. **不跳过门禁直接声称成功。**
   *为什么*：`checkMesh`、`foamRun` 都可能退 0 而结果是错的（网格不合格时 checkMesh 照样退 0），
   自述"我看了一下字典，应该没问题"不是证据。对外说"能跑"的唯一凭据是五道门全 `RC=0`。
3. **不改 `/opt/openfoam13` 里的任何文件。**
   *为什么*：那是唯一权威的源码与教程树，改了它，之后所有"本机能不能跑"的判断都不再有意义
   （同一份证据在两棵不同的树下会给出相反结论）。要扩展就放用户目录。

## 7 已知限制

1. **几何能力上限低**：`blockMesh` 表达不了曲面与复杂装配。这是刻意取舍，不是待办。
2. **`checkMesh` 通过 ≠ 物理正确**：门只保证"能跑、边界齐、场可读"。
3. **v13 语法与旧教程不兼容**：`tutorials/legacy/` 下的 case（旧式 `icoFoam` 等）不要当派生源。
4. **导入网格的 patch 名不可预测**：`gmshToFoam` 之后必须读 `constant/polyMesh/boundary` 拿真实
   patch 名再写 `0/`，不能假设 `inlet` / `wall` 存在。
5. **并行与内存**：本机内存有限（历史上有 OOM 事故）。批量运行默认串行，`--jobs` 上限 2（见 §10）。
6. **`objective` 不做翻译**：需求里写"稳态"，派生来的算例照样可能是瞬态（实测：`incompressibleFluid/cavity`
   是 `ddtSchemes Euler` + `endTime 10`，2000 步跑到 t=10 s）。`post` 会打一行 `OBJ=` 把这件事摆出来，
   但**门全绿不代表稳态需求被满足**。要真做稳态得自己改 `ddtSchemes`/换求解器，那是物理决定。
7. **把层流化之后，`0/` 里可能还留着 `k`、`epsilon`、`omega`、`nuTilda`**（教程原样）。
   本包**不动**这些文件：G1 不要求删，G4 也只读末时刻存在的场。要不要清掉取决于你后续是否切湍流。
8. **`pre` 门禁在求解前后都能跑**：求解产生的 `log.*` 与数字时间目录（`0.01`、`1.5`…）会被当产物忽略，
   不会被判成"越界改文件"。推荐顺序仍是 `pre → 跑 → post`，那是能最早止损的顺序。

## 8 不保证什么

- **不保证物理正确性。** 五道门只判"能不能跑、边界齐不齐、场读不读得出"。结果与实验/文献是否
  一致，需要你提供参照值自己判。上一节第 2 条与这一条是同一件事的两面。
- **不保证多版本。** 只对 OpenFOAM v13 负责；v11/v12、v2012、esi 系、OpenFOAM.com 都不测。
- **不替你决定批量参数值。** 批量入口有（§10），但它只按 `cases.json` 里给的值改参数；
  "改成什么值"、"这个 Re 配这个网格合不合适"，都是你的判断。
- **不支持二次开发**（改 OpenFOAM 源码、编译用户库）。那需要用户目录里的独立编译流程，不在本包内。
- **不做前处理自动化**：不出网格、不处理 STL、不优化网格质量。
- **不造检索层、不做 GUI/Web**：知识只有 `find_template.sh` 一个 grep 入口。

## 9 下一步

- 想立刻跑一遍完整例子（含每一步的真实输出）：读 `QUICKSTART.md`。
- 想知道能做/不能做的完整清单、许可与支持范围：读 `SCOPE.md`。
- 遇到本文没覆盖的情况，按 §5 停下问人，并把它记进你的笔记——那多半是文档的缺口，不是你的错。

## 10 批量运行（v0.2）

一次跑一个参数矩阵。**它不做"智能"**：每组参数改成什么值，全由你在 `cases.json` 里写全。

### 10.1 写 cases.json

```json
{
  "base": {
    "id": "cavity",
    "source": "incompressibleFluid/cavity",
    "spec_file": "cavity.spec.json",
    "set": [
      {"file": "constant/momentumTransport", "entry": "simulationType", "new_value": "laminar"},
      {"file": "constant/physicalProperties", "entry": "nu", "new_value": "1e-5 [m^2/s]"}
    ]
  },
  "vary": [
    {"name": "cm", "file": "system/blockMeshDict", "entry": "convertToMeters",
     "values": ["0.1", "0.15", "0.2"]}
  ]
}
```

四条规则：

1. `set` 与 `vary` 里的每一项都必须是 `{file, entry, new_value}`。**参数位置得你写**——
   harness 不内置"nu 在哪个文件"这类映射表（那等于凭记忆写字典，换个教程就不成立）。
2. `vary` 的每一项是一维，结果 = 所有维度的**笛卡尔积**，顺序按声明顺序。
3. 同一 `{file, entry}` 在 `set` 与 `vary` 里都有 → **`vary` 胜出**。
4. case id = `base.id` + 每维 `_<name><value>`（小写，非 `[a-z0-9.-]` 换成 `-`），
   它同时是目录名与 `results.csv` 的 `task_id`。

**尺寸扫描用 `convertToMeters` 这类标量**。改 `vertices` 表是结构改动，
`{file, entry, new_value}` 表达不了，harness 明确不支持——那种情况请自己在外面准备好算例。

### 10.2 先看一眼再跑（强制建议）

```bash
python3 "$HARNESS/scripts/batch.py" --cases cases.json --dry-run
```

展开是隐式的（2 维 × 3 值 = 6 例，3 维 × 4 值 = 64 例）。`--dry-run` 把每例的
id / source / 全部 `{file,entry}=value` 逐行打出来，**且不创建任何目录**。
展开上限 50 例，超了直接报错不跑（`--max-cases` 可放宽）。

### 10.3 跑

```bash
python3 "$HARNESS/scripts/batch.py" --cases cases.json \
  --dest "$WORK/runs" --batch 20261029T0900 --mode full --timeout 1800
```

- `--mode`：`check` / `short` / `full`（同 `run_case.sh`）
- `--jobs`：默认 1（串行）。允许 2，**不允许更多**——本机内存有限（历史 OOM 事故）
- 每例一个目录 `runs/<批次>/<case_id>/`：`case/` `base/` `case.meta` `spec.json`
  `log.g1..g5` `log.blockMesh|checkMesh|shortRun|run` `metrics.json` `batch.log`

| 退出码 | 含义 | 下一步 |
|---|---|---|
| `0` | 整批跑完，全部 pass | 看 `results.csv` |
| `70` | 整批跑完，**有例失败** | 结果仍可用：逐行看 `status` 与 `note`，失败例的 `batch.log` 有全链路输出 |
| `71` | 整批中止 | 环境缺失（`source` 了吗）/ 展开超上限 / `cases.json` 非法——`stderr` 会点名 |
| `64` | 用法错误 | 改调用 |

### 10.4 读 results.csv

`runs/<批次>/results.csv` 的 15 列**与跨项目基准同一套定义**（唯一权威是项目规则 R12）：

| 列 | 批量运行时的取值 |
|---|---|
| `task_id` | 展开后的 case id |
| `arm` | `ours`（这一列留给跨项目对比，单机批跑恒为本包的标识） |
| `status` | 七态：`pass` / `fail` / `no_artifact` / `malformed` / `blocked` / `overclaim` / `declined` |
| `g1`–`g5` | `0` 过 / `1` 不过 / `unmeasured` 没测（**没测就不许记 0**） |
| `g2b` | 网格检查的诊断信号（`none` / `hard:N` / `soft:N` / `unknown`） |
| `repeats` / `unstable` | 恒为 `1` / `0`：本 harness 确定性，同样的输入给同样的输出 |
| `tokens_total` | 恒为 `0`：不含模型，不消耗 token |
| `wall_time_s` | 本脚本实测墙钟（两位小数） |
| `human_interventions` | 恒为 `0`：全自动、无人介入 |
| `note` | 批次、模式、失败原因摘要 |

**额外指标不进 CSV**：`OBJ=` / `GEO=` / `RE=` / `RES=` 这些诊断写在每例的 `metrics.json` 里。
理由：15 列是封闭契约，而 `note` 是自由文本——写进去就不可重算（结论必须能从 CSV 重算）。

### 10.5 失败怎么处置（四条，都可判定）

| 情形 | `status` | 门列 | 整批 |
|---|---|---|---|
| 派生失败（源不存在等） | `no_artifact` | 全 `unmeasured` | 继续下一个 |
| 参数没改成预期值 | `malformed` | 全 `unmeasured` | 继续（不跑求解，跑了也是假数据） |
| `pre` 门禁不过 | `fail` | `g1`/`g5` 实测，其余 `unmeasured` | **跳过求解**省机时，继续 |
| 求解失败 / 超时 / 无网格 | `fail` | 五门全实测 | 继续 |
| 环境缺失（`run_case` 退 22） | `blocked` | 全 `unmeasured` | **中止整批** |

最后一条是唯一会中止整批的情形：`22` = PATH 里没有 `foamRun`，是整批性的环境问题，
继续跑只会得到 N 行相同的 22。所以 `batch.py` 在开跑前就主动探测一次。
