# paper-analyzer

一个用于精读学术论文、产出**双语结构化研究笔记**的 Claude Skill。

## 这个 skill 做什么

输入一篇学术论文（本地 PDF / arXiv 链接 / 粘贴文本 / DOI / 标题），输出**两份完整的结构化总结**：

- **中文版** —— 根据论文所在领域（密码学、机器学习、系统、理论 …）保留对应的英文术语原文
- **英文版** —— 完整英文笔记，结构与中文版对齐

每份笔记按固定 4 段组织：
1. 元信息 & TL;DR
2. 背景/问题 & 方法
3. 实验与结果（带具体数字）
4. 创新点 · 局限 · 后续思考

## 安装

把 `skills/paper-analyzer/` 整个文件夹复制到你的 Claude skills 目录：

```bash
# Claude Code (macOS / Linux)
cp -R skills/paper-analyzer ~/.claude/skills/

# 或者用符号链接，方便后续更新
ln -s "$(pwd)/skills/paper-analyzer" ~/.claude/skills/paper-analyzer
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
        ├── SKILL.md          # skill 主体
        └── evals/
            └── evals.json    # 测试用例
```

## 开发与测试

```bash
# 运行测试用例（需要 anthropics/skills 的 skill-creator 工具链）
# TODO: 后续添加运行脚本
```

## License

MIT
