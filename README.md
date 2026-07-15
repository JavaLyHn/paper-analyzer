# 📄 paper-analyzer

> 一站式学术论文精读 Skill — 把一篇 PDF / arXiv / DOI 变成 **完整中文翻译 + 双语结构化笔记 + 抽取的 figures/tables/code + 可演示的 .pptx**。
>
> 支持 **Claude Code · Codex · Cursor · Trae · Windsurf · Cline** 等多种 AI 编程工具。

---

## ✨ 解决什么问题

精读一篇论文真正的成本不在"看"，而在"看完之后还能不能复用"。常见痛点：

- AI 工具给你一段散文式的总结，**找不到具体数字**就得回原文翻
- 全中文机翻**丢掉术语命名**（`Transformer` → "变压器"），后续无法搜索/引用
- 想做 slides 还要**手动从 PDF 截图**每张 figure
- 想引用某个表格的数值，**结构化笔记不够细**
- 不同领域（密码学 vs ML vs 系统）的**术语保留惯例完全不同**，一刀切翻译注定不专业

paper-analyzer 把"一次精读"沉淀成一份**完整、可归档、可移植**的笔记包：

```
papers/<paper-title>/
  ├── <title>.zh-full.md   📖 逐段完整中文翻译（术语保留英文，图表按引用位置嵌入）
  ├── <title>.zh.md        🇨🇳 中文结构化总结（4 段骨架）
  ├── <title>.en.md        🇬🇧 英文结构化总结
  ├── <title>-slides.pptx  🎤 演示文稿（用你的模板或内置学术主题）
  ├── figures/             🖼️ figure-1.png, figure-2.png, …（按论文原序）
  ├── tables/              📊 table-1.png, table-2.png, …
  ├── code/                💾 algorithm-N.md, listing-N.md（含代码块和图像备份）
  └── manifest.json        📋 这次抽出来的所有资产清单
```

---

## 🎯 核心特性

### 1. 完整翻译 + 结构化总结 双管齐下
- `.zh-full.md` — **逐段对照翻译**，不合并、不省略、不自由发挥；图表按论文正文里第一次被引用的位置自动嵌入
- `.zh.md` / `.en.md` — 4 段骨架（元信息·方法·实验·创新点），方便快速 scan 和后续引用

### 2. 领域感知的术语保留
开始翻译前会**自动识别领域 + 列出该领域要保留英文的术语清单**让你确认：

```
📋 我识别这篇论文属于：密码学 / 零知识证明系统
保留英文的术语候选：
- 基础概念：zero-knowledge proof, commitment scheme, Merkle tree, SNARK
- 协议：Groth16, Plonk, Diffie-Hellman
- 安全模型：malicious adversary, honest-but-curious, UC framework
- 论文自创：SGitChar, SGitLine（强制保留）
要加/删的吗？没有就回 OK 开始翻译。
```

`Transformer` 不会变成"变压器"，作者自创的方案名永远保留原文 — 让你日后还能搜索/引用。

### 3. 强大的图表抽取
`scripts/extract_assets.py` 基于 PyMuPDF + pdfplumber：
- 自动识别 `Figure N` / `Table N` / `Algorithm N` / `Listing N` caption
- 单/双列、protocol box、带框图表都能处理
- 表格智能拓宽 bbox 防右列截断
- 列感知的边界检测，相邻图不会互相吞并
- 严格按论文原序编号：Figure 3 一定保存为 `figure-3.png`

### 4. 可定制的 PPT 生成
`scripts/generate_slides.py` 基于 python-pptx：
- **有模板** → 深度克隆模板里的封面/章节/正文/封底参考页，把内容覆盖上去（保留原模板的 logo、配色、版式装饰）
- **无模板** → 内置深蓝学术主题（16:9，约 10-15 张）
- 六种 slide 类型：`title` / `section` / `bullets` / `image` / `formula` / `closing`
- 公式通过 matplotlib mathtext 渲染为 PNG 嵌入
- 中文字体自动设为微软雅黑

### 5. 全自动落地
**用户给一篇论文 → 自动产出全套笔记包到 `./papers/<title>/`**，不问"保存到哪"、"附录翻不翻"、"要不要总结"。唯二需要打断的两个交互：
1. Step 2：确认领域 + 术语表
2. Step 8：用户要 PPT 时确认是否有模板（仅当用户要求生成 PPT 时）

---

## 🚀 Quick Start

### 1. 装依赖

```bash
pip3 install --user PyMuPDF pdfplumber python-pptx matplotlib pillow
```

### 2. 克隆 + 安装到 Claude Code

```bash
git clone https://github.com/JavaLyHn/paper-analyzer.git
cd paper-analyzer
ln -s "$(pwd)/skills/paper-analyzer" ~/.claude/skills/paper-analyzer
```

### 3. 用起来

打开 Claude Code，直接说：

```
帮我读一下 ./my-paper.pdf
```

或者：

```
https://arxiv.org/abs/1706.03762  精读一下
```

Claude 会：
1. 抽取 figures / tables / code 资产
2. 识别论文领域，把术语清单给你确认
3. 产出 `.zh-full.md`（完整翻译）+ `.zh.md` + `.en.md`
4. 全部保存到 `./papers/<title>/`

要做 PPT？再说一句：

```
帮我做个 PPT
```

Claude 会问你"有模板吗？"，给路径就用你的模板，没有就用内置主题。

---

## 🛠️ 多工具安装指南

### 🟢 Claude Code（原生支持 Skills · 推荐）

```bash
# 软链 — 仓库 git pull 一更新就生效
ln -s "$(pwd)/skills/paper-analyzer" ~/.claude/skills/paper-analyzer

# 或拷贝（不会跟随仓库更新）
cp -R skills/paper-analyzer ~/.claude/skills/
```

重启 Claude Code → 直接说"帮我读这篇论文 `./xxx.pdf`"会自动触发。

### 🟢 Codex CLI / Codex IDE（OpenAI）

```bash
mkdir -p ~/.codex
cat >> ~/.codex/AGENTS.md <<EOF

## paper-analyzer skill
当用户分享学术论文（PDF 路径 / arXiv URL / DOI / 标题）并要求"读 / 总结 / 翻译 / 精读"时，
严格遵循 $(pwd)/skills/paper-analyzer/SKILL.md 里的完整工作流：
- Step 2 必须先和用户对齐领域 + 术语表
- 资产抽取调用 $(pwd)/skills/paper-analyzer/scripts/extract_assets.py
- PPT 生成调用 $(pwd)/skills/paper-analyzer/scripts/generate_slides.py
EOF
```

> 若你的 Codex 版本支持 `~/.agents/skills/` 标准目录（部分版本已支持 agent-skills 规范），也可以直接：
> `ln -s "$(pwd)/skills/paper-analyzer" ~/.agents/skills/paper-analyzer`

### 🟡 Cursor（通过 Rules 适配）

```bash
mkdir -p ~/.cursor/rules
cat > ~/.cursor/rules/paper-analyzer.mdc <<EOF
---
description: 当用户分享学术论文 PDF / arXiv URL / DOI / 论文标题时触发
alwaysApply: false
---

阅读并严格遵循 @$(pwd)/skills/paper-analyzer/SKILL.md 里的完整工作流。
资产抽取脚本：$(pwd)/skills/paper-analyzer/scripts/extract_assets.py
PPT 生成脚本：$(pwd)/skills/paper-analyzer/scripts/generate_slides.py
EOF
```

**项目级**：把 `.mdc` 放到 `<your-project>/.cursor/rules/paper-analyzer.mdc`。

### 🟡 Trae（通过 Rules 适配）

在 Trae 的**用户规则**或**项目规则**里粘贴：

```
当用户分享学术论文（PDF / arXiv / DOI / 论文标题）并要求阅读/总结/翻译时，请严格遵循以下工作流文件：

<仓库路径>/skills/paper-analyzer/SKILL.md

可用的脚本：
- <仓库路径>/skills/paper-analyzer/scripts/extract_assets.py
- <仓库路径>/skills/paper-analyzer/scripts/generate_slides.py

注意：开始翻译前必须先和用户确认领域 + 要保留英文的术语清单。
```

### 🟡 Windsurf / Cline / Continue / 其他

把 SKILL.md 的关键流程粘进该工具的"系统提示词"或"自定义指令"里。
效果取决于工具的 instruction-following 能力 — Claude Code / Codex 是最稳的两种。

---

## 📚 完整工作流

```
用户输入（PDF / arXiv URL / DOI / 论文标题）
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 1: 拿到论文文本                                       │
│   - PDF → pdfplumber / PyMuPDF                            │
│   - arXiv URL → 下载 PDF                                  │
│   - DOI/标题 → WebSearch 找 PDF                            │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 2: 识别领域 + 和你对齐术语表  ⚠️ 显式交互             │
│   候选领域 + 要保留英文的术语清单 → 等你回 OK              │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 3: 跑 extract_assets.py                              │
│   → figures/ tables/ code/ + manifest.json                │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 4: 产出 <title>.zh-full.md（完整翻译）                │
│   - 一段对一段，不合并不省略                                │
│   - 术语表里的词保留英文                                   │
│   - 公式、引用、作者名原样                                  │
│   - 图表按引用位置自动嵌入                                  │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 5-6: 产出 .zh.md + .en.md（4 段结构化总结）           │
│   元信息·方法·实验·创新点                                  │
└──────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│ Step 7: 落盘到 ./papers/<title>/  ✅ 全自动                │
└──────────────────────────────────────────────────────────┘
        │
        ▼ 用户说"做个 PPT"才触发
┌──────────────────────────────────────────────────────────┐
│ Step 8: 生成 .pptx  ⚠️ 先问"有模板吗？"                    │
│   有 → 套用你的模板                                        │
│   没 → 内置深蓝学术主题                                    │
└──────────────────────────────────────────────────────────┘
```

---

## 📂 输出详解

### `.zh-full.md` 完整翻译版（给深度阅读用）

```markdown
# 论文中文译名 / Original English Title

> 📖 完整翻译版 · 领域：密码学
> 保留术语：zero-knowledge proof, SNARK, Merkle tree, ...

## 摘要 / Abstract

<逐句翻译…>

## 1. 引言 / Introduction

<第 1 段译文>

<第 2 段译文>

![Figure 1](./figures/figure-1.png)
*Figure 1: 系统架构（原文 caption: System Architecture）*

<第 3 段译文>

...

## References

<整段保留原文>
```

### `.zh.md` 中文结构化总结（4 段骨架）

```markdown
# 论文中文译名

## 1. 元信息 & TL;DR
- 作者 / Authors: ...
- 会议 / Venue: ...
- TL;DR: 一句话讲清楚做了什么

## 2. 背景 / 问题 & 方法
### 2.1 要解决什么问题
### 2.2 核心方法
![Figure 1](./figures/figure-1.png)

## 3. 实验与结果
- 数据集 / 基线 / 指标（含具体数值）
![Table 2](./tables/table-2.png)

## 4. 创新点 · 局限 · 后续思考
```

### `.en.md` 英文结构化总结
同样 4 段，全英文，便于英文写作 / 引用。

### `<title>-slides.pptx`（可选）
约 10-15 张幻灯片：标题 → 背景 → 方法 → 公式 → 实验 → 创新点 → 谢幕。

---

## 🔧 单独使用脚本

两个脚本都可以脱离 skill 单独跑（命令行）：

### 资产抽取

```bash
python3 skills/paper-analyzer/scripts/extract_assets.py \
    /path/to/paper.pdf \
    /path/to/output-dir/
```

输出：

```
output-dir/
├── figures/figure-1.png ...
├── tables/table-1.png ...
├── code/algorithm-1.md + algorithm-1.png ...   # 如有
└── manifest.json
```

### PPT 生成

```bash
# 用内置主题
python3 skills/paper-analyzer/scripts/generate_slides.py /path/to/paper-dir/

# 用用户模板
python3 skills/paper-analyzer/scripts/generate_slides.py /path/to/paper-dir/ \
    --template /path/to/template.pptx
```

要求 paper-dir 下有 `slide-plan.json`（schema 见 `SKILL.md` Step 8）。

---

## ⚙️ 配置

如果想固定保存路径，建一个配置文件：

**项目级**：`./paper-analyzer.config.json`
**全局**：`~/.paper-analyzer/config.json`

```json
{
  "outputDir": "~/Documents/papers"
}
```

优先级：会话指定 > 项目配置 > 全局配置 > 默认 `./papers/`

---

## 📂 仓库结构

```
paper-analyzer/
├── README.md
├── README.legacy.md           # 旧版 README 备份
├── .gitignore
└── skills/
    └── paper-analyzer/
        ├── SKILL.md           # skill 主体（工作流定义）
        ├── scripts/
        │   ├── extract_assets.py     # PDF → figures/tables/code
        │   ├── generate_slides.py    # slide-plan.json → .pptx
        │   └── requirements.txt      # PyMuPDF, pdfplumber, python-pptx, matplotlib
        └── evals/
            └── evals.json            # 测试用例
```

---

## 🧠 工作原理简述

**资产抽取 (`extract_assets.py`)**

1. 用 PyMuPDF 扫描每页的文本 block，匹配 caption 正则（要求 `Figure N:` / `Figure N.` / `Figure N <Uppercase>` 才算）
2. 用 `page.get_drawings()` 拿到向量绘图区域作为 figure 主体候选
3. 用 pdfplumber 的 table-detection 找表格 bbox，并用稀疏度/字段长度筛掉误判
4. 单/双列布局检测：按 caption 所在列限制水平拓展边界
5. 邻近 caption 作为同列上下边界，避免相邻 figure 互相吞并
6. 按论文原序编号输出 PNG + manifest.json

**PPT 生成 (`generate_slides.py`)**

- **默认模式**：构造空白 16:9 Presentation，按 slide-plan 逐张创建，加深蓝 header bar + 白底
- **模板模式**：加载用户 .pptx，识别封面/章节/正文/封底参考页，**深度克隆** XML（含 logo、装饰图形、配色），把内容覆盖到克隆页上，最后删除原参考页
- 公式：matplotlib mathtext 渲染为透明 PNG 再嵌入

---

## 🧪 测试

仓库的 `test/` 目录下放有两篇测试论文，可以直接跑：

```bash
python3 skills/paper-analyzer/scripts/extract_assets.py \
    "test/End-to-End Encrypted Git Services.pdf" \
    /tmp/git-test/

ls /tmp/git-test/figures/  # 应该有 figure-1.png ... figure-10.png
```

---

## 🐛 常见问题

**Q: 我的论文是扫描版 PDF，抽不出文字怎么办？**
A: 先 OCR（用 `ocrmypdf` 等工具），把文本层加进去再跑。

**Q: 跑出来的 figure 边缘被切了一点点？**
A: 请提交一个 issue 附 PDF，我会调 `extract_assets.py` 里的边界探测参数（这类问题大多是因为论文版式特殊，需要适配）。

**Q: 中文 PPT 在 macOS 显示乱码？**
A: 确保系统有微软雅黑或苹方字体。脚本默认 fallback 到 `微软雅黑`。

**Q: 公式渲染失败显示成纯文本？**
A: matplotlib 没装，跑 `pip3 install matplotlib`；或者你的 LaTeX 用了 matplotlib mathtext 不支持的命令（如 `\begin{align}`），改成单行就好。

**Q: 想用自己定的 PPT 模板，但生成的幻灯片只复用了一两个版面？**
A: 模板要包含至少 4 张样例幻灯片（封面、章节、正文、封底），脚本会自动识别角色再克隆。

---

## 🤝 贡献

欢迎 PR！特别欢迎以下方向：

- 更多领域的术语清单（生物信息、HCI、量子计算 等）
- 多语言 caption 识别（中文 "图 N / 表 N"，德语 "Abbildung" 等）
- 位图 figure 检测（当前主要靠 vector drawing）
- 更多 PPT 模板适配

提 issue 时麻烦附上：
1. 论文 PDF（如果方便）或截图
2. 用的工具（Claude Code / Codex / Cursor / ...）
3. 期望行为 vs 实际行为

---

## 📄 License

GNU General Public License v3.0（GPL-3.0）— 见 `LICENSE` 文件。可自由使用 / 修改 / 二次发行，衍生作品须同样以 GPL-3.0 开源。

---

## 🙏 致谢

- [Anthropic Claude Code](https://github.com/anthropics/claude-code) — 原生 Skill 系统
- [agent-skills.io](https://agentskills.io) — 跨工具的 skill 标准
- [PyMuPDF](https://pymupdf.readthedocs.io/) / [pdfplumber](https://github.com/jsvine/pdfplumber) — PDF 解析
- [python-pptx](https://python-pptx.readthedocs.io/) — PowerPoint 操作
