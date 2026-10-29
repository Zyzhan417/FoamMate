# references/external —— 外部资料的索引（正文副本不随仓库发布）

> 用途：给 `references/11-delivery-form.md`（交付形态 A/B 的理论支撑）提供可复核的原文出处。
> 抓取日期：2026-10-28。抓取方式：`web_extract` 正文提取（PDF 为原始文件直接 `curl`）。

## 本目录在开源仓库里只有这一个文件

**正文副本不进仓库**（`.gitignore` 里 `references/external/*.md` + `*.pdf`，只放行本文件）。
原因：那些是别人公开发表的文章，版权不是我们的，MIT 许可证不能覆盖它们，随 MIT 仓库再分发
会与 `LICENSE` 冲突。

要读原文，按下面表格里的 URL 直连；要离线复核，自己抓一份到本目录即可（下面的 `复核命令`
给出抓取后应得的行数、字节与 sha256）。

## 边界（先读这一段）

1. **这些是文档，不是仓库，所以不进 `references/registry.csv`。**
   R10 的 registry 列固定包含 `commit_sha`，其门禁（G-R10-1）要求
   `commit_sha == git -C <local_path> rev-parse HEAD`。博客与 PDF 没有 commit，硬塞进去会让门禁红。
   R10 管的是「第三方**项目**下载」，本文档包不属于该口径。
2. **这些不是 OpenFOAM 源码事实来源。** R9 的五个搜索根（`$FOAM_TUTORIALS` / `$FOAM_SRC` /
   `$FOAM_APP` / `$FOAM_ETC` / `$FOAM_UTILITIES`）仍然是唯一权威。本目录只回答
   「别人怎么做 agent 工程」，不回答「本机 OpenFOAM 怎么写字典」。
3. **`.md` 是正文提取结果，不是原始 HTML。** 图片、部分脚注与代码块格式会丢失或变形；
   需要精确引用时以表格里的 URL 原文为准，本地副本只用于离线检索。
4. **本目录不得修改原文**。要加批注请写在 `references/11-delivery-form.md` 里，不要改这里的文件。

## 清单（抓取后应得的校验值）

| 本地文件 | 来源 URL | 行 | 字节 | sha256（前 16） |
|---|---|---|---|---|
| `anthropic-building-effective-agents.md` | https://www.anthropic.com/research/building-effective-agents | 235 | 21130 | `3f8fe9e8de36e48f` |
| `anthropic-writing-tools-for-agents.md` | https://www.anthropic.com/research/writing-tools-for-agents | 223 | 24499 | `0b6ba19b838ee8fb` |
| `anthropic-agent-skills.md` | https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills | 112 | 11624 | `f4889a40333e1753` |
| `anthropic-demystifying-evals.md` | https://www.anthropic.com/research/demystifying-evals-for-ai-agents | 429 | 42763 | `438953103f782839` |
| `anthropic-claude-agent-sdk.md` | https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk | 257 | 22433 | `6ebbf4b13313298a` |
| `humanlayer-12-factor-agents.md` | https://www.humanlayer.dev/blog/12-factor-agents | 709 | 47246 | `ed0b549cdbe74f9a` |
| `openai-a-practical-guide-to-building-agents.pdf` | https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf | — | 7335065 | `1903c2b1837b206d` |
| `openai-practical-guide-extracted.md` | 同上 PDF 的正文提取（便于 grep） | 312 | 29277 | `537e067f372c6533` |

合计 8 个文件，`du -sk` 实测 7376 KB（约 7.2 MB）。

## 为什么选这七篇（每篇对应 11 号文档的哪一节）

| 文献 | 在 11 号文档里的角色 |
|---|---|
| Anthropic《Building effective agents》 | workflow vs agent 的权威定义；「先取最简方案」；工具 Poka-yoke |
| Anthropic《Writing effective tools for agents》 | 「工具是确定性与非确定性系统之间的契约」；错误响应要可操作 |
| Anthropic《Agent Skills》 | skill 里可以带确定性代码；渐进披露；2025-12-18 已标准化为开放格式 |
| Anthropic《Demystifying evals》 | **最关键一篇**：定义 agent harness / trial / outcome，支撑「我们交 harness」 |
| Anthropic《Building agents with the Claude Agent SDK》 | gather → act → verify → repeat 的循环形状与我们 A–G 链同构 |
| HumanLayer《12-Factor Agents》 | Factor 8（控制流自有，支持 B）与 Factor 10（小 agent + 大部分确定性，支持 A）之间的张力 |
| OpenAI《A practical guide to building agents》 | 最严的 agent 定义（LLM 不控制 workflow 执行就不是 agent）；HITL 两条触发 |

## 复核命令

```bash
cd <repo>/references/external
sha256sum *                       # 与上表逐行比对
wc -lc *.md                       # 行数与字节
du -sk .                          # 7376
grep -n "agent harness" anthropic-demystifying-evals.md
```
