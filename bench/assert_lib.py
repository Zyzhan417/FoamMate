#!/usr/bin/env python3
"""bench/assert_lib.py — expect_values 断言的参考实现（judge 的唯一取值入口）。

M4a 阶段只用于**自证**：对未改的 tutorial 副本与被正确修改的副本各跑一次，
证明每条断言能分别给出 mismatch 与 match。**不跑任何被测臂**（R12）。

设计依据（全部实测，见 skill `openfoam-v13-case-assertions`）：
  1. `foamDictionary -entry` 在 v13 **只解析顶层关键字**。任何子字典（boundaryField.patch、
     solvers.p、ddtSchemes.default、RAS.model）都会 FOAM FATAL。子字典必须 dump 父字典再解析。
  2. 顶层标量必须加 `-value`，否则输出带 key 名（`endTime         10;`）→ float() 失败。
  3. 带量纲的 entry 输出带量纲块（`1e-05 [ m^2 / s]`），解析前必须剥掉。
  4. dump 会重排格式（`(1 0 0)` → `( 1 0 0 )`），所以**永不对原始文件做字符串断言**。
  5. 三态结局：match / mismatch / undeterminable。undeterminable 绝不并入 mismatch。

断言类型（对应预注册 §5 的 A–E 五形态）：
  dict        A 顶层标量               file + key + expect(数) + tol
  dict_value  D 子字典某个键的字符串值  file + dict + key + expect(str)
  key_present D 关键字存在性            scope=file|dict + file + (dict) + key + expect_present
  boundary    B 边界向量               file + patch + comp(向量) + tol
  mesh        C 网格指标               metric ∈ {cells, bbox_ratio_xy, bbox_ratio_xz}
  behavior    E 行为（T12）            expect = "refuse" | "produce"
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

OUTCOMES = ("match", "mismatch", "undeterminable")


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def _strip_dimensions(s: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", s).strip()


def _foam_value(case: Path, key: str, rel: str) -> tuple[str | None, str | None]:
    """顶层关键字取值。必须带 -value，否则输出含 key 名。"""
    if not (case / rel).is_file():
        return None, f"文件不存在: {rel}"
    rc, out, _ = _run(["foamDictionary", "-entry", key, "-value", rel], case)
    if rc != 0:
        return None, f"顶层关键字不存在: {key} in {rel}"
    v = out.strip().rstrip(";").strip()
    return (v, None) if v else (None, f"空值: {key} in {rel}")


def _foam_dump(case: Path, name: str, rel: str) -> tuple[str | None, str | None]:
    """子字典 dump。v13 无法点号寻址，只能取整块再解析。"""
    if not (case / rel).is_file():
        return None, f"文件不存在: {rel}"
    rc, out, _ = _run(["foamDictionary", "-entry", name, "-value", rel], case)
    if rc != 0:
        return None, f"子字典不存在: {name} in {rel}"
    return out, None


def _read_file(case: Path, rel: str) -> tuple[str | None, str | None]:
    f = case / rel
    if not f.is_file():
        return None, f"文件不存在: {rel}"
    return f.read_text(encoding="utf-8", errors="replace"), None


def _key_line_value(text: str, key: str) -> str | None:
    """从一段字典文本里取 `key   value;` 的 value（单行、去注释）。"""
    m = re.search(rf"^\s*{re.escape(key)}\s+([^;{{}}]+);", text, re.M)
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------- A 顶层标量

def assert_dict(case: Path, spec: dict) -> tuple[str, object, str | None]:
    raw, err = _foam_value(case, spec["key"], spec["file"])
    if err:
        return "undeterminable", None, err
    try:
        actual = float(_strip_dimensions(raw))
    except ValueError:
        return "undeterminable", raw, f"不是标量: {raw!r}"
    tol = float(spec.get("tol", 0.0))
    ok = abs(actual - float(spec["expect"])) <= tol
    return ("match" if ok else "mismatch"), actual, None


# ---------------------------------------------------------------- D 子字典键值（字符串）

def assert_dict_value(case: Path, spec: dict) -> tuple[str, object, str | None]:
    dump, err = _foam_dump(case, spec["dict"], spec["file"])
    if err:
        return "undeterminable", None, err
    actual = _key_line_value(dump, spec["key"])
    if actual is None:
        return "undeterminable", None, f"子字典 {spec['dict']} 里没有 {spec['key']}"
    ok = actual == str(spec["expect"])
    return ("match" if ok else "mismatch"), actual, None


# ---------------------------------------------------------------- D 关键字存在性

def assert_key_present(case: Path, spec: dict) -> tuple[str, object, str | None]:
    scope = spec.get("scope", "file")
    if scope == "dict":
        text, err = _foam_dump(case, spec["dict"], spec["file"])
    else:
        text, err = _read_file(case, spec["file"])
    if err:
        return "undeterminable", None, err
    present = re.search(rf"^\s*{re.escape(spec['key'])}\b", text, re.M) is not None
    ok = present == bool(spec["expect_present"])
    return ("match" if ok else "mismatch"), {"present": present}, None


# ---------------------------------------------------------------- B 边界向量

def assert_boundary(case: Path, spec: dict) -> tuple[str, object, str | None]:
    dump, err = _foam_dump(case, "boundaryField", spec["file"])
    if err:
        return "undeterminable", None, err
    patch = spec["patch"]
    m = re.search(rf"^\s*{re.escape(patch)}\s*\n\s*\{{(.*?)^\s*\}}", dump, re.S | re.M)
    if not m:
        return "undeterminable", None, f"patch {patch} 不在 boundaryField 里"
    vm = re.search(r"value\s+(?:uniform\s+)?\(([^)]*)\)", m.group(1))
    if not vm:
        return "undeterminable", None, f"patch {patch} 没有 value 行（可能是 noSlip/empty）"
    try:
        actual = [float(x) for x in vm.group(1).split()]
    except ValueError:
        return "undeterminable", vm.group(1), "value 不是数值向量"
    expect = [float(x) for x in spec["comp"]]
    tol = float(spec.get("tol", 1e-9))
    ok = len(actual) == len(expect) and all(abs(a - e) <= tol for a, e in zip(actual, expect))
    return ("match" if ok else "mismatch"), actual, None


# ---------------------------------------------------------------- C 网格指标

def assert_mesh(case: Path, spec: dict) -> tuple[str, object, str | None]:
    rc, out, _ = _run(["checkMesh"], case)
    if "Mesh OK." not in out:
        return "undeterminable", None, "checkMesh 未通过（无 Mesh OK.）"
    metric = spec["metric"]
    expect = float(spec["expect"])
    tol = float(spec.get("tol", 0.0))
    if metric == "cells":
        m = re.search(r"^\s*cells:\s+(\d+)", out, re.M)
        if not m:
            return "undeterminable", None, "找不到 cells:"
        actual = float(m.group(1))
    elif metric in ("bbox_ratio_xy", "bbox_ratio_xz"):
        m = re.search(r"bounding box \(([^)]*)\)\s*\(([^)]*)\)", out)
        if not m:
            return "undeterminable", None, "找不到 bounding box"
        lo = [float(x) for x in m.group(1).split()]
        hi = [float(x) for x in m.group(2).split()]
        dx, dy, dz = hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]
        den = dy if metric == "bbox_ratio_xy" else dz
        if not den:
            return "undeterminable", None, "分母为 0"
        actual = dx / den
    else:
        return "undeterminable", None, f"未知 metric: {metric}"
    ok = abs(actual - expect) <= tol
    return ("match" if ok else "mismatch"), round(actual, 6), None


# ---------------------------------------------------------------- E 行为

def assert_behavior(case: Path, spec: dict, arm_stdout: str = "") -> tuple[str, object, str | None]:
    """T12 负对照。'refuse' = 不应产出可跑 case 且应说明理由。"""
    has_case = (case / "system" / "controlDict").is_file()
    want = spec["expect"]
    if want == "refuse":
        if has_case:
            return "mismatch", {"produced_case": True}, "应拒绝却产出了 case"
        if not arm_stdout.strip():
            return "undeterminable", {"produced_case": False}, "没产出 case，也没给理由"
        return "match", {"produced_case": False, "reason_len": len(arm_stdout)}, None
    if want == "produce":
        return ("match", {"produced_case": True}, None) if has_case else \
               ("mismatch", {"produced_case": False}, "应产出却没有 case")
    return "undeterminable", None, f"未知 expect: {want}"


DISPATCH = {
    "dict": assert_dict,
    "dict_value": assert_dict_value,
    "key_present": assert_key_present,
    "boundary": assert_boundary,
    "mesh": assert_mesh,
}


def evaluate(case: Path, assertions: list[dict], arm_stdout: str = "") -> dict:
    """任一 mismatch → mismatch；否则任一 undeterminable → undeterminable；全 match → match。"""
    results = []
    for spec in assertions:
        kind = spec["kind"]
        if kind == "behavior":
            state, actual, why = assert_behavior(case, spec, arm_stdout)
        else:
            fn = DISPATCH.get(kind)
            if fn is None:
                state, actual, why = "undeterminable", None, f"未知 kind: {kind}"
            else:
                state, actual, why = fn(case, spec)
        results.append({"kind": kind, "state": state, "actual": actual, "why": why})
    states = [r["state"] for r in results]
    if "mismatch" in states:
        overall = "mismatch"
    elif "undeterminable" in states:
        overall = "undeterminable"
    else:
        overall = "match"
    return {"overall": overall, "assertions": results}


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 3:
        print("usage: assert_lib.py <case_dir> <spec.json>")
        raise SystemExit(2)
    spec = json.load(open(sys.argv[2], encoding="utf-8"))
    print(json.dumps(evaluate(Path(sys.argv[1]), spec), ensure_ascii=False, indent=2))
