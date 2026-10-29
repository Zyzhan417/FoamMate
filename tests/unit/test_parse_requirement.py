"""模块 A（需求→四元组）的 L1 测试，共 14 项。

规格来源：`references/09-architecture-and-test-plan.md` §A（模块契约）与 §「A 需求→四元组解析（L1，14 项）」；
「不许填默认值」的原始出处是 `references/06-agent-anatomy.md:59`。

计数口径：
  - 1 个 `pytest.mark.parametrize`，12 组参数 → pytest 展开成 12 条；
  - 另有 A2、A3 各 1 条 → 合计 12 + 2 = 14 条。
  这里刻意不新增第 15 条测试：需要额外断言的语义都写进这 14 条内部（见各测试注释），
  这样「14」这个数字是断言出来的，不是数出来的。

本层不需要 OpenFOAM、不需要 LLM、不需要网络：被测对象只做字符串处理与 JSON 序列化。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "parse_requirement.py"

# 直接按文件路径导入被测模块，避免依赖安装形态（本层不打包、不 pip install -e）
sys.path.insert(0, str(SCRIPT.parent))
import parse_requirement as pr  # noqa: E402

QUAD_KEYS = ("geometry", "properties", "boundary", "objective")
ALL_MISSING = list(QUAD_KEYS)


# ---------------------------------------------------------------------------
# A1：12 例参数化。
# 前 1 例 complete=true；后 11 例 complete=false 且 missing 逐项正确（顺序按 QUAD_KEYS）。
# "text" 走完整流水线（提取器 + 校验器），"quad" 直接喂校验器（模拟将来 LLM 给出的 JSON）。
# ---------------------------------------------------------------------------
A1_CASES = [
    # 01 完整
    ("01-完整", {"text": "一个二维方腔，顶盖 1 m/s，水，kOmegaSST，稳态"}, True, []),
    # 02 缺 geometry：没有任何几何词
    ("02-缺geometry", {"text": "水，顶盖 1 m/s，稳态"}, False, ["geometry"]),
    # 03 缺 properties：既没有流体名，也没有湍流模型
    ("03-缺properties", {"text": "一个二维方腔，顶盖 1 m/s，稳态"}, False, ["properties"]),
    # 04 缺 boundary：有几何有物性，但没有速度（没有 m/s 数值）——也不许用"顶盖"二字补默认值
    ("04-缺boundary", {"text": "一个二维方腔，水，kEpsilon，稳态"}, False, ["boundary"]),
    # 05 缺 objective：没说要算什么
    ("05-缺objective", {"text": "一个二维方腔，顶盖 1 m/s，水"}, False, ["objective"]),
    # 06 缺两键
    ("06-缺两键", {"text": "一个二维方腔，稳态"}, False, ["properties", "boundary"]),
    # 07 全缺：一句寒暄，四个键一个都不该被"脑补"出来
    ("07-全缺", {"text": "帮我弄个算例"}, False, ALL_MISSING),
    # 08 键名拼错：geometery ≠ geometry。拼错的键必须被丢弃，不能"猜"成 geometry
    (
        "08-键名拼错",
        {
            "quad": {
                "geometery": "一个方腔",
                "properties": "水",
                "boundary": "顶盖 1 m/s",
                "objective": "steady",
            }
        },
        False,
        ["geometry"],
    ),
    # 09 类型错：properties 是数字不是字符串 → 视为没给（不做 str() 强转）
    (
        "09-类型错",
        {
            "quad": {
                "geometry": "一个方腔",
                "properties": 1,
                "boundary": "顶盖 1 m/s",
                "objective": "steady",
            }
        },
        False,
        ["properties"],
    ),
    # 10 多余键：多出来的 velocity_lid 不得被当成 objective（也不能替 boundary 之外的任何键作保）。
    #     本行期望 objective 缺（规格表要求这一例 complete=false），测试体内另证"多余键只是被丢弃"。
    (
        "10-多余键",
        {
            "quad": {
                "geometry": "一个方腔",
                "properties": "水",
                "boundary": "顶盖 1 m/s",
                "velocity_lid": 1.0,
            }
        },
        False,
        ["objective"],
    ),
    # 11 空串：空白文案不是需求
    ("11-空串", {"text": ""}, False, ALL_MISSING),
    # 12 中英混：几何/物性/边界中英混写都能取到，唯独没说稳态还是瞬态 → objective 缺
    ("12-中英混", {"text": "2D cavity，水 water，顶盖 1 m/s"}, False, ["objective"]),
]


@pytest.mark.parametrize(
    "label,case,expect_complete,expect_missing",
    A1_CASES,
    ids=[c[0] for c in A1_CASES],
)
def test_a1_quad_contract(label, case, expect_complete, expect_missing):
    if "text" in case:
        spec, code = pr.run(case["text"])
        # 退出码与 complete 必须同源：0 完成 / 10 缺需求
        assert code == (pr.EXIT_COMPLETE if expect_complete else pr.EXIT_INCOMPLETE)
    else:
        spec = pr.validate_quad(case["quad"])
        code = pr.exit_code_for(spec)
        assert code == (pr.EXIT_COMPLETE if expect_complete else pr.EXIT_INCOMPLETE)

    assert spec["complete"] is expect_complete, label
    assert spec["missing"] == expect_missing, label

    # 字段集合固定：只有四个键 + complete + missing
    assert list(spec) == list(QUAD_KEYS) + ["complete", "missing"], label

    # 缺的键必须是 None；在的键必须是非空 str
    for k in QUAD_KEYS:
        if k in expect_missing:
            assert spec[k] is None, f"{label}: {k} 缺时必须是 null，不许填默认值"
        else:
            assert isinstance(spec[k], str) and spec[k].strip(), label

    # 第 10 例额外语义：多余键只是被丢弃，不会让完整输入变不完整，也不会出现在输出里
    if label == "10-多余键":
        full = dict(case["quad"], objective="steady")
        spec_full = pr.validate_quad(full)
        assert spec_full["complete"] is True
        assert spec_full["missing"] == []
        assert "velocity_lid" not in spec_full

    # 第 08 例额外语义：拼错的键原样不出现在输出里（不"修好"，也不"留着"）
    if label == "08-键名拼错":
        spec_bad = pr.validate_quad(case["quad"])
        assert "geometery" not in spec_bad
        assert spec_bad["geometry"] is None


# ---------------------------------------------------------------------------
# A2：「一个方腔，水」→ 缺顶盖速度。boundary 必须是 null，
#     且显式断言它不等于 0.01 / 1.0 / ""（这是本模块最重要的一条：
#     默认值会把「需求没被满足」转成「门全过」）。
# ---------------------------------------------------------------------------
def test_a2_missing_boundary_is_null_not_default():
    spec, code = pr.run("一个方腔，水")

    assert spec["boundary"] is None
    # 类型级：必须是 None，不是 0.0/False 之类的"空值"
    assert spec["boundary"] is not 0.0 and spec["boundary"] is not False

    for forbidden in (0.01, 1.0, 0.0, "", " ", "0.01", "1.0", "0"):
        assert spec["boundary"] != forbidden, f"boundary 不许被填成 {forbidden!r}"

    assert "boundary" in spec["missing"]
    assert spec["complete"] is False
    assert code == pr.EXIT_INCOMPLETE
    # 落盘侧同一条规则：缺需求时不产生 JSON 文件（见 A3 的文件断言，这里只判退出码）


# ---------------------------------------------------------------------------
# A3：「跑个算例看看」→ objective 不许自作主张补。走真实 CLI（子进程），
#     同时覆盖：stdout 一行 JSON、退出码 10、complete=false 时不落盘。
# ---------------------------------------------------------------------------
def test_a3_objective_not_invented_and_exit_10(tmp_path):
    out = tmp_path / "cases" / "demo" / "spec.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--text", "跑个算例看看", "--out", str(out)],
        capture_output=True,
        text=True,
    )

    assert proc.returncode == pr.EXIT_INCOMPLETE == 10, proc.stderr
    assert proc.stderr.strip(), "缺需求时应给人一句提示（stderr），不能静默"

    spec = json.loads(proc.stdout)
    assert spec["objective"] is None
    assert spec["objective"] not in ("层流", "稳态", "瞬态", "steady", "transient")
    assert spec["missing"] and "objective" in spec["missing"]
    assert spec["complete"] is False
    # complete=false 不写文件：下游不会误读半成品
    assert not out.exists()


# ---------------------------------------------------------------------------
# A4（D9）：objective 是枚举 {steady, transient}。给了非法值（如"层流"）→
#     视为没给（null + 进 missing），**不许**猜成 steady/transient。
#     为什么这条必须有：上一版规格把"层流"当 objective，那是湍流模型选择（属 properties）。
#     若校验器不拦，一个没说稳态还是瞬态的算例会被当成需求完整，直接过下游。
# ---------------------------------------------------------------------------
def test_a4_invalid_objective_enum_is_treated_as_missing():
    from parse_requirement import validate_quad  # noqa: PLC0415

    quad = {
        "geometry": "一个二维方腔",
        "properties": "水，laminar",
        "boundary": "顶盖 1 m/s",
        "objective": "层流",          # 不是枚举值
    }
    spec = validate_quad(quad)

    assert spec["objective"] is None, "非法枚举必须收敛成 None，不许保留原串"
    assert spec["objective"] not in ("steady", "transient"), "不许猜成任一合法值"
    assert "objective" in spec["missing"]
    assert spec["complete"] is False
    # 其余三键不受影响：拦住 objective 不等于否认已给出的信息
    assert spec["properties"] == "水，laminar"
    assert set(spec["missing"]) == {"objective"}


def test_a4b_objective_enum_accepts_both_legal_values():
    from parse_requirement import validate_quad  # noqa: PLC0415

    for value in ("steady", "transient"):
        spec = validate_quad({
            "geometry": "一个二维方腔",
            "properties": "水",
            "boundary": "顶盖 1 m/s",
            "objective": value,
        })
        assert spec["objective"] == value
        assert spec["complete"] is True, f"{value} 应被判为合法"
