#!/usr/bin/env bash
# scripts/run_case.sh —— 模块 D：求解执行器（真跑 OpenFOAM）
#
# 契约（references/09-architecture-and-test-plan.md §D）：
#   CLI：run_case.sh --case <dir> --mode check|short|full [--timeout <秒>]
#
#   步骤（固定顺序）：
#     ① 环境探测：`command -v foamRun` 失败 → 22（**主动探测**，不靠子进程退出码兜底：
#        真空环境下 foamRun 退 127，与"求解失败"同形，见下"坑 2"）
#     ② 网格准备：constant/polyMesh 不存在时，system/blockMeshDict 存在 → blockMesh
#        写 log.blockMesh；两者都没有 → 23
#     ③ checkMesh → log.checkMesh
#     ④ mode=short：把 endTime 改成 deltaT*2、writeInterval 改成 2，跑 foamRun → log.shortRun
#        mode=full ：先同样的短跑写 log.shortRun，再恢复原 endTime/writeInterval 跑 log.run
#        mode=check：只到 ③ 为止（**不产** log.shortRun / log.run）
#
#   退出码：0 正常 / 20 求解失败 / 21 超时 / 22 环境缺失 / 23 无可用网格 / 64 用法错误或前置不满足（缺参数、--mode 非法、case 目录不存在）
#   注：环境缺失是 22（不是 64，也不是 127）——22 单独登记，见 D13
#
# 三个已实测的坑（改这个脚本前先读）：
#   坑 1  foamDictionary 的字典文件是**位置参数**：
#            对：foamDictionary system/controlDict -case "$case" -entry endTime -set 0.01
#            错：foamDictionary -case "$case" -entry endTime -set 0.01
#         省掉文件时它打 Usage + stderr 的 `FOAM FATAL ERROR: Wrong number of arguments`，
#         并**退 1**（2026-10-28 实测；早期文档写"退 0"是因为测量时带了 `| head`，
#         $? 取到的是 head 的退出码）。所以用法错**能**从退出码发现。
#         **但下面 set_entry() 仍然一律回读校验**，理由是另一件事：
#         `-set` 对**不存在的 entry 会新增并退 0** —— 拼错键名不会失败，只会悄悄多出一个键。
#         回读不符按求解失败处理（退 20），绝不让"改字典失败"伪装成成功。
#   坑 2  env -i PATH=/usr/bin:/bin bash -c 'foamRun' 退 127（实测），与求解失败同形，
#         所以必须先 `command -v foamRun`（它退 1）主动探测。
#   坑 3  timeout 杀掉子进程时退 124（实测），要映射成 21，不能当 20。
#
# 用法：
#   source "$WM_PROJECT_DIR/etc/bashrc"     # 必须先 source
#   bash scripts/run_case.sh --case cases/foo --mode check
#   bash scripts/run_case.sh --case cases/foo --mode short --timeout 120
#
# 环境变量：无（只读 $PATH 里的 OpenFOAM 可执行；不在脚本里 source bashrc，
#          因为"环境缺失"必须能被脚本**判定出来**，而不是被脚本自己掩盖）。

set -uo pipefail

readonly DEFAULT_TIMEOUT=600

CASE=""
LOG_DIR=""      # 日志目录；缺省 = --case（D20：prereq §12 允许放 run 根）
MODE=""
TIMEOUT="$DEFAULT_TIMEOUT"

die() {
    local code="$1"
    shift
    printf 'run_case: %s\n' "$*" >&2
    exit "$code"
}

usage() {
    cat >&2 <<'EOF'
用法: run_case.sh --case <dir> --mode check|short|full [--timeout <秒>]
  --case     必填。case 目录（须含 system/controlDict）
  --mode     必填。check=只建网格+checkMesh / short=短跑 / full=短跑再全时程跑
  --timeout  可选。单个 OpenFOAM 子进程的墙钟上限，整数秒，默认 600
退出码: 0 正常 / 20 求解失败 / 21 超时 / 22 环境缺失 / 23 无可用网格 / 64 用法错误
EOF
}

# ---------- 参数解析 ----------
while [ $# -gt 0 ]; do
    case "$1" in
        --case)
            [ $# -ge 2 ] || die 64 "--case 缺少参数值"
            CASE="$2"
            shift 2
            ;;
        --case=*)
            CASE="${1#--case=}"
            shift
            ;;
        --mode)
            [ $# -ge 2 ] || die 64 "--mode 缺少参数值"
            MODE="$2"
            shift 2
            ;;
        --mode=*)
            MODE="${1#--mode=}"
            shift
            ;;
        --timeout)
            [ $# -ge 2 ] || die 64 "--timeout 缺少参数值"
            TIMEOUT="$2"
            shift 2
            ;;
        --timeout=*)
            TIMEOUT="${1#--timeout=}"
            shift
            ;;
        --log)
            [ $# -ge 2 ] || die 64 "--log 缺少参数值"
            LOG_DIR="$2"
            shift 2
            ;;
        --log=*)
            LOG_DIR="${1#--log=}"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage
            die 64 "未知参数: $1"
            ;;
    esac
done

[ -n "$CASE" ] || { usage; die 64 "必须给 --case"; }
[ -n "$MODE" ] || { usage; die 64 "必须给 --mode"; }
case "$MODE" in
    check|short|full) ;;
    *) usage; die 64 "--mode 只能是 check|short|full，收到: $MODE" ;;
esac

case "$TIMEOUT" in
    ''|*[!0-9]*) die 64 "--timeout 必须是正整数秒，收到: $TIMEOUT" ;;
esac
[ "$TIMEOUT" -gt 0 ] || die 64 "--timeout 必须 > 0，收到: $TIMEOUT"

[ -d "$CASE" ] || die 64 "case 目录不存在: $CASE"
CASE="$(cd "$CASE" && pwd)" || die 64 "无法进入 case 目录: $CASE"
[ -f "$CASE/system/controlDict" ] || die 64 "不是 case 目录（缺 system/controlDict）: $CASE"

# ---- 日志目录（D20）：缺省写进 case（原行为）；传了 --log 就写到那里——
# prereg §12 把 log.* 放在 run 根（与 case/ 同级）。这里取绝对路径，因为下面会 cd。
[ -n "$LOG_DIR" ] || LOG_DIR="$CASE"
mkdir -p "$LOG_DIR" 2>/dev/null || die 64 "无法创建 --log 目录: $LOG_DIR"
LOGD="$(cd "$LOG_DIR" && pwd)"

# ---------- ① 环境探测（坑 2：必须主动探测，不能靠 127 兜底） ----------
command -v foamRun >/dev/null 2>&1 \
    || die 22 "OpenFOAM 环境未加载"

cd "$CASE" || die 64 "无法进入 case 目录: $CASE"

# ---------- 内部工具 ----------

# run_capped <logfile> <cmd...>：跑一条 OpenFOAM 命令，返回 0/20/21
run_capped() {
    local logf="$1"
    shift
    local rc
    timeout "$TIMEOUT" "$@" > "$logf" 2>&1
    rc=$?
    [ "$rc" -eq 124 ] && return 21   # 坑 3：timeout 杀子进程退 124
    [ "$rc" -ne 0 ] && return 20
    return 0
}

# handle <rc> <描述> <logfile>：把 0/20/21 翻译成退出码与消息
handle() {
    local rc="$1" what="$2" logf="$3"
    case "$rc" in
        0) return 0 ;;
        21) die 21 "$what 超时（--timeout ${TIMEOUT} 秒），见 $logf" ;;
        *)  die 20 "$what 失败（退出码 $rc），见 $logf" ;;
    esac
}

# read_entry <entry>：回读 controlDict 顶层标量的裸值（已剥空白）
read_entry() {
    foamDictionary system/controlDict -case "$CASE" -entry "$1" -value 2>/dev/null \
        | tr -d '[:space:]'
}

# set_entry <entry> <value>：设置 + **回读校验**（坑 1）
set_entry() {
    local entry="$1" want="$2" got
    foamDictionary system/controlDict -case "$CASE" -entry "$entry" -set "$want" \
        >/dev/null 2>&1
    got="$(read_entry "$entry")"
    if ! awk -v a="$got" -v b="$want" 'BEGIN { exit (a + 0 == b + 0) ? 0 : 1 }'; then
        die 20 "设置 $entry=$want 未生效（回读 '$got'）——foamDictionary 静默失败"
    fi
}

is_number() {
    awk -v v="$1" 'BEGIN { exit (v ~ /^[+-]?[0-9]*\.?[0-9]+([eE][+-]?[0-9]+)?$/) ? 0 : 1 }'
}

# ---------- ② 网格准备 ----------
if [ ! -d constant/polyMesh ]; then
    if [ -f system/blockMeshDict ]; then
        run_capped "$LOGD/log.blockMesh" blockMesh
        handle $? "blockMesh" "$LOGD/log.blockMesh"
    else
        die 23 "无可用网格：constant/polyMesh 不存在，且 system/blockMeshDict 也不存在"
    fi
fi

# ---------- ③ checkMesh ----------
run_capped "$LOGD/log.checkMesh" checkMesh
handle $? "checkMesh" "$LOGD/log.checkMesh"

if [ "$MODE" = "check" ]; then
    printf 'CASE=%s\n' "$CASE"
    printf 'MODE=check\n'
    printf 'LOGS=log.checkMesh\n'
    printf 'STATUS=ok\n'
    exit 0
fi

# ---------- ④ 求解 ----------
DELTA_T="$(read_entry deltaT)"
END_TIME_ORIG="$(read_entry endTime)"
WRITE_ORIG="$(read_entry writeInterval)"

is_number "$DELTA_T" || die 20 "system/controlDict 的 deltaT 不是数字: '$DELTA_T'"
is_number "$END_TIME_ORIG" || die 20 "system/controlDict 的 endTime 不是数字: '$END_TIME_ORIG'"

# 短跑目标 = deltaT*2（2 个时间步）。不写死 0.01：不同 case 的 deltaT 不同。
SHORT_END="$(awk -v d="$DELTA_T" 'BEGIN { printf "%.10g", d * 2 }')"
awk -v d="$DELTA_T" 'BEGIN { exit (d > 0) ? 0 : 1 }' || die 20 "deltaT 必须 > 0，收到: $DELTA_T"

set_entry endTime "$SHORT_END"
set_entry writeInterval 2

run_capped "$LOGD/log.shortRun" foamRun
handle $? "短跑 foamRun" "$LOGD/log.shortRun"

if [ "$MODE" = "full" ]; then
    # 恢复原始设定后再跑全时程（恢复也要回读校验）
    set_entry endTime "$END_TIME_ORIG"
    set_entry writeInterval "$WRITE_ORIG"

    run_capped "$LOGD/log.run" foamRun
    handle $? "全时程 foamRun" "$LOGD/log.run"
    printf 'CASE=%s\n' "$CASE"
    printf 'MODE=full\n'
    printf 'SHORT_END=%s\n' "$SHORT_END"
    printf 'LOGS=log.checkMesh log.shortRun log.run\n'
    printf 'STATUS=ok\n'
    exit 0
fi

printf 'CASE=%s\n' "$CASE"
printf 'MODE=short\n'
printf 'SHORT_END=%s\n' "$SHORT_END"
printf 'LOGS=log.checkMesh log.shortRun\n'
printf 'STATUS=ok\n'
exit 0
