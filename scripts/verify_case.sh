#!/usr/bin/env bash
# verify_case.sh — E 层门禁判定，两个入口（D4）：
#   --stage pre   判 G1 结构 + G5 范围，纯文件检查，**零 OpenFOAM 命令**
#                 （不 blockMesh / 不 checkMesh / 不 foamRun / 不 source bashrc）
#   --stage post  判 G2 网格 + G3 短跑 + G4 产物，另出 G2b 诊断信号。
#                 **只解析日志、不跑求解**：输入是模块 D（scripts/run_case.sh）写的
#                 log.checkMesh / log.shortRun，缺省日志目录 = --case。
#
# 用法：
#   bash scripts/verify_case.sh --stage pre --case <dir> [--allowed <glob>]... [--log <dir>]
#
#   参数
#     --stage  {pre,post}     必填
#     --case   <dir>          必填。两种布局都认：
#                               ① run 目录：<dir>/case 是 case 树、<dir>/base 是基线、
#                                  <dir>/case.meta 是元数据、日志写 <dir>/log.gN
#                                  （= bench/preregistration.md:387 的 run<k>/ 布局）
#                               ② 直接指向 case 树（<dir>/system 存在且 <dir>/case 不存在）
#     --allowed <glob>        可重复；也可逗号分隔。未传时读 <dir>/case.meta 的
#                             allowed_files（JSON 数组）。glob 语义用 fnmatch（`*` 跨 `/`），
#                             所以 `system/*` 能匹配 `system/a/b`。
#     --log    <dir>          post 用：日志的读写目录，缺省 = --case。pre 阶段不用
#                             （pre 的日志固定写 <dir>）；接受但忽略，避免接口分叉。
#
# 退出码（D6，references/09-architecture-and-test-plan.md:218）：
#   0 全过 / 1 G1 / 2 G2 / 3 G3 / 4 G4 / 5 G5。**只报第一个失败的门**（按门号取最小 ⇒ G1 优先）。
#   64 用法错误（缺 --stage/--case、未知参数、门名非法）——不属于 D6 语义，别与 1..5 混。
#
# 日志（D7，references/09-architecture-and-test-plan.md:210）——与 bench/judge.py 的唯一接口：
#   log.g1 / log.g5  第 1 行 `RC=0|1`；第 2 行留空（G2B= 只属于 log.g2）；
#                    第 3 行起写失败串（人看，judge 不解析）。
#   log.g2 / log.g3 / log.g4  同上，但 log.g2 的第 2 行是 `G2B=<none|soft:N|hard:N|unknown>`。
#   **pre 绝不写 log.g2..log.g4，post 绝不写 log.g1/log.g5**——各写各的门。
#   一批门都判、都写日志（judge 同时读多个 RC），只是退出码只反映最小的那个失败门。
#   post 阶段**无论哪个门不过，三个日志都要写**：judge 需要三个门才能归约，
#   缺一个就会把 fail 降级成 malformed（bench/judge.py:127-141）。
#
# 为什么 G1 要判 patch 集合（P4a，references/01-landscape.md:170）：三字典齐全但
# `0/U` 的 patch 名与 polyMesh 实际 patch 不一致时，checkMesh 会过、solver 才 FATAL；
# 把这一项前移到 pre，能在零 OpenFOAM 的情况下抓住一类真实的失败。
# boundary 文件不存在 ⇒ 该子项 SKIP（不能当通过：log 里逐字写 SKIP，judge 仍按 RC 读门）。
#
# 纪律（同 verify_references.sh，踩过的坑别改回去）：
#   - 不用 set -e：中段有预期非零的检查（git diff --no-index 有差异就返回 1）。
#   - 不接管道判红绿：每项自己算、自己打印，`0 violations` 与 `扫到 0 个对象` 必须能区分。
#   - 只读：本脚本不建/改/删 case 里的任何文件，唯一写操作是 <dir>/log.g1、log.g5。

set -uo pipefail

SELF="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SELF/.." && pwd)"

usage() {
  cat <<'EOF'
用法: bash scripts/verify_case.sh --stage pre|post --case <dir> [--allowed <glob>]... [--log <dir>]

  --stage pre   判 G1 结构 + G5 范围（纯文件检查，零 OpenFOAM）
  --stage post  判 G2 网格 + G3 短跑 + G4 产物（只解析 log.checkMesh / log.shortRun）
  --case  <dir> run 目录（内含 case/、base/、case.meta）或直接是 case 树
  --allowed <glob>  可重复/逗号分隔；缺省读 <dir>/case.meta 的 allowed_files（仅 pre）
  --log   <dir>     日志读写目录，缺省 = --case（仅 post）
退出码: 0 全过 / 1 G1 / 2 G2 / 3 G3 / 4 G4 / 5 G5 / 64 用法错误
EOF
}

STAGE=""
CASE_DIR=""
ALLOWED_GLOBS=()
# --log 在 post 分支里单独解析（保留原始参数）：上面的循环对 --log 只做 shift，
# 这样 pre 的参数处理路径逐字不变，post 的日志目录也不会与 pre 的行为纠缠。
ORIG_ARGS=("$@")
while [ $# -gt 0 ]; do
  case "$1" in
    --stage)   STAGE="${2:-}"; shift 2 ;;
    --case)    CASE_DIR="${2:-}"; shift 2 ;;
    --log)     shift 2 ;;                        # pre 不用；接受以保持接口一致
    --allowed)
      _v="${2:-}"; shift 2
      IFS=',' read -r -a _parts <<< "$_v"
      for _p in "${_parts[@]}"; do
        [ -n "$_p" ] && ALLOWED_GLOBS+=("$_p")
      done
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "verify_case.sh: 未知参数 '$1'" >&2; usage >&2; exit 64 ;;
  esac
done

case "$STAGE" in
  pre)  ;;
  post) : ;;                       # 判 G2/G3/G4 + G2b；实现见下面的 post 派发块
  "")   echo "verify_case.sh: 缺少 --stage（可选 pre|post）" >&2; usage >&2; exit 64 ;;
  *)    echo "verify_case.sh: 非法 --stage '$STAGE'（可选 pre|post）" >&2; exit 64 ;;
esac

if [ -z "$CASE_DIR" ]; then
  echo "verify_case.sh: 缺少 --case <dir>" >&2; usage >&2; exit 64
fi
if [ ! -d "$CASE_DIR" ]; then
  echo "verify_case.sh: --case '$CASE_DIR' 不是目录" >&2; exit 64
fi

# case 树定位：优先 <dir>/case（prereg:387 的 run 目录布局），否则认为 --case 直接是 case 树。
if [ -d "$CASE_DIR/case" ]; then
  CASE_ROOT="$CASE_DIR/case"
else
  CASE_ROOT="$CASE_DIR"
fi
# ---- 日志目录：--log 缺省 = --case（两个 stage 共用）。
# 为什么 pre 也认 --log：prereg §12 把 log.g* 放在 **run 根**（与 case/ 同级），
# 而 --case 指向 run/case。若 pre 把 log.g1 写进 case 树，judge 读 run/log.g1 会读空
# → 判 malformed。2026-10-28 端到端集成测试抓到的正是这一处。
LOG_DIR=""
_i=0
while [ "$_i" -lt "${#ORIG_ARGS[@]}" ]; do
  if [ "${ORIG_ARGS[$_i]}" = "--log" ]; then
    LOG_DIR="${ORIG_ARGS[$((_i + 1))]:-}"
  fi
  _i=$((_i + 1))
done
[ -n "$LOG_DIR" ] || LOG_DIR="$CASE_DIR"
if [ ! -d "$LOG_DIR" ]; then
  mkdir -p "$LOG_DIR" 2>/dev/null \
    || { echo "verify_case.sh: 无法创建 --log 目录 '$LOG_DIR'" >&2; exit 64; }
fi

LOG_G1="$LOG_DIR/log.g1"
LOG_G5="$LOG_DIR/log.g5"

# ---- case.meta 的两个合法位置（按优先级）：case 树内（C 的默认产出）、run 根（prereg §12）。
# 两处都有时取 case 树内的，并在 stderr 提示——不静默选一个。
if [ -f "$CASE_DIR/case.meta" ]; then
  META="$CASE_DIR/case.meta"
  [ -f "$LOG_DIR/case.meta" ] && \
    echo "verify_case.sh: 注意 case.meta 同时存在于 case 树与 run 根，取 case 树内那份" >&2
elif [ -f "$LOG_DIR/case.meta" ]; then
  META="$LOG_DIR/case.meta"
else
  META="$CASE_DIR/case.meta"      # 都不存在：保留原路径，让报错信息指向最可能的那个
fi

# write_log <path> <rc> [失败串...]  —— D7 格式：第1行 RC=，第2行空，第3行起自由文本
write_log() {
  local p="$1" rc="$2"; shift 2
  {
    printf 'RC=%d\n' "$rc"
    printf '\n'
    if [ "$#" -gt 0 ]; then printf '%s\n' "$@"; fi
  } > "$p"
}

# =============================================================== post 派发
# E-full（--stage post）：判 G2 网格 / G3 短跑 / G4 产物 + G2b 诊断。
# 职责边界：**只解析日志，绝不跑求解**（日志由模块 D 的 run_case.sh 产生）。
# 与 G1/G5 完全分开：post 不写 log.g1/log.g5，也不复用它们的判据；
# 反过来 pre 也不会走到这里（下面的 `exit` 保证 post 跑完就结束）。
if [ "$STAGE" = "post" ]; then

  # ---- 日志目录 LOG_DIR 已在 stage 分派之前算好（pre/post 共用），此处不再重复解析。

  # ------------------------------------------------------------- G2 网格
  # 判据：log.checkMesh 含 `Mesh OK.`。**绝不看 checkMesh 的退出码**（D18）：
  # 实测它对退化网格（`Failed 1 mesh checks.`、无 `Mesh OK.`）依然退出 0，
  # 因为 $FOAM_SRC/functionObjects/utilities/checkMesh/checkMesh.C:180 的
  # `return nFailedChecks == 0` 是函数对象 execute() 的返回值，不是进程退出码。
  # 看退出码 ⇒ 所有不合格网格都会放行。
  G2_ERR=()
  G2B="unknown"
  CM_LOG="$LOG_DIR/log.checkMesh"
  if [ ! -f "$CM_LOG" ]; then
    rc_g2=1
    G2_ERR+=("MISSING log.checkMesh（$CM_LOG）：网格日志缺失 ⇒ 未判定，不是通过")
  else
    # G2b 的 N：以 `***` 开头的行数（诊断信号，不进 RC/退出码）
    _n_star=$(grep -cE '^[[:space:]]*\*\*\*' "$CM_LOG" 2>/dev/null)
    case "$_n_star" in ''|*[!0-9]*) _n_star=0 ;; esac
    if grep -q 'Mesh OK\.' "$CM_LOG"; then
      rc_g2=0
      if [ "$_n_star" -gt 0 ]; then G2B="soft:$_n_star"; else G2B="none"; fi
    else
      rc_g2=1
      # 无 `Mesh OK.` 时按有没有 `***` 分 hard:N / hard:0（后者=网格根本没建/日志被截断）
      if [ "$_n_star" -gt 0 ]; then G2B="hard:$_n_star"; else G2B="hard:0"; fi
      G2_ERR+=("log.checkMesh 不含 'Mesh OK.'（'***' 行 ${_n_star} 条）⇒ 网格门不过")
      _failed=$(grep -m1 -E '^[[:space:]]*Failed' "$CM_LOG" 2>/dev/null)
      [ -n "$_failed" ] && G2_ERR+=("checkMesh 原话：$_failed")
    fi
  fi
  {
    printf 'RC=%d\n' "$rc_g2"
    printf 'G2B=%s\n' "$G2B"                       # D7：第 2 行只属于 log.g2
    if [ "${#G2_ERR[@]}" -gt 0 ]; then printf '%s\n' "${G2_ERR[@]}"; fi
  } > "$LOG_DIR/log.g2"

  # ------------------------------------------------------------- G3 短跑
  # 判据：log.shortRun 存在且非空、不含 `FOAM FATAL`、含 `End`。
  G3_ERR=()
  SR_LOG="$LOG_DIR/log.shortRun"
  if [ ! -f "$SR_LOG" ]; then
    rc_g3=1
    G3_ERR+=("MISSING log.shortRun（$SR_LOG）：短跑日志缺失 ⇒ 未判定，不是通过")
  elif [ ! -s "$SR_LOG" ]; then
    rc_g3=1
    G3_ERR+=("EMPTY log.shortRun（$SR_LOG）：空文件 ⇒ 未判定，不是通过")
  elif grep -q 'FOAM FATAL' "$SR_LOG"; then
    rc_g3=1
    G3_ERR+=("log.shortRun 含 'FOAM FATAL'：$(grep -m1 'FOAM FATAL' "$SR_LOG")")
  elif ! grep -q 'End' "$SR_LOG"; then
    rc_g3=1
    G3_ERR+=("log.shortRun 不含 'End'：求解没有走到正常结束")
  else
    rc_g3=0
  fi
  write_log "$LOG_DIR/log.g3" "$rc_g3" ${G3_ERR[@]+"${G3_ERR[@]}"}

  # ------------------------------------------------------------- G4 产物
  # 判据三条同时成立才 RC=0：
  #   ① 末时刻目录存在（case 下名字可解析为 float 的目录里最大者，排除 0）
  #   ② 其中至少一个场文件 `foamDictionary <file> -entry internalField -value` 非空
  #      （坑 2：字典文件是**位置参数**，写 `-case <dir> -entry …` 只打 Usage 且退 0）
  #   ③ 该目录所有文件 `grep -rilE 'nan|inf'` 为空
  # 三条**都判、都记原因**：②红了不代表③没问题，少判一条就等于少一个判据。
  G4_ERR=()
  rc_g4=0
  if ! command -v foamDictionary >/dev/null 2>&1; then
    rc_g4=1
    G4_ERR+=("OpenFOAM 环境缺失（foamDictionary 不在 PATH）⇒ G4 未判定，记 1")
    printf 'verify_case.sh: G4 需要 foamDictionary，OpenFOAM 环境未加载 ⇒ log.g4 记 RC=1\n' >&2
  else
    LAST=$(CASE_ROOT="$CASE_ROOT" python3 - <<'PY' 2>/dev/null
import os
root = os.environ["CASE_ROOT"]
best = None
try:
    for name in os.listdir(root):
        if not os.path.isdir(os.path.join(root, name)):
            continue
        try:
            v = float(name)
        except ValueError:
            continue
        if v == 0.0:                      # 0/ 是初值，不是产物
            continue
        if best is None or v > best[0]:
            best = (v, name)
except OSError:
    pass
print(best[1] if best else "")
PY
)
    if [ -z "$LAST" ]; then
      rc_g4=1
      G4_ERR+=("末时刻目录不存在：$CASE_ROOT 下没有 0 以外的数字目录（求解没产出结果）")
    else
      LAST_DIR="$CASE_ROOT/$LAST"
      # ② 至少一个场文件可读且非空
      _readable=""
      while IFS= read -r _f; do
        _v=$(foamDictionary "$_f" -entry internalField -value 2>/dev/null | head -n 1)
        if [ -n "${_v//[[:space:]]/}" ]; then _readable="$_f"; break; fi
      done < <(find "$LAST_DIR" -maxdepth 1 -type f 2>/dev/null | sort)
      if [ -z "$_readable" ]; then
        rc_g4=1
        G4_ERR+=("末时刻 $LAST 里没有可读的场文件（foamDictionary -entry internalField -value 全空）")
      fi
      # ③ 无 nan/inf
      _hits=$(grep -rilE 'nan|inf' "$LAST_DIR" 2>/dev/null)
      if [ -n "$_hits" ]; then
        rc_g4=1
        while IFS= read -r _h; do
          [ -n "$_h" ] && G4_ERR+=("末时刻 $LAST 里含 nan/inf：${_h#"$CASE_ROOT"/}")
        done <<< "$_hits"
      fi
    fi
  fi
  write_log "$LOG_DIR/log.g4" "$rc_g4" ${G4_ERR[@]+"${G4_ERR[@]}"}

  # ------------------------------------------------------------- 汇总
  # 三个日志**都已写完**才谈退出码：judge 要三个门才能归约，短路会让 fail 变 malformed。
  printf 'G2 RC=%d  %s  (G2B=%s)\n' "$rc_g2" "$LOG_DIR/log.g2" "$G2B"
  printf 'G3 RC=%d  %s\n' "$rc_g3" "$LOG_DIR/log.g3"
  printf 'G4 RC=%d  %s\n' "$rc_g4" "$LOG_DIR/log.g4"

  # ------------------------------------------------- OBJ 诊断（**不是门**）
  # 「objective」是需求四元组的一格，但**没有任何脚本把它翻译成字典项**：
  # 派生来自哪份 tutorial、它是不是稳态，全看那份 tutorial 自己怎么写。
  # 后果是**门全绿而需求没被满足**——2026-10-29 由陌生用户实测抓到：
  # 需求「…稳态」→ 派生 incompressibleFluid/cavity（ddtSchemes Euler、endTime 10）
  # → 2000 步瞬态跑到 t=10 s，五门全绿。这正是 SKILL §3 步骤 1 警告的那种失败形状。
  #
  # 这里只做**诊断输出**，不改退出码。理由同 G2b（preregistration 决策 #7）：
  # 「objective 是否被满足」依赖物理判断，不是脚本能判的门；把判不了的东西设成门，
  # 结果是所有人学会忽略这道门。但**必须让它可见**——可见性不需要判据。
  if [ -f "$META" ]; then
    _obj_line=$(CASE_ROOT="$CASE_ROOT" META="$META" python3 - <<'PY' 2>/dev/null
import json, os, re
meta = os.environ["META"]
case_root = os.environ["CASE_ROOT"]
try:
    with open(meta, encoding="utf-8") as fh:
        spec = (json.load(fh) or {}).get("spec") or {}
except Exception:
    raise SystemExit(0)
obj = spec.get("objective")
if not obj:
    raise SystemExit(0)
ddt = "?"
try:
    with open(os.path.join(case_root, "system", "fvSchemes"), encoding="utf-8", errors="replace") as fh:
        txt = fh.read()
    m = re.search(r"ddtSchemes\s*\{(.*?)\}", txt, re.S)
    if m:
        d = re.search(r"default\s+(\w+)\s*;", m.group(1))
        if d:
            ddt = d.group(1)
except Exception:
    pass
if ddt == "?":
    verdict = "unknown"
elif obj == "steady" and ddt == "steadyState":
    verdict = "match"
elif obj == "transient" and ddt != "steadyState":
    verdict = "match"
else:
    verdict = "mismatch"
print(f"{verdict}|{obj}|{ddt}")
PY
)
    if [ -n "$_obj_line" ]; then
      _obj_verdict="${_obj_line%%|*}"
      _obj_rest="${_obj_line#*|}"
      printf 'OBJ=%s  (需求 objective=%s，实际 ddtSchemes=%s)\n' \
        "$_obj_verdict" "${_obj_rest%%|*}" "${_obj_rest#*|}"
      if [ "$_obj_verdict" = "mismatch" ]; then
        printf '  警告：需求要 %s，但派生源的 ddtSchemes=%s。**五道门全绿不代表这条需求被满足**——\n' \
          "${_obj_rest%%|*}" "${_obj_rest#*|}"
        printf '        门只判「能不能跑」。要不要改 ddtSchemes/换求解器，由你按物理决定（本 harness 不替你选）。\n'
      elif [ "$_obj_verdict" = "unknown" ]; then
        printf '  注意：读不到 system/fvSchemes 的 ddtSchemes，objective 无法对照。\n'
      fi
    fi
  fi

  # ------------------------------------------------- GEO/RE 诊断（**不是门**）
  # 与上面的 OBJ 同构，回答「需求里的物理量级到底有没有落到算例上」。
  # 2026-10-29 第二轮陌生用户验收抓到实证：需求只说「二维方腔」→ parse_requirement 报
  # complete=true → 边长静默继承 tutorial 的 convertToMeters 0.1、网格 20×20=400 cells、
  # nu=1e-6 ⇒ Re=1e5。五门全绿、OBJ=match，但 400 cells 下 Re=1e5 的结果是 Stokes 流量级
  # （末时刻内部 |U|max≈0.17 m/s，顶盖 1 m/s），物理上无意义。
  #
  # 同 OBJ：**只输出诊断，不改退出码**。物理可信度不是脚本能判的门。
  if [ -f "$META" ]; then
    _geo_line=$(CASE_ROOT="$CASE_ROOT" META="$META" python3 - <<'PY' 2>/dev/null
import json, math, os, re
case_root = os.environ["CASE_ROOT"]
try:
    with open(os.environ["META"], encoding="utf-8") as fh:
        spec = (json.load(fh) or {}).get("spec") or {}
except Exception:
    spec = {}


def read(rel):
    try:
        with open(os.path.join(case_root, rel), encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return ""


# ---- 网格：两个独立来源的 cell 数，**必须分别报**
# ① blockMeshDict 里的 hex 分块 —— 这是「你以为」的网格（改了它不会自动重建）
# ② constant/polyMesh/owner 的 nCells —— 这是「磁盘上真实」的网格（门禁与求解用的是它）
# 2026-10-29 第三轮陌生用户验收实测：只报 ① 会让「改了 blockMeshDict 但没删
# constant/polyMesh」的人看到 GEO=cells=1024 而实际网格仍是 400 —— 拿一个假的 ok 交差。
# 判据必须来自磁盘上的真实网格，同时把两个数并排显示，矛盾时点名。
bm = read("system/blockMeshDict")
ctm = None
m = re.search(r"convertToMeters\s+([0-9.eE+-]+)\s*;", bm)
if m:
    try:
        ctm = float(m.group(1))
    except ValueError:
        ctm = None
cells_bm = 0
for hexline in re.finditer(r"hex\s*\([^)]*\)\s*\(([^)]*)\)", bm):
    nums = [int(x) for x in hexline.group(1).split() if x.lstrip("+-").isdigit()]
    if len(nums) == 3:
        cells_bm += nums[0] * nums[1] * nums[2]

cells_mesh = 0
owner = read("constant/polyMesh/owner")
# owner 的 FoamFile 头里有一行 note：
#   note        "nPoints: 8450 nCells: 4096 nFaces: 16512 nInternalFaces: 8064";
# **只能从这里取 nCells**。2026-10-29 实测：试图用「最后一个纯数字行」兜底会取到
# list 的长度（= nFaces，本例 16512），于是 4096 个格子被报成 16512 —— 又一个"静默取错数"。
# 取不到就报 unknown，绝不猜（R6：数字必须来自实测）。
mm = re.search(r"nCells:\s*(\d+)", owner)
if mm:
    cells_mesh = int(mm.group(1))

# 判据用真实网格；没有网格文件时退回 blockMeshDict（此时 G2 也会因为没日志而红）
cells = cells_mesh or cells_bm

# ---- 物性：nu（剥掉量纲） ----
nu = None
pp = read("constant/physicalProperties")
m = re.search(r"\bnu\b\s+([0-9.eE+-]+)", pp)
if m:
    try:
        nu = float(m.group(1))
    except ValueError:
        nu = None

# ---- 特征速度：0/U 的 boundaryField 里最大的非零 fixedValue ----
u_ref = None
u = read("0/U")
for vm in re.finditer(r"fixedValue\s*;?.*?uniform\s*\(([^)]*)\)", u, re.S):
    parts = vm.group(1).split()
    if len(parts) == 3:
        try:
            vec = [float(p) for p in parts]
        except ValueError:
            continue
        mag = math.sqrt(sum(c * c for c in vec))
        if mag > 0 and (u_ref is None or mag > u_ref):
            u_ref = mag

if ctm is None and cells == 0 and nu is None and not spec.get("geometry"):
    # 连需求里的 geometry 都没有 → 没有任何可对照对象，沉默是正确的（同 OBJ 的 None 分支）
    raise SystemExit(0)

geo_bits = []
if cells_mesh:
    geo_bits.append(f"cells={cells_mesh}(磁盘网格)")
if cells_bm and cells_bm != cells_mesh:
    geo_bits.append(f"blockMeshDict里的cells={cells_bm}")
if ctm is not None:
    geo_bits.append(f"convertToMeters={ctm:g}")
if spec.get("geometry"):
    geo_bits.append(f"需求 geometry={spec['geometry']}")
if not geo_bits:
    geo_bits.append("unknown  (读不到 blockMeshDict 的 convertToMeters/hex，也读不到 owner)")
print("GEO|" + "  ".join(geo_bits))

# blockMeshDict 与磁盘网格不一致 → 必须点明。这是「改了网格但没重建」的证据，
# 此时任何基于 blockMeshDict 的推理都是假的。
#
# **stale 时不许再输出 ok/coarse 结论**（2026-10-29 第四轮陌生用户验收实测）：
# 原实现先打 `RES=stale(...)` 再打 `RES=ok(cells=400 → cellRe≈50)`——同一个 RES 前缀、
# 相反的两个结论并列，而后者是按旧网格算的。读者读到第二行就会把 stale 当成已被覆盖，
# 拿 400 cells 的 Re=1e5 结果去交差。宁可只说一句，也不并列两句互相否定的话。
stale = bool(cells_bm and cells_mesh and cells_bm != cells_mesh)
if stale:
    print(
        f"RES|stale  (blockMeshDict 要 {cells_bm} 个格子，磁盘上是 {cells_mesh} 个："
        "网格没重建。**本次按磁盘网格判定；修好前不要用 RES 的其它结论**)"
    )

if nu and u_ref and ctm:
    L = ctm
    re_num = u_ref * L / nu
    print(f"RE|{re_num:.3g}  (U_ref={u_ref:g}, L={L:g}(按 convertToMeters 量级), nu={nu:g})")
    if not cells:
        print("RES|unknown  (读不到磁盘网格量)")
    elif stale:
        # 网格与 blockMeshDict 不一致时不判 —— 判了也是按一个你不能确定用户想用哪套网格的数。
        # 这不算「漏判」：上面那条 stale 已经明确要求先修网格。
        pass
    else:
        # 量级启发式（**不是判据**）：二维网格的 cell Reynolds 数 ≈ Re/sqrt(cells)。
        # 要求 cellRe 至少 ≲100 才谈得上解析流动；≳1000 基本就是数值扩散主导。
        # 2026-10-29 第三轮验收实测踩过旧阈值的坑：旧判据 `cells < 0.01*Re` 对
        # 1024 cells + Re=1e5 判了 "ok"，而那 1024 个格子的 cellRe≈3100、解仍在 3 倍漂移中。
        # 「明显荒谬」时喊、稍好一点就转安慰性措辞，比不喊更坏。
        cell_re = re_num / math.sqrt(cells)
        # 阈值比较必须带相对容差：Re/√cells 在边界上会因浮点噪声抖动
        # （实测 1e5/√1e6 = 100.00000000000001，判成 marginal 而不是 ok）。
        # 分级在边界上抖动，等于让诊断结果依赖末位比特。
        tol = 1e-9
        if cell_re > 1000 * (1 + tol):
            print(
                f"RES|coarse  (cells={cells} → cellRe≈{cell_re:.3g}，"
                f"Re={re_num:.3g} 基本不可解；结果大概率无物理意义)"
            )
        elif cell_re > 100 * (1 + tol):
            print(
                f"RES|marginal  (cells={cells} → cellRe≈{cell_re:.3g}，"
                "边界层与涡结构大概率没解析够；结果只能当流程演示)"
            )
        else:
            print(
                f"RES|ok  (cells={cells} → cellRe≈{cell_re:.3g}；"
                "按 cellRe 量级不算不足，但本 harness 不做网格无关性验证，仍由你判断)"
            )
else:
    print("RE|unknown  (读不到 nu / 0-U 的 fixedValue / convertToMeters，无法估 Re)")
PY
)
    if [ -n "$_geo_line" ]; then
      printf '%s\n' "$_geo_line" | while IFS='|' read -r _k _v; do
        case "$_k" in
          GEO) printf 'GEO=%s\n' "$_v" ;;
          RE)  printf 'RE=%s\n' "$_v" ;;
          RES) printf 'RES=%s\n' "$_v"
               case "$_v" in
                 stale*)
                   printf '  警告：blockMeshDict 改了但 constant/polyMesh 还是旧的（run_case.sh 只在网格不存在时才 blockMesh）。\n'
                   printf '        想换网格：删掉 constant/polyMesh 后重跑，否则求解用的仍是旧网格。\n' ;;
                 coarse*|marginal*)
                   printf '  提示：网格分辨率与 Re 不匹配时，门全绿也不代表结果可信（门只判「能不能跑」）。\n'
                   printf '        要么加密网格，要么把「本次结果仅作流程演示」写进结论。\n' ;;
               esac ;;
        esac
      done
    fi
  fi

  if [ "$rc_g2" -ne 0 ]; then
    printf 'G2 失败项:\n'; [ "${#G2_ERR[@]}" -gt 0 ] && printf '  %s\n' "${G2_ERR[@]}"
  fi
  if [ "$rc_g3" -ne 0 ]; then
    printf 'G3 失败项:\n'; [ "${#G3_ERR[@]}" -gt 0 ] && printf '  %s\n' "${G3_ERR[@]}"
  fi
  if [ "$rc_g4" -ne 0 ]; then
    printf 'G4 失败项:\n'; [ "${#G4_ERR[@]}" -gt 0 ] && printf '  %s\n' "${G4_ERR[@]}"
  fi

  # 只报第一个失败的门（D6）：按门号取最小。
  if [ "$rc_g2" -ne 0 ]; then
    exit 2
  elif [ "$rc_g3" -ne 0 ]; then
    exit 3
  elif [ "$rc_g4" -ne 0 ]; then
    exit 4
  fi
  exit 0
fi

# =============================================================== G1 结构
G1_ERR=()    # 判红项
G1_SKIP=()   # 不可判定项：写进日志但不改 RC（SKIP ≠ 通过，judge 只看 RC 行）

for _f in controlDict fvSchemes fvSolution; do
  [ -f "$CASE_ROOT/system/$_f" ] || G1_ERR+=("MISSING system/$_f")
done

if [ ! -d "$CASE_ROOT/0" ]; then
  G1_ERR+=("MISSING 目录 0/")
else
  # 非空 = 至少一个直接子项（时间目录里可以只有场文件，也可以有子目录）
  _n0=$(find "$CASE_ROOT/0" -mindepth 1 -maxdepth 1 2>/dev/null | wc -l | tr -d ' ')
  if [ "${_n0:-0}" -eq 0 ]; then
    G1_ERR+=("EMPTY 0/ （判据要求非空，实测 ${_n0:-0} 个子项）")
  fi
fi

# 「constant/ 有对应物理字典」：只认字典名，不解析内容（内容正确性是断言层的事）。
_PHYS_CANDIDATES="momentumTransport turbulenceProperties transportProperties physicalProperties thermophysicalProperties"
if [ ! -d "$CASE_ROOT/constant" ]; then
  G1_ERR+=("MISSING 目录 constant/")
else
  _found=""
  for _f in $_PHYS_CANDIDATES; do
    [ -f "$CASE_ROOT/constant/$_f" ] && { _found="$_f"; break; }
  done
  if [ -z "$_found" ]; then
    G1_ERR+=("MISSING constant/ 物理字典（候选名：${_PHYS_CANDIDATES// /, }）")
  fi
fi

# --- P4a：0/U、0/p 的 patch 集合 == constant/polyMesh/boundary 的 patch 集合
# 解析用 python3（纯文本 token 扫描，不碰 OpenFOAM）。来源不可判定时记 SKIP，不当通过。
while IFS= read -r _line; do
  [ -z "$_line" ] && continue
  case "$_line" in
    SKIP*)   G1_SKIP+=("${_line#SKIP }") ;;                  # 记入日志，不判红
    MISMATCH*) G1_ERR+=("${_line#MISMATCH }") ;;
    OK*)     : ;;                                              # 一致，静默
  esac
done < <(CASE_ROOT="$CASE_ROOT" python3 - <<'PY' 2>&1
import os, re, sys

root = os.environ["CASE_ROOT"]

def tokens(text):
    """去注释后切成 词 / { } ( ) 序列。够用就好：FoamFile 的这几段没有更怪的语法。"""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return re.findall(r"[{}()]|[^\s{}()]+", text)

def dict_patch_names(text, top_key):
    """top_key 后跟 { ... }：返回该块内第一层的「后面紧跟 { 的词」。"""
    tk = tokens(text)
    for i, t in enumerate(tk):
        if t == top_key and i + 1 < len(tk) and tk[i + 1] == "{":
            depth, out = 0, []
            j = i + 1
            while j < len(tk):
                t2 = tk[j]
                if t2 == "{":
                    depth += 1
                elif t2 == "}":
                    depth -= 1
                    if depth == 0:
                        return out
                elif depth == 1 and not t2.startswith("#"):
                    if j + 1 < len(tk) and tk[j + 1] == "{":
                        out.append(t2)
                j += 1
            return out
    return None

def list_patch_names(text, top_key):
    """返回括号列表内「花括号深度 0 处、后面紧跟 { 的词」。

    polyMesh/boundary 没有 `boundary` 关键字（对象名在 FoamFile 里），正文形如
    `3\\n(\\n name\\n { nFaces ...; }\\n ... )`，所以找不到关键字时回退到
    「前面是整数计数的那个 (」。"""
    tk = tokens(text)
    start = None
    for i, t in enumerate(tk):
        if t == top_key and i + 1 < len(tk) and tk[i + 1] == "(":
            start = i + 1
            break
    if start is None:
        for i in range(1, len(tk)):
            if tk[i] == "(" and re.fullmatch(r"\d+", tk[i - 1]):
                start = i
                break
    if start is None:
        return None
    depth, brace, out = 0, 0, []
    j = start
    while j < len(tk):
        t2 = tk[j]
        if t2 == "(":
            depth += 1
        elif t2 == ")":
            depth -= 1
            if depth == 0:
                return out
        elif t2 == "{":
            brace += 1
        elif t2 == "}":
            brace -= 1
        elif depth == 1 and brace == 0 and not t2.startswith("#"):
            if j + 1 < len(tk) and tk[j + 1] == "{":
                out.append(t2)
        j += 1
    return out

bpath = os.path.join(root, "constant", "polyMesh", "boundary")
if not os.path.isfile(bpath):
    print("SKIP constant/polyMesh/boundary 不存在，patch 集合子项未判定")
    raise SystemExit

try:
    bp = list_patch_names(open(bpath, encoding="utf-8", errors="replace").read(), "boundary")
except OSError as e:
    print(f"SKIP 读 boundary 失败: {e}")
    raise SystemExit
if not bp:
    print("SKIP boundary 解析不出 patch 名（格式异常），patch 集合子项未判定")
    raise SystemExit

for field in ("U", "p"):
    fp = os.path.join(root, "0", field)
    if not os.path.isfile(fp):
        print(f"SKIP 0/{field} 不存在，该场的 patch 集合未判定")
        continue
    try:
        names = dict_patch_names(open(fp, encoding="utf-8", errors="replace").read(), "boundaryField")
    except OSError as e:
        print(f"SKIP 读 0/{field} 失败: {e}")
        continue
    if not names:
        print(f"SKIP 0/{field} 无 boundaryField 段，patch 集合未判定")
        continue
    s, b = set(names), set(bp)
    if s != b:
        miss = sorted(b - s)      # boundary 有、场里没有 ⇒ solver 起来会 FATAL
        extra = sorted(s - b)     # 场里有、网格里没有 ⇒ 同样 FATAL
        print(f"MISMATCH 0/{field} 的 patch 集合 != constant/polyMesh/boundary："
              f"缺 {miss if miss else '[]'}，多 {extra if extra else '[]'}"
              f"（boundary={sorted(b)}，0/{field}={sorted(s)}）")
    else:
        print(f"OK 0/{field} patches={len(s)}")
PY
)

if [ "${#G1_ERR[@]}" -eq 0 ]; then rc_g1=0; else rc_g1=1; fi
write_log "$LOG_G1" "$rc_g1" ${G1_ERR[@]+"${G1_ERR[@]}"} ${G1_SKIP[@]+"${G1_SKIP[@]}"}

# =============================================================== G5 范围
# 改动集合的两种求法（顺序固定，先 base 后 mtime）：
#   ① <dir>/base 存在 → git diff --no-index --name-status -z -- base case
#      （git 自己的「内容不同」判定，不受 cp/touch 影响；本仓库不是 git 仓库也能用，
#        --no-index 正是为此存在）
#   ② <dir>/base 不存在 → mtime 晚于 <dir>/case.meta 的文件
#      （弱：任何解包/cp 都会污染，所以只要 base 在就绝不走这条路）
# 判据（prereg:89）：改动必须在 allowed_files 内；改 constant/polyMesh/ 下任何文件
# 必须另有 case.meta.changes 里的非空理由，否则算越界。
G5_ERR=()
G5_NOTE=()
_UNJUDGEABLE=0

while IFS= read -r _line; do
  [ -z "$_line" ] && continue
  case "$_line" in
    VIOLATION*)   G5_ERR+=("${_line#VIOLATION }") ;;
    NOTE*)        G5_NOTE+=("${_line#NOTE }") ;;
    UNJUDGEABLE*) _UNJUDGEABLE=1; G5_ERR+=("UNJUDGEABLE ${_line#UNJUDGEABLE }") ;;
    OK*)          : ;;
    # **兜底：认不出的行一律算失败。**
    # 不这么写就会有一个静默洞：内联 python 崩溃时 traceback 走 2>&1 进到这里，
    # 每行都不匹配上面的模式 → 被丢掉 → G5_ERR 为空 → G5 RC=0。
    # 2026-10-29 实测踩过：`re` 没 import，`re.fullmatch` 抛 NameError，
    # 结果门禁全绿而实际根本没判定。宁可误红，不可假绿。
    *)            _UNPARSEABLE=$(( ${_UNPARSEABLE:-0} + 1 ))
                  [ "$_UNPARSEABLE" -le 3 ] && G5_ERR+=("G5 判定器输出无法解析（内部错误）: $_line") ;;
  esac
done < <(CASE_ROOT="$CASE_ROOT" RUN_DIR="$CASE_DIR" META="$META" \
         ALLOWED_CSV="$(IFS=','; echo "${ALLOWED_GLOBS[*]:-}")" python3 - <<'PY' 2>&1
import fnmatch, json, os, re, subprocess

case_root = os.environ["CASE_ROOT"]
run_dir = os.environ["RUN_DIR"]
meta_path = os.environ["META"]
allowed_csv = os.environ.get("ALLOWED_CSV", "")

def out(kind, msg):
    print(kind + " " + msg)

# --- allowed 集合
if allowed_csv.strip():
    globs = [g.strip() for g in allowed_csv.split(",") if g.strip()]
    src = "--allowed（命令行）"
elif not os.path.isfile(meta_path):
    out("UNJUDGEABLE", "case.meta 不存在，且未传 --allowed ⇒ allowed_files 不可知（不可知 ≠ 合规）")
    raise SystemExit
else:
    try:
        meta = json.load(open(meta_path, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        out("UNJUDGEABLE", f"case.meta 无法解析（{e}）⇒ allowed_files 不可知")
        raise SystemExit
    if "allowed_files" not in meta:
        out("UNJUDGEABLE", "case.meta 无 allowed_files 键，且未传 --allowed ⇒ 范围不可判定")
        raise SystemExit
    globs = [str(g) for g in (meta.get("allowed_files") or [])]
    src = "case.meta.allowed_files"

try:
    meta = json.load(open(meta_path, encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    meta = {}

# --- 「改了什么」
def rel(p, base):
    return os.path.relpath(p, base).replace(os.sep, "/")

base_dir = os.path.join(run_dir, "base")
changed = []          # [(rel_path, status)]
mode = ""
if os.path.isdir(base_dir):
    mode = "git diff --no-index"
    proc = subprocess.run(
        ["git", "diff", "--no-index", "--name-status", "--no-renames", "-z",
         "--", base_dir, case_root],
        capture_output=True)
    raw = proc.stdout.split(b"\0")
    parts = [x.decode("utf-8", "replace") for x in raw if x != b""]
    # -z 下 name-status 是 status\0path\0 交替；R/C 会带两个 path，--no-renames 已排除
    i = 0
    while i + 1 < len(parts):
        st, p = parts[i], parts[i + 1]
        i += 2
        if p.startswith(case_root.rstrip("/") + "/"):
            changed.append((rel(p, case_root), st))
        elif p.startswith(base_dir.rstrip("/") + "/"):
            changed.append((rel(p, base_dir), st))     # 被删的文件也算改动
        else:
            changed.append((p, st))
else:
    mode = "mtime（无 base/）"
    if not os.path.isfile(meta_path):
        out("UNJUDGEABLE", "既无 base/ 也无 case.meta ⇒ 没有可用的改动判定基准")
        raise SystemExit
    m0 = os.path.getmtime(meta_path)
    for dirpath, _dirnames, filenames in os.walk(case_root):
        for fn in filenames:
            fp = os.path.join(dirpath, fn)
            try:
                if os.path.getmtime(fp) > m0:
                    changed.append((rel(fp, case_root), "M"))
            except OSError:
                pass

# --- 抹掉「run 产物本身」：日志/断言/meta 不是 case 的改动。
# 这条在 --case 直接指向 case 树时必须要有：log.g1 就写在 case 根旁边，
# 不排除的话第二次跑会把自己上次的日志判成越界（实测过：exit 5，失败串 log.g1）。
#
# **这里是枚举式清单，漏一项就是假红**（2026-10-29 实测踩过）：原清单列了
# log.checkMesh/shortRun/run，独独漏了 log.blockMesh（run_case.sh 步骤②写的），
# 于是「先求解、后跑 --stage pre」的人会看到 log.blockMesh 被判成越界改文件。
# 现在改为「按类判」：
#   ① 名字在 RUN_ARTIFACTS 里的 → 产物（清单仍保留，用于 tmp/断言这类无模式可判的名字）
#   ② 名字以 `log.` 开头的 → 一律产物（覆盖 log.blockMesh 以及将来新增的任何 log.*）
#   ③ 路径第一段是纯数字且不是 `0` 的 → 求解产生的时间目录（`0/` 不算：那是初始条件，
#      是用户真的会改的地方，必须继续受 allowed_files 约束）
RUN_ARTIFACTS = {
    "case.meta", "assert.json", "tokens.json", "blocked.txt", "arm_stdout.txt",
    "log.g1", "log.g2", "log.g3", "log.g4", "log.g5",
    "log.checkMesh", "log.shortRun", "log.run",
    # fix_case.py 的台账：它把 fingerprint.txt 写在 attempt_<n>/ 里。
    # batch 会把 attempt_1/ 改名成 base/（G5 的基线），于是 base/fingerprint.txt 会以
    # 「被删的文件」形态出现在 git diff 里，被判成越界改文件（2026-10-29 实测：G5 退 5）。
    # 它是 run 的台账、不是 case 的内容，按类排除。
    "fingerprint.txt",
}


def _is_run_artifact(relpath: str) -> bool:
    name = relpath.rsplit("/", 1)[-1]
    if relpath in RUN_ARTIFACTS or name in RUN_ARTIFACTS:
        return True
    if name.startswith("log."):
        return True
    head = relpath.split("/", 1)[0]
    # 时间目录名是 OpenFOAM 的时间值，**可能是浮点**（0.01 / 0.5 / 1.5 …），
    # 用 isdigit() 会漏掉一半（2026-10-29 实测：只剩整数时间目录被忽略，仍报 44 项假红）。
    if head != "0" and re.fullmatch(r"[0-9]+(\.[0-9]+)?", head):
        return True
    return False


_artifacts = sorted({p for p, _st in changed if _is_run_artifact(p)})
changed = [(p, st) for p, st in changed if not _is_run_artifact(p)]
if _artifacts:
    # 只列前若干个：求解过的算例可能有上千个产物文件，全列会把真正的越界项挤到屏幕外
    _shown = ", ".join(_artifacts[:5])
    _more = "" if len(_artifacts) <= 5 else f" …等 {len(_artifacts)} 项"
    out("NOTE", f"忽略 run 产物（不算改动）：{_shown}{_more}")

changed.sort()
out("NOTE", f"改动来源={mode}；allowed 来源={src}（{len(globs)} 条 glob）；改动 {len(changed)} 个文件")

# --- 理由（changes 非空即视为写了理由；只判「有没有写」，不判写得好不好）
def reason_text(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        return " ".join(reason_text(x) for x in v.values()).strip()
    if isinstance(v, (list, tuple)):
        return " ".join(reason_text(x) for x in v).strip()
    return str(v).strip()

has_reason = bool(reason_text(meta.get("changes")))

def allowed(path):
    return any(fnmatch.fnmatchcase(path, g) for g in globs)

n_mesh = 0
for path, st in changed:
    if allowed(path):
        continue
    if path.startswith("constant/polyMesh/"):
        n_mesh += 1
        if has_reason:
            out("NOTE", f"放行 {path}（{st}，constant/polyMesh/ 且 case.meta.changes 有理由）")
        else:
            out("VIOLATION", f"{path}（{st}，改 constant/polyMesh/ 但 case.meta.changes 无理由）")
        continue
    out("VIOLATION", f"{path}（{st}，不在 allowed_files 内）")

if n_mesh and not has_reason:
    out("NOTE", f"constant/polyMesh/ 下有 {n_mesh} 个改动无理由 ⇒ 全部计为越界")
PY
)

if [ "${#G5_ERR[@]}" -eq 0 ]; then rc_g5=0; else rc_g5=1; fi
write_log "$LOG_G5" "$rc_g5" ${G5_ERR[@]+"${G5_ERR[@]}"} ${G5_NOTE[@]+"${G5_NOTE[@]}"}

# =============================================================== 汇总
printf 'G1 RC=%d  %s\n' "$rc_g1" "$LOG_G1"
printf 'G5 RC=%d  %s\n' "$rc_g5" "$LOG_G5"
if [ "$rc_g1" -ne 0 ]; then
  printf 'G1 失败项:\n'
  [ "${#G1_ERR[@]}" -gt 0 ] && printf '  %s\n' "${G1_ERR[@]}"
fi
if [ "$rc_g5" -ne 0 ]; then
  printf 'G5 失败项:\n'
  [ "${#G5_ERR[@]}" -gt 0 ] && printf '  %s\n' "${G5_ERR[@]}"
fi

# 只报第一个失败的门（D6）：G1 优先。
if [ "$rc_g1" -ne 0 ]; then
  exit 1
elif [ "$rc_g5" -ne 0 ]; then
  exit 5
fi
exit 0
