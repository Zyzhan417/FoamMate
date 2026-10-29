"""bench/runners —— 基准跑的「被测臂 + 驱动器」包。

`ours_scripted.py` 是被测臂（12 个任务的确定性改动计划），`run_bench.py` 是驱动器
（12 任务 × 3 次 + 多例展开 + 三层归约 + `results.csv`）。

为什么是独立包：预注册 §11.4 要求「一次 trial 的输入输出」有定义，而 `bench/adapters/`
只给了 B 档契约、没有 A 档实现；`scripts/batch.py` 是 case 级 + repeats=1，
与 bench 的 task 级 + repeats=3 不同构（计划 §3.2）。
"""

__all__ = ["ours_scripted", "run_bench"]
