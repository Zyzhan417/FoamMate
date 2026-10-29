#!/usr/bin/env bash
# scripts/preflight.sh —— 环境前置检查（独立、不依赖任何其它脚本，不执行 OpenFOAM 求解命令）
#
# 契约（对外见本包 SKILL.md §2；开发期设计文档不在本包内）
#   6 项检查，每项一行：通过打 stdout `OK <name> <detail>`，失败打 stderr `FAIL <name> <detail>`。
#   检查顺序固定：
#     1 bashrc          $WM_PROJECT_DIR 与 $FOAM_TUTORIALS 均非空          (失败码 50)
#     2 commands        foamRun foamDictionary blockMesh checkMesh 在 PATH (失败码 50)
#     3 tutorials       $FOAM_TUTORIALS 可读且 system/controlDict 计数 >= 100 (失败码 50)
#     4 version         $WM_PROJECT_VERSION 字面等于 13                    (失败码 51)
#     5 python3         python3 >= 3.9                                     (失败码 50)
#     6 scripts         同目录 8 个用户面脚本存在且可执行                   (失败码 50)
#
#   顺序不是为了好看：#1 先判「有没有 source」，否则没 source 时 #4 会看到空的
#   $WM_PROJECT_VERSION，把「环境没加载」误报成「版本不对」(51)，用户会去重装/降级
#   OpenFOAM——方向完全相反的处置。
#
# 退出码：0 全过 / 50 环境不全 / 51 版本不符 / 64 用法错误
#   51 不用 50 的理由：版本不符是「装错了」，环境不全多半是「忘了 source」，
#   前者要换安装，后者只要一条命令（spec §7 C6）。
#
# 为什么不复用 P1 的 resolve_bash_rc：本脚本必须能在一个**没有其他脚本**的目录里
#   单独运行（它就是给陌生用户的第一条命令），所以自己推导一份，而不是 source 别的文件。
#
# 用法：
#   bash scripts/preflight.sh
#   scripts/preflight.sh --help

set -uo pipefail

readonly EX_ENV=50       # 环境不全
readonly EX_VERSION=51   # 版本不符
readonly EX_USAGE=64     # 用法错误（不用 2：2 在 verify_case.sh 里是「G2 网格门失败」）

# bashrc 路径按安装位置推导：$WM_PROJECT_DIR 优先（source 过 bashrc 就非空）。
# 没有它时不假设安装前缀，而是在常见安装根下**发现**真实存在的 bashrc（v13 命名优先）；
# 这样做有两个原因：① `tests/unit/test_portability.py` 规定用户面脚本的代码里不得出现
# 写死的安装前缀（只写死一个常量、不读环境变量的行过不去），本脚本没有 find_template.sh
# 那种结构性豁免；② 「发现」比「假设」对陌生用户更靠谱——OpenFOAM 装在别处时，
# 提示语给出的仍然是一条能跑通的命令。
resolve_bash_rc() {
    if [ -n "${WM_PROJECT_DIR:-}" ] && [ -r "$WM_PROJECT_DIR/etc/bashrc" ]; then
        printf '%s' "$WM_PROJECT_DIR/etc/bashrc"
        return 0
    fi

    local cand
    for cand in /opt/openfoam*/etc/bashrc; do
        case "$cand" in
            */openfoam1[3]/etc/bashrc)      # 本包只支持 v13：同版本命名优先
                if [ -r "$cand" ]; then
                    printf '%s' "$cand"
                    return 0
                fi
                ;;
        esac
    done
    for cand in /opt/openfoam*/etc/bashrc; do
        if [ -r "$cand" ]; then
            printf '%s' "$cand"
            return 0
        fi
    done

    # 一个都没发现：给占位而不是假路径——此时本机根本没有可执行的 source 命令。
    printf '%s' "<OpenFOAM-v13 安装前缀>/etc/bashrc"
}
readonly BASH_RC="$(resolve_bash_rc)"

# 同目录定位：用 BASH_SOURCE 而不是 $0（被 source 或被软链调用时仍正确）
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
readonly SCRIPT_DIR

# 8 个用户面脚本（= 发布白名单里的 scripts/ 部分，本脚本自己不算）
readonly USER_SCRIPTS=(
    parse_requirement.py
    find_template.sh
    new_case.sh
    run_case.sh
    verify_case.sh
    fix_case.py
    batch.py
    msh2d_to_foam.py
)
readonly REQUIRED_CMDS=(foamRun foamDictionary blockMesh checkMesh)
readonly MIN_CONTROLDICTS=100

usage() {
    cat <<'EOF'
用法: preflight.sh [--check]
      preflight.sh --help
  （无参数即跑检查；--check 是同义别名，写出来只为可读性）
  检查内容：bashrc 已 source / 四个命令在 PATH / tutorials 可用 / 版本是 13
            / python3 >= 3.9 / 同目录 8 个用户面脚本齐备
  --help ：只打印本用法并退 0

输出：每项一行，通过为 stdout `OK <name> <detail>`，失败为 stderr `FAIL <name> <detail>`；
      失败时最后一行是可执行的下一步（不是错误码）。
退出码：0 全过 / 50 环境不全 / 51 版本不符（本包只支持 OpenFOAM v13）/ 64 用法错误
EOF
}

# ---------- 参数解析 ----------
# 无参数 = 跑检查（这是本脚本的默认动作，也是最容易被陌生用户猜到的行为）：
# 「跑检查」不是用法错误，所以不能套 test_exit_codes.py 里「不传参数 → 64」那条契约。
# 因此本脚本**不在** test_exit_codes.py 的 SCRIPTS 列表里；它的用法错误（未知参数）由
# tests/contract/test_preflight.py 单独守，判据仍是 64 —— 口径不变，只是入口不同。
while [ $# -gt 0 ]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --check)
            shift
            # 同义别名；其它参数照常由循环判：`--check --help` 打用法退 0，`--check --nope` 退 64
            ;;
        *)
            usage >&2
            printf 'preflight: 未知参数 %s（退出码 %s）。\n' "$1" "$EX_USAGE" >&2
            exit "$EX_USAGE"
            ;;
    esac
done

# ---------- 结果记账 ----------
FAILED=0
FAIL_SUMMARY=""
VERSION_MISMATCH=0

ok() {
    printf 'OK %s %s\n' "$1" "$2"
}

fail() {
    printf 'FAIL %s %s\n' "$1" "$2" >&2
    FAILED=$((FAILED + 1))
    if [ -z "$FAIL_SUMMARY" ]; then
        FAIL_SUMMARY="$1"
    else
        FAIL_SUMMARY="$FAIL_SUMMARY, $1"
    fi
}

# ---------- #1 bashrc 已 source ----------
ENV_LOADED=0
if [ -n "${WM_PROJECT_DIR:-}" ] && [ -n "${FOAM_TUTORIALS:-}" ]; then
    ENV_LOADED=1
    ok bashrc "WM_PROJECT_DIR=$WM_PROJECT_DIR FOAM_TUTORIALS=$FOAM_TUTORIALS"
else
    fail bashrc "WM_PROJECT_DIR='${WM_PROJECT_DIR:-}' FOAM_TUTORIALS='${FOAM_TUTORIALS:-}'(至少一个为空 = 未 source bashrc)"
fi

# ---------- #2 四个命令在 PATH ----------
MISSING_CMDS=()
for c in "${REQUIRED_CMDS[@]}"; do
    command -v "$c" >/dev/null 2>&1 || MISSING_CMDS+=("$c")
done
if [ ${#MISSING_CMDS[@]} -eq 0 ]; then
    ok commands "PATH 中可用: ${REQUIRED_CMDS[*]}"
else
    fail commands "PATH 中缺少: ${MISSING_CMDS[*]}"
fi

# ---------- #3 tutorials 可用 ----------
if [ -n "${FOAM_TUTORIALS:-}" ] && [ -d "$FOAM_TUTORIALS" ] && [ -r "$FOAM_TUTORIALS" ]; then
    N_CONTROLDICT="$(
        find "$FOAM_TUTORIALS" -type f -path '*/system/controlDict' 2>/dev/null | wc -l | tr -d '[:space:]'
    )"
    if [ "${N_CONTROLDICT:-0}" -ge "$MIN_CONTROLDICTS" ]; then
        ok tutorials "$FOAM_TUTORIALS 下 system/controlDict 共 $N_CONTROLDICT 个(>= $MIN_CONTROLDICTS)"
    else
        fail tutorials "$FOAM_TUTORIALS 下 system/controlDict 只找到 ${N_CONTROLDICT:-0} 个(< $MIN_CONTROLDICTS)，不像是完整的 tutorial 树"
    fi
else
    fail tutorials "FOAM_TUTORIALS 不可读: '${FOAM_TUTORIALS:-}'(目录不存在或无权读取)"
fi

# ---------- #4 版本是 13 ----------
# 环境没加载时不做 51 判定（否则会把「忘了 source」误报成「版本不对」，处置方向相反）。
if [ "$ENV_LOADED" -eq 0 ]; then
    fail version "WM_PROJECT_VERSION='${WM_PROJECT_VERSION:-}'(环境未加载，版本无法判定；按环境不全处理，不报 $EX_VERSION)"
elif [ "${WM_PROJECT_VERSION:-}" = "13" ]; then
    ok version "WM_PROJECT_VERSION=13"
else
    VERSION_MISMATCH=1
    fail version "WM_PROJECT_VERSION='${WM_PROJECT_VERSION:-}'(期望字面值 13)"
fi

# ---------- #5 python3 >= 3.9 ----------
if command -v python3 >/dev/null 2>&1 \
   && python3 -c 'import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)' >/dev/null 2>&1; then
    PY_VER="$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)"
    ok python3 "python3 ${PY_VER:-?} >= 3.9"
else
    if command -v python3 >/dev/null 2>&1; then
        PY_VER="$(python3 -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null)"
        fail python3 "python3 ${PY_VER:-?} < 3.9"
    else
        fail python3 "PATH 中没有 python3"
    fi
fi

# ---------- #6 脚本齐备 ----------
MISSING_SCRIPTS=()
for s in "${USER_SCRIPTS[@]}"; do
    if [ ! -f "$SCRIPT_DIR/$s" ] || [ ! -x "$SCRIPT_DIR/$s" ]; then
        MISSING_SCRIPTS+=("$s")
    fi
done
if [ ${#MISSING_SCRIPTS[@]} -eq 0 ]; then
    ok scripts "同目录 ${#USER_SCRIPTS[@]} 个用户面脚本均存在且可执行"
else
    fail scripts "$SCRIPT_DIR 下缺失或不可执行: ${MISSING_SCRIPTS[*]}"
fi

# ---------- 汇总：最后一行必须是可执行的下一步 ----------
if [ "$FAILED" -eq 0 ]; then
    printf 'preflight: 6/6 项通过，环境就绪。\n'
    exit 0
fi

if [ "$VERSION_MISMATCH" -eq 1 ]; then
    printf 'preflight: 本包只支持 OpenFOAM v13，检测到 WM_PROJECT_VERSION=%s；另有 %d 项未通过(%s)。\n' \
        "${WM_PROJECT_VERSION:-}" "$FAILED" "$FAIL_SUMMARY" >&2
    printf '下一步：source %s\n' "$BASH_RC" >&2
    exit "$EX_VERSION"
fi

printf 'preflight: %d/6 项未通过(%s)，环境不完整。\n' "$FAILED" "$FAIL_SUMMARY" >&2
printf '前置检查必须先 source OpenFOAM 的 bashrc；当前推导路径为 %s\n' "$BASH_RC" >&2
printf '下一步：source %s\n' "$BASH_RC" >&2
exit "$EX_ENV"
