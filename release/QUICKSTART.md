# QUICKSTART · 一个二维方腔，从一句话到五道门全过

本文是一条**完整可复现**的路径：二维方腔、顶盖 1 m/s、水、层流。每一步贴的是命令与**真实输出**。

> **关于本文的输出**：以下全部是 2026-10-29 在一台装有 OpenFOAM v13 的机器上实跑后逐字复制的，
> 不是摘要、不是回忆、不是"预期输出"。唯一做过的改写是**路径归一化**：原文里出现的两个绝对路径
> （项目根与临时工作目录）在本文中一律写成 `$HARNESS` / `$WORK`，以便跨机器阅读。
> 除此之外**逐字相同**——空格、大小写、退出码都没动（时间戳、耗时、残量除外）。
> 你跑的时候会看到你自己的路径。凡是截短的地方都标了 **（已截短）**，首尾行逐字保留。
>
> 关于包内路径：本包解出来后，`SKILL.md`、`QUICKSTART.md`、`SCOPE.md` 与 `scripts/` **同级**，
> 没有 `release/` 这一层。本文所有命令用 `$HARNESS` 指代包根，不要写死任何机器上的路径。

如果你还没读过入口文档，先读 `SKILL.md`。本文只演示"照着做"，不解释为什么。

---

## 0 准备

```bash
source /opt/openfoam13/etc/bashrc          # 必须先 source，否则 $FOAM_* 全空
export HARNESS=/path/to/foam-mate-0.3.0
export WORK=$HOME/foam-work
mkdir -p "$WORK"
```

`source` 这一行有一个实测的坑：**不要在一个 `set -u` 的 shell 里 source 它**。实测输出：

```
/opt/openfoam13/etc/bashrc: line 46: ZSH_NAME: unbound variable
```

先 `source`，之后再加 `set -u`（或者干脆不加）。这与 harness 无关，是 bashrc 自身的行为。

---

## 1 前置检查

```bash
bash "$HARNESS/scripts/preflight.sh"
```

真实输出（`RC=0`，2026-10-29 v0.2 包内重跑）：

```
OK bashrc WM_PROJECT_DIR=/opt/openfoam13 FOAM_TUTORIALS=/opt/openfoam13/tutorials
OK commands PATH 中可用: foamRun foamDictionary blockMesh checkMesh
OK tutorials /opt/openfoam13/tutorials 下 system/controlDict 共 252 个(>= 100)
OK version WM_PROJECT_VERSION=13
OK python3 python3 3.14.9 >= 3.9
OK scripts 同目录 8 个用户面脚本均存在且可执行
preflight: 6/6 项通过，环境就绪。
```

> 两个数字不要混：「6/6 项」是**检查类别**有 6 类（bashrc / commands / tutorials / version /
> python3 / scripts）；「8 个用户面脚本」是最后一类里检查了 8 个**文件**。两者不是一回事。

**`RC=0` 才继续。** 若 `RC=50`，照它末行给的 `source ...` 命令做完再跑一次；若 `RC=51`，
你的 OpenFOAM 不是 v13，本 harness 到此为止（不支持别的版本）。

---

## 2 需求 → 四元组

```bash
python3 "$HARNESS/scripts/parse_requirement.py" \
  --text "一个二维方腔，顶盖 1 m/s，水，层流，稳态" \
  --out "$WORK/cavity-01.spec.json"
```

真实输出（`RC=0`）：

```
{"geometry": "二维方腔", "properties": "水，laminar", "boundary": "顶盖 1 m/s", "objective": "steady", "complete": true, "missing": []}
```

`"complete": true` 说明四个键都齐了，可以继续。（`RC=10` 时 `missing` 会列出缺的键——那时必须
停下问人，不要自己补默认值。）

---

## 3 找派生源

先用关键字搜内容，再按名字找目录：

```bash
bash "$HARNESS/scripts/find_template.sh" --keyword cavity --limit 3
ls -d "$FOAM_TUTORIALS"/*/cavity*
```

真实输出（第一条 `RC=0`）：

```
Lagrangian/cloud/fields/derivedLagrangianPatchFields/reboundVelocity/reboundVelocityLagrangianPatchVectorField.C:87
OpenFOAM/meshes/meshShapes/face/face.C:325
OpenFOAM/meshes/primitiveMesh/primitiveMeshFaceCentresAndAreas.C:29
FOUND=28
SHOWN=3
```

```
/opt/openfoam13/tutorials/fluid/cavity
/opt/openfoam13/tutorials/incompressibleFluid/cavity
/opt/openfoam13/tutorials/incompressibleFluid/cavityCoupledU
```

注意 `FOUND=28 SHOWN=3`：`FOUND` 是命中总数，不受 `--limit` 影响。第一条命令命中的都是**文件内容**
里出现 `cavity` 的行，不是目录名——所以 `find_template.sh` 回答"这个关键字在真实 case 里怎么写"，
"哪个目录叫这个名字"用第二条 `ls -d`。

三个候选里选 `incompressibleFluid/cavity`：单区域、自带 `system/blockMeshDict`、
`system/controlDict` 里有 `solver incompressibleFluid`（v13 主线用 `foamRun`）。
`fluid/cavity` 是多区域（`foamMultiRun`），`cavityCoupledU` 是同题的另一种耦合写法——都不是本例的
最简单起点。

---

## 4 派生

```bash
bash "$HARNESS/scripts/new_case.sh" \
  --source incompressibleFluid/cavity \
  --dest "$WORK/cavity-01" \
  --spec "$WORK/cavity-01.spec.json"
```

真实输出（`RC=0`）：

```
DERIVED=$WORK/cavity-01
SOURCE=incompressibleFluid/cavity
```

生成的 `case.meta`（真实内容，逐字）：

```json
{
  "source": "incompressibleFluid/cavity",
  "derived_at": "2026-10-29T00:22:23+08:00",
  "spec": {
    "geometry": "二维方腔",
    "properties": "水，laminar",
    "boundary": "顶盖 1 m/s",
    "objective": "steady",
    "complete": true,
    "missing": []
  },
  "changes": [],
  "allowed_files": [
    "system/*",
    "constant/*",
    "0/*"
  ],
  "schema_version": 1
}
```

`allowed_files` 就是 G5 会用的白名单：只许改这三类文件。

---

## 5 改字典（需求→字典的翻译，这一步只有你能做）

派生来的教程与需求有**两处**不符。下面两条读原始值的命令是在一个**刚派生、还没改过**的副本上跑的
（实测用的副本是 `$WORK/cavity-00`）：

```
$ foamDictionary constant/momentumTransport -entry simulationType -value
RAS
$ foamDictionary constant/physicalProperties -entry nu -value
1e-05 [ m^2 / s]
```

教程默认是 `RAS`（模型是 `kEpsilon`，它嵌在子字典 `RAS { }` 里，`-entry model` 在顶层查不到，
会报 `Cannot find entry model`），粘度 `1e-05`（不是水）。需求的"层流、水"意味着要改这两个 entry：

```bash
cd "$WORK/cavity-01"
foamDictionary constant/momentumTransport -entry simulationType -set laminar
foamDictionary constant/momentumTransport -entry simulationType -value
foamDictionary constant/physicalProperties -entry nu -set "1e-06 [m^2/s]"
foamDictionary constant/physicalProperties -entry nu -value
```

真实输出（四条都 `RC=0`）：

```
New entry simulationType  laminar;

laminar
New entry nu              1e-06 [ m^2 / s];

1e-06 [ m^2 / s]
```

两条纪律：

- **每条 `-set` 后面紧跟一条回读**。`foamDictionary -set` 对不存在的 entry 会**新增并退 0**，
  拼错键名不报错、只是悄悄多一个键；回读是唯一防线。
- **量纲要带上**：`nu` 这类 entry 的值是 `1e-06 [m^2/s]`，只写 `1e-06` 在需要量纲的 entry 上会 FATAL。

（`foamDictionary` 的字典文件是**位置参数**：`foamDictionary <file> -entry <e> -set <v>`。
写成 `foamDictionary -case <dir> -entry ...` 只会打 Usage，字典一个字节都不会变。）

### 5.1 第三处不符：需求里的"稳态"，本文没有改

上面只处理了"层流"和"水"两处。需求里还有**稳态**，而派生来的 `incompressibleFluid/cavity` 是瞬态：

```
$ grep -A2 ddtSchemes system/fvSchemes | head -3
ddtSchemes
{
    default         Euler;
$ grep -E '^(endTime|deltaT|writeInterval)' system/controlDict
endTime         10;
deltaT          0.005;
writeInterval   100;
```

也就是 2000 步推进到 t = 10 s。本文**不把它改成稳态**，原因是改法属于物理决定（换 `steadyState`
还是换求解器 module、`fvSolution` 的残差与松弛怎么配），harness 不替你选——这一点在
`SKILL.md` 步骤 1 有完整说明。

**但这件事必须被看到**，所以后置门禁会打一行诊断：

```
OBJ=mismatch  (需求 objective=steady，实际 ddtSchemes=Euler)
  警告：需求要 steady，但派生源的 ddtSchemes=Euler。**五道门全绿不代表这条需求被满足**——
        门只判「能不能跑」。要不要改 ddtSchemes/换求解器，由你按物理决定（本 harness 不替你选）。
```

看到 `mismatch` 时你有两条路：① 自己按 v13 语法改 `ddtSchemes` 与相关 `fvSolution` 项（改完
G3/G4 要重跑）；② 把"本次产出是瞬态 t=10 s"写进你的结论，作为已知偏差。**不要**假装它满足了。

**要走路 ① 又不想凭记忆写字典**：`SKILL.md` 步骤 1 末尾那张表给了三处该怎么改，
以及去哪 grep 到 v13 的真实写法（`$FOAM_TUTORIALS/incompressibleFluid/pitzDailySteady`）。
改完重跑，`OBJ=` 会翻成 `match`。

---

## 6 前置门禁（G1 结构 + G5 范围，零 OpenFOAM 命令）

```bash
bash "$HARNESS/scripts/verify_case.sh" --stage pre --case "$WORK/cavity-01"
```

真实输出（`RC=0`）：

```
verify_case.sh: 注意 case.meta 同时存在于 case 树与 run 根，取 case 树内那份
G1 RC=0  $WORK/cavity-01/log.g1
G5 RC=0  $WORK/cavity-01/log.g5
```

第一行是**提示不是警告**：本例把 `--case` 直接指向 case 树（没有独立的 run 目录），于是
`case.meta` 在两处是同一份。结构不动，照常看 `G1 RC=` 与 `G5 RC=` 即可。

此时 `log.g1` 的第三行会如实写「`constant/polyMesh/boundary` 不存在，patch 集合子项未判定」——
网格还没建，这项跳过，不影响 `RC=0`。

---

## 7 跑

```bash
bash "$HARNESS/scripts/run_case.sh" --case "$WORK/cavity-01" --mode full --timeout 600
```

真实输出（`RC=0`，耗时部分是你的机器决定）：

```
CASE=$WORK/cavity-01
MODE=full
SHORT_END=0.01
LOGS=log.checkMesh log.shortRun log.run
STATUS=ok
```

`mode=full` 先跑 2 步（`log.shortRun`，67 行），再恢复原 `endTime` 跑完整算例（`log.run`，22045 行）。
**（已截短）** 中间 2000 步的迭代输出略去，首尾逐字：

```
Time = 0.005s
Time = 0.01s
Time = 0.015s
...（已截短 1995 个 Time 行）...
Time = 9.995s
Time = 10s
smoothSolver:  Solving for Ux, Initial residual = 0.000778623, Final residual = 2.26442e-07, No Iterations 2
smoothSolver:  Solving for Uy, Initial residual = 0.000562924, Final residual = 8.66768e-06, No Iterations 1
GAMG:  Solving for p, Initial residual = 0.00108253, Final residual = 5.62641e-05, No Iterations 2
time step continuity errors : sum local = 1.75542e-08, global = -3.54654e-20
GAMG:  Solving for p, Initial residual = 5.62855e-05, Final residual = 6.01933e-07, No Iterations 5
time step continuity errors : sum local = 2.00231e-10, global = -2.48361e-19, cumulative = -5.45863e-18
ExecutionTime = 2.19102 s  ClockTime = 2 s

End
```

2000 步全部跑完（`deltaT 0.005 × 2000 = endTime 10`），末行是 `End`，没有 `FOAM FATAL`。
时间目录数：

```
$ ls -d "$WORK"/cavity-01/[0-9]* | wc -l
22
```

22 个 = `0` + 短跑留下的 `0.01` + `writeInterval 100`（每 0.5 s 写一次）× 20 个 `0.5 … 10`。

---

## 8 后置门禁（G2 网格 + G3 短跑 + G4 产物）

```bash
bash "$HARNESS/scripts/verify_case.sh" --stage post --case "$WORK/cavity-01"
```

真实输出（`RC=0`，2026-10-29 在陌生环境重跑一次：解出发布包 → `p5` 目录下走完全流程）：

```
verify_case.sh: 注意 case.meta 同时存在于 case 树与 run 根，取 case 树内那份
G2 RC=0  …/cavity-01/log.g2  (G2B=none)
G3 RC=0  …/cavity-01/log.g3
G4 RC=0  …/cavity-01/log.g4
OBJ=mismatch  (需求 objective=steady，实际 ddtSchemes=Euler)
  警告：需求要 steady，但派生源的 ddtSchemes=Euler。**五道门全绿不代表这条需求被满足**——
        门只判「能不能跑」。要不要改 ddtSchemes/换求解器，由你按物理决定（本 harness 不替你选）。
GEO=cells=400  convertToMeters=0.1  需求 geometry=二维方腔
RE=1e+05  (U_ref=1, L=0.1(按 convertToMeters 量级), nu=1e-06)
RES=coarse  (cells=400 远小于 Re=1e+05 所需量级；结果可能无物理意义)
  提示：网格分辨率与 Re 不匹配时，门全绿也不代表结果可信（门只判「能不能跑」）。
        要么加密网格，要么把「本次结果仅作流程演示」写进结论。
```

**`G2/G3/G4` 之后所有以 `OBJ=` / `GEO=` / `RE=` / `RES=` 开头的行都是诊断，不是门**：
它们不改变退出码（这里仍然是 `RC=0`）。意思是——

- `OBJ=mismatch`：门全绿，但"稳态"这条需求**没有被满足**（§5.1）。
- `RES=coarse`：门全绿，但 400 个格子算 Re=1e5 **物理上不可信**。这不是本文档的演示失误，
  而是刻意留在这里的：一个"五门全绿但结果无意义"的例子，比十句警告更能说明
  "门只判能不能跑"这句话。

要继续做可信的结果，你得自己加密网格（改 `blockMeshDict` 的 `(20 20 1)`）或把 `nu` 调大以降低 Re。
两件都是物理决定，harness 不替你选。

三个日志文件的真实内容就是两行（`log.g2` 的第二行是 `G2B=`，其余留空）：

```
$ cat log.g2
RC=0
G2B=none
$ cat log.g3
RC=0
$ cat log.g4
RC=0
```

**五道门全 `RC=0`，到这里才算"能跑"。** 抽查两个值，确认产物真的是场数据：

```
$ grep -E 'cells:|Mesh OK' log.checkMesh
    cells:            400
Mesh OK.
$ foamDictionary 10/U -entry internalField -value | head -1
nonuniform List<vector>
```

`G2` 判的是 `log.checkMesh` 里有没有 `Mesh OK.` 这一行，**不是 checkMesh 的退出码**——
网格不合格时 checkMesh 也可能退 0，而 `Mesh OK.` 会消失。

---

## 9 一次真实失败与修法（照抄本文最容易踩的坑）

想让一个算例"回到干净状态"时，很容易写出 `rm -rf [0-9]*`。**它连 `0/` 一起删**——因为 `0`
也是数字开头。本例实测：

```bash
cp -a cavity-01 cavity-02 && cd cavity-02
rm -rf [0-9]*                 # 陷阱：0/ 也没了
bash "$HARNESS/scripts/run_case.sh" --case "$WORK/cavity-02" --mode full --timeout 600
```

真实输出（`RC=20`）：

```
run_case: 短跑 foamRun 失败（退出码 20），见 $WORK/cavity-02/log.shortRun
```

`log.shortRun` 里的原因是（逐字节选）：

```

--> FOAM FATAL ERROR: 
cannot find file "$WORK/cavity-02/0/p"

    From function virtual Foam::autoPtr<Foam::ISstream> Foam::fileOperations::uncollatedFileOperation::readStream(Foam::regIOobject&, const Foam::fileName&, const Foam::word&, bool) const
    in file global/fileOperations/uncollatedFileOperation/uncollatedFileOperation.C at line 538.

FOAM exiting
```

此时再跑后置门禁，`RC=3`（G3/G4 红，G2 仍绿——网格日志是旧的）：

```
G2 RC=0  $WORK/cavity-02/log.g2  (G2B=none)
G3 RC=1  $WORK/cavity-02/log.g3
G4 RC=1  $WORK/cavity-02/log.g4
G3 失败项:
  log.shortRun 含 'FOAM FATAL'：--> FOAM FATAL ERROR: 
G4 失败项:
  末时刻目录不存在：$WORK/cavity-02 下没有 0 以外的数字目录（求解没产出结果）
```

**修法**：不要删 `0/`。重新派生一个（步骤 4，换 `--dest`），或从派生源把 `0/` 拷回来：

```bash
cp -a "$FOAM_TUTORIALS/incompressibleFluid/cavity/0" "$WORK/cavity-02/0"
```

这个失败里最值得记的一点：**G2 依然是绿的**。门是各判各的，所以别看到某一道门绿就以为整体没问题——
看总退出码（`RC=3` 才是结论）。

---

## 10 一页清单

```bash
source /opt/openfoam13/etc/bashrc
export HARNESS=<包根目录>; export WORK=$HOME/foam-work; mkdir -p "$WORK"

bash "$HARNESS/scripts/preflight.sh"                                     # 期望 RC=0
python3 "$HARNESS/scripts/parse_requirement.py" --text "<需求原话>" --out "$WORK/c.spec.json"
bash "$HARNESS/scripts/find_template.sh" --keyword <词> --limit 20        # 期望 RC=0，FOUND>0
bash "$HARNESS/scripts/new_case.sh" --source <教程相对路径> --dest "$WORK/c-01" --spec "$WORK/c.spec.json"
# 改字典：foamDictionary <文件> -entry <键> -set <值>，每条后跟一条 -value 回读
bash "$HARNESS/scripts/verify_case.sh" --stage pre  --case "$WORK/c-01"   # 期望 RC=0
bash "$HARNESS/scripts/run_case.sh"    --case "$WORK/c-01" --mode full --timeout 1800
bash "$HARNESS/scripts/verify_case.sh" --stage post --case "$WORK/c-01"   # 期望 RC=0
```

任何一步不是 `RC=0` → 回 `SKILL.md` §3/§4 查那个码，或按 §5 停下问人。
