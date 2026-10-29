#!/usr/bin/env bash
# scripts/make_release.sh —— 发布包组装器（P3 · spec D5 / AC6 / C6）
#
# 判据只有一条，但它有四个面（缺一面，绿就是假的）：
#   a) 包内每个 *.sh 过 `bash -n`，每个 *.py 过 `python3 -m py_compile`；
#   b) 包内每个脚本有可执行位；
#   c) 包内没有任何指向 references/repos 的文本；
#   d) 包内文件集合（相对路径，排序）**逐字等于**白名单的映射结果。
#
# 为什么 (d) 是「集合相等」而不是「包含」：
#   包含式判据在第一次往 release/ 里多放一份草稿之后就永久为真，且没人会注意——
#   发布包里会慢慢长出一个 bench/、一份 AGENTS.md，而 README 里的「对外交付物」
#   从那一刻开始撒谎，且没有任何东西会红。相等判据让「多一个」和「少一个」同罪。
#
# 为什么包内是**平铺**布局（release/X.md → X.md）：
#   release/*.md 里所有引用都写成裸文件名（`SKILL.md` / `QUICKSTART.md` / `SCOPE.md`）
#   与 `scripts/<名>`，它们默认的就是「三份 md 与 scripts/ 同级」这个布局。
#   原样保留 release/ 这一层，包里的文档就会互相指向不存在的路径。
#
# 为什么目标目录「先删后建」而不是「已存在即拒绝」：
#   这是构建产物（dist/），不是用户数据。new_case.sh 对 dest 已存在退 13 是因为
#   那底下是用户算例，删了不可恢复；这里删的永远可以重新生成。
#
# 退出码：0 成功 / 60 白名单或包内容违规 / 64 用法错误
#   60 不与任何业务码冲突（0–5 门、10–13、20–23、31–33、40、50/51），spec §7 C6。
#
# 用法：
#   scripts/make_release.sh --dest dist
#   scripts/make_release.sh --dest /tmp/try --no-tar
#   scripts/make_release.sh --help

set -uo pipefail

readonly EX_WHITELIST=60   # 白名单违规 / 包内容自检失败
readonly EX_USAGE=64       # 用法错误（不用 2：2 在 verify_case.sh 里是「G2 网格门失败」）
readonly PKG_NAME="foam-mate"

# 仓库根按脚本位置推导（BASH_SOURCE → 脚本目录 → 父目录），不写死任何绝对路径：
# 组装器必须能在「包被解到任意目录」后仍然工作，而测试会把它跑在 tmp_path 的副本上。
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
readonly REPO_ROOT

usage() {
    cat <<'EOF'
用法: make_release.sh [--dest <dir>] [--no-tar] [--help]

  --dest <dir>   产物目录，缺省 dist（相对仓库根；绝对路径原样使用）
  --no-tar       只出目录树，不打 .tar.gz（测试用）
  --help         显示本帮助并退出 0

退出码: 0 成功 / 60 白名单或包内容违规 / 64 用法错误
EOF
}

usage_err() {
    printf 'make_release: %s\n' "$1" >&2
    usage >&2
    exit "$EX_USAGE"
}

# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------
# 无参数 = 用法错误（spec D5 的契约由 tests/unit/test_exit_codes.py 守：
# 不传参数必须退 64，不能退 0——退 0 会让「忘了写 --dest」静默地在仓库根建 dist/）。
if [ $# -eq 0 ]; then
    usage_err "缺少参数：至少要让调用意图明确（--dest <dir> 或 --no-tar）"
fi

DEST="dist"
NO_TAR=0

while [ $# -gt 0 ]; do
    case "$1" in
        --dest)
            [ $# -ge 2 ] || usage_err "--dest 需要一个目录参数"
            [ -n "$2" ]  || usage_err "--dest 的目录参数为空"
            DEST="$2"
            shift 2
            ;;
        --dest=*)
            DEST="${1#--dest=}"
            [ -n "$DEST" ] || usage_err "--dest 的目录参数为空"
            shift
            ;;
        --no-tar)
            NO_TAR=1
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            usage_err "未知参数: $1"
            ;;
    esac
done

case "$DEST" in
    /*) : ;;
    *)  DEST="$REPO_ROOT/$DEST" ;;
esac

# ---------------------------------------------------------------------------
# 违规收集：一次跑完所有检查再报，而不是撞到第一个就退出
# （撞到就退会让人「修一处、再跑、再红、再修」，四轮才看清全貌）
# ---------------------------------------------------------------------------
VIOLATIONS=()
violation() {
    VIOLATIONS+=("$1")
    printf 'FAIL %s\n' "$1" >&2
}

# ---------------------------------------------------------------------------
# 白名单：进包的**源文件全集**。左列相对仓库根，右列相对包根（映射）。
# LICENSE 只在仓库根真有它时才进包——没有 LICENSE 的包不合法，但「这个仓库
# 还没定许可证」不该把组装器卡死（spec §5：许可证是 v0.1 的未决项）。
# ---------------------------------------------------------------------------
WL_SRC=(
    "VERSION"
    "release/SKILL.md"
    "release/QUICKSTART.md"
    "release/SCOPE.md"
    "scripts/preflight.sh"
    "scripts/parse_requirement.py"
    "scripts/find_template.sh"
    "scripts/new_case.sh"
    "scripts/run_case.sh"
    "scripts/verify_case.sh"
    "scripts/fix_case.py"
    "scripts/batch.py"
    "scripts/msh2d_to_foam.py"
)
WL_DST=(
    "VERSION"
    "SKILL.md"
    "QUICKSTART.md"
    "SCOPE.md"
    "scripts/preflight.sh"
    "scripts/parse_requirement.py"
    "scripts/find_template.sh"
    "scripts/new_case.sh"
    "scripts/run_case.sh"
    "scripts/verify_case.sh"
    "scripts/fix_case.py"
    "scripts/batch.py"
    "scripts/msh2d_to_foam.py"
)

if [ -f "$REPO_ROOT/LICENSE" ]; then
    WL_SRC+=("LICENSE")
    WL_DST+=("LICENSE")
fi

# WL_SRC / WL_DST 是**平行数组**（源路径 → 包内路径，靠下标对应）。只给一边加条目会
# 在后面的 `${WL_DST[$i]}` 处报 `unbound variable`——那个报错看不出是"清单没同步"，
# 2026-10-29 加 batch.py 时实测踩过。所以在这里显式断言长度相等并指名道姓。
if [ "${#WL_SRC[@]}" -ne "${#WL_DST[@]}" ]; then
    printf 'make_release: 白名单错位：WL_SRC 有 %d 条、WL_DST 有 %d 条（两个数组必须等长）\n' \
        "${#WL_SRC[@]}" "${#WL_DST[@]}" >&2
    exit 60
fi

# 禁用清单：包内出现即 60。分三类是因为匹配方式不同——
# 前缀（整棵目录）、裸名（根目录文件）、精确路径（项目治理脚本）。
FORBIDDEN_PREFIX=("bench/" "references/" "tests/" "specs/" "release/" ".git/" ".hermes/" "dist/")
FORBIDDEN_EXACT=("AGENTS.md" "STATUS.md" "README.md" "CHANGELOG.md"
                 "scripts/check_contracts.py" "scripts/status_snapshot.py"
                 "scripts/verify_references.sh" "scripts/check_release_docs.py"
                 "scripts/make_release.sh"
                 # 导出树组装器与校验器：维护侧工具，服务的是**仓库**而不是**用户包**，
                 # 所以不进 12 文件包；登记在这里是为了让「scripts/ 下有白名单未收录的文件」
                 # 这条源树检查认得它们（新增维护脚本必须同时登记，否则组装器退 60——
                 # 实测形态：加完 make_export.sh 后 tests/unit/test_batch.py 立刻红）。
                 "scripts/make_export.sh" "scripts/verify_export.py")

is_forbidden() {
    local rel="$1"
    case "$rel" in
        */__pycache__/*|__pycache__/*|*.pyc) return 0 ;;
    esac
    local p
    for p in "${FORBIDDEN_PREFIX[@]}"; do
        case "$rel" in "$p"*) return 0 ;; esac
    done
    local e
    for e in "${FORBIDDEN_EXACT[@]}"; do
        [ "$rel" = "$e" ] && return 0
    done
    return 1
}

# 源文件是否在白名单里（按仓库相对路径判）
in_whitelist_src() {
    local want="$1" s
    for s in "${WL_SRC[@]}"; do
        [ "$s" = "$want" ] && return 0
    done
    return 1
}

# ---------------------------------------------------------------------------
# VERSION
# ---------------------------------------------------------------------------
if [ ! -f "$REPO_ROOT/VERSION" ]; then
    violation "仓库根缺少 VERSION（发布包的版本来源）"
    VERSION=""
else
    VERSION="$(tr -d '\n\r' < "$REPO_ROOT/VERSION")"
fi
if [ -n "$VERSION" ] && ! printf '%s' "$VERSION" | grep -Eq '^[0-9A-Za-z][0-9A-Za-z._-]*$'; then
    violation "VERSION 内容不是可用的版本串: '$VERSION'（只允许字母数字与 . _ -）"
fi
if [ -z "$VERSION" ]; then
    printf 'make_release: 白名单违规 %d 处，未生成发布包。\n' "${#VIOLATIONS[@]}" >&2
    exit "$EX_WHITELIST"
fi

PKG_DIRNAME="$PKG_NAME-$VERSION"

# ---------------------------------------------------------------------------
# 源侧完整性：组装器只能复制白名单里点名的文件，所以「目录里多出一个文件」
# 在复制阶段是**看不见**的。这正是 T3.7 的变异（往 release/ 偷放一个文件）要求
# 必须退 60 的原因——检查必须落在源树上，否则变异只会被静默忽略，绿得毫无意义。
# ---------------------------------------------------------------------------
if [ ! -d "$REPO_ROOT/release" ]; then
    violation "缺少 release/ 目录（三份入口文档的来源）"
else
    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        in_whitelist_src "release/$rel" \
            || violation "release/ 下有白名单未收录的文件: release/$rel"
    done < <(cd "$REPO_ROOT/release" && find . -type f | sed 's|^\./||' | LC_ALL=C sort)
fi

if [ ! -d "$REPO_ROOT/scripts" ]; then
    violation "缺少 scripts/ 目录"
else
    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        case "$rel" in */__pycache__/*|*.pyc) continue ;; esac
        in_whitelist_src "scripts/$rel" && continue
        # scripts/ 下另有项目治理脚本（契约检查、状态快照、参考库门）——
        # 它们**不进包**是设计，不是遗漏，所以不算违规；除此之外的陌生文件才算。
        is_forbidden "scripts/$rel" \
            || violation "scripts/ 下有白名单未收录的文件: scripts/$rel"
    done < <(cd "$REPO_ROOT/scripts" && find . -type f | sed 's|^\./||' | LC_ALL=C sort)
fi

# 白名单点名的源文件必须真的存在（少一个 = 60）
for s in "${WL_SRC[@]}"; do
    [ -f "$REPO_ROOT/$s" ] || violation "白名单源文件不存在: $s"
done

if [ "${#VIOLATIONS[@]}" -gt 0 ]; then
    printf 'make_release: 白名单违规 %d 处，未生成发布包。\n' "${#VIOLATIONS[@]}" >&2
    printf '下一步：删掉上面点名的多余文件，或补上缺失的白名单文件后重跑。\n' >&2
    exit "$EX_WHITELIST"
fi

# ---------------------------------------------------------------------------
# 组装：先在 mktemp 的临时目录里建好，全部自检通过才落到 dest。
# 这样「失败」不会在 dist/ 里留下半个包——半个包比没有包更危险，它看起来能发。
# ---------------------------------------------------------------------------
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/make_release.XXXXXX")" || {
    printf 'make_release: 无法创建临时目录\n' >&2
    exit "$EX_WHITELIST"
}
trap 'rm -rf -- "$STAGING"' EXIT
BUILD_PKG="$STAGING/$PKG_DIRNAME"
mkdir -p "$BUILD_PKG"

for i in "${!WL_SRC[@]}"; do
    src="$REPO_ROOT/${WL_SRC[$i]}"
    dst="$BUILD_PKG/${WL_DST[$i]}"
    [ -f "$src" ] || { violation "复制源缺失: ${WL_SRC[$i]}"; continue; }
    mkdir -p -- "$(dirname -- "$dst")"
    # cp -p 保留权限位：可执行位是 b) 的判据，丢了它包里的脚本只能 `bash x.sh` 调用
    cp -p -- "$src" "$dst" || violation "复制失败: ${WL_SRC[$i]}"
done

# ---------------------------------------------------------------------------
# 自检 a) + c) + b) + d)
# ---------------------------------------------------------------------------
actual_list="$(cd "$BUILD_PKG" && find . -type f | sed 's|^\./||' | LC_ALL=C sort)"

# c) references/repos 文本：包里出现这类路径 = 把第三方参考库的坐标漏进了对外文档
while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    violation "包内文件含指向 references/repos 的文本: ${hit#"$BUILD_PKG"/}"
done < <(grep -rlF 'references/repos' "$BUILD_PKG" 2>/dev/null || true)

# 禁用清单（包内，含目录）
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    [ "$rel" = "." ] && continue
    if is_forbidden "$rel"; then
        violation "包内出现禁用路径: $rel"
    fi
done < <(cd "$BUILD_PKG" && find . \( -type f -o -type d \) | sed 's|^\./||' | LC_ALL=C sort | grep -v '^$' || true)

# a) 语法：bash -n / py_compile。py_compile 的缓存目录指向临时区，
#    否则它会在包里造 __pycache__，然后被 d) 判成「多出来的文件」——自检污染自己。
PYCACHE_ROOT="$STAGING/pycache"
PYTHON_BIN="$(command -v python3 || true)"
[ -n "$PYTHON_BIN" ] || violation "python3 不在 PATH，无法校验包内 *.py"
need_py=0
while IFS= read -r rel; do
    case "$rel" in
        *.sh)
            if ! err="$(bash -n "$BUILD_PKG/$rel" 2>&1)"; then
                violation "bash -n 失败: $rel — $(printf '%s' "$err" | head -1)"
            fi
            ;;
        *.py)
            need_py=1
            [ -n "$PYTHON_BIN" ] || continue
            if ! err="$(PYTHONPYCACHEPREFIX="$PYCACHE_ROOT" "$PYTHON_BIN" -m py_compile "$BUILD_PKG/$rel" 2>&1)"; then
                violation "py_compile 失败: $rel — $(printf '%s' "$err" | tail -1)"
            fi
            ;;
    esac
done <<< "$actual_list"

# b) 可执行位：包内 scripts/ 下每个文件都必须能直接执行
while IFS= read -r rel; do
    case "$rel" in
        scripts/*)
            [ -x "$BUILD_PKG/$rel" ] \
                || violation "包内脚本没有可执行位: $rel（修法: chmod +x scripts/$(basename -- "$rel")）"
            ;;
    esac
done <<< "$actual_list"

# d) 集合相等：逐字比对，多一个少一个都点名
expected_list="$(printf '%s\n' "${WL_DST[@]}" | LC_ALL=C sort)"
if [ "$expected_list" != "$actual_list" ]; then
    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        violation "包内多出白名单外的文件: $rel"
    done < <(comm -13 <(printf '%s\n' "$expected_list") <(printf '%s\n' "$actual_list"))
    while IFS= read -r rel; do
        [ -n "$rel" ] || continue
        violation "包内缺少白名单要求的文件: $rel"
    done < <(comm -23 <(printf '%s\n' "$expected_list") <(printf '%s\n' "$actual_list"))
fi

if [ "${#VIOLATIONS[@]}" -gt 0 ]; then
    printf 'make_release: 白名单违规 %d 处，未生成发布包。\n' "${#VIOLATIONS[@]}" >&2
    printf '下一步：按上面点名逐条处理（多半是 release/ 或 scripts/ 里多了文件）。\n' >&2
    exit "$EX_WHITELIST"
fi

# ---------------------------------------------------------------------------
# 落盘：先删后建（幂等），再按需打 tar
# ---------------------------------------------------------------------------
mkdir -p -- "$DEST" || { printf 'make_release: 无法创建 %s\n' "$DEST" >&2; exit "$EX_WHITELIST"; }
rm -rf -- "$DEST/$PKG_DIRNAME" || { printf 'make_release: 无法清理 %s\n' "$DEST/$PKG_DIRNAME" >&2; exit "$EX_WHITELIST"; }
mv -- "$BUILD_PKG" "$DEST/$PKG_DIRNAME" || {
    printf 'make_release: 无法落盘到 %s\n' "$DEST/$PKG_DIRNAME" >&2
    exit "$EX_WHITELIST"
}

file_count="$(cd "$DEST/$PKG_DIRNAME" && find . -type f | wc -l | tr -d ' ')"
printf 'make_release: 包目录 %s\n' "$DEST/$PKG_DIRNAME"
printf 'make_release: 文件 %s 个（白名单 %s 条，逐字相等）\n' "$file_count" "${#WL_DST[@]}"

if [ "$NO_TAR" -eq 0 ]; then
    TARBALL="$DEST/$PKG_DIRNAME.tar.gz"
    rm -f -- "$TARBALL"
    # -C 到 dest 再 tar 目录名：归档内顶层就是 foam-mate-<版本>/，不带绝对路径
    if ! tar -czf "$TARBALL" -C "$DEST" "$PKG_DIRNAME"; then
        printf 'make_release: 打包失败: %s\n' "$TARBALL" >&2
        exit "$EX_WHITELIST"
    fi
    printf 'make_release: 归档 %s\n' "$TARBALL"
fi

exit 0
