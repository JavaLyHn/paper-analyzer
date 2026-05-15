---
name: paper-analyzer
description: Read an academic paper (PDF, arXiv link, pasted text, or DOI/title) and produce a complete paper-study package — full Chinese summary, full English summary, plus extracted figures / tables / algorithms / listings saved into per-paper subfolders following the paper's own numbering (Figure 1, Table 1, Algorithm 1, etc.). Covers metadata, motivation, method, experiments, contributions and limitations, with field-appropriate English terminology preserved in the Chinese version. Use this skill whenever the user shares a paper, an arXiv URL, a DOI, a paper title, or pastes a chunk of academic text and asks to "read / summarize / analyze / 解读 / 总结 / 精读" it — even if the user does not explicitly say "use paper-analyzer". Also trigger when the user wants to compare or do a literature review starting from a single paper.
---

# Paper Analyzer

把一篇学术论文变成一份**结构化、可归档、自带原文图表**的研究笔记包：完整中文版 + 完整英文版 + 按原文顺序抽出的 figures / tables / code 子文件夹。中文版里**该保留的英文术语保留**，不强行翻译。

## 为什么需要这个 skill

读论文最贵的不是看，而是**看完之后能不能复用**。问题在于：

- 全中文翻译会丢掉作者的术语命名，下次想搜索/引用时反而找不到（"变压器架构"显然不如 "Transformer architecture" 好用）
- 全英文摘要不够亲切，做中文写作或讲给同事听都得二次翻译
- 用一段散文当总结，下次想引用某个数字还得翻原文
- 关键图表只在 PDF 里 —— 想插进 Notion/Obsidian/写作里都要手动截图

这个 skill 的设计是：**一份完整的论文笔记包**

```
papers/<title>/
  ├── <title>.zh.md     完整中文版（领域术语保留英文）
  ├── <title>.en.md     完整英文版
  ├── figures/          按论文原序: figure-1.png, figure-2.png ...
  ├── tables/           按论文原序: table-1.png, table-2.png ...
  ├── code/             algorithm-N.md / listing-N.md（含代码块和图像备份）
  └── manifest.json     这次抽出来的所有资产清单
```

中英两份都按固定 4 段结构产出。中文版根据论文所在的**学术领域**，保留该领域里大家公认不翻译的英文术语。资产编号严格跟随论文原文（Figure 1 就是 `figure-1.png`）。

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
[Step 2] 识别论文领域和关键术语（决定中文版怎么处理术语）
    │
    ▼
[Step 3] 抽取资产 → figures/ tables/ code/（仅当输入是 PDF 时可用）
    │
    ▼
[Step 4] 产出中文版（preserving field-specific English terms）
    │       └── 引用抽出的 figures/tables/algorithms 时插入相对路径
    │
    ▼
[Step 5] 产出英文版
    │
    ▼
[Step 6] 把整个 papers/<title>/ 包保存到用户配置的路径 + 聊天里展示中文版
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

## Step 2: 识别论文领域 ← 关键

在产出总结前，**先判断这篇论文属于什么领域**，因为不同领域的术语保留惯例完全不同。

### 识别方法
- 看 arXiv 分类（`cs.CR` 是密码学/安全，`cs.LG` 是机器学习，`cs.DB` 是数据库……）
- 看摘要里反复出现的核心名词
- 看引用集中的会议（CRYPTO/USENIX Security → 安全密码；NeurIPS/ICML → ML；SIGMOD/VLDB → 数据库）

### 各领域的术语保留惯例

下面是**中文版**里**应当保留英文原文**的术语类别（按领域）。这是给你的参照，遇到具体术语就按这个尺度判断；如果某个术语在中文学术圈已有非常通用的中译（如 "神经网络""服务器""数据库"），那就翻译。

**密码学 / 系统安全 (cryptography, security)**：
- 协议名/算法名：`AES`、`RSA`、`ECDSA`、`SHA-256`、`HMAC`、`Diffie-Hellman`、`zero-knowledge proof`、`commitment scheme`、`Merkle tree`
- 安全属性：`IND-CPA`、`IND-CCA`、`forward secrecy`、`post-quantum`
- 系统组件：`oblivious RAM`、`trusted execution environment (TEE)`、`SGX`、`zk-SNARK`
- 攻击/威胁模型：`malicious adversary`、`honest-but-curious`、`side-channel`
- 协议步骤：`commit`、`reveal`、`verify`、`challenge`、`response`

**机器学习 / 深度学习 (ML, DL, NLP, CV)**：
- 架构名：`Transformer`、`CNN`、`RNN`、`LSTM`、`GAN`、`VAE`、`Diffusion model`
- 训练机制：`attention`、`backpropagation`、`gradient descent`、`fine-tuning`、`RLHF`、`SFT`
- 数据/任务：`ImageNet`、`GLUE`、`SQuAD`、`few-shot`、`zero-shot`、`in-context learning`
- 指标：`accuracy`、`F1`、`BLEU`、`perplexity`、`AUC`

**系统 / 数据库 / 分布式 (systems, DB, distributed)**：
- 一致性模型：`linearizability`、`serializability`、`eventual consistency`、`CAP theorem`
- 协议：`Paxos`、`Raft`、`2PC`、`MVCC`
- 系统名：`Kubernetes`、`Spanner`、`HDFS`

**理论计算机科学 (theory, algorithms)**：
- 复杂度类：`P`、`NP`、`PSPACE`、`#P`、`BPP`
- 范式：`approximation algorithm`、`online algorithm`、`streaming algorithm`

**其他领域**：如果你不确定该领域的惯例，**问用户**："这篇论文偏密码学还是系统安全？密码学惯例是保留协议名，系统更倾向保留组件名，您希望按哪种处理？"

### 处理新领域

当遇到本节没列的领域（如生物信息、计算金融），**临时识别 5-10 个核心术语**作为该篇论文的"保留词表"，在中文版里统一处理。如果用户经常读这个领域，下次提醒用户把这些术语加进 `references/terminology-by-field.md`（如果存在），让 skill 越用越准。

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

## Step 4-5: 产出中英两份完整总结

两份**都用下面的 4 段固定结构**，顺序不要变。

### 中文版模板（保留领域术语英文原文）

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

### 英文版模板（完整英文，结构相同）

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

## Step 6: 保存整个笔记包

### 输出结构（重要）

每篇论文有自己独立的子目录，所有相关内容都在一起：

```
<base>/<sanitized-title>/
  ├── <sanitized-title>.zh.md
  ├── <sanitized-title>.en.md
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
- 默认在聊天里**完整打印中文版**（包括图表的 markdown 引用，渲染器会显示出来）
- 末尾提示："整个笔记包已保存到 `<base>/<title>/`，含 N 张 figures、M 张 tables"
- 如果用户明说想看英文，再打印英文版

---

## 关键写作规范

下面这些是反复出问题的地方，请认真遵守：

1. **数字必须精确**。论文表 3 里写 84.3 你就写 84.3，不要写"约 84%"、不要写"较高"。如果你没在原文找到数字，宁可空着写 `(N/A in paper)` 也不要编。

2. **领域术语按 Step 2 的清单保留**。在中文版里：`Transformer` 不要翻译成"变压器"；`zero-knowledge proof` 不要翻译成"零知识证明"还可以但应在第一次出现时给出原文（如"零知识证明（zero-knowledge proof, ZKP）"），后续用 ZKP 即可。

3. **不要把摘要复述当成方法理解**。Abstract 是销售文案，正文章节才是技术内容。如果你只看了摘要，**在两份版本的 TL;DR 后都明确加一行 `> ⚠️ 注：本总结仅基于摘要 / Based on abstract only`**。

4. **作者声称 vs. 你的判断分开**。Contribution 用作者原话；局限性、后续 idea 是你的解读，用 `(reviewer's note)` 标明。

5. **遇到不确定就停下来问**：
   - PDF 是扫描件抽不出文字 → "这份 PDF 看起来是扫描件，我只能拿到 X 页，要继续吗？"
   - 论文太长（>30 页，附录庞杂）→ "正文 + 附录都要分析吗？还是只看正文？"
   - 用户只给标题，搜出来有多篇同名 → 列出来让用户选
   - 领域不确定 → "这篇论文偏 X 还是 Y？我会按对应的术语保留惯例处理"

---

## 常见错误（不要犯）

| 错误做法 | 为什么不行 |
|---------|----------|
| 用一段 200 字大段散文当"总结" | 用户没法快速 scan |
| 给"准确率提高了"但没写具体数 | 笔记就废了 |
| 中文意译方法名（Transformer→变压器，TEE→可信执行环境后不给原文） | 后续搜索/引用全要英文原文 |
| 仅靠摘要却不声明，输出看起来像精读全文 | 严重误导用户 |
| 把作者的局限和自己的吐槽混在一起 | 引用时分不清出处 |
| 直接覆盖已有的 papers/xxx/ 目录 | 用户之前的笔记 + 自己批注就丢了 |
| 只产出中文版没产出英文版（或反之） | 设计就是两份并存 |
| 中英两版结构不一致 | 失去对照价值 |
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
2. 识别领域：密码学 + 系统安全（标题里有 Encrypted、Git，正文出现 commit、Merkle tree、authenticated encryption、CCS '25 等）
3. **跑 `python scripts/extract_assets.py ./End-to-End\ Encrypted\ Git\ Services.pdf ./papers/End-to-End-Encrypted-Git-Services/`**
   - 这篇会抽出大约 10 张 figures + 3 张 tables（实测）
   - 读 `manifest.json` 看到每张资产对应的 caption 和页码
4. 应用密码学术语保留规则：`E2EE`、`commit`、`Merkle tree`、`authenticated encryption`、`SGitLine` / `SGitChar`（这是论文里的方案命名，必须保留）、`zero-knowledge` 等保留英文
5. 产出中文版和英文版两份，markdown 里嵌入：
   - `![Figure 1: 架构](./figures/figure-1.png)` 在"背景"一节展示系统架构
   - `![Figure 6: 构造](./figures/figure-6.png)` 在"核心方法"展示 SGit 的构造
   - `![Table 2](./tables/table-2.png)` 在"实验结果"展示通信成本
   - `![Figure 9](./figures/figure-9.png)` 展示存储成本对比
6. 默认保存为：
   ```
   ./papers/End-to-End-Encrypted-Git-Services/
     End-to-End-Encrypted-Git-Services.zh.md
     End-to-End-Encrypted-Git-Services.en.md
     figures/figure-1.png ... figure-10.png
     tables/table-1.png ... table-3.png
     code/  (本篇无算法/列表，目录为空或不创建)
     manifest.json
   ```
7. 聊天里打印中文版完整内容 + 末尾告诉用户文件保存位置和抽到的资产数量

---

## 输出前自检清单

- [ ] 已识别论文领域，并在两份版本元信息里写明
- [ ] 4 大节齐全，顺序没乱（两份版本结构一致）
- [ ] 元信息：标题、作者、年份、链接都填了（不知道写 unknown，不猜）
- [ ] 数字都是原文里的具体数值
- [ ] 中文版里领域术语按 Step 2 的尺度保留了英文
- [ ] 英文版整篇英文，不夹杂中文
- [ ] 如果只基于摘要，已在 TL;DR 处加 `⚠️` 声明
- [ ] 作者 contribution 和 reviewer note 分开了
- [ ] **若输入是 PDF：跑过 `extract_assets.py` 且 manifest 已存在**
- [ ] **markdown 里引用的 `figure-N.png` / `table-N.png` 都在 manifest 里能查到**
- [ ] **所有资产引用用相对路径 `./figures/...`，不要绝对路径**
- [ ] 两份 `.md` 文件都已保存到 `<base>/<title>/` 目录下
- [ ] 已告诉用户文件保存路径 + 抽到的 figures/tables 数量
