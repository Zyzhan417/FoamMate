# 参考库检索协议（冻结于 2026-10-27，M4a）

本文件记录**怎么找到这些项目的**，以及一套可复现的门禁。它和 `01-landscape.md` 的分工：
本文件只写「查了什么、怎么筛、怎么判合规」，结论在 01/02 两份文档里。

规则依据：`AGENTS.md` R9（参考库只读、不作源码事实来源）、R10（体积线与登记）。

---

## 1. 查询式（逐字，可复现）

所有命令在 `source /opt/openfoam13/etc/bashrc` 之后执行（本项目所有操作都在 v13 环境内）。

### 1.1 arXiv（无 key，每次请求间隔 ≥3 s）

```bash
# 主查询：本领域全池
curl -sS "https://export.arxiv.org/api/query?search_query=abs:%22OpenFOAM%22+AND+%28abs:%22LLM%22+OR+abs:%22agent%22+OR+abs:%22language+model%22%29&start=0&max_results=40&sortBy=relevance"

# 同义查询（用于确认没有漏召回，并记录各池大小）
#   abs:"OpenFOAM" AND abs:"agent"                                   -> 22
#   abs:"OpenFOAM" AND abs:"LLM"                                     -> 17
#   abs:"CFD" AND abs:"agent" AND abs:"LLM"                          -> 20
#   abs:"OpenFOAM" AND abs:"RAG"                                     -> 7
#   all:"OpenFOAM" AND all:"large language model"                     -> 14
#   abs:"simulation" AND abs:"LLM agent"                             -> 662（太宽，不采用为主池）
```

实测（2026-10-27）：主查询 `opensearch:totalResults = 25`，返回 25 条。
**结论：池子小到可以全读，因此不做抽样、不做「top10 抽查」，25 条逐条过。**

### 1.2 GitHub（必须用已登录的 `gh api`）

```bash
gh auth status        # 实测已登录（需 `gh auth login` 后才有输出）

for q in "openfoam agent" "openfoam llm" "openfoam mcp" "cfd llm agent" "CFD agent LLM" "OpenFOAM automation"; do
  gh api -X GET search/repositories -f q="$q" -f sort=stars -f order=desc -f per_page=10 \
    --jq '.items[] | "\(.stargazers_count)\t\(.size)\t\(.full_name)\t\(.language // "-")\t\(.pushed_at[0:7])\t\(.license.spdx_id // "-")"'
  sleep 2
done | sort -u > gh_candidates.tsv
```

实测：去重后 **37 条**。各查询命中数：`openfoam agent` 66 / `openfoam llm` 22 / `openfoam mcp` 14 /
`cfd llm agent` 19。

**反例（写下来防止下次再踩）**：匿名 `api.github.com/search/repositories` 在扫到第 6 个查询时返回
`API rate limit exceeded for 153.3.60.168`，而前 5 个查询的结果**看起来像一份完整排名**。
匿名接口只能用于单次查询，多查询扫描必须走 `gh api` 且间隔 ≥2 s。

---

## 2. 纳入 / 排除规则（判据，不需要讨论）

| 规则 | 判据 | 动作 |
|---|---|---|
| I1 | 论文对象是 OpenFOAM（或明确面向 OpenFOAM 的 CFD 工作流） | 纳入 |
| I2 | 有 LLM/agent 成分（提示、微调、RAG、多 agent、工具调用均可） | 纳入 |
| I3 | 仓库能定位到「agent 驱动仿真」而非「GUI / 后处理 / 单点脚本」 | 纳入候选 |
| E1 | 纯算法库、纯求解器开发、与 LLM 无关的耦合平台（如 DRLinFluids、Microbubble、Open ISA） | 排除，但**在 01 的表后列出名字与排除理由**——不许静默丢弃 |
| E2 | 单项目检出体积 > 100 MB（R10） | 降级 `docs_only`，不下载；不得「下一半」 |
| E3 | 需要第二份 OpenFOAM 才能运行（R11） | 保留分析，tier 记 B/C，本阶段不跑 |

排除也必须留痕：E1 的每一条都要在 01 的「排除清单」里点名，因为「没看见」和「看见了但排除」
对读者是两件事。

---

## 3. 去重规则：`project_id` 是主键

本领域论文与仓库高度一一对应（实测三例：`2505.04997`↔`csml-rpi/Foam-Agent`、
`2407.21320`↔`Terry-cyx/MetaOpenFOAM`、`2506.02019`↔`tianhanz/ChatCFD`）。
所以**不按「论文 top-N + 仓库 top-N」两套清单分别处理**，而是：

1. 一条 `project_id` 可以同时挂 `paper_url` 与 `repo_url`；
2. 只下一次代码；
3. 汇报时给 **distinct project 数**，不给「10 篇 + 3 仓 = 13 个研究」这种错误加总。

实测结果：本地 9 个 full + 2 个 docs_only = **11 个 distinct 项目**。

---

## 4. 影响力打分（权重在取数**之前**冻结，不得事后调整）

```
score = 3*has_code + 2*cited_as_baseline + 1*log10(1+stars) + 1*log10(1+citations) + 0.5*recency_ok
```

| 项 | 取数来源 | 说明 |
|---|---|---|
| `has_code` | 仓库 URL 是否可访问 | 0/1 |
| `cited_as_baseline` | 池内其他论文的 Related/Baseline 段是否点名 | 0/1/2，按被引次数封顶 2 |
| `stars` | `gh api repos/<r>` 的 `stargazers_count` | 取数日期必须写进表 |
| `citations` | Semantic Scholar `paper/arXiv:<id>?fields=citationCount` | 取数日期必须写进表 |
| `recency_ok` | `pushed_at` 在最近 12 个月内 | 0/1 |

**为什么要复合分**：本领域论文几乎全落在 2024–2026，纯引用数会把「已经被当作 baseline 的最新工作」
系统性地排到后面（例：Foam-Agent 有 352★ 但发表不足两年）。纯 star 又会把「中文社区热、学界未采用」
的项目抬到前面。权重写死在这里，就是为了防止看完结果再回头调。

---

## 5. 下载与登记（R10 落地）

```bash
git clone --depth 1 --quiet https://github.com/<owner>/<repo>.git references/repos/<project_id>
git -C references/repos/<project_id> rev-parse HEAD      # -> registry.commit_sha
du -sm references/repos/<project_id>                     # -> registry.size_mb
```

列固定（`references/registry.csv`）：

```
project_id, kind, source_url, commit_sha, size_mb, license, declared_of_version, tier, mode, local_path, note
```

**实测教训（务必保留）**：GitHub 报的 `size` 与 `du -sm` 差一个数量级——

| 项目 | GitHub 报 | `du -sm` 实测 |
|---|---|---|
| Foam-Agent | 44627 KB (43.6 MB) | **2 MB** |
| nullflux | 80710 KB (78.8 MB) | **43 MB** |
| cfd-agent | 19438 KB (19.4 MB) | **66 MB** |

两个方向都会发生。以 cfd-agent 为例，实测构成（`du -sm cfd-agent/*`）：
`run_chatcfd/` 15 MB、`inputs/` 14 MB、`database_OFv24/` 14 MB、`figures/` 6 MB——
**检出体积的大头是知识库数据与输入样例，不是代码**。**只认 `du -sm`。**


`tier` 的判定线（静态，读 README/代码，不跑）：

| tier | 判据 | 例 |
|---|---|---|
| **A** | 声明或代码里就是 OpenFOAM 13，无其它版本硬编码 | `harnessfoam`（README:100 "OpenFOAM Version 13"） |
| **B** | 硬编码别的版本 / 需要容器 / 知识库绑版本 | `foam-agent`(v10)、`cfd-agent`(v2406)、`autofoam`(v2412)、`deepflow`(v2412)、`openfoam-mcp-server`(12) |
| **C** | 依赖只有别的版本才有的求解器/库，或根本没有可跑代码 | `openfoamgpt`（无官方仓） |

---

## 6. 门禁（复制即可跑，每条必须能被违反）

```bash
# 一条命令跑完 R9/R10/R11/R12 与文档引用校验（脚本已落盘，含变异自测）
bash scripts/verify_references.sh            # 设计期
bash scripts/verify_references.sh --frozen   # 预注册冻结后（多查 status 多样性）
```

下面保留各条的原理，便于脚本坏了的时候手检。

```bash
# G-R9-1  参考库未被本地修改
#   判据：每个 full 行的仓库 `git status --porcelain` 必须为空。
#   不要用 mtime：把树复制到别处后每个文件都晚于 registry.csv，实测 1791 个文件全部误红。
for p in $(python3 -c "
import csv
for r in csv.DictReader(open('references/registry.csv',encoding='utf-8')):
    if r['mode']=='full': print(r['local_path'])"); do
  [ -z "$(git -C $p status --porcelain)" ] || echo "DIRTY $p"
done

# G-R10-1 sha 与实测体积必须与登记表一致
python3 - <<'EOF'
import csv, subprocess
bad = 0
for r in csv.DictReader(open("references/registry.csv", encoding="utf-8")):
    if r["mode"] != "full":
        assert r["local_path"] == "" and r["note"], f"docs_only 行不合法: {r['project_id']}"
        continue
    sha = subprocess.run(["git","-C",r["local_path"],"rev-parse","HEAD"],capture_output=True,text=True).stdout.strip()
    du  = int(subprocess.run(["du","-sm",r["local_path"]],capture_output=True,text=True).stdout.split("\t")[0])
    if sha != r["commit_sha"] or du != int(r["size_mb"]):
        print("MISMATCH", r["project_id"], sha[:10], r["commit_sha"][:10], du, r["size_mb"]); bad += 1
    if du > 200: print("OVER-CAP", r["project_id"], du); bad += 1
print("checked=%d mismatches=%d" % (sum(1 for _ in csv.DictReader(open("references/registry.csv", encoding="utf-8"))), bad))
EOF

# G-R11-1  只有一个 OpenFOAM
ls -d /opt/openfoam*            # 期望只有 /opt/openfoam13
docker images 2>/dev/null | grep -ci openfoam   # 期望 0

# G-R12-1  设计期禁跑：bench/runs/ 必须为空
find bench/runs -type f 2>/dev/null | head    # 期望空

# G-DOC-1  引用的第三方路径必须真实存在（不是编造的行号）
grep -ohE 'references/repos/[a-z0-9-]+/[^ `:)]+:[0-9]+' references/*.md \
  | sort -u | while IFS=: read p l; do
      [ -f "$p" ] || echo "MISSING-FILE $p"
      total=$(wc -l < "$p" 2>/dev/null || echo 0)
      [ "$l" -le "$total" ] || echo "LINE-OOR $p:$l (total $total)"
    done
```

`G-DOC-1` 是这一批文档最容易失守的一条：架构分析里 90% 的引用是 `path:line`，
而「行号超出文件长度」是编造引文最典型的形态，人眼审不出来。

---

## 7. 本阶段的范围（防止下一个人把设计当实跑）

- 本阶段（M4a）交付 4 份文档 + 参考库 + 登记表，**不跑任何被测项目**（R12）。
- 版本适配（A/B/C → 命令级替换）与 12 任务实跑属于 M4b，前置条件是 `bench/preregistration.md` 已冻结。
- 本文件与 01/02 里的 tier 是**静态判定**，M4b 实跑后允许修正，但必须留下修正记录。
