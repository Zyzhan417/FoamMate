#!/usr/bin/env bash
# verify_references.sh — 把 AGENTS.md R9 / R10 / R11 / R12 的判定机制化。
#
# 为什么要有这个脚本：R9–R12 的门禁原本只写在 references/search-protocol.md §6 里，
# 靠人复制执行。规则一旦只靠记忆，就会在忙的时候被跳过。这里固化成一条命令。
#
# 用法：  bash scripts/verify_references.sh [--frozen]
#   --frozen  预注册已冻结，额外检查 bench/results.csv 的状态多样性（R12）
# 退出码：0 全过 / 1 R9 / 2 R10 / 3 R11 / 4 R12 / 5 文档引用
#
# 纪律（踩过的坑，别改回去）：
#   - 不用 set -e：本脚本中段有预期返回非零的检查，set -e 会静默截断后面全部检查。
#   - 不接管道判红绿：管道退出码是末段命令的。每项自己算并显式打印。
#   - 每项都打印它扫了几个对象，"0 violations" 与 "扫到 0 个对象" 必须能区分。

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
FROZEN=0
[ "${1:-}" = "--frozen" ] && FROZEN=1

fail=0
head1() { printf '\n=== %s ===\n' "$1"; }
report() { # name checked violations -> 累积 fail
  printf '%-14s checked=%-4s violations=%s\n' "$1" "$2" "$3"
  [ "$3" -ne 0 ] && fail=1
}

# ---------------------------------------------------------------- R9 只读
head1 "G-R9-1 参考库未被本地修改（逐个仓库 git status 必须干净）"
# 判据用 git 自身，不用 mtime：mtime 判定不可移植（把树复制/解包到别处，
# 每个文件都晚于 registry.csv，1791 个文件全部误红——实测过）。
# R9 的意图是"第三方代码没被我们改过"，git status --porcelain 直接表达这件事。
if [ -d references/repos ] && [ -f references/registry.csv ]; then
  n=$(python3 -c "
import csv; print(sum(1 for r in csv.DictReader(open('references/registry.csv',encoding='utf-8')) if r['mode']=='full'))")
  v=0
  while read -r lp; do
    dirty=$(git -C "$lp" status --porcelain 2>/dev/null | head -5)
    if [ -n "$dirty" ]; then
      echo "DIRTY $lp"; echo "$dirty" | sed 's/^/    /'; v=$((v+1))
    fi
  done < <(python3 -c "
import csv
for r in csv.DictReader(open('references/registry.csv',encoding='utf-8')):
    if r['mode']=='full': print(r['local_path'])")
  # 辅助信号：mtime 晚于登记表的文件数（仅提示，不判红——见上面的理由）
  aux=$(find references/repos -newer references/registry.csv -type f 2>/dev/null | wc -l)
  echo "note: mtime 晚于 registry.csv 的文件 $aux 个（辅助信息，不判红）"
  report G-R9-1 "$n" "$v"
else
  echo "SKIP: references/repos 或 registry.csv 不存在（尚未下载参考库）"
  report G-R9-1 0 0
fi

# ---------------------------------------------------------------- R10 登记
head1 "G-R10-1 commit_sha / size_mb 与实测一致；docs_only 行 local_path 为空"
if [ -f references/registry.csv ]; then
  out=$(python3 - <<'PY'
import csv, subprocess, sys
bad = 0; n = 0
for r in csv.DictReader(open("references/registry.csv", encoding="utf-8")):
    n += 1
    if r["mode"] != "full":
        if r["local_path"].strip() or not r["note"].strip():
            print("DOCSONLY-BAD", r["project_id"]); bad += 1
        continue
    lp = r["local_path"]
    sha = subprocess.run(["git","-C",lp,"rev-parse","HEAD"],
                         capture_output=True, text=True).stdout.strip()
    try:
        du = int(subprocess.run(["du","-sm",lp], capture_output=True, text=True).stdout.split("\t")[0])
    except (ValueError, IndexError):
        print("DU-FAIL", r["project_id"]); bad += 1; continue
    if sha != r["commit_sha"]:
        print(f"SHA-MISMATCH {r['project_id']} reg={r['commit_sha'][:10]} disk={sha[:10]}"); bad += 1
    if du != int(r["size_mb"]):
        print(f"SIZE-MISMATCH {r['project_id']} reg={r['size_mb']} disk={du}"); bad += 1
    if du > 100:
        print(f"OVER-CAP {r['project_id']} {du}MB > 100MB"); bad += 1
print(f"n={n} bad={bad}")
PY
)
  echo "$out" | grep -v '^n=' || true
  n=$(echo "$out" | sed -n 's/^n=\([0-9]*\).*/\1/p')
  v=$(echo "$out" | sed -n 's/^n=[0-9]* bad=\([0-9]*\).*/\1/p')
  report G-R10-1 "${n:-0}" "${v:-1}"
else
  echo "SKIP: references/registry.csv 不存在"
  report G-R10-1 0 0
fi

# ---------------------------------------------------------------- R11 单一版本
head1 "G-R11-1 只存在一份 OpenFOAM"
paths=$(ls -d /opt/openfoam* 2>/dev/null | wc -l)
ls -d /opt/openfoam* 2>/dev/null
imgs=0
if command -v docker >/dev/null 2>&1; then
  imgs=$(docker images 2>/dev/null | grep -ci openfoam)
  imgs=${imgs:-0}
else
  echo "note: 本机无 docker，镜像计数按 0"
fi
v=0
[ "$paths" -ne 1 ] && v=$((v+1))
[ "$imgs" -ne 0 ] && v=$((v+1))
report G-R11-1 "$((paths+imgs))" "$v"

# ---------------------------------------------------------------- R12 设计期禁跑
head1 "G-R12-1 设计期 bench/runs 必须为空；冻结后 status 必须 >=3 态"
if [ -d bench/runs ]; then
  nruns=$(find bench/runs -type f | wc -l)
else
  nruns=0
fi
echo "bench/runs files=$nruns"
v=0
if [ "$FROZEN" -eq 0 ]; then
  [ "$nruns" -ne 0 ] && { echo "VIOLATION: 未冻结却已有 runs 产物"; v=$((v+1)); }
  echo "note: 未加 --frozen，跳过 status 多样性检查"
  report G-R12-1 1 "$v"
else
  # 冻结记录必须存在且填了时间
  if grep -qE '^冻结于：.*[0-9]{4}-[0-9]{2}-[0-9]{2}' bench/preregistration.md 2>/dev/null; then :; else
    echo "VIOLATION: preregistration.md 未见带日期的冻结记录"; v=$((v+1))
  fi
  states=$(python3 -c "
import csv
rows=list(csv.DictReader(open('bench/results.csv',encoding='utf-8')))
print(len({r['status'] for r in rows if r['status']}), len(rows))
" 2>/dev/null || echo "0 0")
  ns=$(echo "$states" | cut -d' ' -f1); nrows=$(echo "$states" | cut -d' ' -f2)
  echo "results.csv rows=$nrows distinct_status=$ns"
  # 0 行 = 冻结后还没开跑，不是违规（否则冻结当天必然红，等于逼人跳过这门）
  if [ "$nrows" -eq 0 ]; then
    echo "note: 冻结后尚无实跑数据（0 行），跳过 status 多样性检查"
  elif [ "$ns" -lt 3 ]; then
    echo "VIOLATION: status 少于 3 种（七态被简化成二值）"; v=$((v+1))
  fi
  report G-R12-1 "$nrows" "$v"
fi

# ---------------------------------------------------------------- R12-2 冻结后任务集不得改动
head1 "G-R12-2 冻结后 12 个任务 yaml 与冻结清单一致"
if [ "$FROZEN" -eq 1 ] && [ -f bench/tasks/FROZEN.sha256 ]; then
  # 逐文件校验（不是只比聚合指纹）：必须能指出是哪一个变了
  bad=$(sha256sum -c bench/tasks/FROZEN.sha256 2>&1 | grep -v ': OK$' || true)
  # 只数非注释行（清单头部有说明性注释），否则 checked= 会把注释算成被校验的文件
  n=$(grep -cvE '^[[:space:]]*(#|$)' bench/tasks/FROZEN.sha256)
  if [ -z "$bad" ]; then
    report G-R12-2 "$n" 0
  else
    echo "$bad" | sed 's/^/  /'
    echo "VIOLATION: 任务集在冻结后被改动（任何改动须按 §13 N2 开新一轮）"
    report G-R12-2 "$n" 1
  fi
  # 聚合指纹只作为人读的对照，不单独判红
  agg=$(sha256sum bench/tasks/T*.yaml | sort -k2 | awk '{print $1}' | sha256sum | awk '{print $1}')
  echo "note: 聚合指纹 ${agg:0:16}…（冻结记录里应有同一串）"
else
  echo "note: 未加 --frozen 或无 FROZEN.sha256，跳过"
  report G-R12-2 0 0
fi

# ---------------------------------------------------------------- R12-3 冻结章节未被改动
head1 "G-R12-3 预注册的冻结章节（§1–§9 + §13 + 冻结记录）与记录的指纹一致"
if [ "$FROZEN" -eq 1 ] && [ -f bench/freeze_digest.py ]; then
  want=$(grep -o '冻结章节 sha：  [0-9a-f]\{64\}' bench/preregistration.md | head -1 | awk '{print $NF}')
  got=$(python3 bench/freeze_digest.py 2>/dev/null | tail -1)
  if [ -z "$want" ]; then
    echo "VIOLATION: 文档里没有「冻结章节 sha」记录"; report G-R12-3 0 1
  elif [ "$want" = "$got" ]; then
    echo "sha 一致 ${got:0:16}…"
    report G-R12-3 1 0
  else
    echo "want=${want:0:16}…  got=${got:0:16}…"
    echo "VIOLATION: 冻结章节被改动（判据/指标/作废条件只能在「轮次记录」里开新一轮改）"
    report G-R12-3 1 1
  fi
else
  echo "note: 未加 --frozen 或缺少 bench/freeze_digest.py，跳过"
  report G-R12-3 0 0
fi

# ---------------------------------------------------------------- 基准断言自证
head1 "G-BENCH-1 12 个任务的 expect_values 自证（只跑 tutorial 副本）"
if [ -n "${FOAM_TUTORIALS:-}" ] && [ -f bench/selftest_expect.py ]; then
  out=$(TMPDIR="${TMPDIR:-/tmp}" python3 bench/selftest_expect.py 2>&1)
  rc=$?
  # 先打印失败明细（哪几个任务不和预期），再打印汇总——只有计数没有任务名，等于只报"有问题"不报"哪里"
  echo "$out" | grep -E '<<< FAIL' || echo "  （无 FAIL 行）"
  echo "$out" | grep -E '^checked=' || echo "  （无 checked= 汇总行）"
  n=$(echo "$out" | sed -n 's/^checked=\([0-9]*\) failed=.*/\1/p')
  v=$(echo "$out" | sed -n 's/^checked=[0-9]* failed=\([0-9]*\)/\1/p')
  if [ -z "$n" ]; then
    echo "VIOLATION: 自证脚本没有输出 checked= 汇总行（可能崩了）"
    report G-BENCH-1 0 1
  else
    report G-BENCH-1 "$n" "${v:-1}"
  fi
else
  echo "SKIP: 未 source OpenFOAM 或缺少 bench/selftest_expect.py"
  report G-BENCH-1 0 0
fi

# ---------------------------------------------------------------- judge 自证
head1 "G-JUDGE-1 judge 七态归约的合成自测（不跑 OpenFOAM、不需要 LLM）"
if [ -f bench/judge.py ] && [ -f bench/selftest_judge.py ]; then
  out=$(python3 bench/selftest_judge.py 2>&1)
  rc=$?
  # 先打印失败明细，再打印汇总：只有计数没有名字，等于只报"有问题"不报"哪里"
  echo "$out" | grep -E '<<< FAIL' || echo "  （无 FAIL 行）"
  echo "$out" | grep -E '^(checked|majority_checked|mapping_checked|g2b_checked|meta_checked)=' || echo "  （无汇总行）"
  n=$(echo "$out" | sed -n 's/^checked=\([0-9]*\) failed=.*/\1/p')
  v=$(echo "$out" | sed -n 's/^checked=[0-9]* failed=\([0-9]*\)/\1/p')
  mm=$(echo "$out" | sed -n 's/^majority_checked=[0-9]* failed=\([0-9]*\)/\1/p')
  mp=$(echo "$out" | sed -n 's/^mapping_checked=[0-9]* failed=\([0-9]*\)/\1/p')
  gb=$(echo "$out" | sed -n 's/^g2b_checked=[0-9]* failed=\([0-9]*\)/\1/p')
  mt=$(echo "$out" | sed -n 's/^meta_checked=[0-9]* failed=\([0-9]*\)/\1/p')
  if [ -z "$n" ]; then
    echo "VIOLATION: 自测没有输出 checked= 汇总行（可能崩了）"
    report G-JUDGE-1 0 1
  elif [ "$n" -ne 12 ]; then
    # 12 = prereg §11 第 4 条钉死的样本数（7 态 + 5 边界）。少于 12 说明 fixture 被删过。
    echo "VIOLATION: checked=$n，应为 12（prereg §11 第 4 条）"
    report G-JUDGE-1 "$n" 1
  elif [ -z "$mt" ]; then
    # meta 组（case.meta 位置规则，D20）必须存在：缺了它，judge 的「缺 meta → malformed」
    # 这条判据就没有任何测试守着——实测原实现正是把「完全没有 case.meta」判成 pass。
    echo "VIOLATION: 自测没有输出 meta_checked= 汇总行（case.meta 位置规则未被守护）"
    report G-JUDGE-1 "$n" 1
  elif [ -z "$gb" ]; then
    echo "VIOLATION: 自测没有输出 g2b_checked= 汇总行"
    report G-JUDGE-1 "$n" 1
  elif [ "$rc" -ne 0 ]; then
    report G-JUDGE-1 "$n" "$((${v:-1} + ${mm:-0} + ${mp:-0} + ${gb:-0} + ${mt:-0}))"
  else
    report G-JUDGE-1 "$n" 0
  fi
else
  echo "VIOLATION: 缺 bench/judge.py 或 bench/selftest_judge.py（§11 第 4 条要求两者都在）"
  report G-JUDGE-1 0 1
fi

# ---------------------------------------------------------------- R13 状态文档
head1 "G-R13-1 STATUS.md 机器段与当前事实一致（R13 接续点未过期）"
if [ -f STATUS.md ] && [ -f scripts/status_snapshot.py ]; then
  out=$(python3 scripts/status_snapshot.py --check 2>&1)
  rc=$?
  echo "$out" | head -12
  if [ "$rc" -eq 0 ]; then report G-R13-1 1 0; else report G-R13-1 1 1; fi
else
  echo "VIOLATION: 缺 STATUS.md 或 scripts/status_snapshot.py（R13 要求两者都在）"
  report G-R13-1 0 1
fi

# ---------------------------------------------------------------- R13 归档
head1 "G-R13-2 STATUS.md 的归档指针与 .hermes/archive/status-rounds.md 双向一一对应"
# 判据（R13）：STATUS 里每个 `A<n>` 指针必须在归档里有一节 `## A<n>`；
# 归档里每一节也必须被 STATUS 引用（否则是孤儿节，下一个人找不到入口）。
# 双向都要：单向只能抓「指针断链」或「孤儿」之一，合起来才等价于「两边同步」。
# 0 样本不算违规（新克隆 / 导出树没有 .hermes/，那时 STATUS 里也不会有指针）——
# 但要显式打印，否则「0 个对象」会被当成合规证据。
ARCHIVE=.hermes/archive/status-rounds.md
ptr=""
if [ -f STATUS.md ]; then
  ptr=$(grep -oE '`A[0-9]+`' STATUS.md | tr -d '`' | sort -u)
fi
sec=""
if [ -f "$ARCHIVE" ]; then
  sec=$(grep -oE '^## A[0-9]+ ' "$ARCHIVE" | sed 's/^## //; s/ *$//' | sort -u)
fi
n_ptr=$(printf '%s' "$ptr" | grep -c . || true)
n_sec=$(printf '%s' "$sec" | grep -c . || true)
v13=0
for a in $ptr; do
  if ! printf '%s\n' "$sec" | grep -qx "$a"; then
    echo "BROKEN-POINTER $a：STATUS.md 指了它，但 $ARCHIVE 里没有 '## $a' 节"
    v13=$((v13+1))
  fi
done
for a in $sec; do
  if ! printf '%s\n' "$ptr" | grep -qx "$a"; then
    echo "ORPHAN-SECTION $a：$ARCHIVE 有这一节，但 STATUS.md 没有任何指针指向它"
    v13=$((v13+1))
  fi
done
if [ "$n_ptr" -eq 0 ] && [ "$n_sec" -eq 0 ]; then
  echo "note: STATUS 无归档指针、归档文件不存在或无节 —— 本门 0 样本，不构成证据"
fi
echo "  指针 $n_ptr 个 / 归档节 $n_sec 个"
report G-R13-2 "$((n_ptr + n_sec))" "$v13"

# ---------------------------------------------------------------- 文档引用
head1 "G-DOC-1 references/repos 的 path:line 引用必须真实存在且行号不越界"
tmp=$(mktemp)
# 跳过被显式标记的代码块（```text-gate-ignore … ```）。这些块里放的是**变异证据**，
# 不是真引用；不跳过的话门禁会因为"记录了坏引用"而永久红，人就开始忽略它。
for f in references/*.md bench/*.md; do
  [ -f "$f" ] || continue
  awk '
    /^```text-gate-ignore/ { skip=1; next }
    skip && /^```[[:space:]]*$/ { skip=0; next }
    !skip { print FILENAME ":" $0 }
  ' "$f"
done | grep -ohE 'references/repos/[A-Za-z0-9._-]+/[^ `"()<>:]+:[0-9]+' | sort -u > "$tmp"
nref=$(wc -l < "$tmp")
v=0
while IFS=: read -r p l; do
  if [ ! -f "$p" ]; then echo "MISSING-FILE $p"; v=$((v+1)); continue; fi
  total=$(wc -l < "$p")
  if [ "$l" -gt "$total" ]; then echo "LINE-OOR $p:$l (total $total)"; v=$((v+1)); fi
done < "$tmp"
rm -f "$tmp"
# 扫到 0 条引用 = 这门没有样本，不等于合规。必须 print 出来，否则绿色是假的。
if [ "$nref" -eq 0 ]; then
  echo "note: 扫到 0 条 references/repos 引用 —— 本门 0 样本，不构成证据"
fi
report G-DOC-1 "$nref" "$v"

# ---------------------------------------------------------------- G-CONTRACT-1
head1 "G-CONTRACT-1 契约校验器：results.csv 表头与 case.meta schema 必须合规"
if [ -x scripts/check_contracts.py ] || [ -f scripts/check_contracts.py ]; then
  # 用 python3（不保证可执行位在 CI 里；可执行位由 tests/unit/test_script_entrypoints.py 守）
  if python3 scripts/check_contracts.py --results bench/results.csv > /tmp/gc1.out 2>&1; then
    echo "  results.csv：合规（$(head -1 bench/results.csv | awk -F, '{print NF}') 列）"
  else
    echo "VIOLATION: bench/results.csv 不满足契约（列定义见 bench/preregistration.md:388-389）"
    sed -n '1,20p' /tmp/gc1.out
    report G-CONTRACT-1 1 1
    CONTRACT_RC=1
  fi
  # 自测：喂一个坏表头，必须被抓。抓不住说明校验器被削弱了（返回 0 = 什么都放行）。
  _bad=$(mktemp)
  head -1 bench/results.csv | sed 's/,g1,/,gX,/' > "$_bad"
  if python3 scripts/check_contracts.py --results "$_bad" > /dev/null 2>&1; then
    echo "VIOLATION: 校验器对坏表头（g1→gX）返回 0 —— 它已经不会红了"
    report G-CONTRACT-1 2 1
    CONTRACT_RC=1
  else
    echo "  自测：坏表头 g1→gX 被抓（校验器有牙）"
  fi
  rm -f "$_bad"
  [ "${CONTRACT_RC:-0}" -eq 0 ] && report G-CONTRACT-1 2 0
else
  echo "VIOLATION: 缺 scripts/check_contracts.py（契约层 G 的产物）"
  report G-CONTRACT-1 0 1
fi

# ---------------------------------------------------------------- 汇总
printf '\n---- 汇总 ----\n'
if [ "$fail" -eq 0 ]; then echo "RESULT: ALL GATES PASS"; exit 0; fi
echo "RESULT: FAIL（见上面各条的 violation 行）"; exit 1
