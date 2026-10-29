#!/usr/bin/env bash
# scripts/make_export.sh —— 公开导出树组装器（M5 · 发布边界落地物）
#
# 与 make_release.sh 的区别（两个不同的对象，别混）：
#   make_release.sh → 给**使用者**的 12 文件工具包（dist/），只含 6 个用户面脚本 + 3 份文档；
#   make_export.sh  → 给**开发者/审阅者**的完整仓库树，含 scripts/ tests/ bench/ references/ release/。
#   前者是产品，后者是源码。它们各自有独立的白名单与自检，不共享清单。
#
# ## 为什么导出源是 HEAD 提交，而不是工作树
#
# 「要发布的东西」必须能指到一个提交上。从工作树复制会把未提交的临时编辑一起带出去，
# 而导出树上一切绿——因为它是你屏幕上那棵树的复制品，不是别人会 clone 到的那棵树。
# 所以这里用 `git archive HEAD`：只含被跟踪的、已提交的内容，权限位由 git 保留。
# 代价是**未提交的改动不会进导出树**，所以脚本会在开头把未提交项逐个点名，并且
# 在摘要里再打一次「导出 = HEAD <sha>」。工作树脏不阻止导出（导出内容本来就不含它），
# 但必须让操作者看见——否则「我明明改了」与「导出里没有」会变成一次互相怀疑。
#
# ## 为什么不用第二份白名单文件
#
# 发布范围已经由 .gitignore 表达（每条都带理由注释，见该文件）。再维护一份手写的
# 导出清单，就是两份必须同步的清单——本项目 N7 第 15 条（平行数组只改一边）就是这类
# 缺陷的实测形态。所以这里的事实来源是 **git 索引**，而「该不该发布」由
# scripts/verify_export.py 的 E1 反向校验（排除项一个都不许在）。索引里偷偷加了
# references/repos/ 会让 E1 红，这比第二份清单更可靠。
#
# 退出码：0 全过 / 80 导出树违规（来自 verify_export.py） / 81 组装失败（git/tar/落盘） / 64 用法错误
#   81 与 80 分开：80 要改内容，81 要改环境（git 不在、dest 不可写），处置不同。
#
# 用法：
#   scripts/make_export.sh --dest dist/export
#   scripts/make_export.sh --dest /tmp/export --skip-tests     # 只调试，不算验收
#   scripts/make_export.sh --help

set -uo pipefail

readonly EX_OK=0
readonly EX_VIOLATION=80
readonly EX_BUILD=81
readonly EX_USAGE=64

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
readonly REPO_ROOT

usage() {
    cat <<'EOF'
用法: make_export.sh --dest <dir> [--skip-tests] [--help]

  --dest <dir>    导出目录（相对仓库根；已存在则先删后建——它是构建产物，不是用户数据）
  --skip-tests    跳过 E4 的 pytest（只用于调试；跳过时不算验收）
  --help          显示本帮助并退出 0

环境变量:
  PYTHON=/path/to/python   跑 E4 单元测试用的解释器（须装 pytest；
                           缺省由校验器自己挑，挑不到会明确判红而不是静默通过）

导出内容 = `git archive HEAD`，即**已提交**的、未被 .gitignore 排除的文件。
退出码: 0 全过 / 80 导出树违规 / 81 组装失败 / 64 用法错误
EOF
}

usage_err() {
    printf 'make_export: %s\n' "$1" >&2
    usage >&2
    exit "$EX_USAGE"
}

# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------
if [ $# -eq 0 ]; then
    usage_err "缺少参数：必须显式给 --dest（不给默认值，避免在仓库根静默产出导出树）"
fi

DEST=""
SKIP_TESTS=0

while [ $# -gt 0 ]; do
    case "$1" in
        --dest)
            [ $# -ge 2 ] || usage_err "--dest 需要一个目录参数"
            [ -n "$2" ]  || usage_err "--dest 的目录参数为空"
            DEST="$2"; shift 2 ;;
        --dest=*)
            DEST="${1#--dest=}"
            [ -n "$DEST" ] || usage_err "--dest 的目录参数为空"
            shift ;;
        --skip-tests)
            SKIP_TESTS=1; shift ;;
        --help|-h)
            usage; exit "$EX_OK" ;;
        *)
            usage_err "未知参数: $1" ;;
    esac
done

[ -n "$DEST" ] || usage_err "缺少 --dest"

case "$DEST" in
    /*) : ;;
    *)  DEST="$REPO_ROOT/$DEST" ;;
esac

# ---------------------------------------------------------------------------
# 前置：必须在 git 仓库里，且 HEAD 存在
# ---------------------------------------------------------------------------
cd -- "$REPO_ROOT" || { printf 'make_export: 无法进入 %s\n' "$REPO_ROOT" >&2; exit "$EX_BUILD"; }

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    printf 'make_export: %s 不是 git 仓库（导出源是 HEAD，需要提交历史）\n' "$REPO_ROOT" >&2
    exit "$EX_BUILD"
fi
if ! git rev-parse --verify -q HEAD >/dev/null; then
    printf 'make_export: 还没有任何提交（HEAD 不存在），先 commit\n' >&2
    exit "$EX_BUILD"
fi

HEAD_SHA="$(git rev-parse --short=12 HEAD)"
HEAD_SUBJECT="$(git log -1 --pretty=%s HEAD)"
DIRTY="$(git status --porcelain)"

if [ -n "$DIRTY" ]; then
    n_dirty="$(printf '%s\n' "$DIRTY" | grep -c .)"
    printf 'make_export: 注意 — 工作树有 %s 项未提交改动，它们**不会**进导出树：\n' "$n_dirty" >&2
    printf '%s\n' "$DIRTY" | sed 's/^/    /' >&2
fi

# ---------------------------------------------------------------------------
# 组装：先在临时目录里解包，全部自检通过才落到 dest。
# 半个导出树比没有更危险——它看起来能发。
# ---------------------------------------------------------------------------
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/make_export.XXXXXX")" || {
    printf 'make_export: 无法创建临时目录\n' >&2; exit "$EX_BUILD"
}
trap 'rm -rf -- "$STAGING"' EXIT

BUILD="$STAGING/tree"
mkdir -p -- "$BUILD" || { printf 'make_export: 无法创建 %s\n' "$BUILD" >&2; exit "$EX_BUILD"; }

if ! git archive --format=tar HEAD | tar -x -C "$BUILD"; then
    printf 'make_export: git archive HEAD 失败（HEAD=%s）\n' "$HEAD_SHA" >&2
    exit "$EX_BUILD"
fi

n_files="$(cd -- "$BUILD" && find . -type f | wc -l | tr -d ' ')"
printf 'make_export: 导出源 = HEAD %s「%s」；解出 %s 个文件\n' "$HEAD_SHA" "$HEAD_SUBJECT" "$n_files"

# ---------------------------------------------------------------------------
# 落盘（先删后建：这是构建产物，重新生成即可）
# ---------------------------------------------------------------------------
case "$DEST" in
    "$REPO_ROOT"|"$REPO_ROOT"/)
        printf 'make_export: --dest 不能是仓库根（会先删后建，把仓库删掉）\n' >&2
        exit "$EX_USAGE" ;;
esac

rm -rf -- "$DEST" || { printf 'make_export: 无法清理 %s\n' "$DEST" >&2; exit "$EX_BUILD"; }
mkdir -p -- "$(dirname -- "$DEST")" || { printf 'make_export: 无法创建父目录\n' >&2; exit "$EX_BUILD"; }
mv -- "$BUILD" "$DEST" || { printf 'make_export: 无法落盘到 %s\n' "$DEST" >&2; exit "$EX_BUILD"; }

# ---------------------------------------------------------------------------
# 验收：六道门（在落盘后的树上跑，而不是在 staging 里跑）
# ---------------------------------------------------------------------------
VERIFY_ARGS=(--tree "$DEST")
[ "$SKIP_TESTS" -eq 1 ] && VERIFY_ARGS+=(--skip-tests)
# 透传解释器：E4 要跑导出树里的单元测试，而 PATH 上的 python3 未必装了 pytest。
# 缺省由 verify_export.py 自己挑（当前解释器 → PATH 每个 python）；这里只是让调用方能指定。
[ -n "${PYTHON:-}" ] && VERIFY_ARGS+=(--python "$PYTHON")

python3 "$SCRIPT_DIR/verify_export.py" "${VERIFY_ARGS[@]}"
rc=$?

if [ "$rc" -eq "$EX_OK" ]; then
    printf 'make_export: 导出树 %s（HEAD %s）\n' "$DEST" "$HEAD_SHA"
elif [ "$rc" -eq "$EX_VIOLATION" ]; then
    printf 'make_export: 导出树有违规（退出码 %s），见上方逐条列表\n' "$rc" >&2
else
    printf 'make_export: 校验器异常退出（退出码 %s）\n' "$rc" >&2
fi
exit "$rc"
