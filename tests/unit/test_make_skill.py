"""组装产物契约：`scripts/make_skill.sh` 产出的 skill 目录必须**可直接被 Hermes/Codex 加载**。

## 为什么这一层必须有

`make_skill.sh` 是全仓唯一零测试覆盖的脚本（证据：`rg -n "make_skill" tests/` → 0 命中），
而它的产物是交付物：入口卡的 frontmatter、`scripts/` 的可执行位、`references/` 的文档形态
任何一处错，用户复制过去之后**不会有人报错，只会悄悄不生效**。

两个真实事故，都是「对组装产物做清单断言」本该抓到、且当时没有任何测试能抓到的类型
（证据：`git -C . log --oneline -- scripts/make_skill.sh`）：

    8d4a476 fix(scripts): make_skill.sh 的可执行位自检查错目录（$SKILL → $SKILL/scripts）
    9c4323a fix(scripts): make_skill.sh 补 LICENSE 并去掉 references/SKILL.md 的 frontmatter

8d4a476 的形态最贵：自检代码在，但它检查的是 `$SKILL` 而不是 `$SKILL/scripts`，于是
「脚本有没有可执行位」这条自检**永远绿**。9c4323a 同样：少了 LICENSE、`references/SKILL.md`
带 frontmatter 都发生在脚本「自检通过」之后。所以本文件不复用脚本自己的自检结论，
而是**独立读产物**——判据与实现分离，实现里那类目录写错不会被继承进来。

420e76c（`docs: 说明 skill 入口卡与 references/SKILL.md 是两份独立文件`）补的是同一族问题的
文档面：入口卡曾被当成「被裁剪的短版」，于是有人可能把两份合并，或让 references 那份重新
带上 frontmatter（Codex 递归索引会把同一份 frontmatter 当成并列第二条 skill，
见 `make_skill.sh:127-131` 的实测记录）。

## 判据为什么从 `WL_SRC` 派生，而不是在这里再写一份脚本名

用户面脚本集合的**唯一权威是 `WL_SRC`**（`scripts/make_release.sh`，`make_skill.sh` 复用同一份
白名单）。本项目已经有「同一份清单多处置值」的维护债，测试再抄一份就是又加一处：白名单加了
脚本而测试没加 → 这条判据对那个脚本空转，且看不出来。所以 `whitelist_scripts()` 用正则从
`WL_SRC=( ... )` 块里读条目，只取 `scripts/` 下的部分（`WL_SRC` 里还有 VERSION 与三份
`release/*.md`，它们不是脚本）。派生为空不是「通过」，`test_whitelist_derivation_is_real`
专门守这一点。

## 尺子有牙

本项目口径：绿只在「改坏就红」时才算证据。所以每个判据都写成**接受路径参数的纯函数**
（`card_description_violations` / `non_executable_scripts` / `has_frontmatter`），
并在 `tmp_path` 里造合成坏产物证明它会拒绝：

- `description` 61 字符 → 违规；正好 60 → 通过（60 是 Hermes/Codex 的字段上限，
  见 `make_skill.sh:6` 的注释）；
- 一个 644 的 `.sh` → 被判出；
- 开头带 `---` 的 md → 被判出。

合成产物只写在 `tmp_path`，真实仓库文件一个都不动。

## 边界

L1：不 source `bashrc`、不跑 `foamRun`/`checkMesh`、不联网、不写仓库内文件。
真脚本只被调用一次（module 级 fixture），落盘目标是 `tmp_path`——**绝不传 `--target`**：
`install_to()` 会先 `rm -rf` 目标目录，`--target hermes` 会删掉 `~/.hermes/skills/foam-mate`。
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKE_SKILL = REPO_ROOT / "scripts" / "make_skill.sh"
MAKE_RELEASE = REPO_ROOT / "scripts" / "make_release.sh"
BASH = "/usr/bin/bash"

#: `description` 的长度上限，Hermes 与 Codex 都按这个判（出处：`make_skill.sh:6`）。
DESCRIPTION_LIMIT = 60

#: 入口卡必须承诺的两件事：`$HARNESS` = 本目录、完整判据在 `references/SKILL.md`。
CARD_POINTERS = ("$HARNESS", "references/SKILL.md")


# ---------------------------------------------------------------------------
# 判据（纯函数，只读路径参数；真实产物与合成坏产物走同一条代码）
# ---------------------------------------------------------------------------
def parse_frontmatter(text: str) -> dict[str, str]:
    """解析 md 开头的最小 YAML frontmatter（单行 `key: value`，值可带引号）。

    不引入 PyYAML：入口卡只有 name/description 两个键，全仓也是标准库 + bash 的定位
    （`requirements-dev.txt` 只有 pytest）。没有 frontmatter 时返回空 dict——「没有」与
    「有但解析不出」由调用方的违规列表区分，不塞进异常里。
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return {}  # 没见到收尾的 ---：不是完整 frontmatter，按「没有」处理


def card_description_violations(skill_dir: Path) -> list[str]:
    """入口卡 description 的违规列表（空 = 通过）。

    返回列表而不是布尔：调用方能一次看到「缺字段」与「超长」两种情况，且合成产物的
    断言可以说出它抓到的是哪一条，不是笼统的 `assert not ok`。
    """
    card = skill_dir / "SKILL.md"
    if not card.is_file():
        return [f"缺少入口卡: {card}"]
    fields = parse_frontmatter(card.read_text(encoding="utf-8"))
    if not fields:
        return ["入口卡开头没有完整的 YAML frontmatter"]
    desc = fields.get("description", "")
    if not desc:
        return ["frontmatter 里没有 description"]
    if len(desc) > DESCRIPTION_LIMIT:
        return [
            f"description 长 {len(desc)} 字符，超过上限 {DESCRIPTION_LIMIT}：{desc!r}"
        ]
    return []


def card_name(skill_dir: Path) -> str:
    """入口卡的 `name`；没有 frontmatter 时为空串（由调用方的断言给出消息）。"""
    card = skill_dir / "SKILL.md"
    if not card.is_file():
        return ""
    return parse_frontmatter(card.read_text(encoding="utf-8")).get("name", "")


def script_files(skill_dir: Path) -> list[str]:
    """产物 `scripts/` 下的文件名集合（相对该目录，排序）。"""
    scripts = skill_dir / "scripts"
    if not scripts.is_dir():
        return []
    return sorted(
        str(p.relative_to(scripts)) for p in scripts.rglob("*") if p.is_file()
    )


def non_executable_scripts(skill_dir: Path) -> list[str]:
    """产物 `scripts/` 下缺可执行位的文件（空 = 通过）。

    不用 `p.stat().st_mode & 0o111` 自己算：`os.access(p, os.X_OK)` 是「这个文件按当前
    用户能不能直接执行」，正是用户复制过去后要的那件事。8d4a476 的事故形态是判据落在了
    父目录上（`$SKILL` 而非 `$SKILL/scripts`），本函数按文件遍历，不会再退回成目录级判断。
    """
    scripts = skill_dir / "scripts"
    if not scripts.is_dir():
        return ["缺少 scripts/ 目录"]
    return [rel for rel in script_files(skill_dir) if not os.access(scripts / rel, os.X_OK)]


def has_frontmatter(path: Path) -> bool:
    """文件是否以 `---` 开头（= 带着会被 Codex 当成 skill 声明的 frontmatter）。"""
    with path.open("rb") as fh:
        first = fh.readline(200)
    return first.decode("utf-8", "replace").strip() == "---"


def text_files(skill_dir: Path) -> list[Path]:
    """产物里的所有普通文件（本目录的产物全是文本，按字节扫即可）。"""
    return sorted(p for p in skill_dir.rglob("*") if p.is_file())


def whitelist_entries() -> list[str]:
    """`make_release.sh` 里 `WL_SRC=( ... )` 的条目（源路径，相对仓库根）。"""
    text = MAKE_RELEASE.read_text(encoding="utf-8")
    block = re.search(r"^WL_SRC=\(\n(.*?)^\)", text, re.MULTILINE | re.DOTALL)
    assert block, f"{MAKE_RELEASE} 里找不到 WL_SRC=( ... ) 块——派生失败，判据不能空转"
    entries = re.findall(r'"([^"]+)"', block.group(1))
    assert entries, "WL_SRC 块解析出 0 条，判据不能空转"
    return entries


def whitelist_scripts() -> list[str]:
    """`WL_SRC` 里属于 `scripts/` 的条目 → 文件名集合（用户面脚本的唯一权威）。"""
    return sorted(Path(e).name for e in whitelist_entries() if e.startswith("scripts/"))


# ---------------------------------------------------------------------------
# 真实产物（只调一次；落盘到 tmp_path，绝不传 --target）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Build:
    proc: subprocess.CompletedProcess[str]
    skill_dir: Path


@pytest.fixture(scope="module")
def build(tmp_path_factory: pytest.TempPathFactory) -> Build:
    """跑一次真脚本，产物落在临时目录（`--dest` 绝对路径，不安装）。"""
    root = tmp_path_factory.mktemp("make_skill")
    scratch = root / "tmpdir"
    scratch.mkdir()
    dest = root / "foam-mate"

    cmd = [BASH, str(MAKE_SKILL), "--dest", str(dest)]
    assert "--target" not in cmd, "install_to() 会 rm -rf 目标目录，测试不得传 --target"

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        # TMPDIR 指到本次的临时目录：make_skill.sh 与 make_release.sh 都用 mktemp -d
        # 建暂存区，指到这里才不会把残留留在 workspace 的 scratch 里。
        env={**os.environ, "TMPDIR": str(scratch)},
    )
    return Build(proc=proc, skill_dir=dest)


def test_make_skill_exits_zero_and_produces_skill_dir(build: Build):
    """脚本退出码 0，且产物目录存在（下面七条都以它为前置：目录不在就不是「红」而是空转）。"""
    assert build.proc.returncode == 0, (
        f"make_skill.sh 退 {build.proc.returncode}，期望 0\n"
        f"stdout:\n{build.proc.stdout}\nstderr:\n{build.proc.stderr}"
    )
    assert build.skill_dir.is_dir(), (
        f"退出码 0 但产物目录不存在: {build.skill_dir}\nstderr:\n{build.proc.stderr}"
    )


def test_whitelist_derivation_is_real():
    """前置：`WL_SRC` 派生出的脚本集合非空且每个都真在仓库里。

    为什么单独一条：下面 `test_skill_scripts_match_release_whitelist` 是集合相等判断，
    派生若退化成空集，「产物也是空集」同样会相等。这条把派生的有效性钉住。
    """
    derived = whitelist_scripts()
    assert derived, "WL_SRC 里没有任何 scripts/ 条目——派生失败"
    missing = [n for n in derived if not (REPO_ROOT / "scripts" / n).is_file()]
    assert not missing, f"WL_SRC 点了名但仓库里没有的脚本: {missing}"


def test_skill_scripts_match_release_whitelist(build: Build):
    """产物 `scripts/` 的文件名集合 == `WL_SRC` 里的用户面脚本集合。

    期望集合从 `WL_SRC` 派生（唯一权威），不在测试里再抄一份清单：抄一份就是又一次
    「同一份值两处置值」——白名单加了脚本而这里没跟，判据对那个脚本空转且看不出来。
    两个方向都判：少一个（组装漏移）与多一个（把维护侧脚本带进交付物）都要红。
    """
    expected = whitelist_scripts()
    actual = script_files(build.skill_dir)

    assert sorted(actual) == expected, (
        "产物 scripts/ 与 WL_SRC 不一致\n"
        f"  缺少: {sorted(set(expected) - set(actual))}\n"
        f"  多出: {sorted(set(actual) - set(expected))}"
    )


def test_entry_card_declares_name_short_description_and_pointers(build: Build):
    """入口卡：name == foam-mate、description ≤60 字符、正文指向 $HARNESS 与 references/SKILL.md。

    description 上限 60 是 Hermes/Codex 的字段限制（`make_skill.sh:6`）；超了不报错，
    只是 skill 索引里读不到这张卡——正是「没人会发现」的失效形态。
    两个指针是这张卡的核心承诺：自包含（`$HARNESS` = 本目录）与「判据在 references」。
    """
    assert card_name(build.skill_dir) == "foam-mate", (
        f"入口卡 name 应为 foam-mate，实际 {card_name(build.skill_dir)!r}"
    )

    violations = card_description_violations(build.skill_dir)
    assert not violations, "入口卡 description 不合规：" + "; ".join(violations)

    body = (build.skill_dir / "SKILL.md").read_text(encoding="utf-8")
    for pointer in CARD_POINTERS:
        assert pointer in body, (
            f"入口卡正文里没有 {pointer!r}——"
            f"{'自包含承诺丢了（用户不知道 $HARNESS 指哪）' if pointer == '$HARNESS' else '指针卡的承诺丢了（读者会被引到不存在的完整判据）'}"
        )


def test_references_skill_md_is_plain_doc_and_longer_than_card(build: Build):
    """`references/SKILL.md` 不带 frontmatter，且比入口卡长（两份是独立文件，不是裁剪版）。

    不以 `---` 开头是 9c4323a 的回归点：Codex 递归扫描 skills 树下的每个 SKILL.md 并读
    frontmatter 的 name，`release/SKILL.md` 原样带着 `name: openfoam-v13-case-harness`，
    会让它被当成与 foam-mate 并列的第二条同源 skill（实测 codex debug prompt-input 里两条）。
    「更长」守的是 420e76c 那条说明：入口卡是手写指针卡，references 是完整文档；
    若有人把它们合并/裁剪，长度关系会先破。
    """
    ref = build.skill_dir / "references" / "SKILL.md"
    assert ref.is_file(), f"缺少 references/SKILL.md: {ref}"
    assert not has_frontmatter(ref), (
        "references/SKILL.md 仍以 `---` 开头（frontmatter 没被剥掉）："
        "Codex 会把它索引成第二条 skill"
    )

    card_bytes = (build.skill_dir / "SKILL.md").stat().st_size
    ref_bytes = ref.stat().st_size
    assert ref_bytes > card_bytes, (
        f"references/SKILL.md 只有 {ref_bytes} 字节，不大于入口卡的 {card_bytes} 字节——"
        "两份本应是独立文件（完整文档 vs 指针卡），这里像是被裁成了短版"
    )


def test_version_file_matches_repository(build: Build):
    """产物 VERSION 与仓库 VERSION 逐字相同（去首尾空白）。

    VERSION 是 provenance：交付物里的版本号与仓库对不上，后续所有「这份 skill 是哪一版」
    的判断都失去依据（包名 `foam-mate-<version>` 也由它派生）。
    """
    want = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    got_path = build.skill_dir / "VERSION"
    assert got_path.is_file(), f"产物缺少 VERSION: {got_path}"
    got = got_path.read_text(encoding="utf-8").strip()
    assert got == want, f"产物 VERSION={got!r} 与仓库 {want!r} 不一致"


def test_license_is_carried_when_repo_has_one(build: Build):
    """仓库根有 LICENSE 时，产物必须带 LICENSE（9c4323a 的回归点：当时漏了）。

    条件是「仓库根有」而不是「必须有」：许可证是未决项时不该把组装器卡死，
    这条判据随仓库现状成立，不额外发明要求。
    """
    repo_license = REPO_ROOT / "LICENSE"
    if not repo_license.is_file():
        pytest.skip("仓库根没有 LICENSE：本仓库未定许可证，组装器按设计不复制")

    got = build.skill_dir / "LICENSE"
    assert got.is_file(), "仓库根有 LICENSE 但产物里没有（交付物缺授权声明）"
    assert got.read_bytes() == repo_license.read_bytes(), "产物 LICENSE 与仓库根的内容不一致"


def test_all_scripts_are_executable(build: Build):
    """产物 `scripts/` 下每个文件都有可执行位（8d4a476 的回归点）。

    缺了可执行位，脚本只能 `bash x.sh` 调用：入口卡里全部写成 `"$HARNESS/scripts/xxx"`
    直接执行，于是用户第一次照抄就 `Permission denied`（126）。当时脚本自己的自检
    检的是 `$SKILL` 而不是 `$SKILL/scripts`，所以全程没红。
    """
    assert script_files(build.skill_dir), "产物 scripts/ 为空——这条判据会空转"
    bad = non_executable_scripts(build.skill_dir)
    assert not bad, f"产物脚本缺可执行位: {bad}（修法: chmod +x，或在仓库侧补位后重生成）"


def test_no_text_file_mentions_references_repos(build: Build):
    """产物任何文本文件都不含 `references/repos`。

    那是第三方参考库的副本坐标（R9：只读、且不是源码事实来源）。这种字符串进交付物
    等于把「别人怎么实现」的路径递给用户，让他去抄一份非权威树；发布包里这条由
    `make_release.sh` 的 c) 检查守着，本测试守的是 skill 组装之后的新产物
    （入口卡是 heredoc 手写的，不走那套自检）。
    """
    needle = b"references/repos"
    hits: list[str] = []
    for path in text_files(build.skill_dir):
        if needle in path.read_bytes():
            hits.append(str(path.relative_to(build.skill_dir)))
    assert not hits, f"产物里出现指向第三方副本的路径（references/repos）：{hits}"


# ---------------------------------------------------------------------------
# 尺子有牙：合成坏产物（只写 tmp_path，不碰仓库文件与 make_skill.sh）
# ---------------------------------------------------------------------------
def _synth_skill(root: Path, description: str) -> Path:
    """最小的合成 skill 目录：一张入口卡 + scripts/ + references/。"""
    skill = root / "foam-mate"
    (skill / "scripts").mkdir(parents=True)
    (skill / "references").mkdir()
    (skill / "SKILL.md").write_text(
        "---\n"
        "name: foam-mate\n"
        f'description: "{description}"\n'
        "---\n\n"
        "# 合成入口卡\n\n"
        "用 `$HARNESS` 指本目录；完整判据在 `references/SKILL.md`。\n",
        encoding="utf-8",
    )
    ref = skill / "references" / "SKILL.md"
    ref.write_text("# 完整文档\n\n" + ("正文\n" * 200), encoding="utf-8")
    return skill


def test_ruler_rejects_description_one_over_limit(tmp_path: Path):
    """61 字符的 description 必须被判违规（上限 60 是硬字段，不是建议）。"""
    skill = _synth_skill(tmp_path, "x" * (DESCRIPTION_LIMIT + 1))
    violations = card_description_violations(skill)
    assert violations, f"description 61 字符却通过了判据：{violations}"
    assert str(DESCRIPTION_LIMIT + 1) in violations[0], (
        f"违规消息应点名实际长度 {DESCRIPTION_LIMIT + 1}：{violations[0]!r}"
    )


def test_ruler_accepts_description_at_limit(tmp_path: Path):
    """正好 60 字符必须通过——否则「有牙」的另一半会变成「一律红」的假判据。"""
    skill = _synth_skill(tmp_path, "y" * DESCRIPTION_LIMIT)
    assert card_description_violations(skill) == []


def test_ruler_flags_script_without_exec_bit(tmp_path: Path):
    """一个 644 的 .sh 必须被判出（8d4a476 的失效形态，用合成产物复现）。"""
    skill = _synth_skill(tmp_path, "ok")
    scripts = skill / "scripts"
    good = scripts / "good.sh"
    bad = scripts / "bad.sh"
    for p in (good, bad):
        p.write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    good.chmod(0o755)
    bad.chmod(0o644)

    assert non_executable_scripts(skill) == ["bad.sh"], (
        f"判据应只报 bad.sh，实际 {non_executable_scripts(skill)}"
    )


def test_ruler_flags_markdown_starting_with_frontmatter(tmp_path: Path):
    """开头带 `---` 的 md 必须被判出——这是 9c4323a 的失效形态。"""
    dirty = tmp_path / "dirty.md"
    dirty.write_text("---\nname: openfoam-v13-case-harness\ndescription: x\n---\n\n正文\n", encoding="utf-8")
    plain = tmp_path / "plain.md"
    plain.write_text("# 完整文档\n\n正文\n", encoding="utf-8")

    assert has_frontmatter(dirty), "带 frontmatter 的文件没有被判出"
    assert not has_frontmatter(plain), "无 frontmatter 的文件被误判成违规"
