#!/usr/bin/env bash
# scripts/make_skill.sh —— 组装自包含 skill 目录（Hermes / Codex 两用），复制即用。
#
# 产物（skill 目录本身就是 $HARNESS，不依赖任何项目/部署路径）：
#   foam-mate/
#     SKILL.md          入口卡（$HARNESS = 本目录；description <= 60 字符，Hermes/Codex 都认）
#     scripts/          10 个脚本（复用 make_release.sh 的白名单，含 preflight.sh）
#     references/       三份 harness 文档（release/SKILL.md 原样放这里，名字不变靠子目录避撞；
#                       其 YAML frontmatter 被去掉，避免 Codex 递归索引当成第二个 skill）
#       SKILL.md QUICKSTART.md SCOPE.md
#     VERSION           版本号（provenance）
#     LICENSE           授权（条件复制：仓库根有 LICENSE 才带，同 make_release.sh）
#
# 为什么复用 make_release.sh 而不是再列一份文件清单：
#   文件清单只许一处写值（AGENTS.md R14）。make_release.sh 的 WL_SRC/WL_DST 是权威；这里先
#   `--no-tar` 出平铺包，再把三份 md 挪进 references/、补一张入口卡。两份清单必然漂移。
#
# 为什么三份文档用「放 references/」而不是「改名」：
#   release/SKILL.md 内部用裸名互相引用（"读 QUICKSTART.md"、"读 SCOPE.md"），三份放同一目录
#   里引用继续成立；改名字会同时断掉文档正文里的交叉引用。
#
# 退出码：0 成功 / 60 复用 make_release.sh 的白名单违规（透传）/ 61 组装或落盘失败 / 64 用法错误
#
# 用法：
#   scripts/make_skill.sh --target hermes       # 装到 ~/.hermes/skills/foam-mate/
#   scripts/make_skill.sh --target codex        # 装到 ~/.codex/skills/foam-mate/
#   scripts/make_skill.sh --target both         # 两处都装
#   scripts/make_skill.sh --dest /tmp/foam-mate # 只出目录，不安装

set -uo pipefail

readonly EX_WHITELIST=60   # 透传自 make_release.sh
readonly EX_BUILD=61       # 本脚本自己的组装/落盘失败
readonly EX_USAGE=64

readonly SKILL_NAME="foam-mate"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
readonly REPO_ROOT

usage() {
    cat <<'EOF'
用法: make_skill.sh (--target hermes|codex|both | --dest <dir>) [--help]

  --target hermes|codex|both   复制到对应软件的 skills 路径（hermes=~/.hermes/skills，codex=~/.codex/skills）
  --dest <dir>                 只产出目录树，不安装（绝对路径原样用，相对路径相对仓库根）

退出码: 0 成功 / 60 白名单违规（透传 make_release.sh）/ 61 组装或落盘失败 / 64 用法错误
EOF
}

usage_err() {
    printf 'make_skill: %s\n' "$1" >&2
    usage >&2
    exit "$EX_USAGE"
}

# ---------- 参数 ----------
if [ $# -eq 0 ]; then
    usage_err "缺少参数：至少给 --target 或 --dest"
fi

TARGET=""
DEST=""

while [ $# -gt 0 ]; do
    case "$1" in
        --target)
            [ $# -ge 2 ] || usage_err "--target 需要一个值（hermes|codex|both）"
            case "$2" in
                hermes|codex|both) TARGET="$2" ;;
                *) usage_err "--target 只接受 hermes|codex|both，收到: $2" ;;
            esac
            shift 2 ;;
        --dest)
            [ $# -ge 2 ] || usage_err "--dest 需要一个目录参数"
            [ -n "$2" ]  || usage_err "--dest 的目录参数为空"
            DEST="$2"; shift 2 ;;
        --dest=*)
            DEST="${1#--dest=}"
            [ -n "$DEST" ] || usage_err "--dest 的目录参数为空"
            shift ;;
        --help|-h)
            usage; exit 0 ;;
        *)
            usage_err "未知参数: $1" ;;
    esac
done

[ -n "$TARGET" ] || [ -n "$DEST" ] || usage_err "--target 与 --dest 至少要给一个"

# ---------- 1. 复用 make_release.sh 出平铺包 ----------
STAGING="$(mktemp -d "${TMPDIR:-/tmp}/make_skill.XXXXXX")" || {
    printf 'make_skill: 无法创建临时目录\n' >&2; exit "$EX_BUILD"
}
trap 'rm -rf -- "$STAGING"' EXIT

PKGDIR="$STAGING/releasepkg"
if ! bash "$SCRIPT_DIR/make_release.sh" --no-tar --dest "$PKGDIR"; then
    printf 'make_skill: make_release.sh 白名单违规（退出码 %s），未组装\n' "$EX_WHITELIST" >&2
    exit "$EX_WHITELIST"
fi

VERSION="$(tr -d '\n\r' < "$REPO_ROOT/VERSION")"
FLAT="$PKGDIR/$SKILL_NAME-$VERSION"    # make_release.sh 的 PKG_DIRNAME = foam-mate-<version>
[ -d "$FLAT" ] || {
    printf 'make_skill: 平铺包目录不存在: %s（VERSION=%s 与 PKG_NAME 对不上？）\n' "$FLAT" "$VERSION" >&2
    exit "$EX_BUILD"
}

# ---------- 2. 组装 skill 目录 ----------
SKILL="$STAGING/$SKILL_NAME"
mkdir -p "$SKILL/references" "$SKILL/scripts" || { printf 'make_skill: mkdir 失败\n' >&2; exit "$EX_BUILD"; }

mv "$FLAT/SKILL.md" "$FLAT/QUICKSTART.md" "$FLAT/SCOPE.md" "$SKILL/references/" \
    || { printf 'make_skill: 移动三份文档失败\n' >&2; exit "$EX_BUILD"; }
mv "$FLAT/scripts/"* "$SKILL/scripts/" \
    || { printf 'make_skill: 移动脚本失败\n' >&2; exit "$EX_BUILD"; }
cp "$FLAT/VERSION" "$SKILL/VERSION" 2>/dev/null || printf '%s\n' "$VERSION" > "$SKILL/VERSION"
[ -f "$FLAT/LICENSE" ] && cp "$FLAT/LICENSE" "$SKILL/LICENSE"

# 去掉 references/SKILL.md 的 YAML frontmatter（首尾两个 --- 连同 name/description 一起删），
# 让它成为纯参考文档。原因：Codex 递归扫描 skills 树下每个 SKILL.md 并读其 frontmatter 的
# name，release/SKILL.md 原样带着 `name: openfoam-v13-case-harness`，会让 Codex 把它当成与
# foam-mate 并列的第二条同源 skill（实测 codex debug prompt-input 里出现两条）。
# 只改生成副本，不动项目里的 release/SKILL.md。
awk '
    /^---$/ { if (++dash <= 2) next }
    dash >= 2 { print }
' "$SKILL/references/SKILL.md" > "$SKILL/references/SKILL.md.tmp" \
    && mv "$SKILL/references/SKILL.md.tmp" "$SKILL/references/SKILL.md" \
    || { printf 'make_skill: 去掉 references/SKILL.md frontmatter 失败\n' >&2; exit "$EX_BUILD"; }

# ---------- 3. 写入口卡 ----------
cat > "$SKILL/SKILL.md" <<'ENTRY_CARD'
---
name: foam-mate
description: "Use when 把自然语言 CFD 需求做成 v13 可跑 case。"
---

# FoamMate —— 自包含 harness skill（复制即用）

本 skill 目录**自带**全部脚本与文档，`$HARNESS` 就是本目录，不依赖任何项目仓库或部署路径。
把它复制到 Hermes（`~/.hermes/skills/foam-mate/`）或 Codex（`~/.codex/skills/foam-mate/`）即生效。

**本卡不复述判据。** 判据、命令全文、退出码全表在 `references/SKILL.md`（完整 harness 文档），
动手前必读，冲突以它为准。`references/QUICKSTART.md` 是完整可复现例子，`references/SCOPE.md`
是能做/不能做与许可。

## Step 0 — $HARNESS = 本卡所在目录（唯一需要记的）

```bash
# HARNESS 就是这张 SKILL.md 所在的目录。Hermes 里 skill_view 会给 skill_dir；
# Codex 里它在 ~/.codex/skills/foam-mate/。把它设为 HARNESS 即可，不用猜任何其它路径：
export HARNESS="<本 SKILL.md 所在目录>"
ls "$HARNESS/scripts/preflight.sh" "$HARNESS/references/SKILL.md"   # 两个都该存在
```

- 后面所有命令一律写 `"$HARNESS/scripts/xxx"`，不用相对路径：cwd 是任意的。
- 自检不通过（缺 scripts/ 或 references/）→ 停下问人，不要凭记忆补文件。

## Step 1 — 环境（每个新 shell 一次）

```bash
source /opt/openfoam13/etc/bashrc      # 别在 set -u 的 shell 里 source（bashrc 自身会炸）
bash "$HARNESS/scripts/preflight.sh"   # 0 就绪 / 50 忘 source / 51 版本不对
```

preflight 不是门（功能脚本自己判环境：run_case.sh 缺 foamRun 退 22）。它的唯一价值是区分
「忘 source」和「版本不对」。只在换 shell / 换机器 / 莫名失败时跑。

## Step 2 — 三条不可协商（违反 = 结论作废）

1. 不空写字典，从 tutorial 派生（new_case.sh 校验 source 在 $FOAM_TUTORIALS 下）。
2. 说「能跑」必须先过门禁，证据是命令退出码与日志行，不是读了一遍字典。
3. 不改 /opt/openfoam13；二次开发只走 $WM_PROJECT_USER_DIR（dev_lib.py）。

出处：references/SKILL.md §6，以及项目 AGENTS.md R2/R3/R4。

## Step 3 — 命令骨架（参数以 --help 为准）

```bash
python3 "$HARNESS/scripts/parse_requirement.py" --text "<用户原话>" --out "$WORK/x.spec.json"
bash "$HARNESS/scripts/find_template.sh" --keyword cavity --limit 5
bash "$HARNESS/scripts/new_case.sh" --source <tutorial 相对路径> --dest "$WORK/c1" --spec "$WORK/x.spec.json"
bash "$HARNESS/scripts/run_case.sh"  --case "$WORK/c1" --mode full
bash "$HARNESS/scripts/verify_case.sh" --stage pre  --case "$WORK/c1"
bash "$HARNESS/scripts/verify_case.sh" --stage post --case "$WORK/c1"
python3 "$HARNESS/scripts/fix_case.py" locate --case "$WORK/c1" --error-log "$WORK/c1/log.run" --attempt 1
python3 "$HARNESS/scripts/batch.py" --cases "$WORK/cases.json" --dest "$WORK/runs" --dry-run
python3 "$HARNESS/scripts/dev_lib.py" --stage prepare --source <$FOAM_SRC 下子库> --dest "$WM_PROJECT_USER_DIR/src/<名>" --lib <名>
```

`$WORK` 自选（如 `~/foam-work`），算例别放进 `$HARNESS`。

## Step 4 — 必须停下的时刻

- `parse_requirement.py` 退 10（`missing` 非空）：不要替用户补默认值。
- `preflight.sh` 退 51：版本不对，不要降判据、不要改脚本。
- 几何需要曲面/多体装配/STL/边界层加密：停下问人（只走 blockMesh 或导入外部网格）。
- 门全绿但 `OBJ=`/`GEO=`/`RE=`/`RES=` 诊断与需求不符：那是物理问题，不是门的问题。

## Step 5 — 升级

重新生成并覆盖：在项目仓库里跑 `scripts/make_skill.sh --target hermes|codex|both`，再重跑一次
preflight 验证。升级只覆盖这个 skill 目录，不影响别处。不要手改本目录里的脚本——判据在
references/SKILL.md，脚本坏了以重新生成为准。

## Step 6 — 别做

- 在项目外凭记忆写 OpenFOAM 字典 / 假设 patch 名 / 假设边界条件类型（改从 $FOAM_TUTORIALS grep）。
- 把本目录里的脚本或文档复制到别处当"第二份判据"。
- 说「能跑」时不自带证据——证据永远是那次运行的退出码与日志行。

## Checklist

- [ ] `$HARNESS` = 本 SKILL.md 所在目录，且 `scripts/preflight.sh`、`references/SKILL.md` 都在
- [ ] 本 shell 已 `source /opt/openfoam13/etc/bashrc`
- [ ] 读过 `$HARNESS/references/SKILL.md`（本卡不代替它）
- [ ] case 由 `new_case.sh` 派生，`case.meta` 存在且带 `source`/`spec`/`changes`
- [ ] 「能跑」的结论附着 `verify_case.sh` 的退出码与 `checkMesh` 的 `Mesh OK.` 行
ENTRY_CARD

# ---------- 4. 自检：可执行位 + 关键文件齐备 ----------
VIOL=0
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    [ -x "$SKILL/scripts/$rel" ] || { printf 'make_skill: 脚本缺可执行位: %s\n' "$rel" >&2; VIOL=1; }
done < <(cd "$SKILL/scripts" && find . -type f | sed 's|^\./||' | LC_ALL=C sort)

for need in SKILL.md VERSION references/SKILL.md references/QUICKSTART.md references/SCOPE.md; do
    [ -f "$SKILL/$need" ] || { printf 'make_skill: 缺少文件: %s\n' "$need" >&2; VIOL=1; }
done
[ "$VIOL" -eq 1 ] && exit "$EX_BUILD"

# ---------- 5. 落盘 / 安装 ----------
install_to() {
    local dest="$1"
    rm -rf -- "$dest"
    mkdir -p -- "$(dirname -- "$dest")"
    cp -a -- "$SKILL" "$dest" || { printf 'make_skill: 复制到 %s 失败\n' "$dest" >&2; exit "$EX_BUILD"; }
    printf 'make_skill: 已复制到 %s\n' "$dest"
}

if [ -n "$DEST" ]; then
    case "$DEST" in
        /*) : ;;
        *)  DEST="$REPO_ROOT/$DEST" ;;
    esac
    install_to "$DEST"
else
    case "$TARGET" in
        hermes|both) install_to "$HOME/.hermes/skills/$SKILL_NAME" ;;
    esac
    case "$TARGET" in
        codex|both)  install_to "$HOME/.codex/skills/$SKILL_NAME" ;;
    esac
fi

n_files="$(cd "$SKILL" && find . -type f | wc -l | tr -d ' ')"
printf 'make_skill: skill 目录 %s 文件 %s 个\n' "${DEST:-$TARGET}" "$n_files"
exit 0
