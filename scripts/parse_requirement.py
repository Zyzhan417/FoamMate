#!/usr/bin/env python3
"""模块 A：需求（自由文本）→ 四元组（geometry / properties / boundary / objective）。

规格：`references/09-architecture-and-test-plan.md` §A；「不许填默认值」出自
`references/06-agent-anatomy.md:59`：「四个键任一为空即 raise RequirementIncomplete，
不许填默认值——默认值会把『需求没被满足』转成『门全过』」。

===============================================================================
三层结构（这是本文件最重要的设计约束，请不要把层与层搅在一起）
===============================================================================
  [1] 提取器 `extract_quad(text)` —— 纯函数、纯标准库（正则 + 关键词表），
      把自然语言"试"成四个键。它**只负责猜**，猜不到就返回 None，不许猜个默认值顶上。

  [2] 校验器 `validate_quad(quad)` —— 不关心 quad 是正则猜出来的还是 LLM 给的。
      只做契约校验：键名固定四个；值必须是非空 `str`（非字符串/空串/纯空白都算"没给"）；
      缺的键一律 None；`complete = (missing == [])`。

  [3] CLI `main()` —— 只负责落盘策略与退出码（0 完成 / 10 缺需求）。

  **将来接入 LLM 时，只替换 [1]**：把 `extract_quad` 换成"调 API 拿 JSON → 返回 dict"，
  然后照样交给 `validate_quad` 收口。[2] 与 `tests/unit/test_parse_requirement.py`
  一行都不用改。本文件刻意不导入任何 LLM SDK、不发任何网络请求、不读环境变量里的 key。

===============================================================================
契约（下游只认这个形状，字段顺序即输出顺序）
===============================================================================
  {"geometry": str|null, "properties": str|null, "boundary": str|null,
   "objective": "steady"|"transient"|null, "complete": bool, "missing": [str]}

  退出码：0 = complete=true（此时若给了 --out 才落盘）；10 = 缺需求（交人，不是错误，
  此时**不落盘**，避免下游误读半成品）；argparse 层面的用法错误（如没给 --text）= 2。

  字段口径（D9，2026-10-28 用户裁定 + 编排方纠错）：以 `references/06-agent-anatomy.md:57`–`58`
  的接口契约为准 —— 第二个键是 **`properties`**（覆盖物性**与**湍流模型，因为 OpenFOAM 把
  湍流模型放在 `constant/momentumTransport`，只写 `material` 会漏掉 T02 那类任务）；
  **`objective` 只取 `steady` / `transient`** 两个枚举值。

  `objective` 为什么要枚举而不是自由文本：它是**可判定的**。上一版把「层流」当 objective，
  那是湍流模型选择（属 `properties`），不是稳态/瞬态；而不可判定的取值等于没回答这个问题。
  给了非法值的处理是**视为没给**（记 null 并进 missing），不是猜一个 —— 见 A4 用例。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 契约常量
# ---------------------------------------------------------------------------

#: 四个键，顺序固定（输出 JSON 的字段顺序与 missing 的排序都用它）
QUAD_KEYS = ("geometry", "properties", "boundary", "objective")

EXIT_COMPLETE = 0
EXIT_INCOMPLETE = 10  # 缺需求：交人，不是程序错误


# ---------------------------------------------------------------------------
# [2] 校验器 —— 所有出口都必须经过它，提取器和 CLI 都不能绕过
# ---------------------------------------------------------------------------

def _normalize_value(value) -> str | None:
    """把单个字段收敛成 `str | None`。

    算"给了"：非空字符串（两侧空白剥掉后仍非空）。
    算"没给"：None、空串、纯空白、以及任何非字符串（int/float/bool/list/dict）。
    非字符串一律不做 `str()` 强转——`material: 1` 是调用方的错，不是"材质叫 1"。
    """
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def validate_quad(quad: dict | None) -> dict:
    """四元组契约校验器（纯函数）。

    - 缺键 / 空值 / 类型不对 → 该键为 None，并进 `missing`；
    - 多余的键（`velocity_lid`、`properties`、拼错的 `geometery` 等）被**丢弃**，
      既不"猜"成最近的正确键，也不出现在输出里；
    - **不填默认值**：这里没有任何 `or 0.01` / `or 1.0` / `or ""` 之类的兜底。
    """
    source = quad if isinstance(quad, dict) else {}
    out: dict = {key: _normalize_value(source.get(key)) for key in QUAD_KEYS}
    # D9：objective 是枚举，非法值等同没给（不猜、不映射）。
    if out["objective"] not in OBJECTIVE_VALUES:
        out["objective"] = None
    missing = [key for key in QUAD_KEYS if out[key] is None]
    out["complete"] = not missing
    out["missing"] = missing
    return out


def exit_code_for(spec: dict) -> int:
    """由校验结果推退出码（唯一入口，避免 CLI 与测试各算一遍）。"""
    return EXIT_COMPLETE if spec.get("complete") else EXIT_INCOMPLETE


# ---------------------------------------------------------------------------
# [1] 提取器 —— 纯函数、纯标准库；将来整体替换成 LLM 调用，函数签名保持不变
# ---------------------------------------------------------------------------

#: 几何：按顺序找，命中第一条即用（越具体的放越前）
_GEOMETRY_PATTERNS = (
    r"((?:二维|三维|2D|3D|2d|3d|2-D|3-D)\s*(?:方腔|cavity))",
    r"(方腔|cavity)",
    r"((?:二维|三维|2D|3D)\s*(?:管道|通道|圆管|pipe|channel))",
    r"(管道|通道|圆管|pipe|channel)",
    r"(圆柱|cylinder)",
    r"(后台阶|backward[-\s]?facing\s+step)",
    r"(平板|flat\s+plate)",
    r"(球体|球|sphere)",
)

#: 物性/工质：只要出现工质名就算给了。`水` 后面排除"水平/水温/水力"这类词。
_MATERIAL_PATTERNS = (
    (r"水(?!平|温|力|冷)", "水"),
    (r"\bwater\b", "water"),
    (r"空气", "空气"),
    (r"\bair\b", "air"),
    (r"甘油", "甘油"),
    (r"\bglycerin(e)?\b", "glycerin"),
    (r"乙二醇", "乙二醇"),
    (r"\boil\b|油", "油"),
)

#: 边界：必须有"带单位的速度数值"才算给了边界条件。
#: 只写"顶盖驱动"却没给速度 → boundary=None（不许替用户补 1 m/s，见 A2 用例）。
_BOUNDARY_HINT = r"(?:顶盖|lid|top\s+wall|上壁面|入口|inlet|出口|outlet|壁面|wall|来流|inflow|freestream)"
_SPEED_UNIT = r"(?:m/s|m\s*s-1|m·s-1|米/秒|米每秒)"
_BOUNDARY_RE = re.compile(
    rf"(?:(?P<hint>{_BOUNDARY_HINT})\s*[:：=]?\s*)?"
    rf"(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>{_SPEED_UNIT})"
)

#: objective 的合法取值（D9）。提取器只能产出这两个，校验器再兜一层。
OBJECTIVE_VALUES = ("steady", "transient")

#: 目标：先判"瞬态"再判"稳态"，否则 `非定常` 会被 `定常` 抢先命中。
#: **`层流`/`湍流` 不在这里** —— 它们是湍流模型（属 properties），不是稳态/瞬态。
_OBJECTIVE_PATTERNS = (
    (r"(瞬态|非定常|transient|unsteady)", "transient"),
    (r"(稳态|定常|steady)", "steady"),
)

#: 湍流/层流模型线索：并入 properties，不单列键
_TURBULENCE_PATTERNS = (
    (r"(层流|laminar)", "laminar"),
    (r"(kOmegaSSTLM|k-?ω\s*SST\s*LM)", "kOmegaSSTLM"),
    (r"(kOmegaSST|k-?ω\s*SST|SST)", "kOmegaSST"),
    (r"(kEpsilon|k-?ε|k-?epsilon)", "kEpsilon"),
    (r"(kOmega|k-?ω|k-?omega)", "kOmega"),
    (r"(湍流|turbulent)", "turbulent"),
)


def _first_match(patterns, text: str) -> str | None:
    """按顺序试正则，返回第一条命中的整段文本（去两侧空白）。

    两种 patterns 都支持：纯字符串（返回命中原文）与 `(pattern, normalized)` 二元组
    （返回归一化值）。后者用于 objective 的枚举归一：`非定常` → `transient`。
    """
    for pattern in patterns:
        normalized = None
        if isinstance(pattern, tuple):
            pattern, normalized = pattern
        match = re.search(pattern, text)
        if match:
            value = normalized if normalized is not None else match.group(0).strip()
            if value:
                return value
    return None


def _extract_properties(prompt: str) -> str | None:
    """`properties` = 工质（水/空气/...）+ 湍流模型（kOmegaSST/层流/...）的拼接。

    为什么合成一个键：`06-agent-anatomy.md:57` 的契约就是四个键，且 C 模块改动时
    两者都落在 `constant/` 下（`momentumTransport` / `physicalProperties`）。
    两者都没给 → None（不填默认值）。
    """
    parts: list[str] = []
    for pattern, normalized in _MATERIAL_PATTERNS:
        if re.search(pattern, prompt, flags=re.IGNORECASE):
            parts.append(normalized)
            break
    turb = _first_match(_TURBULENCE_PATTERNS, prompt)
    if turb:
        parts.append(turb)
    return "，".join(parts) if parts else None


def extract_quad(text: str) -> dict:
    """把自然语言试成四元组（纯函数，无副作用、无 IO）。

    返回的 dict 可能只有 1~4 个键有值；缺的就是 None。这个函数**不**做补全，
    补全/校验的活归 `validate_quad`。
    """
    prompt = (text or "").strip()
    quad = {key: None for key in QUAD_KEYS}
    if not prompt:
        return quad

    quad["geometry"] = _first_match(_GEOMETRY_PATTERNS, prompt)

    quad["properties"] = _extract_properties(prompt)

    boundary = _BOUNDARY_RE.search(prompt)
    if boundary:
        unit = "m/s" if boundary.group("unit") not in ("米/秒", "米每秒") else boundary.group("unit")
        hint = boundary.group("hint")
        quad["boundary"] = f"{hint} {boundary.group('num')} {unit}".strip() if hint \
            else f"{boundary.group('num')} {unit}"

    quad["objective"] = _first_match(_OBJECTIVE_PATTERNS, prompt)

    return quad


# ---------------------------------------------------------------------------
# [3] 流水线 + CLI
# ---------------------------------------------------------------------------

def run(text: str) -> tuple[dict, int]:
    """完整流水线：提取 → 校验 → 退出码。CLI 与测试共用这一条路径。"""
    spec = validate_quad(extract_quad(text))
    return spec, exit_code_for(spec)


def to_json(spec: dict) -> str:
    """一行 JSON（中文不转义，便于人读与 grep）。"""
    return json.dumps(spec, ensure_ascii=False)


#: 用法错误的统一退出码（所有模块一致）。argparse 默认是 2，但 2 在
#: `verify_case.sh` 里是「G2 网格门失败」，两者混用会让调用方无法区分
#: 「我调错了」与「这个 case 网格没过」。
EXIT_USAGE = 64


class _UsageParser(argparse.ArgumentParser):
    """把 argparse 的用法错误从 2 改成 64。

    argparse 的 `error()` 内部固定 `self.exit(2, ...)`，所以只能覆盖 `error()`。
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def main(argv: list[str] | None = None) -> int:
    parser = _UsageParser(
        description="需求文本 → 四元组 JSON（geometry/properties/boundary/objective）。"
                    "complete=false 时不落盘并退出 10。",
    )
    parser.add_argument("--text", required=True, help="用户原话（自由文本）")
    parser.add_argument(
        "--out",
        default=None,
        help="落盘路径（如 cases/<id>/spec.json）。只有 complete=true 时才会写。",
    )
    args = parser.parse_args(argv)

    spec, code = run(args.text)
    line = to_json(spec)
    print(line)  # stdout：同一份 JSON 回显

    if code == EXIT_COMPLETE:
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(line + "\n", encoding="utf-8")
        return EXIT_COMPLETE

    # 缺需求：不落盘，给人一句可执行的提示（AGENTS.md R8 / 09 §A「失败语义」）
    print(
        f"[incomplete] missing={','.join(spec['missing'])}；"
        "未写文件。请补齐缺项或确认可以接受（不许填默认值）。",
        file=sys.stderr,
    )
    return EXIT_INCOMPLETE


if __name__ == "__main__":
    sys.exit(main())
