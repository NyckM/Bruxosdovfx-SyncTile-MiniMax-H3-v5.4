# bruxosdovfx • SyncTile (MiniMax H3) — v5.4

**[Português](#português) · [English](#english) · [中文](#中文) · [Referências / References / 参考文献](#referências--references--参考文献)**

Custom nodes para ComfyUI que levam o MiniMax H3 a 4K e a vídeos longos (testado em 600 frames = 25 s) sem emendar clipes.
Custom nodes for ComfyUI that take MiniMax H3 to 4K and to long videos (tested at 600 frames = 25 s) without chaining clips.
让 MiniMax H3 生成 4K 和长视频（已测试 600 帧 = 25 秒）的 ComfyUI 自定义节点，无需拼接片段。

Cada entrada dos nodes tem uma explicação em PT / EN / 中文: passe o mouse sobre ela no ComfyUI.
Every node input has a PT / EN / 中文 explanation: hover over it in ComfyUI.
每个节点输入都有 PT / EN / 中文 说明：在 ComfyUI 中把鼠标悬停在输入上即可查看。

---

## Português

### Ideia em uma frase
O vídeo grande ou longo é dividido em **regiões que se sobrepõem** (tiles no espaço × janelas no tempo). A cada chamada do modelo, todas as regiões são previstas e **misturadas numa só tela**, então existe **uma trajetória de denoise só**: sem costura entre tiles, sem colar clipes, e a VRAM é a de uma região.

### Instalação
1. Copie a pasta `bruxosdovfx-SyncTile` para `ComfyUI/custom_nodes/`. **Apague** `ComfyUI-SyncTile-H3` se existir (versão antiga).
2. Reinicie. O console mostra `[bruxosdovfx • SyncTile] v5.4 carregado`.
3. Precisa de um ComfyUI com os nodes nativos do MiniMax H3. Para gravar o arquivo de vídeo: ffmpeg (no PATH, em `FFMPEG_PATH`, ou `pip install imageio-ffmpeg`).

### Os nodes (categoria `bruxosdovfx/SyncTile`)
| Node | Para que serve |
| --- | --- |
| **SyncTile Guider (H3)** | Substitui o Basic Guider. Faz a mistura das regiões a cada chamada do modelo. |
| **SyncTile Ref2VA Conditioning (H3)** | Reference to Video por região: fatia o vídeo de referência por janela, recorta por tile e coloca os frames-guia na janela certa. |
| **SyncTile I2V Conditioning (H3)** | Image to Video (primeiro/último frame) por região. Sem imagem = texto para vídeo. |
| **SyncTile Stream Decode (H3)** | Decodifica bloco a bloco e grava direto no arquivo (h265 10-bit, h264, ProRes), sem estourar a RAM. Saída IMAGE opcional para o Save Video Pro. |

### O workflow (Character/Background Swap longo, v16)
1. **Entradas:** vídeo fonte no Load Video Pro (**forçar 24 fps**, o H3 é 24 fps), foto de referência e prompt.
2. **Estágio 1 (~0,5 MP):** SyncTile Ref2VA Conditioning + Guider com tile 4096 (= sem divisão no espaço) e **janelas de 124 frames**, sobreposição 39. 4 passos do modelo turbo.
3. **Latent upscaler 3D (LBH):** amplia o latent até ~6–8 MP sem decodificar.
4. **Estágio 2 (refino 4K):** SyncTile com tiles 1472×896 × janelas de 124 frames. Sigmas `0.878, 0.8, 0.6316, 0` (só os passos finais: corrige textura, mantém a composição).
5. **Stream Decode:** grava o arquivo e manda IMAGE para o 🧙 Save Video Pro.
6. **Frames-guia (opcional):** stills do vídeo fonte já com o resultado, ancorados em frames (ex.: `1, 100, 220, 340, 460`). Seguram o fundo/personagem no vídeo inteiro.

### O que ajustar
- **Prompt:** diga o que vale "em todos os frames" (cada janela lê o prompt sozinha).
- **window_frames** (124; 107/90 se faltar VRAM) e **window_overlap_frames** (39; 56/73 se houver costura ou cintilação). Mesmo valor nos dois conditionings.
- **Força do refino:** sigmas do estágio 2. Mais fiel e menos detalhe: `0.8, 0.6316, 0`.
- **use_refine_seed / refine_seed:** testa outro refino sem refazer o estágio 1.
- **tile_conditioning_detail + detail_below_sigma:** troca estrutura → detalhe nos passos finais (0.85 = equilíbrio).
- **Saída:** codec, crf (menor = melhor), image_output (full/half/off).

### Não mexa (a menos que saiba o porquê)
Tile 4096 no estágio 1 (significa "sem tiles"), min_overlap 16, sync_mode "per model call", cfg 1.0 (modelo turbo), os 4 passos do estágio 1, fps 24, width/height/length dos nodes SyncTile (vêm do latent).

### Problemas comuns
- **Fundo volta ao original no meio do vídeo:** prompt mais explícito, overlap 56/73 e frames-guia a cada ~4–5 s.
- **Personagem repetido em 4K:** sigmas mais leves no estágio 2 e `ref_video_mode = crop`.
- **Movimento acelerado / áudio fora de sincronia:** o vídeo fonte não está em 24 fps.
- **Erro de ffmpeg / BrokenPipe:** o node mostra a mensagem do ffmpeg; sem libx265 ele grava h264 sozinho.
- **"unexpected keyword argument":** versão antiga instalada; apague a pasta antiga e reinicie.

### LoRA Background Replace v3 (resumo)
Mescla experimental de **cinco LoRAs de outros autores** para MiniMax H3 (não é treino original). Arquivo `Background Replace v3.safetensors`, BF16, ~1,91 GB, mescla por concatenação de ranks (sem SVD); sem metadados (os créditos ficam neste README).

| Componente | Autor | Peso |
| --- | --- | --- |
| Facial Realism CloseUp | [prithivMLmods](https://huggingface.co/prithivMLmods/MiniMax-H3-Facial-Realism-CloseUp) | 1.0 |
| H3 Character Swap | [Akatz Labs](https://huggingface.co/akatz-ai/MiniMax-H3-Character-Swap-LoRA) | 1.0 |
| Realism People | [Lovis Odin — fal](https://huggingface.co/fal/MiniMax-H3-Realism-People-LoRA) | 1.0 |
| Head Swap v1.0 r32 | [Alissonerdx / Alisson Anjos](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/blob/main/docs/head-swap.md) | 0.2 |
| VFX Edit v1.0 r128 | [Alissonerdx / Alisson Anjos](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/blob/main/docs/vfx-edit.md) | 0.2 |

Modelo base: [MiniMax H3 — MiniMaxAI](https://huggingface.co/MiniMaxAI/MiniMax-H3). Use na pasta de LoRAs com força **1.0**. Mistura fontes FL2VA e REF2VA; o nome não garante troca de fundo. A versão exata do Character Swap não foi confirmada (metadados dizem v2, deltas lembram v1.5). Estrutura validada, **ainda não testada em geração**. Valem as licenças dos modelos de origem; os créditos não implicam endosso dos autores.

---

## English

### The idea in one sentence
A large or long video is split into **overlapping regions** (spatial tiles × temporal windows). At every model call all regions are predicted and **blended into one canvas**, so there is **a single denoising trajectory**: no tile seams, no chained clips, and VRAM is one region's.

### Install
1. Copy the `bruxosdovfx-SyncTile` folder into `ComfyUI/custom_nodes/`. **Delete** `ComfyUI-SyncTile-H3` if present (old version).
2. Restart. The console prints `[bruxosdovfx • SyncTile] v5.4 carregado`.
3. Needs a ComfyUI with the native MiniMax H3 nodes. To write the video file: ffmpeg (on PATH, in `FFMPEG_PATH`, or `pip install imageio-ffmpeg`).

### Nodes (category `bruxosdovfx/SyncTile`)
| Node | What it does |
| --- | --- |
| **SyncTile Guider (H3)** | Drop-in for Basic Guider. Blends the regions at every model call. |
| **SyncTile Ref2VA Conditioning (H3)** | Reference to Video per region: slices the reference video per window, crops it per tile, puts frame guides in the right window. |
| **SyncTile I2V Conditioning (H3)** | Image to Video (first/last frame) per region. No image = text to video. |
| **SyncTile Stream Decode (H3)** | Decodes block by block straight into a file (h265 10-bit, h264, ProRes) without filling RAM. Optional IMAGE output for Save Video Pro. |

### The workflow (long Character/Background Swap, v16)
1. **Inputs:** source video in Load Video Pro (**force 24 fps**, H3 runs at 24 fps), reference photo and prompt.
2. **Stage 1 (~0.5 MP):** SyncTile Ref2VA Conditioning + Guider with tile 4096 (= no spatial split) and **124-frame windows**, overlap 39. 4 turbo steps.
3. **3D latent upscaler (LBH):** enlarges the latent to ~6–8 MP without decoding.
4. **Stage 2 (4K refine):** SyncTile with 1472×896 tiles × 124-frame windows. Sigmas `0.878, 0.8, 0.6316, 0` (final steps only: fixes texture, keeps composition).
5. **Stream Decode:** writes the file and sends IMAGE to 🧙 Save Video Pro.
6. **Frame guides (optional):** source-video stills already showing the result, anchored at frames (e.g. `1, 100, 220, 340, 460`). They hold the background/character through the whole video.

### What to tune
- **Prompt:** say what holds "in every frame" (each window reads the prompt on its own).
- **window_frames** (124; 107/90 if out of VRAM) and **window_overlap_frames** (39; 56/73 for seams or flicker). Same value on both conditioning nodes.
- **Refine strength:** stage-2 sigmas. More faithful, less detail: `0.8, 0.6316, 0`.
- **use_refine_seed / refine_seed:** try another refine without redoing stage 1.
- **tile_conditioning_detail + detail_below_sigma:** structure → detail switch in the final steps (0.85 = balanced).
- **Output:** codec, crf (lower = better), image_output (full/half/off).

### Don't touch (unless you know why)
Tile 4096 in stage 1 (means "no tiles"), min_overlap 16, sync_mode "per model call", cfg 1.0 (turbo model), the 4 stage-1 steps, fps 24, width/height/length on the SyncTile nodes (they come from the latent).

### Common problems
- **Background reverts to the original mid-video:** more explicit prompt, overlap 56/73 and a frame guide every ~4–5 s.
- **Repeated character at 4K:** lighter stage-2 sigmas and `ref_video_mode = crop`.
- **Sped-up motion / audio out of sync:** the source video is not 24 fps.
- **ffmpeg error / BrokenPipe:** the node shows ffmpeg's message; without libx265 it writes h264 by itself.
- **"unexpected keyword argument":** old version installed; delete the old folder and restart.

### Background Replace v3 LoRA (summary)
Experimental merge of **five LoRAs by other authors** for MiniMax H3 (not an original training). File `Background Replace v3.safetensors`, BF16, ~1.91 GB, rank-concatenation merge (no SVD); no metadata (credits live in this README). Components and weights: Facial Realism CloseUp — prithivMLmods (1.0); H3 Character Swap — Akatz Labs (1.0); Realism People — Lovis Odin / fal (1.0); Head Swap v1.0 r32 — Alissonerdx / Alisson Anjos (0.2); VFX Edit v1.0 r128 — Alissonerdx / Alisson Anjos (0.2). Links in the table in the Portuguese section. Base model: [MiniMax H3 — MiniMaxAI](https://huggingface.co/MiniMaxAI/MiniMax-H3). Load from your LoRA folder at strength **1.0**. It mixes FL2VA and REF2VA sources; the name does not guarantee background replacement. The exact Character Swap version is unconfirmed (metadata says v2, deltas resemble v1.5). Structure validated, **not yet tested in generation**. The source models' licenses apply; credits do not imply the authors endorse the merge.

---

## 中文

### 一句话原理
把大尺寸或长时长的视频切成**相互重叠的区域**（空间图块 × 时间窗口）。每次调用模型时，所有区域都会被预测并**融合到同一张画布上**，因此只有**一条去噪轨迹**：没有图块接缝，不拼接片段，显存只占一个区域。

### 安装
1. 把 `bruxosdovfx-SyncTile` 文件夹复制到 `ComfyUI/custom_nodes/`。如有旧版 `ComfyUI-SyncTile-H3`，请**删除**。
2. 重启。控制台显示 `[bruxosdovfx • SyncTile] v5.4 carregado`。
3. 需要带有原生 MiniMax H3 节点的 ComfyUI。写出视频文件需要 ffmpeg（在 PATH 中、设置 `FFMPEG_PATH`，或 `pip install imageio-ffmpeg`）。

### 节点（分类 `bruxosdovfx/SyncTile`）
| 节点 | 作用 |
| --- | --- |
| **SyncTile Guider (H3)** | 替代 Basic Guider，每次调用模型时融合各区域。 |
| **SyncTile Ref2VA Conditioning (H3)** | 逐区域的 Reference to Video：参考视频按窗口切片、按图块裁切，帧引导放进对应窗口。 |
| **SyncTile I2V Conditioning (H3)** | 逐区域的图生视频（首帧/尾帧）。不接图像 = 文生视频。 |
| **SyncTile Stream Decode (H3)** | 逐块解码并直接写入文件（h265 10-bit、h264、ProRes），不占满内存。可选 IMAGE 输出给 Save Video Pro。 |

### 工作流（长视频人物/背景替换，v16）
1. **输入：** 在 Load Video Pro 中加载源视频（**强制 24 fps**，H3 为 24 fps）、参考照片和提示词。
2. **第一阶段（约 0.5 MP）：** SyncTile Ref2VA Conditioning + Guider，图块 4096（= 不做空间切分），**窗口 124 帧**，重叠 39。Turbo 模型 4 步。
3. **3D 潜空间放大（LBH）：** 不解码，直接把潜变量放大到约 6–8 MP。
4. **第二阶段（4K 精修）：** SyncTile，图块 1472×896 × 124 帧窗口。Sigma `0.878, 0.8, 0.6316, 0`（只跑最后几步：修正纹理，保持构图）。
5. **Stream Decode：** 写出文件，并把 IMAGE 发给 🧙 Save Video Pro。
6. **帧引导（可选）：** 从源视频中截取、已呈现目标效果的静帧，锚定到指定帧（例如 `1, 100, 220, 340, 460`），可在整段视频中保持背景/人物一致。

### 可调整的参数
- **提示词：** 写明“每一帧都”要满足的内容（每个窗口单独读取提示词）。
- **window_frames**（124；显存不足用 107/90）和 **window_overlap_frames**（39；有接缝或闪烁用 56/73）。两个 Conditioning 节点设为相同值。
- **精修强度：** 第二阶段的 sigma。更忠实、细节更少：`0.8, 0.6316, 0`。
- **use_refine_seed / refine_seed：** 不重跑第一阶段即可尝试另一种精修。
- **tile_conditioning_detail + detail_below_sigma：** 在最后几步从结构切换到细节（0.85 = 平衡）。
- **输出：** codec、crf（越小越好）、image_output（full/half/off）。

### 不要修改（除非清楚原因）
第一阶段的图块 4096（表示“不切图块”）、min_overlap 16、sync_mode "per model call"、cfg 1.0（turbo 模型）、第一阶段的 4 步、fps 24、SyncTile 节点上的 width/height/length（由潜变量决定）。

### 常见问题
- **视频中途背景变回原样：** 提示词写得更明确，重叠设为 56/73，每 4–5 秒加一张帧引导。
- **4K 下人物重复：** 第二阶段用更轻的 sigma，并设 `ref_video_mode = crop`。
- **动作变快 / 音画不同步：** 源视频不是 24 fps。
- **ffmpeg 报错 / BrokenPipe：** 节点会显示 ffmpeg 的报错信息；缺少 libx265 时会自动改用 h264。
- **"unexpected keyword argument"：** 安装的是旧版；删除旧文件夹后重启。

### Background Replace v3 LoRA（摘要）
由**其他作者的五个 LoRA** 合并而成的实验性 MiniMax H3 LoRA（并非从零训练）。文件 `Background Replace v3.safetensors`，BF16，约 1.91 GB，按秩拼接合并（无 SVD）；文件不含元数据（署名见本 README）。组成与权重：Facial Realism CloseUp — prithivMLmods（1.0）；H3 Character Swap — Akatz Labs（1.0）；Realism People — Lovis Odin / fal（1.0）；Head Swap v1.0 r32 — Alissonerdx / Alisson Anjos（0.2）；VFX Edit v1.0 r128 — Alissonerdx / Alisson Anjos（0.2）。链接见葡萄牙语部分的表格。基础模型：[MiniMax H3 — MiniMaxAI](https://huggingface.co/MiniMaxAI/MiniMax-H3)。放入 LoRA 文件夹，强度 **1.0**。它混合了 FL2VA 与 REF2VA 来源；名称并不保证能替换背景。Character Swap 的具体版本未确认（元数据为 v2，差值接近 v1.5）。结构已校验，**尚未在生成中测试**。须遵守各源模型的许可；署名不代表原作者认可此合并。

---

## Modelos / Models / 模型

| Pasta / Folder / 文件夹 | Arquivo / File / 文件 |
| --- | --- |
| `models/diffusion_models/` | [minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot](https://huggingface.co/MATLOWAI/minimax-h3-fused-turbo-int8-convrot/blob/main/diffusion_models/minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors) (21 GB, turbo 4 steps) |
| `models/text_encoders/` | [qwen3vl_32b_minimax_h3_int8_convrot](https://huggingface.co/Comfy-Org/MiniMax-H3/blob/main/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors) (27 GB; nvfp4_awq 15.7 GB) |
| `models/vae/` | [minimax_h3_lynnreal_light_vae_int8_convrot](https://huggingface.co/Kijai/MiniMax-H3-experimental/blob/main/minimax_h3_lynnreal_light_vae_int8_convrot.safetensors) or [Comfy-Org video VAE](https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/vae) |
| `models/vae/` | [minimax_h3_audio_vae_fp32](https://huggingface.co/Comfy-Org/MiniMax-H3/blob/main/vae/minimax_h3_audio_vae_fp32.safetensors) |
| `models/latent_upscale_models/` | [minimax_h3_latent_upscaler_3d_conv_v1](https://huggingface.co/LBH-123-AI/Minimax_h3_latent_Upscaler/tree/main/minimax_h3_latent_upscaler_3d_conv_v1) + node [Comfyui_Minimax_h3_latent_Upscaler](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler) |

---

## Referências / References / 参考文献

Ideias que combinamos (nenhum código copiado, exceto onde indicado) · Ideas we combined (no code copied unless stated) · 我们结合的思路（除注明外未复制代码）：

| Técnica / Technique / 技术 | Fonte / Source / 来源 | Onde entra / Where it is used / 用于 |
| --- | --- | --- |
| Fusão de caminhos de difusão em regiões sobrepostas · Fusing overlapping diffusion paths · 重叠区域扩散路径融合 | Bar-Tal, Yariv, Lipman, Dekel. *MultiDiffusion: Fusing Diffusion Paths for Controlled Image Generation.* ICML 2023. [arXiv:2302.08113](https://arxiv.org/abs/2302.08113) | Base matemática da mistura por região · Math behind the per-region blend · 区域融合的数学基础 |
| SyncTile para MiniMax H3 (tiles 1472×896, refino 4K) · SyncTile for MiniMax H3 · MiniMax H3 的 SyncTile | Tural, A. (2026). [alaintural/synctile-h3](https://github.com/alaintural/synctile-h3) (MIT) · [pixedi.com/lab/minimax-h3-4k-synctile](https://pixedi.com/lab/minimax-h3-4k-synctile) · Zenodo DOI [10.5281/zenodo.23196934](https://doi.org/10.5281/zenodo.23196934) | Modo "SyncTile original", tamanhos de tile, refino nos passos finais · tile sizes, final-step refine · 图块尺寸、末步精修 |
| Janelas de contexto no tempo com ruído compartilhado · Temporal context windows with shared noise · 共享噪声的时间上下文窗口 | Qiu et al. *FreeNoise: Tuning-Free Longer Video Diffusion via Noise Rescheduling.* ICLR 2024. [arXiv:2310.15169](https://arxiv.org/abs/2310.15169) · [DrakenZA/Comfyui-H3-DrakenNodes](https://github.com/DrakenZA/Comfyui-H3-DrakenNodes) (joint context windows for H3) | Janelas de 124 frames, ruído único da tela · 124-frame windows, one canvas noise · 124 帧窗口、统一画布噪声 |
| Divisão espaço + tempo para upscale do H3 · Spatial + temporal chunking for H3 upscaling · H3 放大的时空分块 | [bbaudio-2025/Comfyui-MMH3-UltimateUpscale](https://github.com/bbaudio-2025/Comfyui-MMH3-UltimateUpscale) | Regiões tile × janela · tile × window regions · 图块 × 窗口区域 |
| Encadear clipes (comparação) · Clip chaining (comparison) · 片段拼接（对比） | [mark9009/ComfyUI-H3-LongTake](https://github.com/mark9009/ComfyUI-H3-LongTake) e outros packs de vídeo longo · and other long-video packs · 及其他长视频节点包 | Abordagem que substituímos por uma trajetória só · approach replaced by one trajectory · 被单一轨迹取代的方法 |
| Latent upscaler 3D · 3D latent upscaler · 3D 潜空间放大器 | [LBH-123-AI](https://github.com/LBH-123-AI/Comfyui_Minimax_h3_latent_Upscaler) | Entre os estágios 1 e 2 · between stages 1 and 2 · 第一、二阶段之间 |
| Modelo fused turbo · Fused turbo model · 融合 turbo 模型 | [MATLOWAI](https://huggingface.co/MATLOWAI/minimax-h3-fused-turbo-int8-convrot) (ref2va delta + lightx2v turbo + Mystic) | Os dois estágios · both stages · 两个阶段 |
| VAE leve · Light VAE · 轻量 VAE | [Kijai/MiniMax-H3-experimental](https://huggingface.co/Kijai/MiniMax-H3-experimental) | Encode/decode |
| MiniMax H3 + nodes nativos · native nodes · 原生节点 | [MiniMaxAI](https://huggingface.co/MiniMaxAI/MiniMax-H3) · [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3) · [ComfyUI](https://github.com/comfyanonymous/ComfyUI) | Tudo · everything · 全部 |
| LoRAs da mescla Background Replace v3 · LoRAs in the merge · 合并所用 LoRA | prithivMLmods, Akatz Labs, Lovis Odin / fal, Alissonerdx / Alisson Anjos (ver acima · see above · 见上文) | LoRA opcional · optional LoRA · 可选 LoRA |

O que é novo neste pack · What is new in this pack · 本节点包的新内容：mistura dentro de cada chamada do modelo (qualquer sampler) · blending inside every model call (any sampler) · 在每次模型调用内融合（任意采样器）；regiões espaço × tempo numa trajetória · space × time regions in one trajectory · 单一轨迹中的时空区域；conditioning por região com vídeo de referência fatiado/recortado e frames-guia por janela · per-region conditioning with sliced/cropped reference video and per-window frame guides · 逐区域条件（参考视频切片/裁切、按窗口放置帧引导）；troca estrutura → detalhe por sigma · structure → detail switch by sigma · 按 sigma 切换结构 → 细节；decode em streaming para arquivo · streaming decode to file · 流式解码写入文件。
