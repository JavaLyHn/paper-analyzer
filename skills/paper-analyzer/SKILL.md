---
name: paper-analyzer
description: Read an academic paper (PDF, arXiv link, pasted text, or DOI/title) and produce a complete paper-study package — full paragraph-by-paragraph Chinese translation, plus structured Chinese & English summaries, plus extracted figures / tables / algorithms / listings saved into per-paper subfolders following the paper's own numbering (Figure 1, Table 1, Algorithm 1, etc.). Detects the paper's academic field, confirms a domain glossary with the user, and preserves field-appropriate English terminology in both the Chinese translation and summary. Use this skill whenever the user shares a paper, an arXiv URL, a DOI, a paper title, or pastes a chunk of academic text and asks to "read / summarize / translate / analyze / 解读 / 翻译 / 总结 / 精读" it — even if the user does not explicitly say "use paper-analyzer". Also trigger when the user wants to compare or do a literature review starting from a single paper.
---

# Paper Analyzer

把一篇学术论文变成一份**完整可归档、自带原文图表、术语命名保留**的研究笔记包：

- **完整中文翻译版**（逐段翻译，按原文位置嵌入图表）
- **中文结构化总结**（4 段骨架，便于检索复用）
- **英文结构化总结**（同样 4 段，便于英文写作 / 引用）
- 按原文顺序抽出的 figures / tables / code 子文件夹

中文翻译和中文总结都根据论文所在的**学术领域**，保留该领域大家公认不翻译的英文术语 —— 在翻译开始前会**先和用户对齐领域和术语表**。

## 为什么需要这个 skill

读论文最贵的不是看，而是**看完之后能不能复用**。问题在于：

- **机翻全中文**会丢掉作者的术语命名，下次想搜索/引用时反而找不到（"变压器架构" ≠ "Transformer architecture"）
- **只看英文原文**，做中文写作或讲给同事听都得二次翻译
- 用一段散文当总结，下次想引用某个数字还得翻原文
- 关键图表只在 PDF 里 —— 想插进 Notion/Obsidian/写作里都要手动截图
- 不同领域（密码学 vs ML vs DB）保留英文的惯例完全不同，一刀切翻译注定不专业

这个 skill 的设计是：**一份完整的论文笔记包**

```
papers/<title>/
  ├── <title>.zh-full.md  逐段完整翻译（领域术语保留英文，图表按引用位置嵌入）
  ├── <title>.zh.md       中文结构化总结（4 段骨架）
  ├── <title>.en.md       英文结构化总结
  ├── figures/            按论文原序: figure-1.png, figure-2.png ...
  ├── tables/             按论文原序: table-1.png, table-2.png ...
  ├── code/               algorithm-N.md / listing-N.md（含代码块和图像备份）
  └── manifest.json       这次抽出来的所有资产清单
```

资产编号严格跟随论文原文（Figure 1 就是 `figure-1.png`）。

---

## 何时使用

触发场景（用户不一定明说，应当主动使用）：

- 用户发了 PDF 文件路径、arXiv 链接（`arxiv.org/abs/...`、`arxiv.org/pdf/...`）、DOI、论文标题
- 用户粘贴了一大段明显是论文摘要/正文的英文文字
- 用户说 "帮我读一下"、"精读"、"总结这篇"、"summarize this paper"、"give me a TL;DR"、"analyze this"
- 用户在做综述、从一篇论文切入

**不要使用** 的场景：

- 用户只是问"XX 论文讲了啥"这种**没有附材料**的常识性问题——这是检索任务
- 用户发的是非学术内容（博客、新闻稿、说明书）

---

## 整体流程

> **🔑 核心原则**：用户给一篇论文，**自动产出全套笔记包并落盘到 `./papers/<title>/`**。
> 不要问"要保存到哪"、"附录要不要翻"、"要不要总结也写一份"。
> **三份 `.md` + 全部 figures/tables/code + manifest.json 默认全开**。
> 唯二需要打断用户的是 Step 2（领域 + 术语表）和 Step 8（PPT 模板，只在要求生成 PPT 时）。

```
用户输入
    │
    ▼
[Step 1] 拿到论文文本（PDF / URL / 粘贴 / DOI 四种来源）
    │
    ▼
[Step 2] 识别领域 → 把候选领域 + 该领域要保留的英文术语清单交给用户确认
    │      （← 用户回复前不要开始翻译；这是 .zh-full.md / .zh.md 的术语标准）
    ▼
[Step 3] 抽取资产 → figures/ tables/ code/（仅当输入是 PDF 时可用）
    │
    ▼
[Step 4] 产出 <title>.zh-full.md ← 完整逐段中文翻译
    │      （按确认的术语表保留英文；在 figure/table 首次被引用的段落后嵌入相对路径）
    ▼
[Step 5] 产出 <title>.zh.md ← 中文结构化总结（4 段）
    │
    ▼
[Step 6] 产出 <title>.en.md ← 英文结构化总结（4 段）
    │
    ▼
[Step 7] 把整个 papers/<title>/ 包保存到用户配置的路径 + 聊天里默认展示翻译版
```

---

## Step 1: 拿到论文文本

| 输入类型 | 处理方式 |
|---------|---------|
| 本地 PDF | 用 PDF 抽取工具（pdfplumber / pdftotext / pypdf）拿到完整文本。如果是扫描件 OCR 不出，**明确告诉用户**而不是猜 |
| arXiv URL | 把 `abs` 改成 `pdf` 下载，或调 arXiv API 拿标题/作者/分类作为元信息 |
| 粘贴文本 | 直接用，但在元信息里提示**正文可能不完整**，元信息按用户给的为准 |
| DOI / 论文标题 | 先用 WebSearch 确认标题、作者、年份；能拿到 PDF/arXiv 就抽全文；只能拿到摘要时**明确声明"仅基于摘要"**，不要假装看完了全文 |

**重要**：如果用户给的来源你没把握抽到全文（如 IEEE/Springer 收费墙），**先告诉用户你目前能拿到什么**，让用户决定是基于摘要继续，还是发 PDF 过来。不要静默地拿摘要冒充全文总结。

---

## Step 2: 识别领域并和用户对齐术语表 ← 关键交互

**这一步是显式交互，不要跳过。** 翻译和总结都要按这里确认的术语表来处理。

### 流程

1. **自动识别领域**（用下面三个信号）：
   - arXiv 分类（`cs.CR` 密码学/安全，`cs.LG` 机器学习，`cs.DB` 数据库，`cs.DC` 分布式……）
   - 摘要+引言里反复出现的核心名词
   - 引用集中的会议（CRYPTO/USENIX Security → 密码学；NeurIPS/ICML → ML；SIGMOD/VLDB → 数据库；OSDI/SOSP → 系统）

2. **从论文里挑保留词表**。结合下面的领域参照 + 论文里实际反复出现的特有名词（如作者自创的方案名 `SGitChar`），列出**10-25 个**该篇要保留英文的术语。

3. **把候选领域 + 术语表交给用户确认**，格式如下：

   ```
   📋 我识别这篇论文属于：**密码学 / 零知识证明系统** （置信度：高）

   中文翻译和总结里我打算**保留英文**的术语（你可以增/删/改）：

   - **基础概念**：`zero-knowledge proof`, `commitment scheme`, `Merkle tree`, `SNARK`, `zk-SNARK`
   - **协议/算法**：`Groth16`, `Plonk`, `Halo2`, `Diffie-Hellman`, `Schnorr signature`
   - **安全模型**：`malicious adversary`, `honest-but-curious`, `UC framework`
   - **论文自创术语**：`SGitChar`, `SGitLine`（论文里的方案名，**强制保留**）
   - **数学符号**：`F_p`, `G_1`, `G_2`, `pairing`

   有要加/删的吗？没有就回复"OK"，我开始翻译。
   ```

4. **等用户回复**。用户可能：
   - 回复 "OK" → 用这个表
   - 加几个词 → 加进去
   - 改领域（"这其实是 ML 安全交叉") → 重新拉术语表再问一次
   - 反对某个保留（"`commitment scheme` 翻成'承诺方案'就行"）→ 从表里去掉

5. 用户确认后，**整个 .zh-full.md 和 .zh.md 都用这个术语表**。出现表里的词永远不翻译；首次出现时给括注，如"零知识证明（zero-knowledge proof, ZKP）"，之后用 ZKP 即可。

### 各领域参照清单

下面是给你"拉初稿术语表"用的，**不是要全部塞进去**，要按论文实际内容筛。

**密码学 / 系统安全 (cryptography, security)**：
- 协议/算法名：`AES`、`RSA`、`ECDSA`、`SHA-256`、`HMAC`、`Diffie-Hellman`、`Groth16`、`Plonk`
- 概念：`zero-knowledge proof`、`commitment scheme`、`Merkle tree`、`hash function`、`pairing`
- 安全属性：`IND-CPA`、`IND-CCA`、`forward secrecy`、`post-quantum`、`semantic security`
- 系统组件：`oblivious RAM`、`trusted execution environment (TEE)`、`SGX`、`zk-SNARK`、`MPC`
- 威胁模型：`malicious adversary`、`honest-but-curious`、`semi-honest`、`side-channel`
- 协议步骤：`commit`、`reveal`、`verify`、`challenge`、`response`、`prover`、`verifier`

**机器学习 / 深度学习 (ML, DL, NLP, CV)**：
- 架构名：`Transformer`、`CNN`、`RNN`、`LSTM`、`GAN`、`VAE`、`Diffusion model`、`MoE`
- 训练机制：`attention`、`backpropagation`、`gradient descent`、`fine-tuning`、`RLHF`、`SFT`、`LoRA`
- 数据/任务：`ImageNet`、`GLUE`、`SQuAD`、`few-shot`、`zero-shot`、`in-context learning`、`chain-of-thought`
- 指标：`accuracy`、`F1`、`BLEU`、`ROUGE`、`perplexity`、`AUC`、`mAP`

**系统 / 数据库 / 分布式 (systems, DB, distributed)**：
- 一致性模型：`linearizability`、`serializability`、`eventual consistency`、`CAP theorem`、`snapshot isolation`
- 协议：`Paxos`、`Raft`、`2PC`、`3PC`、`MVCC`、`vector clock`
- 系统名：`Kubernetes`、`Spanner`、`HDFS`、`Kafka`、`Redis`
- 性能术语：`throughput`、`latency`、`tail latency`、`p99`

**理论计算机科学 (theory, algorithms)**：
- 复杂度类：`P`、`NP`、`PSPACE`、`#P`、`BPP`、`PCP`
- 范式：`approximation algorithm`、`online algorithm`、`streaming algorithm`、`randomized algorithm`

**新领域**（生物信息、计算金融、HCI、量子计算等）：
没有预置清单。**从论文里现挖** 10-25 个高频专有名词作为该篇的保留表，照常和用户确认。

**论文自创术语**（任何领域都要！）：
作者在本文里自己起的方案名/算法名/系统名，**强制保留英文原文**，不论是否在通用术语表里。这类词翻译了反而搜不到原文。

---

## Step 3: 抽取论文资产（仅 PDF 输入）

如果输入是 PDF（本地文件或下载好的 arXiv PDF），**先跑一次资产抽取脚本**，让后续的 markdown 总结可以直接引用提取出的图表，而不是要求用户回去翻 PDF。

### 调用方式

```bash
python <skill-dir>/scripts/extract_assets.py <pdf-path> <output-dir>
```

- `<output-dir>` 是 `papers/<sanitized-title>/`，脚本会在里面建 `figures/`、`tables/`、`code/`
- 脚本会扫描 PDF 里所有 `Figure N` / `Table N` / `Algorithm N` / `Listing N` 标题
- 输出按论文**原序**编号：Figure 3 一定保存为 `figure-3.png`
- 表格同时产出 PNG（一定能用）和 markdown（pdfplumber 解析，复杂表头可能丢真度）
- 算法 / 列表同时产出 markdown 代码块和 PNG 备份
- 完成后写一份 `manifest.json` 总结

### 解析 manifest

跑完之后先读 `<output-dir>/manifest.json`，了解：

- 提取到了哪些资产
- 哪些表 pdfplumber 没能解析（manifest 的 `warnings` 字段会标出）
- 资产对应的页码（方便在总结里引用 "见 Figure 3 (p.8)"）

### 何时跳过这一步

- **粘贴文本**：没有 PDF，跳过抽取，在总结开头加一行 `> 注：未提供 PDF，本笔记不含图表附件`
- **仅基于摘要**：同上
- **arXiv URL**：先下载 PDF（`wget <abs-url:s/abs/pdf/>` 或 `curl -L -o`），再跑抽取
- **DOI / 标题**：先用 WebSearch 拿到可用 PDF；拿不到就跳过

### 失败时怎么办

- 脚本依赖 `PyMuPDF` 和 `pdfplumber`。如果 `python3 -c "import fitz"` 失败：
  ```bash
  pip3 install --user PyMuPDF pdfplumber
  ```
  装完重试。如果用户机器装不上（罕见），**告诉用户而不是静默跳过**：说"我没法装 PyMuPDF，这次只产出 markdown 笔记，图表请手动从 PDF 截图保存到 figures/ 子目录"。
- PDF 是扫描件 → caption 找不到 → manifest 里几乎全空。这种情况主动跟用户说："这份 PDF 是扫描版，文本层和 caption 都抽不到，需要先 OCR 后再处理；或者你直接告诉我这篇论文有哪些关键图，我在总结里留好引用占位"

---

## Step 4: 产出完整中文翻译版 `.zh-full.md` ← 新

产出 `<title>.zh-full.md`，把论文**逐段翻译**成中文。这是给用户做深度阅读用的，跟 Step 5 / 6 的结构化总结互补 —— 总结看骨架，翻译看血肉。

### 翻译原则

1. **不要重组结构**。论文怎么分章节就怎么分（1 Introduction → `## 1. 引言 / Introduction`；2.1 Setup → `### 2.1 设定 / Setup`）。章节号保留，标题中英并列。
2. **逐段翻译**。每段单独译，不合并、不删减、不"自由发挥概括"。**原文一段 = 译文一段**。
3. **按 Step 2 用户确认的术语表保留英文**。表里的词永远不强译；首次出现时给中文+英文括注："零知识证明（zero-knowledge proof, ZKP）"，之后用 ZKP。**论文自创术语（如方案名）严格保留**。
4. **数学公式不翻译**。LaTeX `$$...$$` / `$...$` 原样保留，等式编号 `(1)` `(2)` 也保留。
5. **引用文献保留原样**。`[1]`、`[Smith et al., 2023]`、`(He et al., 2016)` 不动；作者名、会议名、机构名都用英文。
6. **代码 / 伪代码不翻译**。代码块原样，注释如果是英文也保留（除非用户明说要译注释）。
7. **图 / 表 / 算法按引用位置嵌入资产**：
   - 原文 "as shown in Figure 3" → 译文 "如 Figure 3 所示"
   - **正文里第一次**引用 Figure 3 的段落**译完后紧跟一行**：
     ```
     ![Figure 3](./figures/figure-3.png)
     *Figure 3: <caption 中译>（原文 caption 全文）*
     ```
   - Table、Algorithm 同理
   - 如果某图整篇正文都没引用（只在 caption 出现 / 只在附录引用）→ 翻译完整篇正文后，在该图最相关的章节末尾插入
   - 论文里有 figure 但 manifest 没抽到 → 在引用处加 `(原文 Figure N，资产抽取失败)` 注释，不要凭空写不存在的路径
8. **作者、机构、致谢、Reference 列表**：作者名 / 机构名保留英文；摘要、正文翻译；References 列表整段保留英文原文（只这一节）。

### 翻译版模板

```markdown
# <论文中文译名> / <Original English Title>

> 📖 完整翻译版 · 领域：<领域名>
> 保留术语：`term1`, `term2`, `term3`, ...（Step 2 用户确认的清单）

## 元信息 / Metadata

- **作者 / Authors**: <英文原名>
- **机构 / Affiliation**: <英文原名>
- **会议·期刊 / Venue**: ...
- **年份 / Year**: ...
- **链接 / Link**: arXiv:xxxx.xxxxx / DOI:...

## 摘要 / Abstract

<逐句翻译；术语按表保留>

## 1. 引言 / Introduction

<第 1 段译文>

<第 2 段译文>

![Figure 1](./figures/figure-1.png)
*Figure 1: <caption 中译>（原文：<caption 英文原文>）*

<第 3 段译文>

...

## 2. 相关工作 / Related Work

...

## 3. 方法 / Method

### 3.1 <小节中译> / <Original Section Title>

<逐段译>

![Table 1](./tables/table-1.png)
*Table 1: <caption 中译>*

...

## References

<整段保留原文，不翻译>

---
*Generated by paper-analyzer skill · 完整翻译版*
```

### 长论文 / 附录处理

- **30+ 页的论文**：耐心译完，**不要省略**。如果单次输出装不下，按章节分批写入文件；不要为了塞下而压缩段落。
- **附录**：默认翻译。用户明说"只要正文"时跳过，并在末尾标 `(附录未翻译 / Appendix not translated)`。
- **数学公式密集章节**：公式照贴，公式之间的解释文字逐句译，**不要因为公式多就少译解释**。

### 翻译里**不要**做的

- ❌ 把多段合并成一段
- ❌ 跳过"作者吐槽前人方法"那种段落
- ❌ 把用户确认的术语表里的词翻译成中文
- ❌ 把作者自己起的方案名翻译（`SGitChar` 不要写"S-Git-字符版"）
- ❌ 翻译引用里的作者名（"Smith et al. 2023" 不要变成 "史密斯等 2023"）
- ❌ "修正"论文里的小错误（typo、命名不一致）—— 原文怎么写就怎么译，可在末尾用 `(reviewer's note)` 标
- ❌ 假装看完了正文（如果你只看到摘要，**在文件顶部加** `> ⚠️ 仅基于摘要 / Based on abstract only`）

---

## Step 5-6: 产出中英两份结构化总结

完整翻译之外，再产出两份**结构化总结**，用同一个 4 段骨架，便于用户后续 scan / 引用 / 比对。

### 中文总结 `.zh.md` 模板（保留领域术语英文原文）

模板里的 `![]()` 用相对路径引用抽出的资产。**只在论文里真有这张图/表/算法时才插入引用**（看 manifest 验证），不要凭空写 "见 figure-5.png" 然后路径不存在。

```markdown
# <论文中文译名> / <Original English Title>

> 📝 中文版 · 关键术语保留 [领域名] 学术惯例

## 1. 元信息 & TL;DR

- **作者 / Authors**: ...
- **机构 / Affiliation**: ...
- **会议·期刊 / Venue**: ...
- **年份 / Year**: ...
- **链接 / Link**: arXiv:xxxx.xxxxx / DOI:...
- **领域 / Field**: [如：密码学协议 / 系统安全]
- **TL;DR**: 一句话说清楚这篇论文做了什么、达到了什么效果（含保留的英文术语）

## 2. 背景 / 问题 & 方法

### 2.1 要解决什么问题
- 问题、为什么重要、之前方法的不足
- 用作者的 problem formulation 描述

### 2.2 核心方法
- 方法名（保留原文）
- 关键步骤 / 架构组件（分点）
- 关键公式或伪代码（**用 LaTeX 或代码块完整抄录**，不要意译）
- 系统/架构图：`![Figure 1](./figures/figure-1.png)` *若有相关图*
- 算法：引用 `./code/algorithm-N.md`
- 与已有方法的区别（vs. baseline X / vs. prior work Y）

## 3. 实验与结果

- **数据集 / 系统设置 / 评估场景**: ...
- **基线 / Baselines**: ...
- **主要指标**:
  - 用表格或要点列出。**必须给出具体数值**，不要写"显著优于"
  - 例：`方法 X: 84.3% 准确率, vs. baseline 81.7% (+2.6 pp)`
- **数据表**：`![Table 2](./tables/table-2.png)`
- **关键结果图**：`![Figure 9](./figures/figure-9.png)`
- **重要消融**: 1-2 个最能说明问题的 ablation
- **作者特别强调的发现**: 论文里 `we find that ...` 之后的话

## 4. 创新点 · 局限 · 后续思考

### 4.1 创新点 / Contributions
- 1-3 条，**以作者声称的 contribution 为骨架**

### 4.2 局限性 / Limitations
- 作者自承的局限
- 你看出来但作者没明说的，标 `(reviewer's note)`

### 4.3 后续 / Future directions
- 论文里提到的 future work
- 你的研究 idea / 可追的引用 / 可复现性（代码/数据是否公开）

---

## 附录 / Assets index

由 `extract_assets.py` 自动抽取（按论文原序）：

- **Figures**: 共 N 张，见 `./figures/figure-1.png` ... `figure-N.png`
- **Tables**: 共 M 张，见 `./tables/table-1.png` ... `table-M.png`
- **Algorithms / Listings**: 见 `./code/`（如有）

---
*Generated by paper-analyzer skill · 中文版*
```

### 英文总结 `.en.md` 模板（完整英文，结构相同）

```markdown
# <Original English Title>

> 📝 English version

## 1. Metadata & TL;DR

- **Authors**: ...
- **Affiliation**: ...
- **Venue**: ...
- **Year**: ...
- **Link**: arXiv:xxxx.xxxxx / DOI:...
- **Field**: [e.g. Cryptographic protocols / System security]
- **TL;DR**: One-sentence summary.

## 2. Motivation & Method

### 2.1 Problem
- What problem, why it matters, prior limitations
- Problem formulation in the author's terms

### 2.2 Core Method
- Method name
- Key steps / architectural components
- Key formulas or pseudocode (**transcribed verbatim**)
- Architecture diagram: `![Figure 1](./figures/figure-1.png)`
- Algorithm: see `./code/algorithm-N.md`
- Differences vs. prior work

## 3. Experiments & Results

- **Datasets / setup**: ...
- **Baselines**: ...
- **Key metrics**:
  - With **specific numbers**, not "significantly better"
- **Result tables**: `![Table 2](./tables/table-2.png)`
- **Result plots**: `![Figure 9](./figures/figure-9.png)`
- **Ablations**: 1-2 informative ones
- **Author-highlighted findings**

## 4. Contributions · Limitations · Future Work

### 4.1 Contributions
- 1-3 bullets, framed around author's stated contributions

### 4.2 Limitations
- Author-acknowledged limitations
- Your additional observations, marked `(reviewer's note)`

### 4.3 Future Directions
- From the paper
- Your own research ideas / follow-up citations / reproducibility notes

---

## Assets index

Automatically extracted by `extract_assets.py` (numbering follows the paper):

- **Figures**: N total, in `./figures/`
- **Tables**: M total, in `./tables/`
- **Algorithms / Listings**: in `./code/` (if any)

---
*Generated by paper-analyzer skill · English version*
```

---

## Step 7: 保存整个笔记包

### 输出结构（重要）

每篇论文有自己独立的子目录，所有相关内容都在一起：

```
<base>/<sanitized-title>/
  ├── <sanitized-title>.zh-full.md   完整翻译版
  ├── <sanitized-title>.zh.md        中文结构化总结
  ├── <sanitized-title>.en.md        英文结构化总结
  ├── figures/
  ├── tables/
  ├── code/
  └── manifest.json
```

注意：**所有路径都是这个论文文件夹内部的相对路径**，markdown 里引用 `./figures/figure-1.png` 而不是 `../figures/...`。这样把整个文件夹拷贝到 Obsidian / Notion / 其他地方也不会失效。

### 默认 base 路径（**直接用，不要问用户**）

`<base>` = `./papers/`（当前工作目录下）

**关键原则**：用户第一次给论文时，**不要问"要保存到哪里"** —— 这是 skill 最大的卖点：用户给一篇论文，就自动落地完整笔记包。直接按下面优先级用第一条命中的路径，**全程不问用户**。

1. **本次会话用户明说的路径**（如"存到 ~/Obsidian/Papers"）→ 用
2. **`./paper-analyzer.config.json` 里的 `outputDir`** → 用
3. **`~/.paper-analyzer/config.json` 里的 `outputDir`** → 用
4. **都没有** → **直接用** `./papers/`，**不要问、不要确认**。落地完成后，在结尾告诉用户保存路径，并**顺带提一句**："如果想以后都存到某个固定路径，可以建一份 `~/.paper-analyzer/config.json`"（这是事后告知，不是事前提问）。

配置文件示例：
```json
{
  "outputDir": "~/Documents/papers"
}
```

### 文件夹/文件名规则
- 取**英文标题**，去除特殊字符（`/\:*?"<>|`），空格换成 `-`，长度限 80 字符
- 如果只有中文标题，用中文标题 + arxiv id（如有）
- 文件夹重名：先 diff 已有的 `.zh.md`，如果是同一篇论文（标题/作者/年份吻合）→ 加 `-v2`、`-v3` 子目录；如果根本是另一篇 → 加序号后缀。**永远不覆盖**用户已有笔记。

### 聊天里展示
- 默认在聊天里**打印 `.zh-full.md` 完整翻译版**（包括图表的 markdown 引用，渲染器会显示出来）
- 长论文翻译版可能很长 —— 如果一次打印不下，先打前 2-3 章 + Abstract，告诉用户"完整版已存到 `<path>.zh-full.md`，要看后面章节告诉我"
- 末尾提示："整个笔记包已保存到 `<base>/<title>/`，含完整翻译 + 中英结构化总结，N 张 figures、M 张 tables"
- 如果用户明说想看总结/英文版，再打印对应的 `.zh.md` / `.en.md`

---

## 关键写作规范

下面这些是反复出问题的地方，请认真遵守：

1. **数字必须精确**。论文表 3 里写 84.3 你就写 84.3，不要写"约 84%"、不要写"较高"。如果你没在原文找到数字，宁可空着写 `(N/A in paper)` 也不要编。

2. **领域术语按 Step 2 用户确认的清单保留**。`Transformer` 不要翻译成"变压器"；用户表里的词在 `.zh-full.md` 和 `.zh.md` 都不强译；首次出现时给括注（"零知识证明（zero-knowledge proof, ZKP）"），后续用 ZKP 即可。**作者自创的方案名永远保留英文**。

3. **翻译版要忠于原文段落结构**。`.zh-full.md` 一段对一段；`.zh.md` 是你重新组织的 4 段总结。两份角色不一样，不要把翻译版写成总结版、也不要把总结版写得太啰嗦。

4. **不要把摘要复述当成方法理解**。Abstract 是销售文案，正文章节才是技术内容。如果你只看了摘要，**在所有三份输出顶部都明确加一行 `> ⚠️ 注：仅基于摘要 / Based on abstract only`**。

5. **作者声称 vs. 你的判断分开**。Contribution 用作者原话；局限性、后续 idea 是你的解读，用 `(reviewer's note)` 标明。这条只用于总结版；**翻译版完全不掺入你的判断**。

6. **默认全自动落地，不要问"要不要做"、"做到哪种程度"、"保存到哪"**。这是 skill 的核心卖点：用户给一篇论文，自动产出三份 `.md` + 全部 figures/tables/code + manifest.json，**全套笔记包默认全开，不要问用户**。例如：
   - 附录长 → **照常翻译**（不要问"附录要不要翻"）
   - 论文 30+ 页 → **照常全翻**（不要问"是不是只看正文"）
   - 数据公开 → **照常记进 reviewer note**（不要问"要不要写 future work"）
   - 没有显式保存路径 → **直接用** `./papers/`（不要问"保存到哪"）

7. **只有真的卡住才问用户，问完一句话能解决的**：
   - PDF 是扫描件、文本抽不出 → "这份 PDF 是扫描版，文本层抽不出。要我基于摘要先写一版，还是你 OCR 后再发我？"
   - 用户只给标题，搜出多篇同名论文 → 列出来让用户选具体哪一篇
   - 收费墙 PDF 拿不到全文 → "我目前只能拿到摘要，要基于摘要继续吗？"

   **保留的两个显式交互**（前面 Step 2、Step 8 已规定，不要省）：
   - Step 2 领域 + 术语表确认（决定翻译保留哪些英文）
   - Step 8 PPT 模板确认（只在用户要求生成 PPT 时）

   **除此之外不要打断用户**。

---

## 常见错误（不要犯）

| 错误做法 | 为什么不行 |
|---------|----------|
| 用一段 200 字大段散文当"总结" | 用户没法快速 scan |
| 给"准确率提高了"但没写具体数 | 笔记就废了 |
| 中文意译方法名（Transformer→变压器，TEE→可信执行环境后不给原文） | 后续搜索/引用全要英文原文 |
| **跳过 Step 2 术语表确认直接开始翻译** | 用户对术语保留有偏好，不问就靠猜 |
| **翻译版里把作者自创方案名也翻译了**（SGitChar → S-Git-字符版） | 全文搜不到这个方案了 |
| **翻译版把多段合成一段、跳过过渡段、自由发挥** | 那是总结不是翻译，用户要的是逐段对照 |
| **翻译版掺入 `(reviewer's note)` 或自己的判断** | 翻译版只能是论文原文，吐槽放总结版 |
| 仅靠摘要却不声明，输出看起来像精读全文 | 严重误导用户 |
| 把作者的局限和自己的吐槽混在一起 | 引用时分不清出处 |
| 直接覆盖已有的 papers/xxx/ 目录 | 用户之前的笔记 + 自己批注就丢了 |
| 三份输出（zh-full / zh / en）只产出一份或两份 | 设计就是三份并存 |
| 中英总结版结构不一致 | 失去对照价值 |
| 翻译版的 figure 全堆在末尾不按引用位置嵌入 | 用户要回翻找位置，读起来累 |
| 在 markdown 里写 `![](./figures/figure-7.png)` 但 figure-7.png 不存在 | 检查 manifest，论文没有就别假装有 |
| 跳过资产抽取，让用户自己手动从 PDF 截图 | skill 就废了一半价值 |
| **跑完 extract_assets.py 没看每张 figure-N.png** | 纯文字 figure（如协议步骤列表）的自动截图常失败，必须人眼检查 |
| **生成 PPT 后没渲染 PNG 校验** | 见到 `✓ Saved` 就交付 → 模板/版式/截图任何一个错都漏过 |
| **PPT 模板模式下用裸 textbox 覆盖** | 模板的装饰（logo / 色块 / 章节方块 / 曲线）就全废了。必须用 clone_slide 克隆样例 slide |
| **以为模板的视觉在 layout 里** | 中文学术 / 企业模板把设计全画在样例 slide 上，layout 几乎空白。剥掉样例 slide = 剥掉所有视觉 |
| **克隆 slide 时不重映射 rId** | logo 会静默消失（rId1 撞车）。必须把 r:embed / r:link / r:id 全 walk 一遍重写 |
| **python-pptx 用 `add_relationship` 而不是 `get_or_add`** | 老教程的过时 API，会被 try/except 静默吞掉。导致看似"成功"但 rel 一个都没加 |
| **PPT 版面字号随意，没有 type scale** | 一页里 5 种字号 = 业余。封面 36/章节 32/正文 22/图注 14，严格执行 |
| **不设 east-asian typeface 让中文 fallback** | `font.name` 只设 latin。CJK 字符会掉回宋体默认。必须用 `<a:ea typeface="微软雅黑"/>` 显式设 |
| **bullets 不设 anchor、不设 line_spacing** | 默认 anchor=TOP 导致 4 条 bullets 时挤在上半部分。20pt+ 需要 line_spacing 1.15 才不挤 |
| **图片 add_picture(left, top, width, height) 强行拉伸** | 论文图等比都失真。必须先 PIL 读尺寸算缩放比，居中放入框 |
| **PPT bullets 写 3-5 字干瘪要点（"性能优秀"）** | 那是 TL;DR 不是讲解 deck。每条 20-40 字、带具体数字 / 算法名 / 引文 |
| **PPT 只生成 10-14 张 slide** | 论文 6-8 节 × 每节 2-3 张 = 20-30 张才正常。10 张说明你在偷懒 |
| **content slide 标题用模板默认字号** | 28pt+ 长中英混标题必然换行掉到 body 区。必须强制 22pt + 占位符 ≥ 0.75 in 高 |
| **PPT 局限性页混作者和 reviewer 观点** | 必须用 `[作者]` / `[reviewer]` 前缀分开 |
| 给 PDF 输入却没跑 extract_assets.py | 等于丢掉图表那半儿 |
| 用相对路径 `../figures/...`、绝对路径或 `~/...` 引用资产 | 笔记包不可移植 |

---

## 示例：End-to-End Encrypted Git Services（密码学领域）

**用户输入**：
> 帮我读一下 `./End-to-End Encrypted Git Services.pdf`

**应有的处理**：
1. 用 PDF 抽取工具读全文（pdfplumber 或 PyMuPDF）
2. **识别领域 + 和用户对齐术语表**（Step 2 显式交互）：
   ```
   📋 我识别这篇论文属于：**密码学 / 端到端加密协议** （置信度：高）
   保留英文的术语候选：
   - 概念：`E2EE`, `commit`, `Merkle tree`, `authenticated encryption`, `zero-knowledge`
   - 协议：`Diffie-Hellman`, `AES-GCM`, `HMAC`
   - 安全属性：`forward secrecy`, `confidentiality`, `integrity`
   - 论文自创：`SGitLine`, `SGitChar`（强制保留）
   要加/删的吗？没有就回 OK 开始翻译。
   ```
   用户回复 "OK" 后才继续。
3. **跑 `python scripts/extract_assets.py ./End-to-End\ Encrypted\ Git\ Services.pdf ./papers/End-to-End-Encrypted-Git-Services/`**
   - 这篇会抽出大约 10 张 figures + 3 张 tables（实测）
   - 读 `manifest.json` 看到每张资产对应的 caption 和页码
4. 产出 `.zh-full.md` 完整翻译版：
   - 逐段译；`E2EE`、`commit`、`SGitChar` 等术语保留英文
   - 正文第一次提到 Figure 1 的段落（"Section 3 introduces the architecture, as shown in Figure 1"）后嵌入 `![Figure 1](./figures/figure-1.png)`
   - 公式、定理、`[12]` 引用全部原样
   - References 整段保留英文
5. 产出 `.zh.md` 4 段结构化总结，重点摘录 SGitLine vs SGitChar 的设计差异和实验数据
6. 产出 `.en.md` 同样 4 段结构化总结
7. 默认保存为：
   ```
   ./papers/End-to-End-Encrypted-Git-Services/
     End-to-End-Encrypted-Git-Services.zh-full.md
     End-to-End-Encrypted-Git-Services.zh.md
     End-to-End-Encrypted-Git-Services.en.md
     figures/figure-1.png ... figure-10.png
     tables/table-1.png ... table-3.png
     code/  (本篇无算法/列表，目录为空或不创建)
     manifest.json
   ```
8. 聊天里打印 `.zh-full.md` 内容（长则前 2-3 章）+ 末尾告诉用户文件保存位置和抽到的资产数量

---

## Step 8 (按需): 生成 PPT 演示文稿

当用户要求生成演示文稿时执行，默认**不主动**生成。

**触发条件**：用户在读论文时说了 "做个PPT"、"生成幻灯片"、"make slides" 等，或读完后单独要求。

### 流程

**① 先问用户有没有模板（必须问，不能跳过）**

在做任何事情之前，先问：

```
您好，在生成 PPT 之前——

您有自己的 PowerPoint 模板（.pptx 文件）吗？
• 有的话请提供文件路径，我会套用您模板的配色、字体和背景样式来生成幻灯片。
• 没有的话我用内置的默认学术主题（深蓝标题栏 + 白底，16:9）。
```

**等用户回复后**再继续。两种情况：
- 用户提供了 `.pptx` 路径 → 验证文件存在，记下路径
- 用户说"没有"/"用默认" → 使用内置主题

**② 写 `<paper-dir>/slide-plan.json`**

根据论文内容决定幻灯片结构，写入 JSON。**推荐结构（约 10-14 张）**：

| 顺序 | 类型 | 内容建议 |
|------|------|----------|
| 1 | `title` | 论文标题、作者、会议/期刊、年份 |
| 2 | `section` | "背景与问题 / Background" |
| 3-5 | `bullets` × 2-3 | 问题陈述 / 现状不足 / 相关工作差距 |
| 5 | `image` | 威胁模型 / 整体架构图 |
| 6 | `section` | "方法 / Method" |
| 7 | `bullets` | 设计目标 / 设计考量 |
| 8 | `image` | 方法关键示意图 |
| 9 | `bullets` | 协议步骤分解 |
| 10 | `image` | 协议全图 |
| 11 | `formula` | 核心公式 + 一句解释 |
| 12 | `bullets` | 检测/验证算法说明（可带图） |
| 13 | `section` | "安全性分析" 或 "实验评估 / Experiments" |
| 14-15 | `bullets` | 安全模型 / 实验设置 |
| 16-18 | `image` × 多张 | 关键结果图，每张一页 + 解读 caption |
| 19 | `bullets` | 关键数值汇总 |
| 20 | `section` | "讨论 · 局限 · 后续" |
| 21-23 | `bullets` × 2-3 | 可用性 / Contributions / Limitations / Future |
| 24 | `closing` | "Thank You / Q&A" |

**slide 数量目标：20–30 张**。少于 15 张内容必然空泛；超过 35 张听众疲劳。每个一级章节配 2-4 张内容页 + 1 张分页。

**JSON 格式**：

```json
{
  "output_filename": "<sanitized-title>-slides",
  "slides": [
    {
      "type": "title",
      "title": "Full Paper Title",
      "authors": "Author A, Author B",
      "venue": "Conference/Journal 2025",
      "year": "2025"
    },
    {
      "type": "section",
      "title": "Background & Problem"
    },
    {
      "type": "bullets",
      "title": "Problem Statement",
      "bullets": ["Point 1 — concise (≤15 字)", "Point 2", "Prior work X fails because Y"],
      "figure": "figures/figure-1.png"
    },
    {
      "type": "image",
      "title": "System Architecture",
      "image": "figures/figure-2.png",
      "caption": "Figure 2: System overview"
    },
    {
      "type": "formula",
      "title": "Core Formula",
      "latex": "\\pi = \\text{Prove}(CRS, x, w)",
      "caption": "Prover generates proof π given CRS, statement x, and witness w"
    },
    {
      "type": "closing",
      "title": "Thank You",
      "subtitle": "Q & A"
    }
  ]
}
```

**写 bullets 的原则**：

- 每条 **20–40 个汉字** / **14–28 个英文单词**：短到能扫读、长到能承载真实信息。
- **必须带具体数字 / 算法名 / 引用**（错例 "性能不错"；对例 "登录额外延迟 36 ± 8 ms"、对例 "Amnesia [Wang-Reiter USENIX'21] 也只解决 same-party detection"）。
- 用动词或主语开头，但允许带子句解释。**不要纯标题党**。
- 单页 bullets **5–7 条**最佳（脚本会自动 tighten 7+ 时的行距）；多于 8 条强制拆两页。
- 涉及多步流程（如协议、算法）→ 每步一条 bullet，**别合并**。
- 直接放论文里的真实数字（百分比、毫秒、GB、概率界）、定理名、算法名、引文 → 让 PPT 直接成为讲解骨架。
- 局限性页用 `[作者]` / `[reviewer]` 前缀区分**作者自承的局限**和**你的额外观察**。

**别只写 "TL;DR 风格"的 3-5 字干瘪要点**。听众要的是"够讲 60 秒"的密度，不是阅读后再回去翻论文。

**只嵌入 manifest.json 里确认存在的图**，不存在的留 `"figure": null`。

**📐 版面纪律（脚本已硬编码，但你必须懂规则）**

整个 PPT 必须遵循下面这套类型尺度（type scale）和栅格（grid），否则就显得业余：

**字号阶（point sizes）**：
| 用途 | 字号 | 字重 |
|---|---|---|
| 封面标题 | **40 pt** | Bold |
| 封面 byline（作者/会议/年份） | 18 pt | Regular |
| 章节分页标题 | **30 pt** | Bold |
| **Content slide 标题（强制显式，否则换行）** | **22 pt** | Bold |
| 正文 bullet（单栏，无图） | 19 pt | Regular |
| 正文 bullet（两栏，含图） | 16 pt | Regular |
| 公式渲染 | 30 pt | Regular |
| 公式 caption | 17 pt | Regular |
| 图注 caption | 13 pt | Italic |
| Closing "Thank You" | 44 pt | Bold |

**字体**：中英文都明确指定，**不要让运行时挑**。中文用 `微软雅黑`（标题）+ `微软雅黑 Light`（byline/caption），英文用 `Arial`。如果模板的 theme 写明了别的字体，按 theme 来；脚本里的 `_apply_font()` 同时设置 latin 和 east-asian typeface。

**栅格**：基于 16:9 (13.33×7.5 in)
- 内容页 body 区域：上下 0.25 in gap from title / 0.50 in margin from bottom；左右继承标题占位符宽度（通常 0.6-0.7 in margin）。
- **Content slide 标题占位符高度强制 ≥ 0.75 in**（模板默认常仅 0.5 in，长中英混标题会换 2 行掉到 body 区）。
- 两栏（bullets + figure）：50/50 分割 + 0.35 in 中间间隔。
- 图片：等比缩放居中放入 body 区域（绝不拉伸），caption 紧贴下方留 0.10 in gap + 0.5 in 高。
- 公式：竖向居中于 body 区域，占 70% 高度，caption 占下方 0.8 in。

**对齐**：
- 封面标题：水平居中 + 垂直居中于色块上半部（55% 高），byline 居中于色块下半部（32% 高）。
- 章节标题：水平左对齐到章节方块的左边界，竖向贴近方块下方 0.25 in。
- 正文：标题继承模板占位符，bullets 顶对齐 + 左对齐。

**bullet 间距**：行内 line spacing 1.15；行间 `space_after` 默认 = 字号的一半（22pt → 11pt）。

**禁止**：
- ❌ 用 `••` 自定义 bullet 符号——直接用 U+2022 `•` 加空格
- ❌ 多字号混搭（一页里只能有一两种字号）
- ❌ 不设定 east-asian typeface 让中文 fallback 成宋体
- ❌ 图片用 add_picture 不等比缩放
- ❌ 文字框 anchor 用默认 TOP 导致竖向偏上 / 偏下不一致

**③ 模板使用的核心机制 —— 克隆样例 slide（脚本自动处理，但你必须懂）**

⚠️ **`--template` 不是"借用 layout"，而是"克隆样例 slide"**。原因：

中文学术 / 企业 PPT 模板（如北工大、清华、各类公司模板）的视觉设计 —— logo、配色色块、章节方块、装饰曲线、顶部蓝条 —— **几乎全部画在 4-6 张样例 slide 上**，不在 master / layout 里。master 大多接近空白。所以仅用 layout 渲染只会得到光秃秃的占位符，**模板视觉一点都没用上**。

正确做法：把模板里现有的 slide 识别成"参考模板"，按 slide 类型 deep-clone 它们（连同所有装饰），再往克隆体上叠加 title / bullets / image。

脚本里的 role 识别（`identify_references`）：

- `cover` — 含 PICTURE 形状（logo）、无 GROUP（章节方块）的 slide。默认第一张。
- `section` — 含 GROUP 形状（"01" 章节方块）的 slide。
- `content` — 有 TITLE placeholder、无 GROUP 的 slide。
- `closing` — 最后一张 section-style slide（"02"、"03"……号通常作为结尾）。

脚本里的 slide-type → role 映射：

- `title`   → 克隆 cover
- `section` → 克隆 section，自动把 "01" 改成当前章节号
- `bullets` → 克隆 content；可选 figure 走两栏布局
- `image`   → 克隆 content；body 区域放等比缩放图片 + caption
- `formula` → 克隆 content；body 区域放 matplotlib 渲染的公式 PNG
- `closing` → 克隆 closing，badge 改成 "总章节数+1"

克隆完所有新 slide 后，脚本删除模板原来的 4-6 张参考 slide。

**已知坑 + 解法**（脚本里已修，写在这里给你解释为什么）：

1. **rId 碰撞 → logo 消失**。最隐蔽也最致命的 bug。`prs.slides.add_slide(layout)` 给新 slide 自动分配 `rId1` 给 slide→layout 关系。原 cover 的 logo XML 引用 `rId1` 当图片，克隆后撞车，PowerPoint 静默把 logo 解析成 layout part → logo 不显示。
   - 修法：克隆 XML 时**重映射 rId**。每个源 rel 通过 `Part.rels.get_or_add(reltype, target_part)` 加到新 slide（API 自动选下一个空闲 rId 并返回），然后用 `{old_rId: new_rId}` 映射表 walk 克隆出的 XML，把所有 `r:embed` / `r:link` / `r:id` 属性改写为新 rId。
2. **python-pptx 没有 `add_relationship`，但很多教程里写它**。实际 API 是 `_Relationships.get_or_add()` 和 `get_or_add_ext_rel()`，写错名 + 用 try/except 会**静默吞掉错误**让你浑然不觉。一定要写 `print(...)` 才能发现。
3. **"01" 章节方块的数字是写在 GROUP 内部的 TextFrame 里**。脚本递归遍历 GROUP 找到匹配 `^\d{1,3}$` 的 TextFrame，按当前章节号替换。如果模板用别的标识方式（如 "Chapter 1" 或图标），需要在 `_update_badge_number` 里扩展规则。
4. **模板的样例 slide 不要用 zip 层暴力剥离**。前一版做法是预处理 zip、删 slide 文件后再交给 python-pptx — 这把整个模板的视觉设计也一起扔了。**现在的做法是保留它们当参考模板**，生成新 slide 后才一并删除。
5. **图片放进 placeholder 会被 PowerPoint 拉伸填满**。脚本用 PIL 读原图尺寸做等比缩放再 `add_picture`，永不拉伸。
6. **soffice / LibreOffice 字体替换**。模板里指定的字体如果 LibreOffice 没装，转 PDF 预览时会用 fallback 字体（常退化成手写体）。**在真正的 PowerPoint / Keynote / WPS 打开时会显示正确字体** —— 不要被 PDF 预览误导。如果用户在 Mac 上要做 PDF 导出，最好用 Keynote 或 PowerPoint 而非 soffice。

**④ 运行脚本**

```bash
# 无模板（内置学术主题）
python3 <skill-dir>/scripts/generate_slides.py <paper-dir>

# 使用用户模板
python3 <skill-dir>/scripts/generate_slides.py <paper-dir> --template /path/to/template.pptx
```

**⑤ 跑完一定要可视化校验**（这是给你的硬性要求）：

```bash
# 转 PDF 然后渲染前几张 PNG 检查
soffice --headless --convert-to pdf --outdir /tmp/check <paper-dir>/<output>.pptx
python3 -c "import fitz; d=fitz.open('/tmp/check/<output>.pdf'); [d[i].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(f'/tmp/check/s{i+1:02d}.png') for i in range(len(d))]"
```

然后用 Read 工具看 `/tmp/check/s01.png`、`s05.png`、几张 image slide。**任何一张明显挤压、图截不全、版式不对就改 slide-plan 或脚本重试**。不要看到 `✓ Saved` 就交付。

**⑥ 关于 figure 截图（extract_assets.py 的已知失败模式）**

抽图脚本对**没有 vector 边框、纯文字组成的 figure**（如 BnR 协议步骤列表）会失败 —— 这类 figure 没有 `page.get_drawings()` 矩形可定位，cropper 回退到文本块边界检测，常常把协议代码误判成"正文段落"而切掉。**处理方法**：

1. 跑完 extract_assets.py 后，**用 Read 工具看每张 figure-N.png** —— 这是硬性步骤。
2. 截不全的，**手动用 PyMuPDF 重截**：
   ```python
   import fitz
   doc = fitz.open('<pdf>')
   page = doc[<page_idx>]
   # 用 page.get_text('blocks') 找正确的 bbox
   rect = fitz.Rect(x0, y0, x1, y1)
   pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72), clip=rect)
   pix.save('<paper-dir>/figures/figure-N.png')
   ```
3. 重截后再生成 PPT。

**⑦ 告知用户**：保存路径、张数、是否套用了模板、公式是否渲染成功，**以及哪些 figure 你手动重截过**。

---

## 输出前自检清单

- [ ] **Step 2 已和用户确认领域 + 术语表**（不是自己猜的）
- [ ] 三份输出都生成：`<title>.zh-full.md` + `<title>.zh.md` + `<title>.en.md`
- [ ] **翻译版** 章节号、段落数和原文一一对应，没合并、没省略
- [ ] **翻译版** 术语表里的词全部保留英文；作者自创方案名一个没翻译
- [ ] **翻译版** 引用的 figure/table 都嵌在正文第一次引用的段落后（不是堆在末尾）
- [ ] **翻译版** 公式、`[1]`-引用、作者名都是原文形式
- [ ] **翻译版** 没掺入 `(reviewer's note)` 或自己的判断
- [ ] **总结版** 4 大节齐全，顺序没乱（中英两版结构一致）
- [ ] 元信息：标题、作者、年份、链接都填了（不知道写 unknown，不猜）
- [ ] 数字都是原文里的具体数值
- [ ] 英文总结整篇英文，不夹杂中文
- [ ] 如果只基于摘要，三份输出顶部都加了 `⚠️` 声明
- [ ] 作者 contribution 和 reviewer note 分开了
- [ ] **若输入是 PDF：跑过 `extract_assets.py` 且 manifest 已存在**
- [ ] **每张 figure-N.png 都用 Read 工具看过**，截不全的已手动重截
- [ ] **markdown 里引用的 `figure-N.png` / `table-N.png` 都在 manifest 里能查到**
- [ ] **所有资产引用用相对路径 `./figures/...`，不要绝对路径**
- [ ] 三份 `.md` 文件都已保存到 `<base>/<title>/` 目录下
- [ ] 已告诉用户文件保存路径 + 抽到的 figures/tables 数量
- [ ] **若用户要求 PPT**：slide-plan.json 已写入 paper-dir；脚本已跑；.pptx 路径已告诉用户
