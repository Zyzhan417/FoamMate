#!/usr/bin/env python3
"""bench/selftest_expect.py — 证明 12 个任务的 expect_values 真的会咬人。

**这个脚本不跑任何被测臂**（R12）：它只在 `$FOAM_TUTORIALS` 的副本上施加已知的改动，
验证断言能分别给出 mismatch / match / undeterminable。

对每个任务做三份副本：
  baseline  未修改的 tutorial                 -> 必须 ≠ match
  correct   按需求正确修改                    -> 必须 = match
  wrong     看似做了但做错                    -> 必须 = mismatch

**断言从 yaml 读，不在脚本里手写**（否则脚本和产品会各说各话，测试与产品走两条路径）。

用法：  source /opt/openfoam13/etc/bashrc && python3 bench/selftest_expect.py
退出码：0 全过 / 1 有 FAIL
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))
from assert_lib import evaluate  # noqa: E402

TUT = Path(os.environ["FOAM_TUTORIALS"])   # yaml 里的 reference_tutorial 自带组名（如 incompressibleFluid/cavity）
WORK = Path(os.environ.get("TMPDIR", "/tmp")) / "foam_expect_selftest"


# ---------------------------------------------------------------- yaml 读取

def load_task(tid: str) -> dict:
    """从 yaml 抽 spec。只解析本框架用到的那几个键，避免引入 yaml 依赖。"""
    text = (BENCH / "tasks" / f"{tid}.yaml").read_text(encoding="utf-8")
    ref = re.search(r"^reference_tutorial:\s*(\S+)", text, re.M).group(1)
    expect = re.search(r"^expect:\s*(\S+)", text, re.M).group(1)
    blk = re.search(r"^expect_values:[^\n]*\n((?:  - .*\n)*)", text, re.M)
    specs = [json.loads(ln.strip()[2:]) for ln in blk.group(1).splitlines()
             if ln.strip().startswith("- ")]
    return {"id": tid, "ref": ref, "expect": expect, "specs": specs}


# ---------------------------------------------------------------- 副本与改动

def sh(cmd: str, cwd: Path) -> int:
    return subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True).returncode


def fresh(src: str, name: str) -> Path:
    d = WORK / name
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(TUT / src, d)
    return d


def set_dict(case: Path, key: str, val: str, rel: str) -> None:
    assert sh(f'foamDictionary -entry {key} -set "{val}" {rel}', case) == 0, (key, rel)


def set_boundary(case: Path, patch: str, vec: str, rel: str = "0/U") -> None:
    p = subprocess.run(["foamDictionary", "-entry", "boundaryField", "-value", rel],
                       cwd=case, capture_output=True, text=True)
    dump = p.stdout
    m = re.search(rf"(^\s*{re.escape(patch)}\s*\n\s*\{{\s*\n\s*type\s+\S+;\s*\n"
                  r"\s*value\s+uniform\s+)\([^)]*\)", dump, re.M)
    assert m, f"patch {patch} 的 value 行没找到"
    new = dump[:m.start()] + m.group(1) + f"({vec})" + dump[m.end():]
    q = subprocess.run(["foamDictionary", "-entry", "boundaryField", "-set", new, rel],
                       cwd=case, capture_output=True, text=True)
    assert q.returncode == 0, q.stderr


def sed(case: Path, expr: str, rel: str) -> None:
    sh(f"sed -i '{expr}' {rel}", case)


# ---------------------------------------------------------------- 每个任务的 correct / wrong

def _correct(tid: str):
    return {
        "T01": lambda c: set_dict(c, "endTime", "5", "system/controlDict"),
        "T02": lambda c: sed(c, "s/model           kEpsilon;/model           kOmegaSST;/",
                            "constant/momentumTransport"),
        "T03": lambda c: (sed(c, "s/(1 0 0)/(2 0 0)/; s/(1 1 0)/(2 1 0)/; "
                                "s/(1 0 0.1)/(2 0 0.1)/; s/(1 1 0.1)/(2 1 0.1)/",
                               "system/blockMeshDict"),
                          sh("blockMesh >/dev/null 2>&1", c), set_boundary(c, "movingWall", "2 0 0")),
        "T04": lambda c: sed(c, "s/model           kOmegaSSTLM;/model           kOmegaSST;/",
                            "constant/momentumTransport"),
        "T05": lambda c: set_dict(c, "writeInterval", "50", "system/controlDict"),
        "T06": lambda c: (sed(c, "44s/^SIMPLE$/PIMPLE/", "system/fvSolution"),
                          sed(c, "s/default         steadyState;/default         Euler;/",
                              "system/fvSchemes")),
        "T07": lambda c: set_boundary(c, "movingWall", "0.5 0 0"),
        "T08": lambda c: (sed(c, "s/(20 20 1)/(40 40 1)/", "system/blockMeshDict"),
                          sh("blockMesh >/dev/null 2>&1", c)),
        "T09": lambda c: set_boundary(c, "movingWall", "2 0 0"),
        "T10": lambda c: set_dict(c, "nu", "2e-05 [m^2/s]", "constant/physicalProperties"),
        "T11": lambda c: set_dict(c, "nu", "2e-05 [m^2/s]", "constant/physicalProperties"),
        # T12 不是"改文件"，是"拒绝"，用 behavior 断言单独验（见 main）
        "T12": None,
    }[tid]


def _wrong(tid: str):
    return {
        "T01": lambda c: set_dict(c, "endTime", "50", "system/controlDict"),          # 量级错
        "T02": lambda c: sed(c, "s/kEpsilon;/kOmegaSSTX;/", "constant/momentumTransport"),  # 拼错
        "T03": lambda c: (sed(c, "s/(1 0 0)/(3 0 0)/; s/(1 1 0)/(3 1 0)/; "
                                "s/(1 0 0.1)/(3 0 0.1)/; s/(1 1 0.1)/(3 1 0.1)/",
                               "system/blockMeshDict"),
                          sh("blockMesh >/dev/null 2>&1", c), set_boundary(c, "movingWall", "2 0 0")),  # 3:1
        "T04": lambda c: sed(c, "s/kOmegaSSTLM;/kEpsilon;/", "constant/momentumTransport"),
        "T05": lambda c: set_dict(c, "writeInterval", "500", "system/controlDict"),   # 方向对、数错
        "T06": lambda c: sed(c, "44s/^SIMPLE$/SIMPLEC/", "system/fvSolution"),        # 没换求解器
        "T07": lambda c: set_boundary(c, "movingWall", "5 0 0"),                      # 小数点点错
        "T08": lambda c: (sed(c, "s/(20 20 1)/(20 20 2)/", "system/blockMeshDict"),
                          sh("blockMesh >/dev/null 2>&1", c)),                        # 加密方向错
        "T09": lambda c: set_boundary(c, "movingWall", "1 0 0"),                      # 只跑了一例
        "T10": lambda c: set_dict(c, "nu", "1e-04 [m^2/s]", "constant/physicalProperties"),
        "T11": lambda c: set_dict(c, "nu", "1e-05 [m^2/s]", "constant/physicalProperties"),
        "T12": None,
    }[tid]


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    rows, failed = [], 0

    for i in range(1, 13):
        tid = f"T{i:02d}"
        t = load_task(tid)

        if tid == "T12":  # 负对照：三种合成情形
            cases = {}
            d = WORK / "T12_refuse"; shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True)
            cases["correct(拒绝+理由)"] = evaluate(
                d, t["specs"], "按 R5：曲面几何与边界层加密需用户提供网格，不尝试 snappyHexMesh")
            d2 = WORK / "T12_produce"; shutil.rmtree(d2, ignore_errors=True)
            (d2 / "system").mkdir(parents=True)
            (d2 / "system" / "controlDict").write_text("// x\n", encoding="utf-8")
            cases["wrong(仍产出case)"] = evaluate(d2, t["specs"], "done")
            cases["baseline(无case无理由)"] = evaluate(d, t["specs"], "")
            bm = cases["baseline(无case无理由)"]["overall"]
            cm = cases["correct(拒绝+理由)"]["overall"]
            wm = cases["wrong(仍产出case)"]["overall"]
            ok = cm == "match" and wm == "mismatch" and bm == "undeterminable"
            failed += 0 if ok else 1
            rows.append({"tid": tid, "baseline": bm, "correct": cm, "wrong": wm,
                         "verdict": "OK" if ok else "FAIL"})
            print(f"{tid}  负对照(behavior)                          base={bm:<14} "
                  f"correct={cm:<14} wrong={wm:<14} {'OK' if ok else '<<< FAIL'}")
            continue

        def one(tag, builder):
            d = fresh(t["ref"], f"{tid}_{tag}")
            if builder:
                builder(d)
            return evaluate(d, t["specs"])["overall"]

        b = one("baseline", None)
        cm = one("correct", _correct(tid))
        wm = one("wrong", _wrong(tid))
        ok = (cm == "match") and (wm == "mismatch") and (b != "match")
        failed += 0 if ok else 1
        rows.append({"tid": tid, "baseline": b, "correct": cm, "wrong": wm,
                     "verdict": "OK" if ok else "FAIL"})
        print(f"{tid}  {t['ref'].split('/')[-1]:<20} n={len(t['specs'])}  "
              f"base={b:<14} correct={cm:<14} wrong={wm:<14} {'OK' if ok else '<<< FAIL'}")

    print(f"\nchecked={len(rows)} failed={failed}")
    out = Path(os.environ.get("TMPDIR", "/tmp")) / "expect_selftest.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print("证据表:", out)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
