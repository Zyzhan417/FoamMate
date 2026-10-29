#!/usr/bin/env python3
"""bench/selftest_judge.py — judge 七态归约的合成自测（prereg §11 第 4 条）。

**只在临时目录里造 fixture，不碰真实项目、不跑 OpenFOAM、不需要 LLM。**

12 个 fixture = 七态各 1 例（相对 prereg §4）+ 5 个边界（prereg §11.4 逐字列出的五条）：
  七态：pass / fail / no_artifact / malformed / blocked / overclaim / declined
  边界：日志为空 / 日志含 FOAM FATAL 但退出码 0 / 末时刻存在但场为 nan /
        case.meta 缺 source / case/ 存在但缺 system/controlDict

另跑三组独立用例（不在 prereg 钉死的 12 个内，是对 §11 第 3/7 条与 D4/D7 的加固）：
  majority=3  三次重复 → 任务级归约（prereg §11 第 3 条）
  mapping=3   断言 undeterminable → malformed；M-d 短路合法 / 矛盾
  g2b=2       log.g2 第 2 行 G2B= 的解析（D7）

必须打印 `checked=12 failed=0`（STATUS.md N5-1 的完成判据）。

用法：python3 bench/selftest_judge.py [-v]
退出码：0 全部通过 / 1 有失败
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import judge  # noqa: E402

VERBOSE = "-v" in sys.argv


def build_run(d: Path, *, case: bool = True, control_dict: bool = True,
              meta: bool = True, meta_source: bool = True,
              gates: dict | None = None, assert_overall: str = "match",
              arm_stdout: str = "", blocked: str | None = None,
              gate_log: str = "rc", g2b: str | None = None) -> Path:
    """在 d 下造一个 run 目录。gate_log: rc=写 RC 行 / empty=空文件 / missing=不写。"""
    d.mkdir(parents=True, exist_ok=True)
    if blocked:
        (d / "blocked.txt").write_text(blocked + "\n", encoding="utf-8")
    if case:
        (d / "case" / "system").mkdir(parents=True, exist_ok=True)
        if control_dict:
            (d / "case" / "system" / "controlDict").write_text(
                "FoamFile { version 2.0; }\nendTime 1;\n", encoding="utf-8")
    if meta:
        m = {"source": "incompressibleFluid/cavity", "derived_at": "2026-10-28T00:00:00",
             "spec": {}, "changes": []}
        if not meta_source:
            m.pop("source")
        (d / "case.meta").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    for i in range(1, 6):
        p = d / f"log.g{i}"
        if gate_log == "missing":
            continue
        if gate_log == "empty":
            p.write_text("", encoding="utf-8")
            continue
        status = (gates or {}).get(f"g{i}", "pass")
        if status == "missing":          # 逐门缺失（M-d 短路用）
            continue
        rc = {"pass": 0, "fail": 1, "undeterminable": None}[status]
        body = "" if rc is None else f"RC={rc}\n"
        if i == 2 and g2b:
            body += f"G2B={g2b}\n"      # D7：第 2 行
        p.write_text(body, encoding="utf-8")
    (d / "arm_stdout.txt").write_text(arm_stdout, encoding="utf-8")
    (d / "assert.json").write_text(json.dumps({"overall": assert_overall}), encoding="utf-8")
    return d


def fixtures(root: Path) -> list[tuple[str, Path, str, str]]:
    """(名字, run 目录, 期望 status, 该 fixture 想证明什么)"""
    out = []
    out.append(("pass", build_run(root / "pass"), "pass",
                "五门全过 + 断言全 match"))
    out.append(("fail", build_run(root / "fail", assert_overall="mismatch"), "fail",
                "能跑但需求没满足（T05 那类：什么都不改也能过门）"))
    out.append(("no_artifact", build_run(root / "no_artifact", case=False, meta=False,
                                         arm_stdout=""), "no_artifact",
                "什么都没交"))
    out.append(("malformed", build_run(root / "malformed", gate_log="missing"), "malformed",
                "闸门日志缺失 → 无法判定，不是判为错"))
    out.append(("blocked", build_run(root / "blocked", case=False, meta=False,
                                     blocked="版本不兼容：需要 openfoam12"),
                "blocked", "环境前置不满足，臂根本没启动"))
    out.append(("overclaim", build_run(root / "overclaim", gates={"g3": "fail"},
                                       arm_stdout="已完成，算例已跑通。"), "overclaim",
                "自称完成但 G3 未过"))
    out.append(("declined", build_run(root / "declined", case=False, control_dict=False,
                                      meta=False,
                                      arm_stdout="该需求需要曲面几何与边界层加密，超出支持范围，不产出算例。"),
                "declined", "正确拒绝，且理由指向 R5 的限制"))
    out.append(("边界-日志为空", build_run(root / "empty_log", gate_log="empty"), "malformed",
                "空日志 ≠ 通过"))
    out.append(("边界-FATAL但退出码0", build_run(root / "fatal_rc0", gates={"g3": "fail"}), "fail",
                "judge 不得因为退出码 0 就把 G3 的失败改判成 pass"))
    out.append(("边界-末时刻存在但场为nan", build_run(root / "nan_field", gates={"g4": "fail"}), "fail",
                "产物存在 ≠ 产物可用"))
    out.append(("边界-case.meta缺source", build_run(root / "no_source", meta_source=False),
                "malformed", "派生来源不可追溯 → 无法判定，不得记 pass"))
    out.append(("边界-有case目录但缺controlDict",
                build_run(root / "half_baked", control_dict=False), "malformed",
                "目录半成品：产出了东西但不是可判定的 case"))
    return out


def majority_cases() -> list[tuple[str, list[str], str, int, str]]:
    """(名字, 三次 run 的 status, 期望任务级 status, 期望 unstable, 证明什么)"""
    return [
        ("三次一致", ["pass", "pass", "pass"], "pass", 0, "稳定"),
        ("多数归约", ["pass", "pass", "fail"], "pass", 0, "2/3 取多数，不记 unstable"),
        ("三次各异", ["pass", "fail", "malformed"], "malformed", 1,
         "prereg §11.3：三次各不同 → malformed + unstable=1（单独一例）"),
    ]


def mapping_cases() -> list[tuple[str, dict, str, str]]:
    """三态映射的独立用例（不在 prereg 的 12 个 fixture 内，是对 §11 第 7 条的加固）。

    变异探针 J-M1 曾在此存活：12 个 fixture 里没有"五门全过但断言 undeterminable"这一例，
    于是把 undeterminable 改成 pass 也不会变红。补这一组之后才咬得住。
    """
    return [
        ("断言 undeterminable（五门全过）", {"assert_overall": "undeterminable"}, "malformed",
         "prereg §11 第 7 条：undeterminable 任何情况下不得映射到 pass"),
        ("M-d 短路：G1 失败，后续门未跑",
         {"gates": {"g1": "fail", "g2": "missing", "g3": "missing", "g4": "missing", "g5": "missing"}},
         "fail",
         "D4：pre 阶段被拦下时 G2–G4 合法缺失，判 fail 而不是 malformed"),
        ("M-d 矛盾：G1 通过但 G3 缺失",
         {"gates": {"g3": "missing"}}, "malformed",
         "缺失的门排在失败门之前（此处根本没有失败门）→ 状态自相矛盾"),
    ]


def g2b_cases() -> list[tuple[str, dict, tuple[str, str], str]]:
    """(名字, 构造参数, (期望 status, 期望 g2b), 证明什么)。D7 的回归保护。"""
    return [
        ("g2b=soft:2 不影响 status", {"gates": {"g2": "pass"}, "g2b": "soft:2"},
         ("pass", "soft:2"), "G2b 是诊断信号不是门（prereg §5）"),
        ("log.g2 无 G2B 行", {"gates": {"g2": "pass"}},
         ("pass", "unknown"), "缺失记 unknown，不得默认 none"),
    ]



def meta_cases() -> list[tuple[str, str, str]]:
    """(名字, 期望 status, 证明什么) —— case.meta 位置规则的独立用例（D20）。

    为什么必须单独一组：`gather()` 里读 meta 的分支是**真文件系统**分支，
    而上面 12 个 fixture 走的是构造参数，覆盖不到「meta 放在哪」这件事。
    变异探针 J-M9（把二义判断删掉、静默取 run 根）只有这组能咬住。
    """
    return [
        ("meta 只在 case 树内 → 可判定", "pass",
         "C 的 --dest 就是 case 树，meta 写在那里；judge 必须能找到它"),
        ("meta 只在 run 根 → 可判定", "pass",
         "prereg §12 的写法；两种布局都得认，否则 M4b 的 adapter 一换布局就全 malformed"),
        ("meta 两处都有 → malformed", "malformed",
         "两份可能漂移的溯源信息 ⇒ 二义，必须交人裁定，不许静默选边"),
        ("meta 两处都无 → malformed", "malformed",
         "既无 meta 又无 source ⇒ 派生来源不可追溯"),
    ]


def _build_meta_run(root: "Path", where: str) -> "Path":
    """按 `where` 摆出一棵能判 pass 的最小 run 目录（五门 RC=0 + 断言 match）。"""
    import json as _json

    run = root / f"meta_{where}"
    if run.exists():
        import shutil as _shutil
        _shutil.rmtree(run)
    (run / "case" / "system").mkdir(parents=True)
    (run / "case" / "system" / "controlDict").write_text("FoamFile{}\n", encoding="utf-8")
    (run / "case" / "0").mkdir()
    (run / "case" / "0" / "U").write_text("FoamFile{}\n", encoding="utf-8")

    meta = {"source": "incompressibleFluid/cavity", "spec": {}, "changes": [], "allowed_files": []}
    if where in ("tree", "both"):
        (run / "case" / "case.meta").write_text(_json.dumps(meta), encoding="utf-8")
    if where in ("root", "both"):
        (run / "case.meta").write_text(_json.dumps(meta), encoding="utf-8")

    for g in ("g1", "g2", "g3", "g4", "g5"):
        (run / f"log.{g}").write_text("RC=0\n", encoding="utf-8")
    (run / "log.g2").write_text("RC=0\nG2B=none\n", encoding="utf-8")
    (run / "assert.json").write_text(_json.dumps({"overall": "match"}), encoding="utf-8")
    return run


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="selftest_judge_"))
    failed = 0
    checked = 0
    try:
        for name, run_dir, want, why in fixtures(root):
            checked += 1
            got = judge.judge_run(run_dir)["status"]
            ok = got == want
            if not ok:
                failed += 1
            if VERBOSE or not ok:
                print(f"  {'ok  ' if ok else '<<< FAIL'} {name:<28} want={want:<12} got={got:<12} {why}")
        print(f"checked={checked} failed={failed}")

        m_failed = 0
        m_checked = 0
        for name, states, want, want_unstable, why in majority_cases():
            m_checked += 1
            runs = [{"status": s} for s in states]
            got = judge.reduce_task(runs)
            ok = got["status"] == want and got["unstable"] == want_unstable
            if not ok:
                m_failed += 1
            if VERBOSE or not ok:
                print(f"  {'ok  ' if ok else '<<< FAIL'} {name:<28} "
                      f"want={want}/{want_unstable} got={got['status']}/{got['unstable']} {why}")
        print(f"majority_checked={m_checked} failed={m_failed}")

        g_failed = 0
        g_checked = 0
        for name, kwargs, want, why in mapping_cases():
            g_checked += 1
            # 每个用例造一个新目录，避免与上面 12 个共用路径
            run_dir = build_run(root / ("mapping_" + str(g_checked)), **kwargs)
            got = judge.judge_run(run_dir)["status"]
            ok = got == want
            if not ok:
                g_failed += 1
            if VERBOSE or not ok:
                print(f"  {'ok  ' if ok else '<<< FAIL'} {name:<28} want={want:<12} got={got:<12} {why}")
        print(f"mapping_checked={g_checked} failed={g_failed}")

        b_failed = 0
        b_checked = 0
        for name, kwargs, (want_s, want_b), why in g2b_cases():
            b_checked += 1
            run_dir = build_run(root / ("g2b_" + str(b_checked)), **kwargs)
            got = judge.judge_run(run_dir)
            ok = got["status"] == want_s and got.get("g2b") == want_b
            if not ok:
                b_failed += 1
            if VERBOSE or not ok:
                print(f"  {'ok  ' if ok else '<<< FAIL'} {name:<28} "
                      f"want={want_s}/{want_b} got={got['status']}/{got.get('g2b')} {why}")
        print(f"g2b_checked={b_checked} failed={b_failed}")

        e_failed = 0
        e_checked = 0
        for name, want, why in meta_cases():
            e_checked += 1
            where = {"meta 只在 case 树内 → 可判定": "tree",
                     "meta 只在 run 根 → 可判定": "root",
                     "meta 两处都有 → malformed": "both",
                     "meta 两处都无 → malformed": "none"}[name]
            run = _build_meta_run(root, where)
            got = judge.judge_run(run)["status"]
            ok = got == want
            if not ok:
                e_failed += 1
            if VERBOSE or not ok:
                print(f"  {'ok  ' if ok else '<<< FAIL'} {name:<28} want={want:<12} got={got:<12} {why}")
        print(f"meta_checked={e_checked} failed={e_failed}")
        return 0 if (failed == 0 and m_failed == 0 and g_failed == 0 and b_failed == 0) else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
