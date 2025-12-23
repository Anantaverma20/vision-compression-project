# Page 1

```json
{
  "page_number": 1,
  "markdown": "# DeepSeek-OCR: Contexts Optical Compression\n\n**Authors:** Haoran Wei, Yaofeng Sun, Yukun Li  \n**Affiliation:** DeepSeek-AI  \n**Date:** 21 Oct 2025  \n**Source:** arXiv:2510.18234v1 [cs.CV]\n\n## Abstract\n\nWe present DeepSeek-OCR as an initial investigation into the feasibility of compressing long contexts via optical 2D mapping. DeepSeek-OCR consists of two components: DeepEncoder and DeepSeek3B-MoE-A570M as the decoder. Specifically, DeepEncoder serves as the core engine, designed to maintain low activations under high-resolution input while achieving high compression ratios to ensure an optimal and manageable number of vision tokens. Experiments show that when the number of text tokens is within 10 times that of vision tokens (i.e., a compression ratio < 10×), the model can achieve decoding (OCR) precision of 97%. Even at a compression ratio of 20×, the OCR accuracy still remains at about 60%. This shows considerable promise for research areas such as historical long-context compression and memory forgetting mechanisms in LLMs. Beyond this, DeepSeek-OCR also demonstrates high practical value. On OmniDocBench, it surpasses GOT-OCR2.0 (256 tokens/page) using only 100 vision tokens, and outperforms MinerU2.0 (6000+ tokens per page on average) while utilizing fewer than 800 vision tokens. In production, DeepSeek-OCR can generate training data for LLMs/VLMs at a scale of 200k+ pages per day (a single A100-40G). Codes and model weights are publicly accessible at http://github.com/deepseek-ai/DeepSeek-OCR.\n\n## Figures\n\n### Figure 1\n\n**(a) Compression on Fox benchmark**  \n*(Chart displays Precision (%) vs Text Tokens in Per Page (Ground-truth). It compares performance using

---

# Page 2

```json
{
  "page_number": 2,
  "markdown": "# Contents\n\n**1 Introduction** ................................................................................................................................. **3**\n\n**2 Related Works** ............................................................................................................................... **4**\n* 2.1 Typical Vision Encoders in VLMs ........................................................................................ 4\n* 2.2 End-to-end OCR Models ........................................................................................................ 4\n\n**3 Methodology** ................................................................................................................................. **5**\n* 3.1 Architecture ............................................................................................................................... 5\n* 3.2 DeepEncoder ............................................................................................................................. 5\n    * 3.2.1 Architecture of DeepEncoder ........................................................................................ 5\n    * 3.2.2 Multiple resolution support ........................................................................................... 6\n* 3.3 The MoE Decoder ..................................................................................................................... 7\n* 3.4 Data Engine ............................................................................................................................... 7\n    * 3.4.1 OCR 1.0 data ..................................................................................................................... 7\n    * 3.4.2 OCR 2.0 data ..................................................................................................................... 8\n    * 3.4.3 General vision data .......................................................................................................... 9\n    * 3.4.4 Text-only data ................................................................................................................... 9\n* 3.5 Training Pipelines ..................................................................................................................... 9\n    * 3.5.1 Training DeepEncoder .................................................................................................... 10\n    * 3.5.2 Training DeepSeek-OCR ................................................................................................ 10\n\n**4 Evaluation** .................................................................................................................................... **10**\n* 4.1 Vision-text Compression Study .............................................................................................. 10\n* 4.2 OCR Practical Performance ..................................................................................................... 12\n* 4.3 Qualitative Study ...................................................................................................................... 12\n    * 4.3.1 Deep parsing ..................................................................................................................... 12\n    * 4.3.2 Multilingual recognition ................................................................................................. 16\n    * 4.3.3 General vision understanding ........................................................................................ 17\n\n**5 Discussion** .................................................................................................................................... **18**\n\n**6 Conclusion** .................................................................................................................................... **19**",
  "entities": [
    "Introduction",
    "Related Works",
    "Vision Encoders",
    "VLMs",
    "End-to-end OCR Models",
    "Methodology",
    "DeepEncoder",
    "MoE Decoder",
    "Data Engine",
    "OCR 1.0 data",
    "OCR 2.0 data",
    "General vision data",
    "Text-only data",
    "Training Pipelines",
    "DeepSeek-OCR",
    "Evaluation",
    "Vision-text Compression Study",
    "OCR Practical Performance",
    "Qualitative Study",
    "Deep parsing",
    "Multilingual recognition",
    "General vision understanding",
    "Discussion",
    "Conclusion"
  ],
  "summary": "This is the Table of Contents (page 2) for a technical

---

# Page 3

```json
{
  "page_number": 3,
  "markdown": "# 1. Introduction\n\nCurrent Large Language Models (LLMs) face significant computational challenges when processing long textual content due to quadratic scaling with sequence length. We explore a potential solution: leveraging visual modality as an efficient compression medium for textual information. A single image containing document text can represent rich information using substantially fewer tokens than the equivalent digital text, suggesting that optical compression through vision tokens could achieve much higher compression ratios.\n\nThis insight motivates us to reexamine vision-language models (VLMs) from an LLM-centric perspective, focusing on how vision encoders can enhance LLMs' efficiency in processing textual information rather than basic VQA [12, 16, 24, 32, 41] what humans excel at. OCR tasks, as an intermediate modality bridging vision and language, provide an ideal testbed for this vision-text compression paradigm, as they establish a natural compression-decompression mapping between visual and textual representations while offering quantitative evaluation metrics.\n\nAccordingly, we present **DeepSeek-OCR**, a VLM designed as a preliminary proof-of-concept for efficient vision-text compression. Our work makes three primary contributions:\n\n1.  **First**, we provide comprehensive quantitative analysis of vision-text token compression ratios. Our method achieves 96%+ OCR decoding precision at 9-10× text compression, ~90% at 10-12× compression, and ~60% at 20× compression on Fox [21] benchmarks featuring diverse document layouts (with actual accuracy being even higher when accounting for formatting differences between output and ground truth), as shown in Figure 1(a). The results demonstrate that compact language models can effectively learn to decode compressed visual representations, suggesting that larger LLMs could readily acquire similar capabilities through appropriate pretraining design.\n\n2.  **Second**, we introduce **DeepEncoder**, a novel architecture that maintains low activation memory and minimal vision tokens even with high-resolution inputs. It serially connects window attention and global attention encoder components through a 16× convolutional compressor. This design ensures that the window attention component processes a large number of vision tokens, while the compressor reduces vision tokens before they enter the dense global attention component, achieving effective memory and token compression.\n\n3.  **Third**, we develop DeepSeek-OCR based on DeepEncoder and DeepSeek3B-MoE [19, 20]. As shown in Figure 1(b), it achieves state-of-the-art performance within end-to-end models on OmniDocBench while using the fewest vision tokens. Additionally, we equip the model with capabilities for parsing charts, chemical formulas, simple geometric figures, and natural images to enhance its practical utility further. In production, DeepSeek-OCR can generate 33 million pages of data per day for LLMs or VLMs using 20 nodes (each with 8 A100-40G GPUs).\n\nIn summary, this work presents a preliminary exploration of using visual modality as an efficient compression medium for textual information processing in LLMs. Through DeepSeek-OCR, we demonstrate that vision-text compression can achieve significant token reduction (7-20×) for different historical context stages, offering a promising direction for addressing long-context challenges in large language models. Our quantitative analysis provides empirical guidelines for VLM token allocation optimization, while the proposed DeepEncoder architecture showcases practical feasibility with real-world deployment capabilities. Although focused on OCR as a proof-of-concept, this paradigm opens new possibilities for rethinking how vision and language modalities can be synergistically combined to enhance computational efficiency in large-scale text processing and agent systems.",
  "entities": [
    "DeepSeek-OCR",
    "DeepEncoder",
    "DeepSeek3B-MoE",
    "OmniDocBench",
    "Fox benchmark",
    "LLMs",
    "VLMs",
    "A100-40G GPUs",
    "OCR"
  ],
  "summary": "This page introduces DeepSeek-OCR, a Vision-Language Model (VLM) designed to test the efficiency of using visual modality for text compression in Large Language Models (LLMs). The authors propose 'DeepEncoder,' a novel architecture utilizing a 16x convolutional compressor to minimize vision tokens and memory usage. The model achieves high OCR precision (96%+) at 9-10x compression ratios and state-of-the-art performance on OmniDocBench. It is highly

---

# Page 4

```json
{
  "page_number": 4,
  "markdown": "![Figure 2: Diagram comparing three types of vision encoders in popular VLMs: Vary/DeepSeekVL (Dual-tower), InternVL series (Tile-based), and Qwen2/3VL series (Adaptive resolution). It lists deficiencies for each, such as unsupported pipeline parallel, too many vision tokens, and large activations.]\n\n**Figure 2 | Typical vision encoders in popular VLMs.** Here are three types of encoders commonly used in current open-source VLMs, all of which suffer from their respective deficiencies.\n\n# 2. Related Works\n\n## 2.1. Typical Vision Encoders in VLMs\n\nCurrent open-source VLMs employ three main types of vision encoders, as illustrated in Figure 2. The first type is a dual-tower architecture represented by Vary [36], which utilizes parallel SAM [17] encoder to increase visual vocabulary parameters for high-resolution image processing. While offering controllable parameters and activation memory, this approach suffers from significant drawbacks:

---

# Page 5

```json
{
  "page_number": 5,
  "markdown": "![Figure 3: The architecture of DeepSeek-OCR.](figure_3_diagram)\n\n**Figure 3 | The architecture of DeepSeek-OCR.** DeepSeek-OCR consists of a DeepEncoder and a DeepSeek-3B-MoE decoder. DeepEncoder is the core of DeepSeek-OCR, comprising three components: a SAM [17] for perception dominated by window attention, a CLIP [29] for knowledge with dense global attention, and a 16× token compressor that bridges between them.\n\n## 3. Methodology\n\n### 3.1. Architecture\n\nAs shown in Figure 3, DeepSeek-OCR enjoys a unified end-to-end VLM architecture consisting of an encoder and a decoder. The encoder (namely DeepEncoder) is responsible for extracting image features and tokenizing as well as compressing visual representations. The decoder is used for generating the required result based on image tokens and prompts. DeepEncoder is approximately 380M in parameters, mainly composed of an 80M SAM-base [17] and a 300M CLIP-large [29] connected in series. The decoder adopts a 3B MoE [19, 20] architecture with 570M activated parameters. In the following paragraphs, we will delve into the model components, data engineering, and training skills.\n\n### 3.2. DeepEncoder\n\nTo explore the feasibility of contexts optical compression, we need a vision encoder with the following features: 1.Capable of processing high resolutions; 2.Low activation at high resolutions; 3.Few vision tokens; 4.Support for multiple resolution inputs; 5. Moderate parameter count. However, as described in the Section 2.1, current open-source encoders cannot fully satisfy all these conditions. Therefore, we design a novel vision encoder ourselves, named DeepEncoder.\n\n#### 3.2.1. Architecture of DeepEncoder\n\nDeepEncoder mainly consists of two components: a visual perception feature extraction component dominated by window attention, and a visual knowledge feature extraction component with dense global attention. To benefit from the pretraining gains of previous works, we use SAM-base (patch-size 16) and CLIP-large as the main architectures for the two components respectively. For CLIP, we remove the first patch embedding layer since its input is no longer images but output tokens from the previous pipeline. Between the two components, we borrow from Vary [36] and use a 2-layer convolutional module to perform 16× downsampling of vision tokens. Each convolutional layer has a kernel size of 3, stride of 2, padding of 1, and channels increase from 256 to 1024. Assuming we input a 1024×1024 image, the DeepEncoder will segment it into 1024/16×1024/16=4096 patch tokens. Since the first half of encoder is dominated by window attention and only 80M, the activation is acceptable. Before entering global attention,",
  "entities": [
    "DeepSeek-OCR",
    "DeepEncoder",
    "DeepSeek-3B-MoE",
    "SAM",
    "CLIP",
    "VLM",
    "SAM-base",
    "CLIP-large",
    "Vary",
    "ViTDet",
    "ViT",
    "MoE"
  ],
  "summary": "This page details the methodology and architecture of DeepSeek-OCR, specifically focusing on its unified end-to-end VLM structure. The system comprises a custom vision encoder called DeepEncoder and a DeepSeek-3B-MoE decoder. The DeepEncoder is designed to handle high resolutions efficiently by combining an 80M SAM-base model (local attention) and a 300M

---

# Page 6

```json
{
  "page_number": 6,
  "markdown": "![Figure 4: Diagram showing Resize, Padding, and Dynamic Resolution modes](figure_4)\n\n**Figure 4 |** To test model performance under different compression ratios (requiring different numbers of vision tokens) and enhance the practicality of DeepSeek-OCR, we configure it with multiple resolution modes.\n\nthe 4096 tokens go through the compression module and the token count becomes 4096/16=256, thus making the overall activation memory controllable.\n\n**Table 1 |** Multi resolution support of DeepEncoder. For both research and application purposes, we design DeepEncoder with diverse native resolution and dynamic resolution modes.\n\n| | **Native Resolution** | | | | **Dynamic Resolution** | |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n| **Mode** | **Tiny** | **Small** | **Base** | **Large** | **Gundam** | **Gundam-M** |\n| Resolution | 512 | 640 | 1024 | 1280 | 640+1024 | 1024+1280 |\n| Tokens | 64 | 100 | 256 | 400 | n×100+256 | n×256+400 |\n| Process | resize | resize | padding | padding | resize + padding | resize + padding |\n\n### 3.2.2. Multiple resolution support\n\nSuppose we have an image with 1000 optical characters and we want to test how many vision tokens are needed for decoding. This requires the model to support a variable number of vision tokens. That is to say the DeepEncoder needs to support multiple resolutions.\n\nWe meet the requirement aforementioned through dynamic interpolation of positional encodings, and design several resolution modes for simultaneous model training to achieve the capability of a single DeepSeek-OCR model supporting multiple resolutions. As shown in Figure 4, DeepEncoder mainly supports two major input modes: native resolution and dynamic resolution. Each of them contains multiple sub-modes.\n\nNative resolution supports four sub-modes: Tiny, Small, Base, and Large, with corresponding resolutions and token counts of 512×512 (64

---

# Page 7

```json
{
  "page_number": 7,
  "markdown": "Dynamic resolution can be composed of two native resolutions. For example, Gundam mode consists of $n \\times 640 \\times 640$ tiles (local views) and a $1024 \\times 1024$ global view. The tiling method following InternVL2.0 [8]. Supporting dynamic resolution is mainly for application considerations, especially for ultra-high-resolution inputs (such as newspaper images). Tiling is a form of secondary window attention that can effectively reduce activation memory further. It's worth noting that due to our relatively large native resolutions, images won't be fragmented too much under dynamic resolution (the number of tiles is controlled within the range of 2 to 9). The vision token number output by the DeepEncoder under Gundam mode is: $n \\times 100 + 256$, where $n$ is the number of tiles. For images with both width and height smaller than 640, $n$ is set to 0, i.e., Gundam mode will degrade to Base mode.\n\nGundam mode is trained together with the four native resolution modes to achieve the goal of one model supporting multiple resolutions. Note that Gundam-master mode ($1024 \\times 1024$ local views + $1280 \\times 1280$ global view) is obtained through continued training on a trained DeepSeek-OCR model. This is mainly for load balancing, as Gundam-master's resolution is too large and training it together would slow down the overall training speed.\n\n### 3.3. The MoE Decoder\n\nOur decoder uses the DeepSeekMoE [19, 20], specifically DeepSeek-3B-MoE. During inference, the model activates 6 out of 64 routed experts and 2 shared experts, with about 570M activated parameters. The 3B DeepSeekMoE is very suitable for domain-centric (OCR for us) VLM research, as it obtains the expressive capability of a 3B model while enjoying the inference efficiency of a 500

---

# Page 8

```json
{
  "page_number": 8,
  "markdown": "![Figure 5: Comparison of (a) Ground truth image containing geometry and text, and (b) Fine annotations with layouts showing XML-like tags with coordinates.](figure_5)\n\n**Figure 5 | OCR 1.0 fine annotations display.** We format the ground truth into an interleaved layout and text format, where each paragraph of text is preceded by the coordinates and label of it in the original image. All coordinates are normalized into 1000 bins.\n\ndirectly from the full dataset using *fitz*, aimed at teaching the model to recognize optical text, especially in minority languages. Fine annotations include 2M pages each for Chinese and English, labeled using advanced layout models (such as PP-DocLayout [33]) and OCR models (such as MinuerU [34] and GOT-OCR2.0 [38]) to construct detection and recognition interleaved data. For minority languages, in the detection part, we find that the layout model enjoys certain generalization capabilities. In the recognition part, we use *fitz* to create small patch data to train a GOT-OCR2.0, then use the trained model to label small patches after layout processing, employing a model flywheel to create 600K data samples. During the training of DeepSeek-OCR, coarse labels and fine labels are distinguished using different prompts. The ground truth for fine annotation image-text pairs can be seen in Figure 5. We also collect 3M *Word* data, constructing high-quality image-text pairs without layout by directly extracting content. This data mainly brings benefits to formulas and HTML-formatted tables. Additionally, we select some open-source data [28, 37] as supplements.\n\nFor natural scene OCR, our model mainly supports Chinese and English. The image data sources come from LAION [31] and Wukong [13], labeled using PaddleOCR [9], with 10M data samples each for Chinese and English. Like document OCR, natural scene OCR can also control whether to output detection boxes through prompts.\n\n### 3.4.2. OCR 2.0 data\n\nFollowing GOT-OCR2.0 [38], we refer to chart, chemical formula, and plane geometry parsing data as OCR 2.0 data. For chart data, following OneChart [7], we use pyecharts and matplotlib",
  "entities": [
    "OCR 1.0",
    "OCR 2.0",
    "fitz",
    "PP-DocLayout",
    "MinuerU",
    "GOT-OCR2.0",
    "DeepSeek-OCR",
    "Word data",
    "LAION",
    "Wukong",
    "PaddleOCR",
    "OneChart",
    "pyecharts",
    "matplotlib",
    "Chinese",
    "English"
  ],
  "summary": "This page details the data preparation process for an OCR model, specifically distinguishing between 'OCR 1.0 fine annotations' and 'OCR 2

---

# Page 9

![Figure 6: Image-text ground truth examples. (a) shows a bar chart with corresponding HTML table code. (b) shows a geometric diagram with corresponding dictionary format data.](figure_6)

**Figure 6 |** For charts, we do not use OneChart’s [7] dictionary format, but instead use HTML table format as labels, which can save a certain amount of tokens. For plane geometry, we convert the ground truth to dictionary format, where the dictionary contains keys such as line segments, endpoint coordinates, line segment types, etc., for better readability. Each line segment is encoded using the Slow Perception [39] manner.

to render 10M images, mainly including commonly used line, bar, pie, and composite charts. We define chart parsing as image-to-HTML-table conversion task, as shown in Figure 6(a). For chemical formulas, we utilize SMILES format from PubChem as the data source and render them into images using RDKit, constructing 5M image-text pairs. For plane geometry images, we follow Slow Perception [39] for generation. Specifically, we use perception-ruler size as 4 to model each line segment. To increase the diversity of rendered data, we introduce geometric translation-invariant data augmentation, where the same geometric image is translated in the original image, corresponding to the same ground truth drawn at the centered position in the coordinate system. Based on this, we construct a total of 1M plane geometry parsing data, as illustrated in Figure 6(b).

### 3.4.3. General vision data

DeepEncoder can benefit from CLIP’s pretraining gains and has sufficient parameters to incorporate general visual knowledge. Therefore, we also prepare some corresponding data for DeepSeek-OCR. Following DeepSeek-VL2 [40], we generate relevant data for tasks such as caption, detection, and grounding. Note that DeepSeek-OCR is not a general VLM model, and this portion of data accounts for only 20% of the total data. We introduce such type of data mainly to preserve the general vision interface, so that researchers interested in our model and general vision task can conveniently advance their work in the future.

### 3.4.4. Text-only data

To ensure the model’s language capabilities, we introduced 10% of in-house text-only pretrain data, with all data processed to a length of 8192 tokens, which is also the sequence length for DeepSeek-OCR. In summary, when training DeepSeek-OCR, OCR data accounts for 70%, general vision data accounts for 20%, and text-only data accounts for 10%.

### 3.5. Training Pipelines

Our training pipeline is very simple and consists mainly of two stages: a).Training DeepEncoder independently; b).Training the DeepSeek-OCR. Note that the Gundam-master mode is obtained by continuing training on a pre-trained DeepSeek-OCR model with 6M sampled data. Since the training protocol is identical to other modes, we omit the detailed description hereafter.

---

# Page 10

```json
{
  "page_number": 10,
  "markdown": "### 3.5.1. Training DeepEncoder\n\nFollowing Vary [36], we utilize a compact language model [15] and use the next token prediction framework to train DeepEncoder. In this stage, we use all OCR 1.0 and 2.0 data aforementioned, as well as 100M general data sampled from the LAION [31] dataset. All data is trained for 2 epochs with a batch size of 1280, using the AdamW [23] optimizer with cosine annealing scheduler [22] and a learning rate of 5e-5. The training sequence length is 4096.\n\n### 3.5.2. Training DeepSeek-OCR\n\nAfter DeepEncoder is ready, we use data mentioned in Section 3.4 to train the DeepSeek-OCR with the entire training process conducted on the HAI-LLM [14] platform. The entire model uses pipeline parallelism (PP) and is divided into 4 parts, with DeepEncoder taking two parts and the decoder taking two parts. For DeepEncoder, we treat SAM and the compressor as the vision tokenizer, place them in PP0 and freeze their parameters, while treating the CLIP part as input embedding layer and place it in PP1 with unfrozen weights for training. For the language model part, since DeepSeek3B-MoE has 12 layers, we place 6 layers each on PP2 and PP3. We use 20 nodes (each with 8 A100-40G GPUs) for training, with a data parallelism (DP) of 40 and a global batch size of 640. We use the AdamW optimizer with a step-based scheduler and an initial learning rate of 3e-5. For text-only data, the training speed is 90B tokens/day, while for multimodal data, the training speed is 70B tokens/day.\n\nTable 2 | We test DeepSeek-OCR's vision-text compression ratio using all English documents with 600-1300 tokens from the Fox [21] benchmarks. Text tokens represent the number of tokens after tokenizing the ground truth text using DeepSeek-OCR's tokenizer. Vision Tokens=64 or 100 respectively represent the number of vision tokens output by DeepEncoder after resizing input images to 512×512 and 640×640.\n\n| Text Tokens | Vision Tokens =64 Precision | Vision Tokens =64 Compression | Vision Tokens=100 Precision | Vision Tokens=100 Compression | Pages |\n| :--- | :---: | :---: | :---: | :---: | :---: |\n| 600-700 | 96.5% | 10.5× | 98.5% | 6.7× | 7 |\n| 700-80

---

# Page 11

```json
{
  "page_number": 11,
  "markdown": "Table 3 | We use OmniDocBench [27] to test the performance of DeepSeek-OCR on real document parsing tasks. All metrics in the table are edit distances, where smaller values indicate better performance. \"Tokens\" represents the average number of vision tokens used per page, and \"$^{\\dagger 200dpi}$\" means using *fitz* to interpolate the original image to 200dpi. For the DeepSeek-OCR model, the values in parentheses in the \"Tokens\" column represent valid vision tokens, calculated according to Equation 1.\n\n| Model | Tokens | English overall | English text | English formula | English table | English order | Chinese overall | Chinese text | Chinese formula | Chinese table | Chinese order |\n| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |\n| **Pipeline Models** | | | | | | | | | | | |\n| Dolphin [11] | - | 0.356 | 0.352 | 0.465 | 0.258 | 0.35 | 0.44 | 0.44 | 0.604 | 0.367 | 0.351 |\n| Marker [1] | - | 0.2

---

# Page 12

```json
{
  "page_number": 12,
  "markdown": "a feature of the forgetting mechanism. When compressing tokens by nearly 20×, we find that precision can still approach 60%. These results indicate that optical contexts compression is a very promising and worthwhile research direction, and this approach does not bring any overhead because it can leverage VLM infrastructure, as multimodal systems inherently require an additional vision encoder.\n\nTable 4 | Edit distances for different categories of documents in OmniDocBench. The results show that some types of documents can achieve good performance with just 64 or 100 vision tokens, while others require Gundam mode.\n\n| Mode \\ Type | Book | Slides | Financial Report | Textbook | Exam Paper | Magazine | Academic Papers | Notes | Newspaper | Overall |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n| Tiny | 0.147 | 0.116 | 0.207 | 0.173 | 0.294 | 0.201 | 0.395 | 0.297 | 0.94 | 0.32 |\n| Small | 0.085 | 0.111 | 0.079 | 0.147 | 0.171 | 0.107 | 0.131 | 0.187 | 0.744 | 0.205 |\n| Base | 0.037 | 0.08 | 0.027 | 0.1 | 0.13 | 0.073 | 0.052 | 0.176 | 0.645 | 0.156 |\n| Large | 0.038 | 0.108 | 0.022 | 0.084 | 0.109 | 0.06 | 0.053 | 0.155 | 0.353 | 0.117 |\n| Gundam | 0.035 | 0.085 | 0.289 | 0.095 | 0.094 | 0.059 | 0.039 | 0.153 | 0.122 | 0.083 |\n| Gundam-M | 0.052 | 0.09 | 0.034 | 0.091 | 0.079 | 0.079 | 0.048 | 0.1 | 0.099 | 0.077 |\n\n### 4.2. OCR Practical Performance\n\nDeepSeek-OCR is not only an experimental model; it has strong practical capabilities and can construct data for LLM/VLM pretraining. To quantify OCR performance, we test DeepSeek-OCR on OmniDocBench [27], with results shown in Table 3. Requiring only 100 vision tokens (640×640 resolution), DeepSeek-OCR surpasses GOT-OCR2.0 [38] which uses 2

---

# Page 13

```json
{
  "page_number": 13,
  "markdown": "# Figure 7: DeepSeek-OCR Deep Parsing Mode\n\n**Caption:** In the field of financial research reports, the deep parsing mode of DeepSeek-OCR can be used to obtain structured results of charts within documents. Charts are a crucial form of data representation in finance and scientific fields, and the chart structured extraction is an indispensable capability for future OCR models.\n\n## Visual Process Demonstration\n\nThe figure displays a workflow transforming a financial document titled **\"Macro news and views\"**.\n\n### 1. Input Image & Result\n*   **Input:** A complex layout containing columns for **US**, **Japan**, **Europe**, and **Emerging Markets**, mixed with text and charts.\n*   **Result:** The system converts the document to markdown with grounding coordinates.\n\n### 2. Deep Parsing Example\n\nA specific chart titled **\"A European defense renaissance likely ahead\"** (GS forecasts of military spending, % of GDP) is isolated and converted into structured tabular data.\n\n#### Extracted Data Table (from Deep Parsing quadrant)\n\n| | 2024 | 2025 | 2026 | 2027 |\n| :--- | :--- | :--- | :--- | :--- |\n| **

---

# Page 14

```json
{
  "page_number": 14,
  "markdown": "# Figure 8: Deep Parsing Mode for Books and Articles\n\n**Caption:** Figure 8 | For books and articles, the deep parsing mode can output dense captions for natural images in the documents. With just a prompt, the model can automatically identify what type of image it is and output the required results.\n\n## Process Flow\nThe figure illustrates a four-step process for analyzing a document page:\n1.  **Input image:** The raw scan of a magazine page.\n2.  **Result:** The document converted to markdown with grounding (bounding boxes).\n3.  **Deep Parsing:** A detailed analysis of the visual content within the document.\n4.  **Rendering:** A clean reconstruction of the text and image content.\n\n## Deep Parsing Output\n*(Text extracted from the \"Deep Parsing\" callout box describing the image within the article)*\n\n> The image depicts an indoor classroom setting with a group of children and an adult. The children are seated on the floor, facing a woman who is standing and appears to be reading or presenting to them. The woman is wearing a brown sweater and blue jeans. The children are dressed in various colors, with some wearing short pants and others in long pants.\n> \n> The classroom has a green wall with educational posters and a bulletin board. The floor is covered with a gray carpet. To the left, there is a wooden dresser with a drawer partially open, and a chair is visible behind it. On the right side of the image, there is a purple bean bag chair.\n> \n> The children are engaged with the woman, with some looking at her and others looking down or away. The room is well-lit, and the overall atmosphere seems to be one of attentiveness and learning.\n> \n> The text \"BIBLIOTECA\" is visible on the wall, suggesting that the room may be part of a library or a section dedicated to books. The presence of educational materials and the organized layout of the room indicate that this is a space designed for learning and reading.\n\n## Inner Document Content\n*(Content from the

---

# Page 15

```json
{
  "page_number": 15,
  "markdown": "# Figure 9 | DeepSeek-OCR in deep parsing mode\n\n**Caption:** DeepSeek-OCR in deep parsing mode can also recognize chemical formulas within chemical documents and convert them to SMILES format. In the future, OCR 1.0+2.0 technology may play a significant role in the development of VLM/LLM in STEM fields.\n\n## Visual Workflow Components\nThe figure illustrates a four-step process:\n1.  **Input image:** A raw scan of a patent document.\n2.  **Result:** The document converted to markdown with grounding tags (e.g., `<image>\n[grounding]`).\n3.  **Deep Parsing:** Detailed extraction of chemical structures (shown as `Parse the figure`).\n4.  **Rendering:** The final digital reconstruction of text and chemical diagrams.\n\n## Content of Example Document (WO 2013/171642)\n\n**Header:** WO 2013/171642 | PCT/IB2013/053771\n\n**[00369]** The title compound was prepared in an analogous fashion to that described in Stage 22.1 using 5-bromo-6-chloro-N-(4-(chlorodifluoromethoxy)phenyl)nicotinamide (Stage 22.2) and 2-methylamino

---

# Page 16

![Figure 10: Composite image showing Input image, Result, Deep Parsing, and Rendering of a geometry problem worksheet.](figure_10)

**Figure 10 | DeepSeek-OCR also possesses the capability to copy (structure) simple planar geometric figures. Due to the intricate interdependencies among line segments in geometric shapes, parsing geometry task is extremely challenging and has a long way to go.**

### 4.3.2. Multilingual recognition

PDF data on the Internet contains not only Chinese and English, but also a large amount of multilingual data, which is also crucial when training LLMs. For PDF documents, DeepSeek-OCR can handle nearly 100 languages. Like Chinese and English documents, multilingual data also supports both layout and non-layout OCR formats. The visualization results are shown in Figure 11, where we select Arabic and Sinhala languages to demonstrate results.

16

---

# Page 17

![Figure 11: Examples of OCR capabilities on multilingual documents. Top left: An Arabic document with text and a table. Top right: A document in Sinhala script showing grounding and markdown conversion.]

**Figure 11 |** To endow the capability of processing widely crawled PDFs (multilingual data), we train our model with OCR capabilities for nearly 100 languages. Minority language documents can also support both layout and non-layout outputs through different prompts.

### 4.3.3. General vision understanding

We also provide DeepSeek-OCR with a certain degree of general image understanding capabilities. The related visualization results are shown in Figure 12.

---

# Page 18

![Figure 12: A composite image showing six examples of DeepSeek-OCR capabilities including locating math problems, describing a bean paste jar, locating a cartoon teacher, object detection in a park, describing a fire hydrant in Chinese, and OCR grounding on a mug with Chinese poetry.]

**Figure 12 |** We retain DeepSeek-OCR's capabilities in general visual understanding, mainly including image description, object detection, grounding, etc. Meanwhile, due to the inclusion of text-only data, DeepSeek-OCR's language capabilities are also retained. Note that since we do not include SFT (Supervised Fine-Tuning) stage, the model is not a chatbot, and some capabilities need completion prompts to be activated.

# 5. Discussion

Our work represents an initial exploration into the boundaries of vision-text compression, investigating how many vision tokens are required to decode *N* text tokens. The preliminary results are encouraging: DeepSeek-OCR achieves near-lossless OCR compression at approximately 10× ratios, while 20× compression still retains 60% accuracy. These findings suggest promising directions for future applications, such as implementing optical processing for dialogue histories beyond *k* rounds in multi-turn conversations to achieve 10× compression efficiency.

18

---

# Page 19

```json
{
  "page_number": 19,
  "markdown": "### Figure 13 Data Representation\n\n| Domain | Crystal Clear | Very Clear | Clear | Blurry | Very Blurry | Almost Gone | Direction |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n| **Memory** | Just happened | 1 hour | 1 day | 1 week | 1 month | 1 year | Time → |\n| **Vision** | 10cm | 50cm | 1m | 3m | 10m | 20m | Distance ↑ |\n| **Text** | Text token | Gundam | Large | Base | Small | Tiny | Resolution ↓ |\n\n**Figure 13 | Forgetting mechanisms constitute one of the most fundamental characteristics of human memory.** The contexts optical compression approach can simulate this mechanism by rendering previous rounds of historical text onto images for initial compression, then progressively resizing older images to achieve multi-level compression, where token counts gradually decrease and text becomes increasingly blurred, thereby accomplishing textual forgetting.\n\nFor older contexts, we could progressively downsizing the rendered images to further reduce token consumption. This assumption draws inspiration from the natural parallel between human memory decay over time and visual perception degradation over spatial distance—both exhibit similar patterns of progressive information loss, as shown in Figure 13. By combining these mechanisms, contexts optical compression method enables a form of memory decay that mirrors biological forgetting curves, where recent information maintains high fidelity while distant memories naturally fade through increased compression ratios.\n\nWhile our initial exploration shows potential for scalable ultra-long context processing, where recent contexts preserve high resolution and older contexts consume fewer resources, we acknowledge this is early-stage work that requires further investigation. The approach suggests a path toward theoretically unlimited context architectures that balance information retention with computational constraints, though the practical implications and limitations of such vision-text compression systems warrant deeper study in future research.\n\n# 6. Conclusion\n\nIn this technical report, we propose DeepSeek-OCR and preliminarily validate the feasibility of contexts optical compression through this model, demonstrating that the model can effectively decode text tokens exceeding 10 times the quantity from a small number of vision tokens. We believe this finding will facilitate the development of VLMs and LLMs in the future

---

# Page 20

```json
{
  "page_number": 20,
  "markdown": "# References\n\n[1] Marker. URL https://github.com/datalab-to/marker.\n\n[2] Mathpix. URL https://mathpix.com/.\n\n[3] Ocrflux, 2025. URL https://github.com/chatdoc-com/OCRFlux.\n\n[4] G. AI. Gemini 2.5-pro, 2025. URL https://gemini.google.com/.\n\n[5] S. Bai, K. Chen, X. Liu, J. Wang, W. Ge, S. Song, K. Dang, P. Wang, S. Wang, J. Tang, H. Zhong, Y. Zhu, M. Yang, Z. Li, J. Wan, P. Wang, W. Ding, Z. Fu, Y. Xu, J. Ye, X. Zhang, T. Xie, Z. Cheng, H. Zhang, Z. Yang, H. Xu, and J. Lin. Qwen2.5-vl technical report. arXiv preprint arXiv:2502.13923, 2025.\n\n[6] L. Blecher, G. Cucurull, T. Scialom, and R. Stojnic. Nougat: Neural optical understanding for academic documents. arXiv preprint arXiv:2308.13418, 2023.\n\n[7] J. Chen, L. Kong, H. Wei, C. Liu, Z. Ge, L. Zhao, J. Sun, C. Han, and X. Zhang. Onechart: Purify the chart structural extraction via one auxiliary token. In Proceedings of the 32nd ACM International Conference on Multimedia, pages 147–155, 2024.\n\n[8] Z. Chen, W. Wang, H. Tian, S. Ye, Z. Gao, E. Cui, W. Tong, K. Hu, J. Luo, Z. Ma, et al. How far are we to gpt-4v? closing the gap to commercial multimodal models with open-source suites. arXiv preprint arXiv:2404.16821, 2024.\n\n[9] C. Cui, T. Sun, M. Lin, T. Gao, Y. Zhang, J. Liu, X. Wang, Z. Zhang, C. Zhou, H. Liu, et al. Paddleocr 3.0 technical report. arXiv preprint arXiv:2507.05595, 2025.\n\n[10] M. Dehghani, J. Djolonga, B. Mustafa, P. Padlewski, J. Heek, J. Gilmer, A. Steiner, M. Caron, R. Geirhos, I. Alabdulmohsin, et al. Patch n’ pack: Navit, a vision transformer for any aspect ratio and resolution. Advances in Neural Information Processing Systems, 36:3632–3656, 2023.\n\n[11] H. Feng, S. Wei, X. Fei, W. Shi, Y. Han, L. Liao, J. Lu, B. Wu, Q. Liu, C. Lin, et al. Dolphin: Document image parsing via heterogeneous anchor prompting. arXiv preprint arXiv:2505.14059, 2025.\n\n[12] Y. Goyal, T. Khot, D. Summers-Stay, D. Batra, and D. Parikh. Making the v in vqa matter: Elevating the role of image understanding in visual question answering. In Proceedings of the IEEE conference on computer

---

# Page 21

```json
{
  "page_number": 21,
  "markdown": "17. A. Kirillov, E. Mintun, N. Ravi, H. Mao, C. Rolland, L. Gustafson, T. Xiao, S. Whitehead, A. C. Berg, W.-Y. Lo, et al. Segment anything. arXiv preprint arXiv:2304.02643, 2023.\n\n18. Z. Li, Y. Liu, Q. Liu, Z. Ma, Z. Zhang, S. Zhang, Z. Guo, J. Zhang, X. Wang, and X. Bai. Monkeyocr: Document parsing with a structure-recognition-relation triplet paradigm. arXiv preprint arXiv:2506.05218, 2025.\n\n19. A. Liu, B. Feng, B. Wang, B. Wang, B. Liu, C. Zhao, C. Dengr, C. Ruan, D. Dai, D. Guo, et al. Deepseek-v2: A strong, economical, and efficient mixture-of-experts language model. arXiv preprint arXiv:2405.04434, 2024.\n\n20. A. Liu, B. Feng, B. Xue, B. Wang, B. Wu, C. Lu, C. Zhao, C. Deng, C. Zhang, C. Ruan, et al. Deepseek-v3 technical report. arXiv preprint arXiv:2412.19437, 2024.\n\n21. C. Liu, H. Wei, J. Chen, L. Kong, Z. Ge, Z. Zhu, L. Zhao, J. Sun, C. Han, and X. Zhang. Focus anywhere for fine-grained multi-page document understanding. arXiv preprint arXiv:2405.14295, 2024.\n\n22. I. Loshchilov and F. Hutter. Sgdr: Stochastic gradient descent with warm restarts. arXiv preprint arXiv:1608.03983, 2016.\n\n23. I. Loshchilov and F. Hutter. Decoupled weight decay regularization. In ICLR, 2019.\n\n24. A. Masry, D. X. Long, J. Q. Tan, S. Joty, and E. Hoque. Chartqa: A benchmark for question answering about charts with visual and logical reasoning. arXiv preprint arXiv:2203.1

---

# Page 22

```json
{
  "page_number": 22,
  "markdown": "[32] A. Singh, V. Natarajan, M. Shah, Y. Jiang, X. Chen, D. Batra, D. Parikh, and M. Rohrbach. Towards vqa models that can read. In _Proceedings of the IEEE/CVF conference on computer vision and pattern recognition_, pages 8317–8326, 2019.\n\n[33] T. Sun, C. Cui, Y. Du, and Y. Liu. Pp-doclayout: A unified document layout detection model to accelerate large-scale data construction. _arXiv preprint arXiv:2503.17213_, 2025.\n\n[34] B. Wang, C. Xu, X. Zhao, L. Ouyang, F. Wu, Z. Zhao, R. Xu, K. Liu, Y. Qu, F. Shang, et al. Mineru: An open-source solution for precise document content extraction. _arXiv preprint arXiv:2409.18839_, 2024.\n\n[35] P. Wang, S. Bai, S. Tan, S. Wang, Z. Fan, J. Bai, K. Chen, X. Liu, J. Wang, W. Ge, et al. Qwen2-vl: Enhancing vision-language model’s perception of the world at any resolution. _arXiv preprint arXiv:2409.12191_, 2024.\n\n[36] H. Wei, L. Kong, J. Chen, L. Zhao, Z. Ge, J. Yang, J. Sun, C. Han, and X. Zhang. Vary: Scaling up the vision vocabulary for large vision-language model. In _European Conference on Computer Vision_, pages 408–424. Springer, 2024.\n\n[37] H. Wei, L. Kong, J. Chen, L. Zhao, Z.

---

