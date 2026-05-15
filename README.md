# paper-analyzer

一个用于精读学术论文、产出**完整中文翻译 + 双语结构化研究笔记 + 自动抽取图表代码**的 Claude Skill。

## 这个 skill 做什么

输入一篇学术论文（本地 PDF / arXiv 链接 / 粘贴文本 / DOI / 标题），输出一个**完整的论文笔记包**：

```
papers/<title>/
  ├── <title>.zh-full.md  逐段完整中文翻译（领域术语保留英文，图表按引用位置嵌入）
  ├── <title>.zh.md       中文结构化总结（4 段骨架）
  ├── <title>.en.md       英文结构化总结
  ├── figures/            按论文原序: figure-1.png, figure-2.png ...
  ├── tables/             按论文原序: table-1.png, table-2.png ...
  ├── code/               algorithm-N.md / listing-N.md（含代码块和图像备份）
  └── manifest.json
```

**翻译版 (`.zh-full.md`)** —— 给做深度阅读用：
- 章节、段落和原文一一对应，不合并不省略
- 领域专业术语保留英文（开始翻译前会先和用户对齐**领域 + 术语表**）
- 公式、引用文献、作者名保留原样
- 图表按正文第一次引用的位置嵌入

**结构化总结 (`.zh.md` / `.en.md`)** —— 给后续 scan / 复用 / 引用：
1. 元信息 & TL;DR
2. 背景/问题 & 方法
3. 实验与结果（带具体数字）
4. 创新点 · 局限 · 后续思考

**资产抽取**靠 `scripts/extract_assets.py`（PyMuPDF + pdfplumber 实现）：
- 自动找论文里所有 `Figure N` / `Table N` / `Algorithm N` / `Listing N` caption
- 按论文原序裁出来：Figure 3 一定是 `figure-3.png`
- 单/双列、protocol box、带框图表都能处理；表格智能拓宽防右列截断

**PPT 生成**靠 `scripts/generate_slides.py`（python-pptx 实现）：
- 用户提供 `.pptx` 模板 → 套用母版配色/字体，内容重新填
- 无模板 → 内置深蓝学术主题（16:9，约 10-14 张）
- 支持 title / bullets / image / formula / section / closing 六种幻灯片类型
- 公式通过 matplotlib 渲染为 PNG 嵌入

## 安装

### Step 1 — 装 Python 依赖（所有工具都要）

```bash
pip3 install --user PyMuPDF pdfplumber python-pptx matplotlib
```

### Step 2 — 克隆仓库

```bash
git clone https://github.com/JavaLyHn/paper-analyzer.git
cd paper-analyzer
```

### Step 3 — 让你的 AI 工具接入这份 skill

**核心思路**：让 AI 工具能读到 `skills/paper-analyzer/SKILL.md` 这份工作流，并能调用 `scripts/` 下的 Python 脚本。下面按工具分别说明。

---

#### 🟢 Claude Code（原生支持 Skills · 推荐）

```bash
# 软链 — 仓库 git pull 一更新就生效
ln -s "$(pwd)/skills/paper-analyzer" ~/.claude/skills/paper-analyzer

# 或者拷贝（不会跟随仓库更新）
cp -R skills/paper-analyzer ~/.claude/skills/
```

重启 Claude Code → 直接说"帮我读这篇论文 `./xxx.pdf`"会自动触发。

---

#### 🟢 Codex CLI / Codex IDE（OpenAI）

Codex CLI 不直接原生支持 Anthropic 风格的 SKILL.md，但可以通过**全局自定义指令**接入。

```bash
# 把工作流写入 Codex 的全局 instructions
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

---

#### 🟡 Cursor（通过 Rules 适配）

Cursor 没有 skill 系统，用 `.cursor/rules/*.mdc` 注入工作流：

**全局**（所有项目都用）：

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

**项目级**：把上面的 `.mdc` 放到 `<your-project>/.cursor/rules/paper-analyzer.mdc`。

---

#### 🟡 Trae（通过 Rules 适配）

Trae 也是 rules-based 工具。在 Trae 的**用户规则**或**项目规则**里粘贴：

```
当用户分享学术论文（PDF / arXiv / DOI / 论文标题）并要求阅读/总结/翻译时，请严格遵循以下工作流文件：

<仓库路径>/skills/paper-analyzer/SKILL.md

可用的脚本：
- <仓库路径>/skills/paper-analyzer/scripts/extract_assets.py  (PDF → figures/tables/code)
- <仓库路径>/skills/paper-analyzer/scripts/generate_slides.py (生成 .pptx)

注意：开始翻译前必须先和用户确认领域 + 要保留英文的术语清单。
```

把 `<仓库路径>` 换成你 clone 的实际绝对路径。

---

#### 🟡 Windsurf / Cline / Continue / 其他

通用做法：把这段加进该工具的"系统提示词"或"自定义指令"：

```
当用户分享学术论文时，参考 <仓库路径>/skills/paper-analyzer/SKILL.md 的工作流：
1. 抽取资产用 scripts/extract_assets.py
2. 翻译前必须先和用户对齐领域 + 术语表
3. 产出 .zh-full.md（完整翻译）+ .zh.md / .en.md（结构化总结）
4. 用户要 PPT 时调用 scripts/generate_slides.py
```

> 这些工具没有原生 skill 系统，主要靠 prompt 注入。效果取决于工具的 instruction-following 能力。Claude Code / Codex 是最稳的两种。

## 使用

直接和 Claude 说：

```
帮我读一下 ./my-paper.pdf
```

```
https://arxiv.org/abs/1706.03762  精读一下
```

Claude 会自动触发 `paper-analyzer`，**先和你对齐论文领域 + 要保留英文的术语清单**，然后产出三份 `.md`（完整翻译 + 中英结构化总结）加图表资产，默认保存到 `./papers/`。

## 配置

如果想固定保存路径，建一个 `paper-analyzer.config.json`（项目级）或 `~/.paper-analyzer/config.json`（全局）：

```json
{
  "outputDir": "~/Documents/papers"
}
```

## 仓库结构

```
paper-analyzer/
├── README.md
├── .gitignore
└── skills/
    └── paper-analyzer/
        ├── SKILL.md                  # skill 主体
        ├── scripts/
        │   ├── extract_assets.py     # PDF → figures/tables/code 抽取器
        │   └── requirements.txt      # PyMuPDF + pdfplumber
        └── evals/
            └── evals.json            # 测试用例
```

## 单独使用资产抽取器

抽取器可独立运行：

```bash
python3 skills/paper-analyzer/scripts/extract_assets.py \
    /path/to/paper.pdf \
    /path/to/output-dir/
```

输出（只含资产，不含 markdown 笔记 —— 那部分由 Claude skill 流程生成）：

```
output-dir/
├── figures/figure-1.png ...
├── tables/table-1.png ...
├── code/algorithm-1.md + algorithm-1.png ...   # 如有
└── manifest.json
```

## 开发与测试

```bash
# 运行测试用例（需要 anthropics/skills 的 skill-creator 工具链）
# TODO: 后续添加运行脚本
```

## License

MIT
