# 六、OpenFOAM 智能体的代码级部件清单（问题①）

> 本文件是纯综合层：只允许使用 03 / 04 / 05 三份文档里的证据 + README.md §3/§4/§6。
> **不引入任何新证据**。如果某个部件在 03–05 里找不到锚点，它就不许出现在本文件里。

## 0 口径

1. 部件粒度以「能独立替换」为准（换掉它不影响其他部件的接口）。
2. 每个部件必须给六项：职责 / 输入 / 输出（含落盘路径形态）/ 失败模式 / 是否必需（K 值）/ 最小可运行版本。
3. 每个部件必须标「确定性 or 模型责任」。这是本项目 P1（LLM 做翻译与决策，脚本做判定与调度）
   的直接后果：**标错的部件是最危险的部件**（判定被交给模型 = 不可重算）。
4. 「必需」只能给能对应到 `05` §3 候选表的部件，且其 K≥2；K=1 的必须标「可选（单点实现）」。
   **不在这 8 条候选里的基础步骤**（需求解析 / 求解执行 / 人机停点）标 `K 不适用（非候选机制）`——
   K 是「有多少个互不相关的独立实现采用同一**机制**」，对「任何 agent 都必须有的步骤」它没有分辨力。
   这类部件的必要性由 `README.md` 的 R / P 规则论证，不由 K 论证。（2026-10-28 编排方补，见 §7）
5. 禁止跨臂比较、禁止未测数字、禁止引用 `bench/preregistration.md` §10 预测。

## 1 部件总表

锚点缩写：`03:` / `04:` / `05:` 分别指 `references/03-evidence-audit.md` /
`references/04-harnessfoam-deepdive.md` / `references/05-cross-project-matrix.md`；
`README.md:` 指本仓 README；第三方代码一律写全 `references/repos/<repo>/<file>:<line>`。

| 部件 | 职责 | 输入 | 输出（含落盘路径形态） | 失败模式 | 必需性(K) | 确定性归属 | 证据锚点 |
|---|---|---|---|---|---|---|---|
| 1 需求→四元组解析 | 把一句自然语言翻成四个可填槽位：几何 / 物性 / 边界条件 / 求解目标 | 需求自由文本（用户原话，无 schema） | 四元组 dict（进程内）；落盘为 `cases/<id>/case.meta` 的 `requirement` 键值段 | 缺项仍继续 → 生成时用默认值补，四门全过但需求没被满足（G 门不判「需求是否满足」） | K 不适用（非候选机制） | 模型决策+脚本校验 | references/00-project-readme.md:76-77；references/00-project-readme.md:215-217；`references/repos/harnessfoam/harnessfoam/agents/architect.py:43` |
| 2 知识检索（grep） | 在 `$FOAM_TUTORIALS` / `$FOAM_SRC` 上按字面取路径与行段，为派生源与字典写法提供事实 | 关键词列表（模型生成，自由文本）+ 固定搜索根 | `path:line:text` 命中列表；落盘 `runs/<batch>/<case_id>/log.grep` | 关键词写错 → 空结果被当「查不到」而改由记忆补答（编造形态）；检索层用随机采样 → 同一查询两次不同结果 | K=3 | 脚本判定 | 05:103（C2 中）；references/00-project-readme.md:103-105；`references/repos/harnessfoam/harnessfoam/knowledge.py:156`；`references/repos/nullflux/server.js:1081` |
| 3 case 生成（tutorial 派生 + 字典改写） | 从命中 tutorial 复制出 case 目录，再按四元组改写字典内容并记录改动 | 派生源路径（结构化）+ 四元组（结构化）+ 检索行段（文本） | `cases/<id>/` 目录树 + `cases/<id>/case.meta`（`source` / `derived_at` / `requirement` / `changes`）+ 差异文本 | 派生源版本错（v10 / legacy 语法）→ 语法对语义错；或从空目录凭空写字典 | K=3 | 模型决策+脚本校验 | 05:102（C1 中）；references/00-project-readme.md:79-81；`references/repos/harnessfoam/harnessfoam/tutorial_regression.py:17`；`references/repos/harnessfoam/harnessfoam/agents/input_writer.py:19` |
| 4 求解执行 | 拼 Allrun / 命令串，起子进程跑 `blockMesh` / `checkMesh` / `foamRun`，收退出码与日志 | case 目录 + 短跑步数 + 超时秒数 | `{returncode:int, log:path}`；落盘 `log.checkMesh` / `log.shortRun` / `log.run`（固定名） | 退出码 0 但一步没写（被当成功）；超时；日志被常量字符串替换（HPC 分支） | K 不适用（非候选机制） | 脚本判定 | references/00-project-readme.md:182；references/00-project-readme.md:228；`references/repos/harnessfoam/harnessfoam/agents/runner.py:143`；`references/repos/harnessfoam/harnessfoam/agents/graph.py:253` |
| 5 门禁判定（G1–G4 + G2b） | 对文件树 / 网格 / solver 日志做纯函数判定，出退出码 | case 目录 + 日志文件路径 | 退出码 `0/1/2/3/4` + 每门 pass/fail（CSV 列 `g1..g4`） | 判据写成子串匹配（`correct` 命中 `incorrect`）；把 soft `***` 当门 → 假失败；`SKIPPED` 与通过同值 | K=7 | 脚本判定 | 05:104（C3，K=7，**强**）；references/00-project-readme.md:180-184；references/00-project-readme.md:230；`references/repos/harnessfoam/harnessfoam/validation.py:128` |
| 6 失败反馈与修复 | 失败串 → 定位文件与 entry → 出补丁 → 重跑；带轮数上限与备份 | 失败串 + case 目录 + attempt 号 + 上限 | 新字典内容（写回 `cases/<id>/system/*`）+ 备份 `attempt_<n>/` + 改动清单 | 认不出 FATAL 指名文件即空转（只剩整份重生成）；两类失败共享一个计数器；到顶仍报「已修」 | K=6 | 模型决策+脚本校验 | 05:105（C4，K=6，**强**）；`references/repos/harnessfoam/harnessfoam/agents/graph.py:68`；`references/repos/autofoam/openfoam_agent/dict_fix.py:106` |
| 7 阶段状态机 | 把流程切成命名阶段，定「下一个跑谁」与「这一段算不算过」 | 阶段产出物路径 + 该阶段门禁退出码 | `{next_stage:枚举, passed:bool, attempts:int}`；落盘 `runs/<runId>/state.json` | 阶段只决定「下一个跑谁」不判「过没过」→ 无指纹守卫的实现（metaopenfoam，`max_loop=20`）会把同一 FATAL 烧到上限；两处声明了但不可达的路由 | K=5 | 脚本判定 | 05:108（C7 中）；`references/repos/nullflux/server.js:323`；`references/repos/cfd-agent/src/workflow.py:43` |
| 8 反思记忆 | 把失败经验按固定 schema 落盘，供跨轮 / 跨任务复用 | attempt 号 + prompt + 错误串 + 建议列表 | `.harnessfoam/failure_ledger.jsonl`（一条一行、四键）；或 `<case>/.harnessfoam/memory/<agent>.md` | 只写不读；schema 只在写侧定义；默认关闭；只记修复轮不记发散轮 | K=2 | 模型决策+脚本校验 | 05:106（C5，K=2，中）；`references/repos/harnessfoam/harnessfoam/agents/graph.py:317`；`references/repos/harnessfoam/harnessfoam/failure_ledger.py:7` |
| 9 工具接口 | 把动作封装成可被外部编排器调用的 tool（参数 schema + 返回值） | tool 名 + JSON 参数 | JSON 结果（部分 tool 带 `status`）；写类接口落盘前做路径逃逸检查 | 同一动作两套粒度并存 → 无权威；返回值与「是否真跑」无关；写接口不做逃逸检查 | K=5 | 脚本判定 | 05:107（C6 中）；`references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8`；`references/repos/harnessfoam/harnessfoam/core/mcp_server.py:127` |
| 10 版本断言 | 把 OpenFOAM 版本号当硬信号检查（日志 `Version: N` 或环境变量） | solver 日志文本 + 期望版本串（必填） | `(bool, error:str)`；错误串进 `errors` 列表 | 默认参数为空 = 断言静默关闭；`\b13\b` 命中 `13.1`；常量不被门禁复用 | K=2 | 脚本判定 | 05:109（C8 中）；`references/repos/harnessfoam/harnessfoam/validation.py:134`；`references/repos/harnessfoam/harnessfoam/case_manifest.py:8` |
| 11 人机停点 | 在「修不动 / 超能力 / 需价值判断」时停机，把现象与选项交回用户 | 终止原因（闭集枚举）+ 已试动作列表 + 选项与代价 | `{stop:true, reason, report_text}`；退出码与门禁 1–4 分流；终止状态落 `state.json` | 无显式停点 → 无限重试或静默降级；或「先做了再说」 | K 不适用（非候选机制） | 模型决策+脚本校验 | `references/repos/harnessfoam/harnessfoam/agents/graph.py:312`；`references/repos/harnessfoam/harnessfoam/core/mcp_server.py:145`；`references/repos/nullflux/server.js:3501` |

「确定性归属」只取三值：`脚本判定` / `模型决策` / `模型决策+脚本校验`。本表 `模型决策` 一栏为空是 P1 的直接结果，不是分类遗漏：
11 个部件里没有一个把判定**完全**交给模型。最接近的是部件 11——「停机时说什么、给哪些选项」由模型写，
「该不该停机」的阈值由脚本判（`references/repos/harnessfoam/harnessfoam/agents/graph.py:312` 的
`errors < max_errors` 是脚本判定，而 `references/repos/nullflux/server.js:4647` 的「熔断即汇报」是写在提示词里的规则，
靠模型执行）。

数据来源：K 值与三档评级取 `sed -n '100,109p' references/05-cross-project-matrix.md`（C1–C8 共 8 行，`grep -c '^| C'` → 8）；
「确定性归属」的判据取 `sed -n '371p;399,404p' references/04-harnessfoam-deepdive.md`（唯一由模型输出改写 `status` 的路径
及其边界）与 `sed -n '182p;215,217p' README.md`（门只判能不能跑、门与断言正交）；
本表 23 条 `references/repos/...:N` 逐条 `sed -n '<N>p'` 回切，命中 23 / 缺 0
（计数命令：`sed -n '15,45p' references/06-agent-anatomy.md | grep -oE 'references/repos/[^` ）]+:[0-9]+' | wc -l` → 23）。

## 2 逐部件展开

每个部件三件事：接口契约（输入输出的精确形状）/ 最小可运行版本（一句话落成什么命令或函数）/ 证据锚点。
**「最小可运行版本」一律是命令形态，不是伪代码**——它的作用是让「这个部件到底吃什么、吐什么」无法含糊过去。

### 2.1 需求→四元组解析

- **接口契约**：入 `prompt: str`（自由文本）→ 出 `quad: dict`，四个键 `geometry` / `properties` /
  `boundary` / `objective`（`objective` 只取 `steady` / `transient`），另加 `version_assumption: str`。
  四个键任一为空即 `raise RequirementIncomplete`，**不许填默认值**——默认值会把「需求没被满足」转成
  「门全过」，而四门恰好不判这件事。落盘：`cases/<id>/case.meta` 的 `requirement` 段（键值文本，
  `grep -n '^geometry' cases/<id>/case.meta` 可取回）。
- **最小可运行版本**：`printf '%s' "$需求" | python3 -c 'import json,sys;print(json.dumps(parse_requirement(sys.stdin.read())))'`
  —— 一个函数、一次 stdin、四个键、缺项抛异常。
- **证据锚点**：`references/00-project-readme.md:76-77`（P1：写字典是文本工作，能否运行必须由命令判定——即「翻译」归模型、
  「判定」归脚本，四元组正是翻译的产物）；`references/00-project-readme.md:215-217`（门只判能不能跑，不判改对了没有 → 需求
  是否被满足没有第二个承载点）；单点实现的对应物是
  `references/repos/harnessfoam/harnessfoam/agents/architect.py:43` 的 `plan_simulation`（返回
  `List[dict]`，是**文件清单**不是四元组，所以只能算「同形不同物」）。
- **【待定：四元组的字段名与类型在 03/04/05/README §3/§4/§6 里没有定义（04 解剖的是 file plan）。
  本文件只给四个语义槽位，不给字段名、不给类型；谁定 schema 需用户裁定。】**

### 2.2 知识检索（grep）

- **接口契约**：入 `terms: list[str]`（每项一个 grep 词）+ `roots: list[path]`（固定为
  `$FOAM_TUTORIALS` / `$FOAM_SRC`）→ 出 `hits: list[{path,line,text}]`，落盘 `runs/<batch>/<case_id>/log.grep`，
  一行 `path:line:text`。**空结果必须是显式返回值 `hits=[]`**，不是异常、不许回落到模型记忆
  （`references/00-project-readme.md:83-96`：源码是唯一权威）。
- **最小可运行版本**：`source /opt/openfoam13/etc/bashrc && grep -rn "lookupOrDefault<scalar>(\"maxCo\"" $FOAM_APP --include=*.C | head -20`；
  退出码 1 = 空 = 有效结论。
- **证据锚点**：`05:103`（C2，K=3，中；支撑 harnessfoam / nullflux / cfd-agent）；
  `references/repos/harnessfoam/harnessfoam/knowledge.py:156`（`format_context(query, k=4, max_chars=2500)`，
  词袋打分 `tag_hits*4 + min(text_hits,12)`）；`references/repos/nullflux/server.js:1081`
  （`foamFindTutorial(query, topK=12)`）；`references/repos/cfd-agent/src/database.py:161`（`# Level 1` 结构化库过滤）。
  两条反例都在 `05:103`：`references/repos/cfd-agent/src/database.py:217` 的 `random.sample(...)` 让同一查询
  两次给不同参考；`references/repos/cfd-agent/ReadMe.md:78` 的 `database_OFv24` 说明文本检索不天然版本无关。

### 2.3 case 生成（tutorial 派生 + 字典改写）

- **接口契约**：入 `{source: path（必须存在）, quad: 四元组, hits: 检索行段}` → 出 `cases/<id>/` 目录树 +
  `cases/<id>/case.meta`（四键：`source` / `derived_at` / `requirement` / `changes`）+ 一份「改了什么」的
  内容差异（不是行数差异）。派生动作只允许 `foamCloneCase <source> <target>` 或 `cp -r`；**不许从空目录写文件**。
  字典改写粒度是「文件 + entry + 新值」，不是「整份重写」。
- **最小可运行版本**：`foamCloneCase $FOAM_TUTORIALS/incompressibleFluid/cavity cases/cavity_001 &&
  printf 'source=incompressibleFluid/cavity\n' > cases/cavity_001/case.meta`；
  单点改写 `foamDictionary -entry endTime -set 0.5 cases/cavity_001/system/controlDict`。
- **证据锚点**：`05:102`（C1，K=3，中）；`references/00-project-readme.md:79-81`（P2：派生必须记录来源，凭空写字典是幻觉主源）；
  `references/repos/harnessfoam/harnessfoam/tutorial_regression.py:17`（4 个官方 tutorial 逐个复制到隔离目录
  再跑同一套门禁）；`references/repos/nullflux/server.js:259`（`foam_clone_tutorial` 的工具定义，收 `tutorial_path` + `dest`；`server.js:1081` 那一行是 `foamFindTutorial` 的关键词打分，不含派生工具）；
  `references/repos/metaopenfoam/src/Langchain_database_add_tutorial.py:22`（检索单元 = tutorial 内的一个
  输入文件块，直接作生成基底）；字典侧的接口形状取
  `references/repos/harnessfoam/harnessfoam/agents/input_writer.py:19`（按 plan 逐文件返回 dict，**不写盘**）。
- **为什么脚本只能校验到「头」**：`references/repos/harnessfoam/harnessfoam/validation.py:29` 的判据是
  `if "FoamFile" not in content:`——它能查有没有 FoamFile 头，查不出单位、量纲、边界类型是否与源 case 一致。
  这就是本部件必须标 `模型决策+脚本校验` 而不是 `脚本判定` 的原因。

### 2.4 求解执行

- **接口契约**：入 `case_dir: path` + `steps: int`（短跑步数）+ `timeout_s: int` → 出
  `{returncode: int, log: path}`；日志固定名 `log.checkMesh` / `log.shortRun` / `log.run`（门按名取，
  不靠猜）。超时必须返回 `returncode=124` 一类的显式值，不允许「还在跑」这种中间态泄到门禁层。
- **最小可运行版本**：`source /opt/openfoam13/etc/bashrc && foamRun -case <c> > log.shortRun 2>&1; echo $?`；
  短跑前 `foamDictionary -entry endTime -set <小值> -case <c> system/controlDict`。
- **证据锚点**：`references/00-project-readme.md:182`（G3 的判据对象就是 `foamRun` 的退出码与 `FOAM FATAL`）；`references/00-project-readme.md:228`
  （G3 是真正抓 bug 的那一道）；`references/repos/harnessfoam/harnessfoam/agents/runner.py:143`
  （`process.wait(timeout=300)`）；`:145`（`return process.returncode, stdout_str, ""`）；
  `references/repos/harnessfoam/harnessfoam/agents/graph.py:253`（`if returncode != 0:` 才置 `FAILED`）。
- **两条已记录的失效形态**：`04:580`（HPC 分支 `:225`/`:228` 用 `asyncio` 但模块顶部没 import，
  一旦走到就 `NameError` 被吞成 `FAILED`；且 `:230` 把日志换成常量 `"HPC Run Complete"` → 该通道
  既跑不通也无法用日志判定）；`04:581`（「一步没写」会被物理闸读成初场并通过）。

### 2.5 门禁判定（G1–G4 + G2b）

- **接口契约**：入 `case_dir: path` + `log_paths: dict` → 出 `{exit_code: 0/1/2/3/4, gates: {g1,g2,g3,g4}}`，
  退出码语义固定（`0` 全过 / `1` G1 / `2` G2 / `3` G3 / `4` G4，`references/00-project-readme.md:230`）。判据函数必须是纯函数：
  入参只有文件内容与日志文本，返回 `(bool, metrics, errors)` —— 让「判据」与「报告」同源，调用方不必二次解析日志。
  `G2b` 是辅助信号，`none` / `soft:N` / `hard:N` / `unknown`，**不进 pass/fail**。
- **最小可运行版本**：`test -f system/controlDict && test -f system/fvSchemes && test -f system/fvSolution`
  （G1）；`grep -q "Mesh OK." log.checkMesh`（G2）；`grep -q "FOAM FATAL" log.shortRun && exit 3`（G3）；
  `grep -cE '^\s*\*\*\*' log.checkMesh`（G2b）。
- **证据锚点**：`05:104`（C3，K=7，**强**——E 已按 05:113 更正为 `有对照`）；`references/00-project-readme.md:180-184`（四门 + G2b 的完整判据表）；
  `references/repos/harnessfoam/harnessfoam/validation.py:128`（`FOAM FATAL|FOAM FATAL IO ERROR|FOAM aborting`
  三合一正则）、`:138`（`return not errors, metrics, errors` 契约）；
  `references/repos/harnessfoam/harnessfoam/physics_validation.py:43`（`validate_physics`）；
  `references/repos/harnessfoam/harnessfoam/reference_benchmarks.py:11`（5 条 cavity 阈值的第一条）。
- **边界一（必须与「确定性」同时写）**：第五道视觉闸不是确定性判据。
  `references/repos/harnessfoam/harnessfoam/agents/reviewer.py:100` 逐字
  `passed = "yes" in response.content.lower() or "correct" in response.content.lower()`；
  `"incorrect".find("correct") == 2`（`04:392`），且提示词自身含 `correct`（`references/repos/harnessfoam/harnessfoam/agents/reviewer.py:92`）→ 该闸趋近恒 PASSED；
  而 `references/repos/harnessfoam/harnessfoam/agents/graph.py:370` 允许它改写 `status`（`04:371`）。
  所以本部件写「脚本判定」，指的是 **preflight / runtime / physics / reference 四道**；
  第五道只能记为「需模型看」，且其结果不能被脚本复算（`04:400-404`）。本次不把它列为第 12 个部件，
  因为它不满足「判据可被脚本重算」，进不了结构清单的确定性栏。
- **边界二**：`G2b` 的 soft 分支到今天仍然只有源码 4 处注释行作证据，没有用 `blockMesh` 复现
  （`03:42` 该缺口状态仍是「仍缺」）。本文件不把它写成已复现的事实。

### 2.6 失败反馈与修复

- **接口契约**：入 `{error_text: str, case_dir: path, attempt: int, max_attempts: int}` → 出
  `{changes: [{file, entry, new_value}], written: bool, backup_dir: path}`。写回前整目录备份到
  `attempt_<n>/`；`attempt >= max_attempts` 时必须返回终止（交部件 11），不允许「再试一次」。
  `changes` 是结构化列表而不是一段建议文本——这是本部件唯一能被脚本校验的地方（每个 `file` 必须存在、
  每个 `entry` 必须在 `file` 里恰好命中 1 次）。
- **最小可运行版本**：`while [ $n -lt 3 ]; do foamRun -case <c> > log.run 2>&1 && break; n=$((n+1));
  改字典; done` —— 一个计数器、一个备份目录、一次改写、一次重跑。
- **证据锚点**：`05:105`（C4，K=6，**强**——8 条候选里的两个强档之一，另一个是 C3）；`05:112`（强档的 E 依据：同篇内开关修复轮
  的消融 71.8% → 96.4%）；`references/repos/harnessfoam/harnessfoam/agents/graph.py:68`
  （`state['max_errors'] = 3`）、`:312`（`RETRY_PENDING` / `RETRY_EXHAUSTED` 的三元表达式）；
  `references/repos/cfd-agent/src/state.py:124`（`max_attempts: int = 30`）、
  `references/repos/cfd-agent/src/workflow.py:118`（`if consecutive >= 4:` → 升级为重写）。
- **两条反例（都在 `05:105`）**：`references/repos/autofoam/openfoam_agent/dict_fix.py:106`
  （认不出 FATAL 指名的文件就 `return None` → 环在，定向修复路径空转）；同段反例列记录的
  「scripted reflection 增益为零」（`05:105` 转记的 `01:103`/`01:19`/`01:139`；按溯源规则本文件只引 `05`，不直接引 `01`）→ **环有效，环里的反思文本无效**。这一条直接决定部件 8 的评级只能是「中」。
- **一条接口事实**：`04:234` 记录 harnessfoam 的 reviewer 轮与 autopilot 轮**共享**同一个 `errors` 计数
  （`:302` 与 `:390` 都自增），所以「恢复预算」不是按失败类型分开的。接口若照抄，两类失败会互相吃预算。

### 2.7 阶段状态机

- **接口契约**：入 `{stage: 枚举, artifacts: list[path], gate_exit_code: int}` → 出
  `{next_stage: 枚举, passed: bool, attempts: int}`；落盘 `runs/<runId>/state.json`（阶段名 → `passed` / `attempts`，
  可断点续跑）。`passed` 必须由该阶段门禁退出码决定，**不能**由「产物文件存在」决定。
- **最小可运行版本**：`python3 -c 'import json,sys;json.dump({"stage":"mesh","passed":sys.argv[1]=="0"},open(sys.argv[2],"w"))' $? runs/x/state.json`
  —— 一个 6 键 dict（`geom/mesh/setup/solve/post/report`）加一次 `json.dump`。
- **证据锚点**：`05:108`（C7，K=5，中）；`references/repos/nullflux/server.js:323`（`run_stage_done` 工具 → 
  `runs/<runId>/state.json` 断点续跑）、`:4643`（每个阶段必须以对应 `*_verify` 通过为条件）；
  `references/repos/cfd-agent/src/workflow.py:43`（`STEPS` 表，11 步）；
  `references/repos/harnessfoam/harnessfoam/agents/graph.py:470`（条件边之一；`04:77` 已用 `grep -c` 把 02 的
  「3 条」修正为 4 条：470/477/487/495）。
- **反例（决定它是「中」而非「强」）**：`05:108` 记录五家里只有 nullflux 把 `passed` 写成阶段退出条件（同格亦记载：foam-agent 有错误指纹守卫、同一 FATAL 压到 2 轮，无守卫的反例是 metaopenfoam `max_loop=20`），
  其余只决定「下一个跑谁」→ 于是同一 FATAL 只能靠轮数上限终止（metaopenfoam `max_loop=20`，`05:108` 同格反例；注意 foam-agent **不属**此列，它有错误指纹守卫，`references/repos/foam-agent/src/nodes/reviewer_node.py:23`）。
  另 `04:230-232`：harnessfoam 有两处声明了但接不上的路由（`:435-437` 的函数未被任何条件边引用；
  `:474` 映射里的 `physics_autopilot` 键不可达）——图能读通不等于路径能走到。

### 2.8 反思记忆

- **接口契约**：写侧入 `{attempt: int, prompt: str, error: str, suggestions: list[str]}` → 追加一行 JSONL 到
  `.harnessfoam/failure_ledger.jsonl`，四键固定、`error` 截断、追加模式；读侧出
  `{available: bool, attempts: int, suggestions: int, latest_error: str, file: str}`，文件缺失或 JSON 解析失败
  返回 `available: false` 而**不抛异常**（可安全嵌进报告生成）。
- **最小可运行版本**：`jq -c '{attempt,prompt,error,suggestions}' >> .harnessfoam/failure_ledger.jsonl`
  加一个 ≤24 行的只读汇总函数。
- **证据锚点**：`05:106`（C5，K=2，中）；`references/repos/harnessfoam/harnessfoam/agents/graph.py:317`
  （路径拼接）、`:320-325`（四个键的追加写）；`references/repos/harnessfoam/harnessfoam/failure_ledger.py:7`
  （`summarize_failure_ledger`，只读、返回 5 键）；`references/repos/nullflux/server.js:380`（`skill_save`
  工具描述，`05:106` 记录其约束是「只有本轮 verifier 通过才允许落盘」）。
- **三条已知缺陷（合起来说明它为什么只能是「中」）**：`04:442`（schema 只在写侧定义，读侧全程 `.get()`——
  改键名不报错，只会让 `latest_error` 恒为空）；`04:462`（`record_self_improvement` 的唯一调用点外面套
  `if state.get('memory_enabled')`，默认关）；`04:586`（`physics_autopilot_node` 也自增 `errors` 但不落账本，
  发散路径上 `attempt` 会跳号）。

### 2.9 工具接口

- **接口契约**：入 `tool_name + args(JSON)` → 出 `JSON`；返回值里**必须显式带 `status`**，不许让调用方
  自己从日志推断。写类接口必须先做路径逃逸检查：`os.path.commonpath([case_dir, target]) != case_dir` 即拒。
  粒度纪律：一个动作一个 tool，**同一动作不许有两套粒度**。
- **最小可运行版本**：一个 argparse CLI 一个动作（`python3 -m foam_agent clone <source> <target>`），
  要封成 tool 就在外面套一层 `FastMCP` 的一个 `@mcp.tool()`，参数与 CLI 完全同形。
- **证据锚点**：`05:107`（C6，K=5，中；支撑 foam-agent 7 tool / openfoam-mcp-server 12 tool（主程序 9）/
  nullflux 91 tool / deepflow 11 个 `@tool` / harnessfoam 8+11 计 1）；
  `references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8`（`mcp = FastMCP("HarnessFOAM")`，8 tool）与
  `references/repos/harnessfoam/harnessfoam/core/mcp_server.py:6`（`app = FastMCP("HarnessFOAM-MCP")`，11 tool）
  两套并存；入口分裂的实证在 `04:498`（`cli.py:84` 起 A、`main.py:1` 起 B）。路径逃逸检查的实例之一是
  `references/repos/harnessfoam/harnessfoam/core/mcp_server.py:127`。
- **两条反例**：`05:107`（openfoam-mcp-server 主程序只注册 9 个、7 个只在测试程序；且 `pipe_flow` 返回的
  `maxVelocity` / `pressureDrop` 是解析公式而非仿真产物 → 封得越整齐，越难看出返回值与算例是否真跑无关）；
  `04:491`（`run_simulation` 表面返回门禁结论，实际返回的是入图前的旧 `job` 快照）。
- **【待定：tool 的返回 schema 在 8+11 个 tool 里没有统一形状（`04` §7 两张表逐行看，`status` 只出现在部分
  tool 的返回里），本文件不定义统一 schema。】**

### 2.10 版本断言

- **接口契约**：入 `log_text: str, expected_version: str` → 出 `(bool, error: str)`；`expected_version`
  必须是**必填参数**，不给默认空串（`validation.py:125` 的默认 `""` 就是「不传就关」的意思）。
  版本号匹配要锚定整行（`^Version:\s*13$` 形态），不用 `\b13\b`。
- **最小可运行版本**：`grep -qE '^Version: *13$' log.run || exit 3`（接在 G3 后面一条）。
- **证据锚点**：`05:109`（C8，K=2，中；V 列记「无关（期望值为字面 `"13"`，机制本身不绑版本）」）；
  `references/repos/harnessfoam/harnessfoam/validation.py:134`（正则断言）、`:125`（`expected_version: str = ""`）；
  `references/repos/harnessfoam/harnessfoam/case_manifest.py:8`（`EXPECTED_OPENFOAM_VERSION = "13"`）；
  `04:255`（该常量只喂 manifest、不喂门禁，四个调用点各自写死 `"13"`——`graph.py:271` 是其中之一）；
  第二实现 `references/repos/foam-agent/src/utils.py:1175`（仅当显式指定 target 才校验 `WM_PROJECT_VERSION`），
  其默认值 `references/repos/foam-agent/src/config.py:46`（`openfoam_target: str = ""`）等于默认不校验。
- **已知边界**：`\b13\b` 对 `Version: 13.1` 成立、对 `Version:  130` 不成立（`04:332`）。要只匹配 `13`
  单值须改写成 `\bVersion:\s*13\s*$`（`04:562`）。

### 2.11 人机停点

- **接口契约**：入 `{reason: 闭集枚举, tried: list[str], options: [{act, cost}]}` → 出
  `{stop: true, reason, report_text}`。`reason` 只允许 `RETRY_EXHAUSTED` / `UNSUPPORTED` /
  `REQUIRES_USER_DECISION` 三个值；`options` 必须每项带代价（时间 / 风险 / 做不到什么），
  否则调用方无法选择。退出码与门禁 1–4 分流（`references/00-project-readme.md:230` 已占 0–4）。
- **最小可运行版本**：`if [ $n -ge $max ]; then printf '{"stop":true,"reason":"RETRY_EXHAUSTED"}\n'; exit 5; fi`
  —— 一个阈值判断加一次 JSON 打印。
- **证据锚点**：`references/repos/harnessfoam/harnessfoam/agents/graph.py:312`（轮数到顶标 `RETRY_EXHAUSTED`，
  条件是脚本判的 `errors < max_errors`）；`references/repos/harnessfoam/harnessfoam/core/mcp_server.py:145`
  （`REQUIRES_WORKFLOW_RETRY`：改完请重跑再判，即拒绝在写接口里假装判定已完成）；
  `references/repos/nullflux/server.js:3501`（`[WATCHDOG_HALT]` 的返回值里直接写「建议：告知用户」）、
  `:4647`（「熔断即汇报、禁止继续硬冲」——**这一条是写在提示词里的规则，靠模型执行**，不是脚本门）。
- **为什么它是 `模型决策+脚本校验` 而不是 `脚本判定`**：阈值（`errors < max_errors`、`maxFailPerTool: 5` +
  `maxRunMs: 6h`，`references/repos/nullflux/server.js:3400`）是脚本；「停机时向用户说什么、给哪几个选项」
  是模型产的自由文本，且 `:4647` 那条规则本身就靠模型遵守。这正是 P1 的边界样例。

## 3 数据流（文本图 + 每边的传递物类型）

```
主线：[1] → [2]/[3] → [5 G1] → [4] → [5 G2-G4]/[10] → [7] → {[6] / [8] / [9] / [11]} → 终止
逐边清单（每行一条边，箭头左侧是发出方、右侧是接收方，行尾是该边传递物的类型）：

需求（用户原话）
  ─E1 自由文本→ 1 需求→四元组解析
1 需求→四元组解析
  ├─E2 自由文本（grep 关键词）→ 2 知识检索（grep）
  │        2 知识检索 ─E3 结构化（path:line 列表）→ 3 case 生成
  └─E4 结构化（四元组）→ 3 case 生成
3 case 生成（tutorial 派生 + 字典改写）
  └─E5 结构化（文件清单 / 路径）→ 5 门禁判定 G1
5 门禁判定 G1 ─E6 结构化（退出码 0）→ 4 求解执行
4 求解执行 ─E7 结构化（退出码 + 日志路径）→ 5 门禁判定 G2/G3/G4
4 求解执行 ─E8 自由文本（solver 日志正文）→ 10 版本断言
10 版本断言 ─E9 结构化（bool + 错误串）→ 5 门禁判定
5 门禁判定 ─E10 结构化（门结论：门 id / 退出码 / 失败串）→ 7 阶段状态机
7 阶段状态机 ─E11 结构化（失败串 + attempt 号）→ 6 失败反馈与修复
6 失败反馈与修复 ─E12 自由文本（模型补丁内容）→ 3 case 生成（写回字典）
7 阶段状态机 ─E13 结构化（账本四键）→ 8 反思记忆
8 反思记忆 ─E14 自由文本（markdown 记忆注入 prompt）→ 6 失败反馈与修复
7 阶段状态机 ─E15 结构化（tool 参数 JSON）→ 9 工具接口
9 工具接口 ─E16 结构化（JSON 结果）→ 7 阶段状态机
7 阶段状态机 ─E17 结构化（终止原因枚举）→ 11 人机停点
11 人机停点 ─E18 结构化（终止状态）→ 终止
```

统计：**18 条边里，自由文本 5 条 / 结构化 13 条**（自由文本 = E1 / E2 / E8 / E12 / E14）。

这 5 条自由文本边的来源不是同一类，必须分开看：

- **E1（用户需求）**：外部产生，格式不可控 → 只能靠部件 1 把它结构化，之后再也回不到自由文本。
- **E8（solver 日志）**：外部产生（OpenFOAM 自己打的），不是模型产物。它「自由文本」但**可复算**——
  同一份 `log.run` 两次解析结果相同，所以门禁可以在它上面做判定。
- **E2（grep 关键词）/ E12（模型补丁）/ E14（记忆注入 prompt）**：**模型产生**。这三条是可校验性的真实缺口：
  E2 让检索结果的召回不可复算（换一次关键词就换一批命中）；E12 让「改了什么」在落盘前只是一段文本
  （`{file, entry, new_value}` 结构化之后才可校验）；E14 让记忆以 markdown 注入，schema 只约束写侧不约束读侧
  （`04:442`）。

因此数据流的设计目标可以一句话说清：**把 13 条结构化边保持为结构化（它们已经能被脚本判定），把 3 条模型产生的
自由文本边逐步结构化**——但本文件不承诺任何时间表，也不给出「结构化后能提升多少」的数字（`03:111` §4-1）。

数据来源：上图为按 §1 表 11 个部件与 §2 各小节的输入/输出形状手工连线；边数与两类的计数方法是
「在图块内跑一遍正则 `re.findall(r'E(\d+) (自由文本|结构化)')`」，实测输出
`18 Counter({'结构化': 13, '自由文本': 5})`（18 条边、13 条结构化、5 条自由文本）；
「自由文本但不是模型产物」这一区分依据 `03` 的 §0.1 证据分级（E0 = 本机命令输出可复算；模型输出没有对应等级，只能落「需模型看」）。

## 4 最小骨架（6 部件）与完整版（11 部件）的取舍

最小骨架 = **1 需求→四元组解析 / 2 知识检索（grep）/ 3 case 生成 / 4 求解执行 / 5 门禁判定 / 6 失败反馈与修复**。
完整版另加 7 阶段状态机 / 8 反思记忆 / 9 工具接口 / 10 版本断言 / 11 人机停点（共 11 个）。

理由只允许两类依据：`05` §3 的强 / 中评级，或 `README.md` §3 的 P 规则与 §6 的门判据。

6 个部件各自不可再减的理由（依据类型写在括号里）：

1. **需求→四元组解析** —— 唯一把自由文本变成结构化对象的入口；没有它，后面 5 个部件的输入类型都不存在
   （`references/00-project-readme.md:76-77`，P1「翻译归模型」）。K 不适用（非候选机制），入选依据不是收敛度而是入口唯一。
2. **知识检索（grep）** —— 派生源必须由它产出：`references/00-project-readme.md:83-96`（P3「源码是唯一权威，用 grep 查」）+
   `05:103`（C2 中）。少了它，「派生」只能凭印象指定源 → `03:117` 记录过的编造同型。
3. **case 生成** —— 唯一产出 case 文件树的部件；`references/00-project-readme.md:79-81`（P2）在此落地 + `05:102`（C1 中）。
   删掉它，部件 5 没有判定对象、部件 6 没有修复对象。
4. **求解执行** —— 唯一产出退出码与日志的部件；`references/00-project-readme.md:182`（G3 的判据对象）与 `references/00-project-readme.md:228`
   （G3 是真正抓 bug 的那一道）。K 不适用（非候选机制），但门禁层没有它就没有输入。
5. **门禁判定** —— 唯一把「能不能跑」从 agent 自述移到命令输出的部件（`references/00-project-readme.md:76-77`，P1）+
   `05:104`（C3 强，K=7）。
6. **失败反馈与修复** —— 8 条候选里的两个**强**档之一（`05:152-156`：强 2 / 中 6 / 弱 0）；且是唯一让 agent 从「一次生成」变成
   「收敛」的部件（`05:105`）。

**被砍掉的 5 个部件，各自的加回触发条件（都可判定，不许写「当需要时」）**：

1. **7 阶段状态机** —— 当出现「同一 case 被两次独立调用跑同一阶段」时（判据：`runs/<batch>/<case_id>/` 下
   出现第二份 `log.run`，且它不在 `attempt_<n>/` 备份目录里）→ 说明需要断点续跑，才值得把 `passed` 落盘。
2. **8 反思记忆** —— 当同一个 FATAL 首行在 **≥3 个不同 case** 的 `log.shortRun` 里出现，且现有代码无法回答
   「这条错误上次是怎么修的」时 → 才值得落账本（`05:106` 的反例说明：落账本本身不产生增益，
   只有可检索的复用才可能产生）。
3. **9 工具接口** —— 当出现**第二个消费者**且它的参数形状与现有 CLI 不同（例：需要 JSON 输入而不是 argv）时。
   `references/00-project-readme.md:120-122` 已记录「MCP 被否决」：本阶段没有第二个消费者，封装只会把「版本」与「跑完算不算成功」
   两个问题推到接口之外（`05:131`）。
4. **10 版本断言** —— 当 `ls -d /opt/openfoam* | wc -l` 的结果 > 1，或「同一 case 换机器复跑」成为验收要求时。
   本项目 R11（AGENTS.md 硬规则）禁止装第二份 OpenFOAM，所以这个触发条件在当前约束下**只能经 R11 豁免生效**。
5. **11 人机停点** —— 当同一 case 连续两轮修不好时（判据：`log.shortRun` 连续 2 次非 0 退出且失败串首行相同）。
   这条同时是 R8-4「G1–G3 连续两轮修不好 → 停下问用户」的判定形态；在此之前，部件 6 的 `max_attempts` 到顶
   本身就是停点。

**第 6 条不是砍部件而是砍粒度**：完整版把「tutorial 派生」与「字典改写」拆成两个 §2 小节讨论，最小骨架里合并为部件 3。
拆开的触发条件：同一四元组命中 **≥2 个不同 solver** 的 tutorial，且换派生源时不需重写字典（判据：
两个 tutorial 的 `system/` 文件集合完全相同、只有 `constant/` 下的物性字典不同）。

**与 §0 第 4 条的一处口径冲突，已由编排方裁定并记录（不再是待定项）**：§0 第 4 条原写「必需只能给 K≥2 的部件；
K=1 的必须标可选（单点实现）」，而部件 1 / 4 / 11 的 K 都取不到 2，最小骨架却收了部件 1 与 4。
**根因是 K 被用在了它没有分辨力的地方**：K 数的是「有多少个互不相关的独立实现采用同一**机制**」（`05:13`），
而「需求解析 / 求解执行 / 人机停点」不是 `05` §3 的候选机制，它们是任何 agent 都必须有的步骤——
在「每个实现都有」的情况下 K 恒等于实现数，不携带信息。故 §0 第 4 条已补一条豁免：
这三类标 `K 不适用（非候选机制）`，必要性由 README 的 R / P 规则论证（见 §7 口径变更记录）。
**这不是放宽判据**：凡能对应到候选表的部件（2/3/5/6/7/8/9/10）仍必须给 K 并按 K 判必需性。

## 5 部件 × 项目支撑矩阵

强度三档的判据（本表自定，写在此处以免含糊）：`强` = 多实现且判据确定；`中` = 多实现但判据部分依赖模型
或存在明确反例；`弱` = 单实现，或判据本身带模型。**强度列只表达「有多少实现 + 判据是否独立于模型」，
不能当作可比较的量**（`03:118` §4-8：不得用判据条数做质量依据）。

**这张表的「强 / 中 / 弱」与 `05` §3 的机制评级不是同一把尺，同名不同义**：`05` 的评级按 K/E/V 三维机械落档，
本表只看「实现数 + 判据是否独立于模型」。两处**现在多数一致、但不是同一判据**：
C3 确定性门禁两侧都是「强」（`05:104` 在 2026-10-28 更正后 E=`有对照`），C4 两侧都是「强」；
例：C1 tutorial 派生在 `05:102` 是「中」（E 只有 `仅实现`），本表部件 3 也是「中」（见 §5 表：派生判据确定、字典内容判据不确定）——**这一格两处恰好一致**；两把尺真正分开的地方在 C3：`05:104` 与 §5 部件 5 的**评级字母相同（都写「强」）**，但落档理由不同——前者因 E 有回放（`05:113`），后者因判据不依赖模型。**字母相同不等于同一判据**，这正是不能互相引用的原因。
**两处评级不可互相引用**：引 `05` 的评级必须写 `05:行号`，引本表的必须写 §5。
（`03:118` §4-8 已禁：不得用判据条数做质量依据。）

| 部件 | 哪些项目实现过 | 实现强度 | 最强实现锚点 |
|---|---|---|---|
| 1 需求→四元组解析 | harnessfoam（Pydantic file plan）、foam-agent（plan 服务）、metaopenfoam（InputWriter 按消息切上下文） | 弱（多实现但输出无统一 schema，判据带模型） | `references/repos/harnessfoam/harnessfoam/agents/architect.py:43` |
| 2 知识检索（grep） | harnessfoam（词袋打分 k=4）、nullflux（本机 tutorials 关键词 topK=12）、cfd-agent（结构化库四级回退） | 中（判据是打分公式可复算；但 cfd-agent 的 `random.sample` 使结果不可复算） | `references/repos/harnessfoam/harnessfoam/knowledge.py:156` |
| 3 case 生成 | harnessfoam（tutorial 回归注册表）、nullflux（`foam_clone_tutorial`）、metaopenfoam（tutorial 内文件块作基底） | 中（派生判据确定，字典内容判据不确定） | `references/repos/harnessfoam/harnessfoam/tutorial_regression.py:17` |
| 4 求解执行 | 除 hpc-skills（无任何执行/判定实现，`03:95`）外的 9 个 full 仓 | 强（多实现，判据 = 退出码，确定） | `references/repos/harnessfoam/harnessfoam/agents/runner.py:143` |
| 5 门禁判定 | harnessfoam（前四道纯函数）、nullflux、autofoam、metaopenfoam、cfd-agent、openfoam-mcp-server、foam-agent + ai-cfd-scientist（同源计 1） | 强（多实现且判据确定；harnessfoam 第五道视觉闸为例外，见 §2.5 边界一） | `references/repos/harnessfoam/harnessfoam/validation.py:128` |
| 6 失败反馈与修复 | foam-agent、metaopenfoam、nullflux、cfd-agent + ChatCFD（计 1）、harnessfoam、autofoam、openfoamgpt（文档级） | 强（多实现；E 依据是 05:105 的同篇消融，注意 C3 在 `05:113` 也是 `有对照`） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:68` |
| 7 阶段状态机 | nullflux、cfd-agent、harnessfoam、foam-agent + ai-cfd-scientist（计 1）、autofoam | 中（只有 nullflux 把 `passed` 写成阶段退出条件） | `references/repos/nullflux/server.js:323` |
| 8 反思记忆 | harnessfoam（ledger + 可选 md 记忆）、nullflux（`skill_save` + 错误库）、cfd-agent + ChatCFD（`<reflexion>`，文档级） | 中（实现了但默认关闭 / 未落盘复用；同篇消融显示 scripted reflection 无增益，`05:106`） | `references/repos/harnessfoam/harnessfoam/agents/graph.py:317` |
| 9 工具接口 | foam-agent（7 tool）、openfoam-mcp-server（12 tool，主程序 9）、nullflux（91 tool）、deepflow（11 个 `@tool`）、harnessfoam（8+11 计 1） | 中（多实现，但粒度无共识、两套并存、返回值语义不统一） | `references/repos/harnessfoam/harnessfoam/api/mcp_server.py:8` |
| 10 版本断言 | harnessfoam（日志正则，4 个调用点）、foam-agent（仅显式 target 时校验 `WM_PROJECT_VERSION`） | 中（判据确定，但两个实现里一个默认关闭） | `references/repos/harnessfoam/harnessfoam/validation.py:134` |
| 11 人机停点 | nullflux（`[WATCHDOG_HALT]` → `run_stage_done({passed:false})` → 汇报）、harnessfoam（`REQUIRES_WORKFLOW_RETRY`） | 弱（两处都只是「把状态交回调用方」的返回值或提示词约定，没有一处把「该停机了」写成独立的门） | `references/repos/nullflux/server.js:3501` |

数据来源：支撑项目与反例取 `sed -n '100,109p' references/05-cross-project-matrix.md` 的「支撑项目」与「反例」两列
（C1–C8，`grep -c '^| C'` → 8）；`hpc-skills` 无实现的依据是 `sed -n '95p' references/03-evidence-audit.md`；
「最强实现锚点」列共 11 条 `references/repos/...:N`
（`sed -n '/^## 5 /,/^## 6 /p' references/06-agent-anatomy.md | grep -oE 'references/repos/[^` ）]+:[0-9]+' | wc -l` → 11），
逐条 `sed -n '<N>p' <path>` 回切，命中 11 / 缺 0。

## 6 问题①的结论句 + 三个不可省略的理由

**一句话**：一个 OpenFOAM 智能体在代码层面由 **11 个部件**组成——需求→四元组解析、grep 知识检索、
case 生成（tutorial 派生 + 字典改写）、求解执行、门禁判定（G1–G4 + G2b）、失败反馈与修复、阶段状态机、
反思记忆、工具接口、版本断言、人机停点；按 P1 的口径，这 11 个里 **6 个是「脚本判定」、5 个是
「模型决策+脚本校验」、0 个是纯「模型决策」**。

**部件数**：11。数法贴真实输出（**不要用全文件 `grep -c` 反推**：本文现在有 3 张表，全文件计数会把它们混在一起）——

```
$ awk '/^## 1 /{f=1} /^## 2 /{f=0} f && /^\| [0-9]+ /' references/06-agent-anatomy.md | wc -l
11
$ awk '/^## 1 /{f=1} /^## 2 /{f=0} f && /^\| /' references/06-agent-anatomy.md | wc -l
12
```

第一行直接数「以 `| <数字> ` 开头的行」，只在 §1 那个区间内扫，得到 **11**（每个部件一行）。
第二行含表头，12 = 1 表头 + 11 部件。两数互相印证，且**不依赖表的总数**。

> 口径变更（2026-10-28）：初版用全文件 `grep -c '^| '` 得 24，再推 `(24 − 2) / 2 = 11`。
> 那个推导在只有 2 张表时勉强成立，**§7 变更记录表一加就失效**（该全局量本身也在漂移：写这句时是 27 行 / 24 行，加完 §7 表后实测 **29 行 / 26 行**——这正是它不能当判据的证据）。
> 「11」的结果当时是对的，但数法是错的——**用一个会随文档增长而变化的全局量去推一个局部量**。
> 现在改为按区间数，文档再加表也不会影响这两条命令。

**三个不可省略的部件**：

1. **门禁判定**（对应 C3 确定性门禁，`05:104`，K=7，评级「强」）—— 它是唯一把「能不能跑」从 agent 自述挪到
   命令输出的部件（`references/00-project-readme.md:76-77`，P1）。没有它，pass/fail 不可重算，`bench/results.csv` 的 `g1..g4`
   四列没有来源，报告里的每个「过了」都只能是自述。
2. **失败反馈与修复**（对应 C4 失败反馈环，`05:105`，K=6，评级「强」）—— 8 条稳定架构候选里落「强」档的两条之一
   （另一条是 C3 确定性门禁；`05:156` 已按更正后的口径写成「强 2 / 中 6 / 弱 0」）。它也是两条 `E=有对照` 里唯一以「消融」形式给出的（C3 是回放形式）
   （`05:112`：同篇内开关修复轮 71.8% → 96.4%）。没有它，智能体退化为「一次生成器」，而一次生成器没有第二次机会。
3. **case 生成**（对应 C1 tutorial 派生，`05:102`，K=3，评级「中」）—— 唯一产出 case 文件树的部件，`references/00-project-readme.md:79-81`（P2）
   的硬约束在此落地。删掉它，部件 5 没有判定对象、部件 6 没有修复对象：这条依存关系是单向的、不可用别的部件替代。

本清单是**结构清单**，不含任何关于「哪个部件更重要」的绩效主张：K 只表示「有多少个互不相关的独立实现这么做」，
不表示「有多少个验证过它有效」（`05:13`、`05:146`）；三档评级只表达「收敛度 × 证据强度 × 版本无关性」，不是实测绩效
（`05:146-148`）；本文件不含任何跨臂数字（`03:111` §4-1），未给 `human_interventions` 任何取值（`03:114` §4-4），
未引用 `bench/preregistration.md` §10（`03:113` §4-3）。

## 7 口径变更记录

| 日期 | 改了哪条 | 为什么 | 谁批的 |
|---|---|---|---|
| 2026-10-28 | §0 第 4 条：新增「不在 8 条候选里的基础步骤标 `K 不适用（非候选机制）`」豁免 | K 度量的是「多少个独立实现采用同一**机制**」；需求解析 / 求解执行 / 人机停点不是 `05` §3 的候选机制，任何 agent 都有，K 恒等于实现数、不携带信息。原条文会强制把这三类标成「可选」，与最小骨架收录部件 1 与 4 直接冲突 | 编排方（本条由 worker 以【待定】上报，未自行改写 §0；裁决与记录由编排方补） |
| 2026-10-28 | §1 表中 C3 的评级「中」→「强」、C4 的 K「7」→「6」、C5 的 K「3」→「2」；§2/§4/§6 同步 | `05` 在本文件写完后被独立 critic 判定 FAIL 并更正：C3 的 E 由 `仅实现` 改为 `有对照`（§0:111 明写覆盖「消融**或回放**」，CFD Forge 36 状态回放符合）→ 评级升「强」；C4 剔除 docs_only 的 openfoamgpt → K=6；C5 剔除未落盘复用的 cfd-agent↔ChatCFD → K=2。本文件原先引用的是更正前的值 | 编排方（依据 `05:113` 的更正记录） |
| 2026-10-28（修正前一行） | 上一行当时**只改了 §2/§4/§6，§1 表的「必需性(K)」列漏改**（部件 6 仍 K=7、部件 8 仍 K=3），于是同一行的「证据锚点」写 K=6/K=2、K 列写 K=7/K=3，表内自相矛盾 | 被 06 的独立 critic 逐行对照 05 时发现（E1）。**教训：一次「同步多处」的批量改写必须逐单元格复核，尤其当同一行里既有值又有它的来源时**——两处不一致比一处错更难发现，因为任何单点检查都只看其中一处 | 编排方 |
| 2026-10-28 | §6 部件数的数法：全文件 `grep -c '^\| '` → 改为按 §1 区间 `awk` 计数 | 初版的 `(24−2)/2 = 11` 用一个**会随文档增长而变化的全局量**推局部量；§7 变更记录表一加（第 3 张表）推导即失效（实测 27 / 24）。结果 11 当时正确，数法错误 | 编排方（critic E4） |

**教训**：本文件是 06 写于 `05` 定稿之前，于是 `05` 一改，06 的三处 K 值与两处评级全部变陈旧。
**下游文档引用上游的「可变量」时，必须引用「行号 + 值」而不是只引行号**——本次三个值都变了，
只引 `05:104` 的话，读者回去看到的是新值，正文却是旧值，两边都对不上。
