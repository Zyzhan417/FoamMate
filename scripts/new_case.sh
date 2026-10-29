#!/usr/bin/env bash
# scripts/new_case.sh —— 模块 C：从 tutorial 派生新 case + 写 case.meta
#
# 契约（references/09-architecture-and-test-plan.md:143-158，C1…C7 在 :350-356）：
#   输入：--source <tutorial 路径> --dest <目录> --spec <四元组 JSON 文件>
#         [--allowed a,b,c]         # 覆盖 case.meta.allowed_files（G5 白名单）
#   输出：<dest>/ 文件树（= source 的逐字节副本）+ <dest>/case.meta（六键）
#
# 派生方式：cp -a（D11，:147）。**不用 foamCloneCase**——它有三处隐式行为让 C1/C4 判据不可判定：
#   ① 只复制 `file` 认得的 shell 脚本（/opt/openfoam13/bin/foamCloneCase:259-264）
#   ② 对时间目录删 phi / Uf / uniform（:80）
#   ③ 目标已存在直接 error 退出（:215，与 C4「两个 dest」并不冲突，但与「不覆盖」的显式退出码语义不同）
#
# source 校验（三条全过才算合法，任一不过 → 退出 12，且 **dest 完全不存在**）：
#   ① 目录存在
#   ② realpath 后在 $FOAM_TUTORIALS 下（用 realpath 规范化，防 ../ 与软链绕过；R3）
#   ③ 含 system/controlDict
#
# case.meta 六键：
#   source         相对 $FOAM_TUTORIALS 的路径（不带前导 /）
#   derived_at     ISO8601 带时区（本机时区）
#   spec           --spec 文件解析出的 JSON，原样（D5）
#   changes        初始空数组（派生本身不算改动）
#   allowed_files  默认 ["system/*","constant/*","0/*"]，可被 --allowed 覆盖
#   schema_version 常量 1
#
# 退出码：0 成功（写完 case.meta 才算） / 12 source 不合法 / 13 dest 已存在（不覆盖、不改动）
#         / 64 用法错误或前置不满足（缺参数、参数非法、--spec 不存在或非法 JSON、
#           找不到 python3、cp/写 case.meta 失败）
#   注：64 不用 2——2 在 verify_case.sh 里是「G2 网格门失败」，混用会让调用方
#       无法区分「我调错了」与「这个 case 网格没过」。
#
# 用法：
#   source "$WM_PROJECT_DIR/etc/bashrc"      # 需要 $FOAM_TUTORIALS
#   bash scripts/new_case.sh \
#       --source incompressibleFluid/cavity \
#       --dest cases/cavity-01 \
#       --spec cases/cavity-01.spec.json
#   # 相对路径的 --source 先按当前目录解析，不存在再按 $FOAM_TUTORIALS/<path> 解析。

set -uo pipefail

readonly SCRIPT_NAME="new_case.sh"
readonly DEFAULT_ALLOWED="system/*,constant/*,0/*"
readonly META_DIRS_DEFAULT=("system/*" "constant/*" "0/*")

die() {
    local code="$1"
    shift
    printf '%s: %s\n' "$SCRIPT_NAME" "$*" >&2
    exit "$code"
}

usage() {
    cat >&2 <<'EOF'
用法: new_case.sh --source <tutorial 路径> --dest <目录> --spec <JSON 文件> [--allowed a,b,c]

  --source   必填。tutorial 目录（绝对路径，或相对当前目录 / 相对 $FOAM_TUTORIALS）。
             必须在 $FOAM_TUTORIALS 下且含 system/controlDict，否则退出 12。
  --dest     必填。目标目录。已存在 → 退出 13（不覆盖、不改动它）。
  --spec     必填。四元组 JSON 文件（geometry/properties/boundary/objective）。
             文件不存在或不是合法 JSON → 退出 2。
  --allowed  可选。逗号分隔的白名单，覆盖 case.meta.allowed_files。
             默认 system/*,constant/*,0/*

退出码: 0 成功 / 12 source 不合法 / 13 dest 已存在 / 64 用法错误
EOF
}

# ---------- 参数解析 ----------
SOURCE=""
DEST=""
SPEC_FILE=""
ALLOWED_RAW=""
ALLOWED_SET=0

while [ $# -gt 0 ]; do
    case "$1" in
        --source)      [ $# -ge 2 ] || die 64 "--source 缺少参数值";  SOURCE="$2"; shift 2 ;;
        --source=*)    SOURCE="${1#--source=}"; shift ;;
        --dest)        [ $# -ge 2 ] || die 64 "--dest 缺少参数值";    DEST="$2";   shift 2 ;;
        --dest=*)      DEST="${1#--dest=}"; shift ;;
        --spec)        [ $# -ge 2 ] || die 64 "--spec 缺少参数值";    SPEC_FILE="$2"; shift 2 ;;
        --spec=*)      SPEC_FILE="${1#--spec=}"; shift ;;
        --allowed)     [ $# -ge 2 ] || die 64 "--allowed 缺少参数值"; ALLOWED_RAW="$2"; ALLOWED_SET=1; shift 2 ;;
        --allowed=*)   ALLOWED_RAW="${1#--allowed=}"; ALLOWED_SET=1; shift ;;
        -h|--help)     usage; exit 0 ;;
        *)             usage; die 64 "未知参数: $1" ;;
    esac
done

[ -n "$SOURCE" ]     || { usage; die 64 "必须给 --source"; }
[ -n "$DEST" ]       || { usage; die 64 "必须给 --dest"; }
[ -n "$SPEC_FILE" ]  || { usage; die 64 "必须给 --spec"; }

# ---------- 白名单：默认值或被 --allowed 覆盖 ----------
allowed=()
if [ "$ALLOWED_SET" -eq 1 ]; then
    IFS=',' read -r -a _raw <<< "$ALLOWED_RAW"
    for item in ${_raw[@]+"${_raw[@]}"}; do
        item="${item#"${item%%[![:space:]]*}"}"     # 去前导空白
        item="${item%"${item##*[![:space:]]}"}"     # 去尾随空白
        [ -n "$item" ] && allowed+=("$item")
    done
    [ ${#allowed[@]} -gt 0 ] || die 64 "--allowed 解析后为空: ${ALLOWED_RAW}"
else
    allowed=("${META_DIRS_DEFAULT[@]}")
fi

# ---------- --spec 校验（文件存在 + 合法 JSON，否则 2） ----------
PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || die 64 "找不到 $PYTHON：写 case.meta 需要 python3（只用标准库 json）"

[ -e "$SPEC_FILE" ] || die 64 "--spec 文件不存在: $SPEC_FILE"
[ -f "$SPEC_FILE" ] || die 64 "--spec 不是普通文件: $SPEC_FILE"
"$PYTHON" -c 'import json,sys; json.load(open(sys.argv[1], encoding="utf-8"))' "$SPEC_FILE" 2>/dev/null \
    || die 64 "--spec 不是合法 JSON: $SPEC_FILE"

# ---------- 路径规范化 ----------
# dest 去尾随 /（保留根 "/"）；不做 realpath，因为 dest 本来就不该存在
while [ "${DEST%/}" != "$DEST" ] && [ "$DEST" != "/" ]; do DEST="${DEST%/}"; done
[ -n "$DEST" ] && [ "$DEST" != "/" ] || die 64 "--dest 不能是根目录 /"

# source：先按原样，再按 $FOAM_TUTORIALS/<path>（相对路径两种口径都支持）
src=""
if [ -e "$SOURCE" ]; then
    src="$SOURCE"
elif [ -n "${FOAM_TUTORIALS:-}" ] && [ -e "$FOAM_TUTORIALS/$SOURCE" ]; then
    src="$FOAM_TUTORIALS/$SOURCE"
else
    src="$SOURCE"          # 留原值，下面统一按「不存在」退 12
fi

# ---------- source 校验三条（任一不过 → 12，且 dest 不产生） ----------
[ -d "$src" ] || die 12 "source 不是目录（不存在？）: $SOURCE"
src_real="$(realpath -e -- "$src" 2>/dev/null)" || die 12 "source 无法解析为真实路径（可能是断链）: $SOURCE"
[ -n "$src_real" ] || die 12 "source 无法解析为真实路径: $SOURCE"

[ -n "${FOAM_TUTORIALS:-}" ] \
    || die 12 "环境变量 FOAM_TUTORIALS 为空：R3 只允许从 tutorial 派生（先 source OpenFOAM 的 bashrc）"
[ -d "$FOAM_TUTORIALS" ] || die 12 "FOAM_TUTORIALS 不是目录: $FOAM_TUTORIALS"
tut_real="$(realpath -e -- "$FOAM_TUTORIALS" 2>/dev/null)" || die 12 "FOAM_TUTORIALS 无法解析为真实路径: $FOAM_TUTORIALS"
tut_real="${tut_real%/}"

case "$src_real/" in
    "$tut_real"/*) : ;;
    *) die 12 "source 不在 \$FOAM_TUTORIALS 下（R3 禁止）：$src_real 不在 $tut_real 下" ;;
esac

[ -f "$src_real/system/controlDict" ] \
    || die 12 "source 缺 system/controlDict，不是可派生的 case: $src_real"

# ---------- dest 已存在 → 13（不覆盖、不改动） ----------
[ -e "$DEST" ] && die 13 "dest 已存在，拒绝覆盖（由调用方决定要不要先删）: $DEST"
[ -L "$DEST" ] && die 13 "dest 已存在（符号链接），拒绝覆盖: $DEST"

# ---------- 派生（cp -a，D11） ----------
parent="$(dirname -- "$DEST")"
[ -d "$parent" ] || mkdir -p -- "$parent" || die 64 "无法创建父目录: $parent"

# "$src_real/." 而不是 "$src_real"：前者把内容铺进 dest，后者会多一层同名子目录
cp -a -- "$src_real/." "$DEST/" || {
    rm -rf -- "$DEST"          # 只删我们自己刚创建的东西（上面的 [ -e ] 已保证此前不存在）
    die 64 "cp -a 失败，已回滚 dest: $src_real -> $DEST"
}

# ---------- case.meta（六个键，UTF-8 中文不转义） ----------
src_rel="$("$PYTHON" - "$SPEC_FILE" "$src_real" "$tut_real" "$DEST" ${allowed[@]+"${allowed[@]}"} <<'PY'
import datetime
import json
import os
import sys

spec_path, src_real, tut_real, dest = sys.argv[1:5]
allowed = list(sys.argv[5:])

with open(spec_path, encoding="utf-8") as fh:
    spec = json.load(fh)

rel = os.path.relpath(src_real, tut_real)
meta = {
    "source": rel if rel != "." else "",
    "derived_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    "spec": spec,
    "changes": [],
    "allowed_files": allowed,
    "schema_version": 1,
}
with open(os.path.join(dest, "case.meta"), "w", encoding="utf-8", newline="\n") as fh:
    json.dump(meta, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

print(meta["source"])
PY
)"
meta_rc=$?
[ "$meta_rc" -eq 0 ] || {
    rm -rf -- "$DEST"
    die 64 "写 case.meta 失败，已回滚 dest（没有 case.meta 的目录不算 case）: $DEST"
}

[ -f "$DEST/case.meta" ] || die 64 "写完但 case.meta 不存在（不可预期的失败）: $DEST/case.meta"

printf 'DERIVED=%s\n' "$DEST"
printf 'SOURCE=%s\n' "$src_rel"
exit 0
