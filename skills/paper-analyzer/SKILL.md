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

### 默认 base 路径

`<base>` = `./papers/`（当前工作目录下）

### 路径可由用户配置（按优先级查找）

1. **本次会话用户明说的路径**（如"存到 ~/Obsidian/Papers"）→ 直接用
2. **`./paper-analyzer.config.json` 里的 `outputDir`** → 用
3. **`~/.paper-analyzer/config.json` 里的 `outputDir`** → 用
4. **都没有** → 用默认 `./papers/`，**第一次保存时主动问一句**："默认保存到 `./papers/`，要改路径吗？如果想以后都用某个目录，告诉我我帮你写到 `~/.paper-analyzer/config.json`"

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

6. **遇到不确定就停下来问**：
   - PDF 是扫描件抽不出文字 → "这份 PDF 看起来是扫描件，我只能拿到 X 页，要继续吗？"
   - 论文太长（>30 页，附录庞杂）→ "正文 + 附录都要翻译吗？还是只看正文？"
   - 用户只给标题，搜出来有多篇同名 → 列出来让用户选
   - 领域识别有歧义 → Step 2 的术语表交互里自然就解决了，不用再单独问
   - 跨学科论文（如 ML 安全） → 把两套术语都列出来让用户挑

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

**① 确认模板**

- 用户提供了 `.pptx` 模板路径 → 记下，传给脚本（会套用母版配色/字体/背景，内容重新填）
- 没有提供 → 使用脚本内置的默认学术主题（深蓝 header + 白底）

**② 写 `<paper-dir>/slide-plan.json`**

根据论文内容决定幻灯片结构，写入 JSON。**推荐结构（约 10-14 张）**：

| 顺序 | 类型 | 内容建议 |
|------|------|----------|
| 1 | `title` | 论文标题、作者、会议/期刊、年份 |
| 2 | `section` | "背景与问题 / Background" |
| 3 | `bullets` | 问题陈述 3-4 条 + 可选右侧图 |
| 4 | `bullets` | 相关工作差距（可选） |
| 5 | `section` | "方法 / Method" |
| 6 | `bullets` | 核心方法概览 + 架构图 |
| 7 | `image` | 方法示意图 / 系统架构图（单独一张） |
| 8 | `formula` | 核心公式 + 一句解释 |
| 9 | `section` | "实验与结果 / Experiments" |
| 10 | `bullets` | 实验设置 + 基线 |
| 11 | `image` | 结果表/图（嵌入 table-N.png 或 figure-N.png） |
| 12 | `bullets` | 创新点 + 局限性 |
| 13 | `closing` | "Thank You / Q&A" |

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

**写 bullets 的原则**：每条不超过 15 个字（中）或 12 个英文单词；用动词开头；幻灯片 ≠ Word 文档。**只嵌入 manifest.json 里确认存在的图**，不存在的留 `"figure": null`。

**③ 运行脚本**

```bash
# 无模板（内置学术主题）
python3 <skill-dir>/scripts/generate_slides.py <paper-dir>

# 使用用户模板
python3 <skill-dir>/scripts/generate_slides.py <paper-dir> --template /path/to/template.pptx
```

**④ 告知用户**：保存路径、张数、是否套用了模板、公式是否渲染成功（需要 matplotlib）。

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
- [ ] **markdown 里引用的 `figure-N.png` / `table-N.png` 都在 manifest 里能查到**
- [ ] **所有资产引用用相对路径 `./figures/...`，不要绝对路径**
- [ ] 三份 `.md` 文件都已保存到 `<base>/<title>/` 目录下
- [ ] 已告诉用户文件保存路径 + 抽到的 figures/tables 数量
- [ ] **若用户要求 PPT**：slide-plan.json 已写入 paper-dir；脚本已跑；.pptx 路径已告诉用户
