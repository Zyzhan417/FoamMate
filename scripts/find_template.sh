#!/usr/bin/env bash
# scripts/find_template.sh —— 模块 B：知识检索（grep）
#
# 契约（references/09-architecture-and-test-plan.md §B）：
#   输入：--keyword "<词>" [--limit N]
#   输出：stdout 每行一个 "相对路径:行号"，按相对路径排序；
#         末两行 FOUND=<命中总数> 与 SHOWN=<实际输出行数>（FOUND 不受 --limit 影响）
#         n = 实际输出的命中行数（即 --limit 截断后的条数，故恒等于命中行数）。
#   空命中：只输出一行 FOUND=0 并退出 11。**不**回退到任何记忆/默认值/别的目录。
#   搜索根：只有五个（AGENTS.md R1），可用同名环境变量覆盖：
#         $FOAM_TUTORIALS $FOAM_SRC $FOAM_APP $FOAM_ETC $FOAM_UTILITIES
#   $HOME/OpenFOAM 下的副本一律拒绝（那是我们的二次开发副本，不是权威，R1/R9）。
#   确定性：无 random、不依赖 ls / grep 的遍历顺序（输出统一排序 + 绝对路径去重），
#         同一输入连续两次输出逐字相同。
#
# 退出码：0 有命中 / 11 无命中 / 64 用法错误或前置不满足（缺参数、--limit 非法、搜索根非法/不存在/全空）
#   注：64 不用 2——2 在 verify_case.sh 里是「G2 网格门失败」
#
# 用法：
#   source "$WM_PROJECT_DIR/etc/bashrc"      # 必须先 source，否则 $FOAM_* 全空
#   bash scripts/find_template.sh --keyword cavity --limit 5

set -uo pipefail

# bashrc 路径按安装位置推导：$WM_PROJECT_DIR 优先（source 过 bashrc 就非空），
# 缺省回退到本机默认安装前缀——回退值是故意的，因为「没 source」的提示语里必须给出
# 一条可执行的下一步（tests/unit/test_exit_codes.py::test_find_template_env_missing_is_64_not_2）。
resolve_bash_rc() {
    if [ -n "${WM_PROJECT_DIR:-}" ] && [ -r "$WM_PROJECT_DIR/etc/bashrc" ]; then
        printf '%s' "$WM_PROJECT_DIR/etc/bashrc"
    else
        printf '%s' "/opt/openfoam13/etc/bashrc"
    fi
}
readonly BASH_RC="$(resolve_bash_rc)"
# 五个根的环境变量名，顺序固定（同时决定同一文件被多个根覆盖时的归属优先级）
readonly ROOT_VARS=(FOAM_TUTORIALS FOAM_SRC FOAM_APP FOAM_ETC FOAM_UTILITIES)

KEYWORD=""
LIMIT=0

die() {
    local code="$1"
    shift
    printf 'find_template: %s\n' "$*" >&2
    exit "$code"
}

usage() {
    cat >&2 <<'EOF'
用法: find_template.sh --keyword "<词>" [--limit N]
  --keyword  必填。字面匹配（等同 grep -F，不解释正则）
  --limit N  可选。最多输出 N 行（N > 0）；默认 0 = 不截断
  stdout 末两行为 FOUND=<命中总数> / SHOWN=<输出行数>；无命中时只输出 FOUND=0 并退出 11
EOF
}

# ---------- 参数解析 ----------
while [ $# -gt 0 ]; do
    case "$1" in
        --keyword)
            [ $# -ge 2 ] || die 64 "--keyword 缺少参数值"
            KEYWORD="$2"
            shift 2
            ;;
        --keyword=*)
            KEYWORD="${1#--keyword=}"
            shift
            ;;
        --limit)
            [ $# -ge 2 ] || die 64 "--limit 缺少参数值"
            LIMIT="$2"
            shift 2
            ;;
        --limit=*)
            LIMIT="${1#--limit=}"
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

[ -n "$KEYWORD" ] || { usage; die 64 "必须给 --keyword"; }
case "$LIMIT" in
    ''|*[!0-9]*) die 64 "--limit 必须是非负整数: $LIMIT" ;;
esac

# ---------- 搜索根收集（固定五个，不许新增） ----------
roots=()
for var in "${ROOT_VARS[@]}"; do
    p="${!var:-}"                       # 空 = 未 source bashrc 或用户显式清空，跳过该根
    [ -n "$p" ] || continue
    # R1：禁止把我们自己的副本当权威
    case "$p" in
        "$HOME/OpenFOAM"|"$HOME/OpenFOAM"/*)
            die 64 "搜索根 $var=$p 落在 \$HOME/OpenFOAM（R1 禁止，只能搜 \$WM_PROJECT_DIR 下的五个根）"
            ;;
    esac
    [ -d "$p" ] || die 64 "搜索根 $var=$p 不存在或不是目录"
    roots+=("$p")
done

[ ${#roots[@]} -gt 0 ] || die 64 "五个搜索根全为空：请先 source $BASH_RC"

# ---------- 检索 ----------
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

: > "$tmpdir/raw"
for root in "${roots[@]}"; do
    # -r 递归 / -n 行号 / -I 跳过二进制 / -m1 每文件只取第一个命中 / -- 防词以 - 开头
    grep -rnI -m1 -F -- "$KEYWORD" "$root" 2>/dev/null |
        awk -v root="$root" -v OFS='\t' '
            {
                i = index($0, ":")                  # grep 输出 "路径:行号:内容"，路径不含 ":"
                if (i == 0) next
                path = substr($0, 1, i - 1)
                rest = substr($0, i + 1)
                ln   = rest
                sub(/:.*/, "", ln)
                if (path != "" && ln ~ /^[0-9]+$/) print root, path, ln
            }' >> "$tmpdir/raw"
done

# 去重（同一绝对路径只留第一次出现的根口径）+ 换成相对路径
# 然后按相对路径排序；同一路径理论上只出现一次，行号作第二键只为彻底消除并列不确定性
LC_ALL=C awk -F'\t' -v OFS='\t' '
    {
        root = $1; abs = $2; ln = $3
        if (seen[abs]++) next
        print substr(abs, length(root) + 2), ln
    }' "$tmpdir/raw" |
    LC_ALL=C sort -t"$(printf '\t')" -k1,1 -k2,2n > "$tmpdir/sorted"

total=$(wc -l < "$tmpdir/sorted" | tr -d ' ')

if [ "$total" -eq 0 ]; then
    # 空结果不编造：不猜、不回退、不给"最接近"的候选
    echo "FOUND=0"
    exit 11
fi

if [ "$LIMIT" -gt 0 ] && [ "$total" -gt "$LIMIT" ]; then
    head -n "$LIMIT" "$tmpdir/sorted" > "$tmpdir/out"
else
    cp "$tmpdir/sorted" "$tmpdir/out"
fi

awk -F'\t' '{ print $1 ":" $2 }' "$tmpdir/out"
# FOUND 是**命中总数**，不受 --limit 影响（规格：`n = 命中文件数`）。
# 输出行数是 --limit 的机械结果，单独给 SHOWN，否则下游把「被截断」误读成「只有这么多候选」。
echo "FOUND=$total"
echo "SHOWN=$(wc -l < "$tmpdir/out" | tr -d ' ')"
exit 0
