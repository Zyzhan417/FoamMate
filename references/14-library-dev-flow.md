# 14 · 二次开发流程：系统子库 → 用户副本 → 改 Make → 编译 → 加载

> 本文是二次开发流程（`S0`–`S6`）与四道门（`V1`–`V4`）的**唯一写值处**。
> `AGENTS.md` R15 只写规则并指到本文；`release/SKILL.md` §11 只写命令与退出码。
> 建立于 2026-10-31（在 T0 spike 实测之后写；本文出现的每个数字都来自本机实测，命令就写在它旁边）。
> 源码行一律来自 `/opt/openfoam13`（R1 配方②/③），第三方代码不作源码证据（R9）。

---

## 1 边界：这条流程做什么

一句话：把一个**系统自带的子库**复制到 `$WM_PROJECT_USER_DIR` 下，改写它的 `Make/`，
用 `wmake libso` 编出 `lib<名>.so`，再证明这个 `.so` 能被 OpenFOAM 真的 `dlopen` 进来。

| 动作 | 谁做 | 是否可判定 |
|---|---|---|
| 判定「真的需要二次开发」 | agent（R1 配方⑤） | 是（能找到现成 type 就不该做） |
| 选派生源、`cp -a` 副本 | 脚本 | 是（`V1`） |
| 改 `Make/files` 的 `LIB` 行、`Make/options` 的外部相对 `-I` | 脚本 | 是（`V1`，改写前后字节都留证） |
| 改 `.C` / `.H`（真正的二次开发） | agent / 人 | 只能**事后**判（`V2` 越界检查），判不了「改得对不对」 |
| 编译 | 脚本调 `wmake` | 是（`V3`） |
| 证明库能被加载 | 脚本调 `foamRun` | 是（`V4`，判据见 §4.4） |

**不做**：不生成 C++ 代码（正则改 C++ 会产出「能编译但语义错」的库，那种库门禁全绿，比编译失败贵得多）。
`scripts/dev_lib.py` 只做上表里「脚本」那四行。

---

## 2 为什么 `cp -r` 之后 `wmake` 会失败（实测）

### 2.1 两个样本的 `Make/options` 对照

要改的那份（`multiphaseEuler/populationBalance`，47 个 `.C`）：

```text
/opt/openfoam13/applications/modules/multiphaseEuler/populationBalance/Make/options:1  EXE_INC = \
/opt/openfoam13/applications/modules/multiphaseEuler/populationBalance/Make/options:2      -I../phaseSystem/lnInclude \
/opt/openfoam13/applications/modules/multiphaseEuler/populationBalance/Make/options:3      -I$(LIB_SRC)/meshTools/lnInclude \
```

不该改的那份（`fvAgglomerationMethods/pairPatchAgglomeration`，1 个 `.C`）：全部用 `$(LIB_SRC)`。

```text
/opt/openfoam13/src/fvAgglomerationMethods/pairPatchAgglomeration/Make/options:1  EXE_INC = \
/opt/openfoam13/src/fvAgglomerationMethods/pairPatchAgglomeration/Make/options:2      -I$(LIB_SRC)/finiteVolume/lnInclude \
/opt/openfoam13/src/fvAgglomerationMethods/pairPatchAgglomeration/Make/options:3      -I$(LIB_SRC)/meshTools/lnInclude \
/opt/openfoam13/src/fvAgglomerationMethods/pairPatchAgglomeration/Make/options:4      -I$(LIB_SRC)/OpenFOAM/lnInclude
```

两份的差别只有一处，但性质不同：

- `$(LIB_SRC)` 是 **make 变量**，由 `wmake` 在场展开成 `$WM_PROJECT_DIR/src`，副本搬到哪都指向系统树。
- `../phaseSystem/lnInclude` 是**相对当前目录的路径**。在系统树里，`populationBalance` 的上一级是
  `multiphaseEuler/`，那里确实有 `phaseSystem/lnInclude`（`ls -d /opt/openfoam13/applications/modules/multiphaseEuler/phaseSystem/lnInclude` 有输出）。
  复制到 `$WM_PROJECT_USER_DIR/src/<名>` 之后，上一级变成 `$WM_PROJECT_USER_DIR/src/`，那里没有 `phaseSystem/`。

### 2.2 实测：不改 `-I`，`wmake` 在第 4 行日志就失败

命令与产物（2026-10-31 00:03 CST，`$W=$TMPDIR/t0`；`$TMPDIR` 是本机临时目录，与仓库树无关）：

```bash
cp -a /opt/openfoam13/applications/modules/multiphaseEuler/populationBalance "$W/pb"
sed -i 's|^LIB.*|LIB = $(FOAM_USER_LIBBIN)/libpopulationBalanceMod|' "$W/pb/Make/files"
( cd "$W/pb" && FOAM_USER_LIBBIN="$W/lib3" wmake -j 2 libso ) > "$W/log.pb" 2>&1
```

结果：`rc=2`，墙钟 2 s，`grep -c 'error:' "$W/log.pb"` = **3**，`$W/lib3` 为空。`log.pb` 逐字：

```text
log.pb:2  wmake libso .
log.pb:3  wmakeLnIncludeAll: running wmakeLnInclude on dependent libraries:
log.pb:4      wmakeLnInclude error: base directory ../phaseSystem/ does not exist
log.pb:8  could not open file phaseSystem.H for source file populationBalanceSystem/populationBalanceSystem.C due to No such file or directory
log.pb:142  diameterModels/velocityGroup/velocityGroup.H:68:10: fatal error: diameterModel.H: No such file or directory
```

注意失败点比「找不到 `phaseSystem.H`」更早：`wmakeLnInclude` 在**编译前**就要进那个相对目录，
第 4 行就报 `base directory ../phaseSystem/ does not exist`。所以「拷过来直接编译」不是慢一步，
是第一步就走不下去。

### 2.3 实测：只改这一条 `-I` 就够

同一份副本，只把 `Make/options` 第 2 行换成绝对路径：

```bash
sed -i 's|^\( *\)-I\.\./phaseSystem/lnInclude|    -I/opt/openfoam13/applications/modules/multiphaseEuler/phaseSystem/lnInclude|' "$W/pb2/Make/options"
( cd "$W/pb2" && FOAM_USER_LIBBIN="$W/lib4" wmake -j 4 libso ) > "$W/log.pb2" 2>&1
```

结果：`rc=0`，墙钟 **61 s**，`grep -c 'error:' "$W/log.pb2"` = **0**，
`$W/lib4/libpopulationBalanceMod.so` 存在（3022968 字节）。

这份 `Make/options` 共 19 行、`-I` 起头的 15 条，其中**只有 1 条**是相对路径：

```bash
grep -n '^\s*-I' /opt/openfoam13/applications/modules/multiphaseEuler/populationBalance/Make/options | grep -v '\$'
# → 2:    -I../phaseSystem/lnInclude \
```

### 2.4 由此得到的两条规则

1. 相对 `-I` 必须在副本里被改写，否则编译在第一步失败。改写规则见 §5。
2. 「拷过来能编过」不是常态，是**改写后的结果**。`wmake` 的成功本身不能证明派生正确（`V1` 管这件事）。

---

## 3 步骤：`S0`–`S6`

`S` 是动作，`V` 是门。**判据只写在 `V` 上**（§4），`S` 只写做什么、谁做、失败退哪个码。

| 步骤 | 动作 | 谁做 | 失败 → 退出码 |
|---|---|---|---|
| S0 | 判定是否真的需要二次开发：先按 R1 配方⑤ 找现成 type（`ls $FOAM_SRC/.../derived`、`grep -rn addToRunTimeSelectionTable`）。现成能用就不做 | agent | 不是门；这是判断 |
| S1 | 选派生源：`$FOAM_APP` 或 `$FOAM_SRC` 下**带 `Make/files` 且 `Make/files` 里有 `^LIB`** 的最小子库；记录 `LIB` 原值 | agent | 选到不可编译目录 → `85` |
| S2 | `dev_lib.py --stage prepare`：`cp -a` 到 `$WM_PROJECT_USER_DIR/src/<名>`，改写 `Make/files` 的 `LIB` 行与 `Make/options` 的外部相对 `-I`，写 `dev.meta`（逐文件 sha256） | 脚本 | `85` |
| S3 | 改 `.C` / `.H`，且只改 `dev.meta.allowed_files` 声明过的文件 | agent / 人 | 越界的后果在 S4 才出现 |
| S4 | `dev_lib.py --stage check`：当前树与 `dev.meta.manifest` 比对 | 脚本 | `86` |
| S5 | `dev_lib.py --stage build`：`wmake -j N libso`，日志 `log.wmake`，产物核对 | 脚本 | `87` |
| S6 | `dev_lib.py --stage verify`：`dlopen` 证明 + 系统树未被改 | 脚本 | `88` / `89` |
| S6b | 算例侧：`controlDict` 的 `libs` 加 `lib<名>.so`，再把 type 改成新名，然后回到既有 G1–G4 | 既有模块 D/E | `1`–`5` |

两条与顺序有关的实测坑（都会让人以为「工具坏了」）：

1. **`wmake` 的选项必须写在目标前面**。`wmake libso -j 4` 会退 1，日志逐字
   `wmake error: could not change to directory '-j'`（实测 2026-10-31 00:01 CST）。
   正确形态是 `wmake -j 4 libso`。依据：`/opt/openfoam13/wmake/wmake:72` 的 `Usage: $Script [OPTION] [dir]`
   与 `:137`–`:195` 的选项解析循环（遇到第一个非 `-` 开头的参数就 `break`）。
2. **`-libs` 的值是 `fileNameList`**（`/opt/openfoam13/src/OpenFOAM/global/argList/argList.C:463`
   `libs.open(fileNameList((IStringStream(argv[argi+1]))()));`），所以里面的库名**必须带引号**。
   三种写法的实测差别见 §4.4 的表；写错形态时 `foamRun` 退 1 且**不会**报 `dlopen error`，
   于是 `V4` 会把一个好库判红。

---

## 4 四道门 `V1`–`V4`

### 4.1 V1 · 派生完整

**判据**：副本里每个普通文件的 `sha256` 与源文件一致，**除** `Make/files` 与 `Make/options`
这两份被改写过的（改写前后的字节都记进 `dev.meta`）。符号链接只记指向、不跟随。
`prepare` 结束即判；不过 → `85`，并**删掉 dest**（不留半成品）。

**为什么**：`cp -a` 之后「看起来一样」不等于一样；而后面 `V2` 的全部意义都建立在
「清单是开工时的真值」之上——清单本身错了，越界检查就是假绿。

### 4.2 V2 · 改动在声明范围内

**判据**：`sha256(当前树)` 与 `dev.meta.manifest` 的差集（`modified` / `added` / `deleted`）
必须被 `allowed_files`（glob，`fnmatch` 语义，`*` 跨 `/`）全覆盖。任一越界 → `86`，
payload 里列出越界文件。`dev.meta` 自身被改动也判 `86`（防「改判据绕过判据」，同 `bench` 冻结清单的理由）。
判据的载体是 `dev.meta` 的第 8 键 `meta_self_sha256`（对其余 7 键的规范序列化取 sha256）：
`manifest` 按定义不含 `dev.meta` 自己，所以没有这个封印就没有任何地方能记它的哈希，那道门不成立。

**为什么**：`S3` 是本流程里唯一「人写代码」的步骤，也是唯一无法事后判断对错的地方。
能判的只有范围：**「改了不该改的文件」是可判定的**，「改得对不对」不是。

### 4.3 V3 · 构建成功且产物在位

**判据**（三条全部满足才算过，否则 `87`）：

1. `wmake` 退出码 0；
2. `log.wmake` 里 `error:` 计数为 **0**；
3. `$FOAM_USER_LIBBIN/lib<名>.so` 存在、是普通文件，且 sha256 与构建后记录一致。

**为什么 rc 不够**：`wmake` 会留下上一次的 `.so`，日志里带 `error:` 也可能退 0（G2 同口径：
「不信退出码，只信日志行」）。反方向也实测到了：§3 的 `wmake libso -j 4` 退 1，日志里恰好有一行
`wmake error: ...` 被 `error:` 计数抓到——**rc 与 `error:` 计数各自都不完备，两条一起才闭合**。

### 4.4 V4 · 可加载 + 系统树干净

#### 命令形态（这一步的判据是实测标定的，不是设计出来的）

**唯一的加载证明命令**（逐字，注意 `-libs` 后面的引号与括号都在引号内）：

```bash
foamRun -libs '("lib<名>.so")' -help
```

**判据**：合并 stdout+stderr 后 `grep -c 'dlopen error'` = **0**。
`-help` 会在打印用法**之前**加载库（实测：坏库名的 `dlopen error` 出现在 `Usage:` 之前），
所以这条命令真的能当加载证明用。

#### 标定表（2026-10-31 00:02–00:03 CST 实测，`$W=$TMPDIR/t0`）

| 写法 | 好库名 | 坏库名 | 能否区分好坏 |
|---|---|---|---|
| `-libs "libX.so"` | rc=1，`dlopen`=0 | rc=1，`dlopen`=0 | **不能**（`FOAM FATAL IO ERROR: incorrect first token, expected <int> or '(', found on line 0 the word 'libX.so'`） |
| `-libs "(libX.so)"` | rc=1，`dlopen`=0 | rc=1，`dlopen`=0 | **不能**（`wrong token type - expected string`） |
| `-libs '("libX.so")'` | **rc=0，`dlopen`=0** | **rc=0，`dlopen`=1** | 能（只有 `dlopen` 计数不同） |

第二条结论比第一条更重要：

- **退出码在这条命令上不是判据**。好库名与坏库名**都退 0**——坏库名只打印
  `--> FOAM Warning :` 与 `could not load "..."`，然后照常打印用法。若 `V4` 判「退出 0」，
  它恒绿，等于没有这道门。判据只能是 `dlopen error` 计数。
- 前两种错误形态会**把好库判红**（rc=1 且没有 `dlopen error`）。所以命令形态必须照抄，
  不许「顺手把引号去掉」。

坏库名的逐字输出（`$W/bad4`）：

```text
bad4:1  --> FOAM Warning : 
bad4:2      From function void* Foam::dlOpen(const fileName&, bool)
bad4:3      in file POSIX.C at line 1247
bad4:4      dlopen error : libdefinitelynotexist.so: cannot open shared object file: No such file or directory
bad4:5  --> FOAM Warning : 
bad4:8      could not load "libdefinitelynotexist.so"
```

好库名的逐字输出（`$W/ok4`，第 1 行为空行，之后就是用法正文）：

```text
ok4:2  Usage: foamRun [OPTIONS]
ok4:3  options:
ok4:4    -case <dir>       specify alternate case directory, default is the cwd
```

旁证：`foamRun -help` 打出来的用法里，这条选项本身就是带引号的形态
（`bad4:17` 逐字 `  -libs '("lib1.so" ... "libN.so")'`）。源码同一件事：
`/opt/openfoam13/src/OpenFOAM/global/argList/argList.C:92` 逐字 `"'(\\"lib1.so\\" ... \\"libN.so\\")'",`。

#### 变异自证：`dlopen` 计数确实在测「加载」

把同一个**好**库名保留，只把它所在的目录从 `LD_LIBRARY_PATH` 里去掉：

```bash
LD_LIBRARY_PATH=$(echo "$LD_LIBRARY_PATH" | tr ':' '\n' | grep -v "scratch/t0/lib" | paste -sd: -) \
  foamRun -libs '("libpairPatchAgglomerationMod.so")' -help   # → rc=0，dlopen=1
```

退 0 但 `dlopen`=1。这证明计数反映的是「有没有真加载」，不是「参数里有没有这个字符串」。
推论（对使用者的实际含义）：`.so` 必须在 `LD_LIBRARY_PATH` 上。
`$FOAM_USER_LIBBIN` 本来就在里面（`echo "$LD_LIBRARY_PATH" | tr ':' '\n' | grep -n "$FOAM_USER_LIBBIN"`
实测命中第 7 项），所以正常流程不需要额外设置——**但把 `.so` 挪到别处就会让这道门变红**。

#### 系统树未改（R2 的一半）

**判据**：`find /opt/openfoam13/src /opt/openfoam13/applications -newer /opt/openfoam13/build-stamp -type f` 的文件数为 **0**；
非 0 → `89` 并列出文件。基线存在：`build-stamp`（0 字节，mtime 2026-04-07）。
本次实测该命令输出 **0** 条。

---

## 5 `Make` 改写规则（可判定，实现照抄）

只碰两处，其它行一字不动。

### 5.1 `Make/files` 的 `LIB` 行

1. 找**第一条**匹配 `^LIB\s*=.*$` 的行，整行替换为 `LIB = $(FOAM_USER_LIBBIN)/lib<名>`。
2. 没有 `LIB` 行 → 把这一行插到文件首行（后跟一个空行）。
3. 原行文本记进 `dev.meta`（`V1` 要它证明「只改了这两份」）。

样本原值（改写前）：`/opt/openfoam13/src/fvAgglomerationMethods/pairPatchAgglomeration/Make/files:3`
逐字 `LIB = $(FOAM_LIBBIN)/libpairPatchAgglomeration`；
`/opt/openfoam13/applications/modules/multiphaseEuler/populationBalance/Make/files:64`
逐字 `LIB = $(FOAM_LIBBIN)/libpopulationBalance`。

### 5.2 `Make/options` 的 `-I`

对每一条形如 `<缩进>-I<路径><尾部空白或 \>` 的行，按下列顺序判定：

| 情形 | 处理 |
|---|---|
| 路径含 `$`（make 变量，如 `$(LIB_SRC)`） | **原样** |
| 路径是绝对路径（`/...`） | **原样** |
| 相对路径，且 `(src_root / 路径).resolve()` 仍在 `src_root` 内 | **原样**（副本内相对，搬过去仍成立） |
| 相对路径，解析到 `src_root` 之外，且目标目录存在 | 改成解析后的**绝对路径** |
| 相对路径，解析到 `src_root` 之外，目标目录不存在 | **退 `85`**（不猜、不改半成品：先把 dest 删掉） |

缩进与行尾的 `\` 必须原样保留——`EXE_INC` 靠行尾 `\` 连成一条，删掉 `\` 会让后续行变成独立语句，
`wmake` 的报错会指向完全无关的地方。

### 5.3 不许碰的

`EXE_INC` / `LIB_LIBS` / `EXE_LIBS` 的赋值本身、变量定义、注释、行序、空行、行尾空白。
判据来自 `V1`：除这两份文件外逐文件 sha256 必须与源一致。

---

## 6 不保证什么

1. **不保证物理正确**。编译通过 + 能加载 + 算例门禁通过，三件事都不涉及「结果对不对」。
   模型改错（比如系数漏了一个量纲、增长率符号反了）会一路绿到底。
2. **不保证新 type 被算例选中**。`libs` 里加载了库、`type` 拼对了，`OpenFOAM` 才会用你改的那份；
   这条由 `S6b` 的既有 G1–G4 与断言层管，不由本文的四道门管。
3. **不生成 C++ 代码**。`S3` 的改动由 agent / 人做，脚本只在事后核对范围（`V2`）。
4. **不改系统树**。`$WM_PROJECT_DIR` 只读引用头文件（R2）；`V4` 的后半段专门判这件事。
5. **不装第二份 OpenFOAM**（R11）。派生副本依赖系统的 `lnInclude` 与 `libbin`，所以副本不能脱离本机 v13 单独存在。

---

## 7 本机实测成本（2026-10-31 CST）

环境：`source /opt/openfoam13/etc/bashrc`；工作目录 `$W=$TMPDIR/t0`（仓库外，删掉不影响任何门）；
`wmake` 取 PATH 上的 `/opt/openfoam13/wmake/wmake`。墙钟用 `date +%s` 前后差值。

| 对象 | 规模 | 动作 | 墙钟 | 产物 | `error:` 计数 |
|---|---|---|---|---|---|
| `pairPatchAgglomeration` | 1 个 `.C`（`Make/files:1`） | `wmake -j 4 libso` | **4 s**（首次）/ **3 s**（换名重建一次） | `libpairPatchAgglomerationMod.so`，128576 字节 | 0 |
| `populationBalance` | 47 个 `.C`（`grep -c '\.C' …/Make/files`）、目录 1.1 MB（`du -sh`） | 只改 `LIB`，`wmake -j 2 libso` | 2 s（未编译即失败） | 无 | 3 |
| `populationBalance` | 同上 | 改 `LIB` + 1 条 `-I` 改绝对，`wmake -j 4 libso` | **61 s** | `libpopulationBalanceMod.so`，3022968 字节 | 0 |

加载证明：`foamRun -libs '("…so")' -help`，好库名 `rc=0 / dlopen=0`，坏库名 `rc=0 / dlopen=1`（§4.4）。
系统树检查：`find /opt/openfoam13/src /opt/openfoam13/applications -newer /opt/openfoam13/build-stamp -type f` → 0 条。
真实的 `$FOAM_USER_LIBBIN` 在所有编译前后都是 0 个条目（`ls -A … | wc -l`），即
`FOAM_USER_LIBBIN=<临时目录>` 覆盖有效、spike 没污染用户库。

**成本判读**（给 L2 用）：1 个 `.C` 的最小库 **3–4 s**，可以放进契约层每次都跑。
真实模型（47 个 `.C`）**61 s**，超出「每次全量跑」的预算——L2 选 `pairPatchAgglomeration` 这类最小库是对的，
不要拿 `populationBalance` 当 L2 的样本。

---

## 8 退出码 ↔ 本文哪一节

| 码 | 含义 | 判据在本文哪 | 由哪个 stage 抛 |
|---|---|---|---|
| `0` | 全过 | — | 任一 stage |
| `85` | 规格不合法（源不可编译 / dest 已存在 / 库名冲突 / `-I` 解析不了） | §3 S1·S2、§5.2 末行 | `prepare` |
| `86` | 改动越界（`allowed_files` 之外） | §4.2 | `check` |
| `87` | 构建失败 / 日志有 `error:` / `.so` 不在位 | §4.3 | `build` |
| `88` | 加载证明失败（`dlopen error` 计数非 0） | §4.4 | `verify` |
| `89` | 系统树被改动（R2） | §4.4 末段 | `verify` |
| `64` | 用法错误（全仓统一） | — | 任一 stage |

---

## 9 本文与其它文档的分工

| 信息 | 在哪 |
|---|---|
| 「只能派生 + 最小差异」这条规则本身、`dev.meta.allowed_files` 的义务 | `AGENTS.md` R15 |
| 命令、参数、退出码的对外语义 | `release/SKILL.md` §11（随 `dev_lib.py` 一起落地） |
| 本文该在哪份文档里被引用 | `references/13-maintenance.md` §2 |
| 当前做到哪一步、还剩什么 | `STATUS.md` N1 / N4 / N17 |
