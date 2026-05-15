# paper-analyzer

一个用于精读学术论文、产出**双语结构化研究笔记 + 自动抽取图表代码**的 Claude Skill。

## 这个 skill 做什么

输入一篇学术论文（本地 PDF / arXiv 链接 / 粘贴文本 / DOI / 标题），输出一个**完整的论文笔记包**：

```
papers/<title>/
  ├── <title>.zh.md     完整中文版（领域术语保留英文原文）
  ├── <title>.en.md     完整英文版
  ├── figures/          按论文原序: figure-1.png, figure-2.png ...
  ├── tables/           按论文原序: table-1.png, table-2.png ...
  ├── code/             algorithm-N.md / listing-N.md（含代码块和图像备份）
  └── manifest.json
```

**两份笔记**都按固定 4 段组织：
1. 元信息 & TL;DR
2. 背景/问题 & 方法
3. 实验与结果（带具体数字）
4. 创新点 · 局限 · 后续思考

**资产抽取**靠 `scripts/extract_assets.py`（PyMuPDF + pdfplumber 实现）：
- 自动找论文里所有 `Figure N` / `Table N` / `Algorithm N` / `Listing N` caption
- 按论文原序裁出来：Figure 3 一定是 `figure-3.png`
- 单/双列布局都处理；表格智能拓宽 bbox 防右列截断

## 安装

```bash
# 1. 装 Python 依赖（用于资产抽取）
pip3 install --user PyMuPDF pdfplumber

# 2. 安装 skill — 推荐用软链，仓库一更新就生效
ln -s "$(pwd)/skills/paper-analyzer" ~/.claude/skills/paper-analyzer

# 或一次性拷贝
cp -R skills/paper-analyzer ~/.claude/skills/
```

Claude Code 会在下次启动时自动发现这个 skill。

## 使用

直接和 Claude 说：

```
帮我读一下 ./my-paper.pdf
```

```
https://arxiv.org/abs/1706.03762  精读一下
```

Claude 会自动触发 `paper-analyzer`，识别论文领域，产出中英两份 `.md` 文件，默认保存到 `./papers/`。

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

输出：

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
