# bruxosdovfx • SyncTile (MiniMax H3) — v6.2

**[Português](#português) · [English](#english) · [中文](#中文) · [Referências / References / 参考文献](#referências--references--参考文献)**

SyncTile: [NyckM/Bruxosdovfx-SyncTile-MiniMax-H3-v5.4](https://github.com/NyckM/Bruxosdovfx-SyncTile-MiniMax-H3-v5.4) · Media IO: [NyckM/Video-Util-ComfYUI](https://github.com/NyckM/Video-Util-ComfYUI) · LoRA: [Background Replace v3](https://huggingface.co/NyckM/Background_Replace_Minimax_H3)

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
**Jeito fácil (Windows):** coloque `bruxosdovfx_EasyInstall_MiniMaxH3.bat` na pasta do ComfyUI (ou do ComfyUI-Easy-Install) e dê dois cliques. Ele acha as pastas, instala os custom nodes (SyncTile, Media IO, Latent Upscaler, Easy-Use) e baixa modelos e LoRAs; o que já existir com o mesmo nome é ignorado, e downloads interrompidos continuam de onde pararam. Opções no topo do arquivo: text encoder int8/nvfp4, VAE light/full, LoRAs opcionais, atualizar nodes.

**Manual:**
1. `git clone https://github.com/NyckM/Bruxosdovfx-SyncTile-MiniMax-H3-v5.4` dentro de `ComfyUI/custom_nodes/` (ou copie a pasta `bruxosdovfx-SyncTile`). **Apague** `ComfyUI-SyncTile-H3` se existir (versão antiga).
2. Reinicie. O console mostra `[bruxosdovfx • SyncTile] v5.5 carregado`.
3. Instale também o pack **bruxosdovfx Media IO** — [https://github.com/NyckM/Video-Util-ComfYUI](https://github.com/NyckM/Video-Util-ComfYUI) (Load Video Pro, Load Image, Save Video Pro — veja abaixo). Precisa de um ComfyUI com os nodes nativos do MiniMax H3. Para gravar o arquivo de vídeo: ffmpeg (no PATH, em `FFMPEG_PATH`, ou `pip install imageio-ffmpeg`).

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
- **temporal_mode = carry previous frames** (v5.5, no SyncTile Guider): as janelas rodam em sequência e o começo de cada uma fica preso aos últimos `carry_frames` (21) frames prontos da anterior. Acaba com o fantasma/dupla exposição nas transições e segura melhor o movimento de câmera.
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

### LoRAs do workflow
Ficam em `Models` → duas pilhas **easy loraStack**, as duas **desligadas** por padrão (o modelo fused já tem o turbo de 4 passos). Ligue o toggle da pilha para usar.

| Pilha | LoRA | Força | Fonte | Para que serve |
| --- | --- | --- | --- | --- |
| 1 | `minimax_h3_pdmd_4step_lora_avg_rank_57_bf16` | 1.0 | [Kijai/MiniMax-H3-experimental (loras)](https://huggingface.co/Kijai/MiniMax-H3-experimental/tree/main/loras) — conversão do [PDMD 4 passos](https://huggingface.co/pdmd2026/pdmd_4NFE_lora) | Distilação em 4 passos (PDMD). Alternativa ao turbo do modelo fused, com menos saturação/textura artificial. Use com um modelo **não** turbo. |
| 1 | `Background Replace v3` | 1.0 | [NyckM/Background_Replace_Minimax_H3](https://huggingface.co/NyckM/Background_Replace_Minimax_H3) (mescla bruxosdovfx, abaixo) | Troca de fundo/personagem. |
| 2 | `minimax_h3_lms_v1.0_r64` | 0.3 | [Alissonerdx / Minimax-H3-ComfyUI](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/blob/main/loras/minimax_h3_lms_v1.0_r64.safetensors) | Nitidez/detalhe guiado pelo vídeo fonte alinhado. Usa uma legenda fixa de "enhancement" como gatilho. |

### Nodes Bruxos Media IO (necessários no workflow)
O workflow também usa o pack **bruxosdovfx Media IO** (nodes 🧙 de entrada e saída): [https://github.com/NyckM/Video-Util-ComfYUI](https://github.com/NyckM/Video-Util-ComfYUI). Instale-o junto com o SyncTile (`git clone` em `custom_nodes` + `pip install -r requirements.txt`, ou pelo .bat).

| Node | No workflow v16 | O que faz |
| --- | --- | --- |
| **🧙 Load Video Pro** | Sim (vídeo fonte) | Carrega o vídeo com `force_rate` (use **24**), `frame_load_cap` (0 = todos), `skip_first_frames`, `select_every_nth`, crop/fit, giro/flip e `pad_grade` **"H3 17n+5"** (ajusta o nº de frames à grade do H3). Saídas: images, video, audio, fps, frame_count, width, height, video_info. Opções de cache em SSD e de importar mais bits. |
| **🧙 Load Image** | Sim (foto de referência / guia 1) | Carrega imagem com fit/crop, aspecto, giro e flip. Saídas: image, mask, width, height. |
| **🧙 Save Video Pro** | Sim (recebe IMAGE do Stream Decode) | Grava mp4/h264 e outros formatos (inclui EXR), crf/preset, espaço de cor, `start_frame` (1001), versão automática no nome, seed no nome, burn-in, grão de filme (ex.: Kodak 5207), review mp4 e JSON lateral com os dados do render. |
| **Load Video** | Não | Versão simples do carregador de vídeo. |
| **Load EXR** | Não | Lê EXR e sequências EXR com gestão de cor OCIO/ACES (ACEScg → sRGB), exposição, camadas e janela de dados. |
| **Hold to Seconds** | Não | Segura/estende frames até uma duração em segundos (ou corta o excesso). |
| **H3 Frames** | Não | Converte duração/nº de frames para a grade do H3 (17n+5), com arredondamento e ajuste (ex.: pingpong). |

### LoRA Background Replace v3 (resumo)
Mescla experimental de **cinco LoRAs de outros autores** para MiniMax H3 (não é treino original). Download: [Background Replace v3.safetensors](https://huggingface.co/NyckM/Background_Replace_Minimax_H3/blob/main/Background%20Replace%20v3.safetensors) → `models/loras/minimax/`. BF16, ~1,91 GB, mescla por concatenação de ranks (sem SVD); sem metadados (os créditos ficam neste README).

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
**Easy way (Windows):** put `bruxosdovfx_EasyInstall_MiniMaxH3.bat` in the ComfyUI folder (or the ComfyUI-Easy-Install folder) and double-click it. It finds the folders, installs the custom nodes (SyncTile, Media IO, Latent Upscaler, Easy-Use) and downloads models and LoRAs; anything already present with the same name is skipped, and interrupted downloads resume. Options at the top of the file: text encoder int8/nvfp4, VAE light/full, optional LoRAs, update nodes.

**Manual:**
1. `git clone https://github.com/NyckM/Bruxosdovfx-SyncTile-MiniMax-H3-v5.4` inside `ComfyUI/custom_nodes/` (or copy the `bruxosdovfx-SyncTile` folder). **Delete** `ComfyUI-SyncTile-H3` if present (old version).
2. Restart. The console prints `[bruxosdovfx • SyncTile] v5.5 carregado`.
3. Also install the **bruxosdovfx Media IO** pack — [https://github.com/NyckM/Video-Util-ComfYUI](https://github.com/NyckM/Video-Util-ComfYUI) (Load Video Pro, Load Image, Save Video Pro — see below). Needs a ComfyUI with the native MiniMax H3 nodes. To write the video file: ffmpeg (on PATH, in `FFMPEG_PATH`, or `pip install imageio-ffmpeg`).

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
- **temporal_mode = carry previous frames** (v5.5, on SyncTile Guider): windows run in sequence and the start of each one is locked to the last `carry_frames` (21) finished frames of the previous one. Removes ghosting/double exposure at the joins and holds camera motion better.
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

### Workflow LoRAs
They live in `Models` → two **easy loraStack** nodes, both **off** by default (the fused model already includes 4-step turbo). Flip the stack toggle to use them.

| Stack | LoRA | Strength | Source | What it is for |
| --- | --- | --- | --- | --- |
| 1 | `minimax_h3_pdmd_4step_lora_avg_rank_57_bf16` | 1.0 | [Kijai/MiniMax-H3-experimental (loras)](https://huggingface.co/Kijai/MiniMax-H3-experimental/tree/main/loras) — conversion of [PDMD 4-step](https://huggingface.co/pdmd2026/pdmd_4NFE_lora) | 4-step distillation (PDMD). Alternative to the fused model's turbo, with less oversaturation/artificial texture. Use with a **non**-turbo model. |
| 1 | `Background Replace v3` | 1.0 | [NyckM/Background_Replace_Minimax_H3](https://huggingface.co/NyckM/Background_Replace_Minimax_H3) (bruxosdovfx merge, below) | Background/character replacement. |
| 2 | `minimax_h3_lms_v1.0_r64` | 0.3 | [Alissonerdx / Minimax-H3-ComfyUI](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/blob/main/loras/minimax_h3_lms_v1.0_r64.safetensors) | Sharpness/detail guided by the aligned source video. Uses a fixed "enhancement" caption as trigger. |

### Bruxos Media IO nodes (required by the workflow)
The workflow also uses the **bruxosdovfx Media IO** pack (🧙 input/output nodes): [https://github.com/NyckM/Video-Util-ComfYUI](https://github.com/NyckM/Video-Util-ComfYUI). Install it together with SyncTile (`git clone` into `custom_nodes` + `pip install -r requirements.txt`, or via the .bat).

| Node | In workflow v16 | What it does |
| --- | --- | --- |
| **🧙 Load Video Pro** | Yes (source video) | Loads the video with `force_rate` (use **24**), `frame_load_cap` (0 = all), `skip_first_frames`, `select_every_nth`, crop/fit, rotate/flip and `pad_grade` **"H3 17n+5"** (fits the frame count to the H3 grid). Outputs: images, video, audio, fps, frame_count, width, height, video_info. SSD cache and higher-bit import options. |
| **🧙 Load Image** | Yes (reference photo / guide 1) | Loads an image with fit/crop, aspect, rotate and flip. Outputs: image, mask, width, height. |
| **🧙 Save Video Pro** | Yes (gets IMAGE from Stream Decode) | Writes mp4/h264 and other formats (EXR included), crf/preset, color space, `start_frame` (1001), auto-versioned names, seed in name, burn-in, film grain (e.g. Kodak 5207), review mp4 and a sidecar JSON with render data. |
| **Load Video** | No | Simple video loader. |
| **Load EXR** | No | Reads EXR files and sequences with OCIO/ACES color management (ACEScg → sRGB), exposure, layers and data window. |
| **Hold to Seconds** | No | Holds/extends frames to a duration in seconds (or cuts the excess). |
| **H3 Frames** | No | Converts duration/frame count to the H3 grid (17n+5), with rounding and fitting (e.g. pingpong). |

### Background Replace v3 LoRA (summary)
Experimental merge of **five LoRAs by other authors** for MiniMax H3 (not an original training). Download: [Background Replace v3.safetensors](https://huggingface.co/NyckM/Background_Replace_Minimax_H3/blob/main/Background%20Replace%20v3.safetensors) → `models/loras/minimax/`. BF16, ~1.91 GB, rank-concatenation merge (no SVD); no metadata (credits live in this README). Components and weights: Facial Realism CloseUp — prithivMLmods (1.0); H3 Character Swap — Akatz Labs (1.0); Realism People — Lovis Odin / fal (1.0); Head Swap v1.0 r32 — Alissonerdx / Alisson Anjos (0.2); VFX Edit v1.0 r128 — Alissonerdx / Alisson Anjos (0.2). Links in the table in the Portuguese section. Base model: [MiniMax H3 — MiniMaxAI](https://huggingface.co/MiniMaxAI/MiniMax-H3). Load from your LoRA folder at strength **1.0**. It mixes FL2VA and REF2VA sources; the name does not guarantee background replacement. The exact Character Swap version is unconfirmed (metadata says v2, deltas resemble v1.5). Structure validated, **not yet tested in generation**. The source models' licenses apply; credits do not imply the authors endorse the merge.

---

## 中文

### 一句话原理
把大尺寸或长时长的视频切成**相互重叠的区域**（空间图块 × 时间窗口）。每次调用模型时，所有区域都会被预测并**融合到同一张画布上**，因此只有**一条去噪轨迹**：没有图块接缝，不拼接片段，显存只占一个区域。

### 安装
**简便方式（Windows）：** 把 `bruxosdovfx_EasyInstall_MiniMaxH3.bat` 放到 ComfyUI 文件夹（或 ComfyUI-Easy-Install 文件夹）中并双击运行。它会自动找到目录，安装自定义节点（SyncTile、Media IO、Latent Upscaler、Easy-Use），并下载模型和 LoRA；同名文件已存在则跳过，下载中断可续传。文件顶部可设置：文本编码器 int8/nvfp4、VAE light/full、可选 LoRA、更新节点。

**手动安装：**
1. 在 `ComfyUI/custom_nodes/` 中执行 `git clone https://github.com/NyckM/Bruxosdovfx-SyncTile-MiniMax-H3-v5.4`（或复制 `bruxosdovfx-SyncTile` 文件夹）。如有旧版 `ComfyUI-SyncTile-H3`，请**删除**。
2. 重启。控制台显示 `[bruxosdovfx • SyncTile] v5.5 carregado`。
3. 另需安装 **bruxosdovfx Media IO** 节点包 —— [https://github.com/NyckM/Video-Util-ComfYUI](https://github.com/NyckM/Video-Util-ComfYUI)（Load Video Pro、Load Image、Save Video Pro，见下文）。需要带有原生 MiniMax H3 节点的 ComfyUI。写出视频文件需要 ffmpeg（在 PATH 中、设置 `FFMPEG_PATH`，或 `pip install imageio-ffmpeg`）。

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
- **temporal_mode = carry previous frames**（v5.5，SyncTile Guider）：窗口依次运行，每个窗口的开头锁定为上一个窗口已完成的最后 `carry_frames`（21）帧。消除衔接处的重影/双重曝光，更好地保持镜头运动。
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

### 工作流中的 LoRA
位于 `Models` → 两个 **easy loraStack** 节点，默认均**关闭**（融合模型已包含 4 步 turbo）。打开该组的开关即可使用。

| 组 | LoRA | 强度 | 来源 | 用途 |
| --- | --- | --- | --- | --- |
| 1 | `minimax_h3_pdmd_4step_lora_avg_rank_57_bf16` | 1.0 | [Kijai/MiniMax-H3-experimental (loras)](https://huggingface.co/Kijai/MiniMax-H3-experimental/tree/main/loras) —— [PDMD 4 步](https://huggingface.co/pdmd2026/pdmd_4NFE_lora) 的转换版 | 4 步蒸馏（PDMD）。可替代融合模型自带的 turbo，过饱和/假纹理更少。请配合**非** turbo 模型使用。 |
| 1 | `Background Replace v3` | 1.0 | [NyckM/Background_Replace_Minimax_H3](https://huggingface.co/NyckM/Background_Replace_Minimax_H3)（bruxosdovfx 合并，见下文） | 背景/人物替换。 |
| 2 | `minimax_h3_lms_v1.0_r64` | 0.3 | [Alissonerdx / Minimax-H3-ComfyUI](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/blob/main/loras/minimax_h3_lms_v1.0_r64.safetensors) | 以对齐的源视频为引导增强清晰度/细节。用固定的 "enhancement" 描述作为触发词。 |

### Bruxos Media IO 节点（工作流必需）
工作流还使用 **bruxosdovfx Media IO** 节点包（🧙 输入/输出节点）：[https://github.com/NyckM/Video-Util-ComfYUI](https://github.com/NyckM/Video-Util-ComfYUI)。请与 SyncTile 一起安装（在 `custom_nodes` 中 `git clone` 并 `pip install -r requirements.txt`，或使用 .bat）。

| 节点 | v16 工作流中 | 作用 |
| --- | --- | --- |
| **🧙 Load Video Pro** | 是（源视频） | 加载视频：`force_rate`（请用 **24**）、`frame_load_cap`（0 = 全部）、`skip_first_frames`、`select_every_nth`、裁切/适配、旋转/翻转，以及 `pad_grade` **"H3 17n+5"**（把帧数对齐到 H3 网格）。输出：images、video、audio、fps、frame_count、width、height、video_info。支持 SSD 缓存和高位深导入。 |
| **🧙 Load Image** | 是（参考照片 / 引导 1） | 加载图像，支持适配/裁切、宽高比、旋转和翻转。输出：image、mask、width、height。 |
| **🧙 Save Video Pro** | 是（接收 Stream Decode 的 IMAGE） | 写出 mp4/h264 及其他格式（含 EXR）、crf/preset、色彩空间、`start_frame`（1001）、文件名自动版本号、文件名含种子、烧录信息、胶片颗粒（如 Kodak 5207）、审片 mp4，以及记录渲染数据的 JSON 附属文件。 |
| **Load Video** | 否 | 简易视频加载器。 |
| **Load EXR** | 否 | 读取 EXR 文件和序列，支持 OCIO/ACES 色彩管理（ACEScg → sRGB）、曝光、图层和数据窗口。 |
| **Hold to Seconds** | 否 | 把帧保持/延长到指定秒数（或裁掉多余部分）。 |
| **H3 Frames** | 否 | 把时长/帧数换算到 H3 网格（17n+5），支持取整和补齐方式（如 pingpong）。 |

### Background Replace v3 LoRA（摘要）
由**其他作者的五个 LoRA** 合并而成的实验性 MiniMax H3 LoRA（并非从零训练）。下载：[Background Replace v3.safetensors](https://huggingface.co/NyckM/Background_Replace_Minimax_H3/blob/main/Background%20Replace%20v3.safetensors) → `models/loras/minimax/`。BF16，约 1.91 GB，按秩拼接合并（无 SVD）；文件不含元数据（署名见本 README）。组成与权重：Facial Realism CloseUp — prithivMLmods（1.0）；H3 Character Swap — Akatz Labs（1.0）；Realism People — Lovis Odin / fal（1.0）；Head Swap v1.0 r32 — Alissonerdx / Alisson Anjos（0.2）；VFX Edit v1.0 r128 — Alissonerdx / Alisson Anjos（0.2）。链接见葡萄牙语部分的表格。基础模型：[MiniMax H3 — MiniMaxAI](https://huggingface.co/MiniMaxAI/MiniMax-H3)。放入 LoRA 文件夹，强度 **1.0**。它混合了 FL2VA 与 REF2VA 来源；名称并不保证能替换背景。Character Swap 的具体版本未确认（元数据为 v2，差值接近 v1.5）。结构已校验，**尚未在生成中测试**。须遵守各源模型的许可；署名不代表原作者认可此合并。

---

## Rostos pequenos / Small faces / 小脸 (SAM 3.1) — v5.9

**PT:** Dois nodes novos, `bruxosdovfx • Face Crop (SAM 3.1)` e `bruxosdovfx • Face Stitch` (baseados no Tracked Crop/Stitch e no FaceStitchUpscale da Bruxos). O SAM 3.1 nativo do ComfyUI (`Run SAM3 Video Track` → `SAM3 Track to Mask`, prompt `face`) segue o rosto; o Face Crop amplia o rosto para um quadrado de 768 px em todos os frames; o H3 refaz só o rosto com uma **referência de rosto** (`<Picture 1>`) e o áudio para a boca; o Face Stitch cola de volta só a silhueta do rosto, com cor casada. Modelo: [`sam3.1_multiplex_fp16.safetensors`](https://huggingface.co/Comfy-Org/sam3.1) em `models/checkpoints/`. Workflow: `minimaxH3BackgroundSwap_v22_rosto_SAM31.json`.

**EN:** Two new nodes, `bruxosdovfx • Face Crop (SAM 3.1)` and `bruxosdovfx • Face Stitch` (based on the Bruxos Tracked Crop/Stitch and FaceStitchUpscale). ComfyUI's native SAM 3.1 (`Run SAM3 Video Track` → `SAM3 Track to Mask`, prompt `face`) tracks the face; Face Crop zooms it to a 768 px square in every frame; H3 re-renders only the face with a **face reference** (`<Picture 1>`) and the audio for the mouth; Face Stitch pastes back only the face silhouette, colour matched. Model: [`sam3.1_multiplex_fp16.safetensors`](https://huggingface.co/Comfy-Org/sam3.1) in `models/checkpoints/`.

**中文：** 新增两个节点 `bruxosdovfx • Face Crop (SAM 3.1)` 和 `bruxosdovfx • Face Stitch`（基于 Bruxos 的 Tracked Crop/Stitch 与 FaceStitchUpscale）。ComfyUI 原生 SAM 3.1（`Run SAM3 Video Track` → `SAM3 Track to Mask`，提示词 `face`）跟踪人脸；Face Crop 在每一帧把人脸放大成 768 像素的正方形；H3 只重绘人脸，使用**人脸参考**（`<Picture 1>`）和音频驱动口型；Face Stitch 只贴回人脸轮廓并匹配颜色。模型：[`sam3.1_multiplex_fp16.safetensors`](https://huggingface.co/Comfy-Org/sam3.1)，放在 `models/checkpoints/`。

## Fundo com o movimento real da câmera / Background with the real camera motion / 跟随真实镜头运动的背景 (EXPERIMENTAL) — v5.9

**PT:** `bruxosdovfx • Background Plate (camera match, experimental)` mede o movimento da câmera só no fundo do vídeo fonte (a pessoa sai pela máscara do SAM 3.1 `person`), aplica o mesmo movimento (pan, tilt, zoom, rotação) na imagem do novo fundo e compõe a pessoa por cima. Esse composite entra como `<Video 1>`, então o fundo gerado segue a câmera real. Só 2D, sem paralaxe de profundidade. Workflow: `minimaxH3BackgroundSwap_v23_fundoCamera_EXPERIMENTAL.json`.

**EN:** `bruxosdovfx • Background Plate (camera match, experimental)` measures the camera motion on the source background only (the person is removed with the SAM 3.1 `person` mask), applies the same motion (pan, tilt, zoom, roll) to the new background image and composites the person on top. That composite goes in as `<Video 1>`, so the generated background follows the real camera. 2D only, no depth parallax.

**中文：** `bruxosdovfx • Background Plate (camera match, experimental)` 只在源视频背景上测量镜头运动（用 SAM 3.1 `person` 遮罩去掉人物），把同样的运动（平移、俯仰、缩放、旋转）应用到新背景图片，并把人物合成在上面。合成结果作为 `<Video 1>`，生成的背景因此跟随真实镜头。仅 2D，无深度视差。

## Fundo 3D / 3D background / 3D 背景 (MoGe, EXPERIMENTAL) — v5.9

**PT:** `bruxosdovfx • Background Plate 3D (MoGe, experimental)`, na linha do [CrossView-Warp](https://huggingface.co/Cseti/MiniMax-H3_Ref2VA-LoRA-CrossView-Warp_v1): o MoGe nativo do ComfyUI dá a profundidade do vídeo fonte e da foto do novo fundo; pontos do fundo rastreados viram 3D e dão a rotação e a translação reais da câmera (PnP com keyframes, sem drift acumulado); a foto vira uma malha com profundidade renderizada dessa câmera, com paralaxe. Funciona com os LoRAs e modelos que você já usa (sem LoRA obrigatório). Modelo: [`moge_2_vitl_normal_fp16.safetensors`](https://huggingface.co/Comfy-Org/MoGe) em `models/geometry_estimation/`. Workflow: `minimaxH3BackgroundSwap_v24_fundo3D_MoGe_EXPERIMENTAL.json`.

**EN:** `bruxosdovfx • Background Plate 3D (MoGe, experimental)`, in the CrossView-Warp spirit: ComfyUI's native MoGe gives the depth of the source video and of the new background photo; tracked background points are lifted to 3D and give the real camera rotation and translation (keyframe PnP, no accumulated drift); the photo becomes a depth mesh rendered from that camera, with parallax. Works with the LoRAs and models you already use (no LoRA required).

**中文：** `bruxosdovfx • Background Plate 3D (MoGe, experimental)`，思路同 CrossView-Warp：ComfyUI 原生 MoGe 给出源视频和新背景照片的深度；跟踪的背景点提升为 3D，求出真实镜头的旋转和平移（关键帧 PnP，无累积漂移）；照片变成带深度的网格并从该镜头渲染，产生视差。可与现有的 LoRA 和模型一起使用（无需额外 LoRA）。

## Novidades / What's new / 新功能 (v5.6 – v6.2)

**PT**
- **Saída VIDEO no Stream Decode + DLSS 5 como pós-processo (v6.2).** O Stream Decode agora também entrega o arquivo gravado como `VIDEO` (lido do disco). Ligado no [RH DLSS5 Enhance](https://github.com/RH-RunningHub/ComfyUI-RH-DLSS5), ele processa em blocos e grava em streaming: 600 frames 2K → 4K sem estourar a RAM. Workflows `minimaxH3_v30_Regenerate2K_SyncTile_DLSS5.json` e `minimaxH3_v30b_HIBRIDO_Regenerate2K_DLSS5.json`.
- **Open-H3 Regenerate 2K no SyncTile (v29).** Refino em 3 passos (0.909375 / 0.857143 / 0.666667 / 0) com o modelo fl2va + LoRA Regenerate, em tiles × janelas de 124 frames; TARA desligado.
- **Atenção temporal à referência — TARA-H3 (v6.0).** Método de **Alisson Anjos** ([relatório técnico TARA-H3 v0.1.2, 2026](https://github.com/alisson-anjos/ai-toolkit/tree/tara-h3-v0.1.2/research/tara-h3)). O relógio (RoPE temporal) do vídeo de referência `<Video 1>` é alinhado com o vídeo gerado e cada frame gerado é levemente penalizado ao olhar frames distantes da referência: movimento, boca e ritmo seguem a referência com mais precisão. No SyncTile Guider: `temporal_reference = true` (+ `tara_strength`, `tara_window_seconds`, `tara_falloff_seconds`, `tara_max_penalty`, `tara_motion_video`). A nossa versão (`tara.py`) foi escrita a partir do relatório, sem copiar código dos repositórios dele; funciona por tile/janela e aceita frames-guia (pula as linhas de keyframe), então combina com o modo "frame anterior como guia". O node original dele é o [ComfyUI-BFSNodes](https://github.com/alisson-anjos/ComfyUI-BFSNodes/tree/feat/h3-native-temporal) (GPL-3.0) — use um ou outro, não os dois. Workflows: `minimaxH3_v26_VID2VID_TARA_FastH3.json`, `..._T2V_...`, `..._I2V_...`.
- **`guide from previous window (latent clip)` (v6.1):** os frames prontos da janela anterior entram direto em latent como clipe-guia (sem VAE, levando o movimento) — ideia do [mo-akkakk](https://github.com/mo-akkakk/ComfyUI-MiniMaxH3-TemporalWindow-SpatialTiles). TARA mais rápido (kernels sem máscara).
- **`temporal_mode = guide from previous window (1 frame)` (v5.6).** Janelas em sequência; o frame pronto onde cada janela começa vira o frame-guia da próxima, com troca seca. O modo carry também passou a usar troca seca (sem dupla exposição).
- **Face Crop / Face Stitch com SAM 3.1 (v5.7)** para refinar rostos pequenos com uma referência de rosto (baseados no Tracked Crop/Stitch e no FaceStitchUpscale da Bruxos).
- **Background Plate 2D e 3D — experimental (v5.8/v5.9).** Mede o movimento real da câmera no fundo do vídeo fonte e aplica na foto do novo fundo; a versão 3D usa a profundidade do MoGe e renderiza com paralaxe (ideia do [CrossView-Warp](https://huggingface.co/Cseti/MiniMax-H3_Ref2VA-LoRA-CrossView-Warp_v1) do Cseti e do [Meridian](https://huggingface.co/Viggle/Meridian) da Viggle, sem os LoRAs deles).

**EN**
- **Stream Decode VIDEO output + DLSS 5 post-process (v6.2).** Stream Decode also outputs the written file as a file-backed `VIDEO`; [RH DLSS5 Enhance](https://github.com/RH-RunningHub/ComfyUI-RH-DLSS5) streams it in chunks (600 frames 2K → 4K without filling RAM). Open-H3 Regenerate 2K inside SyncTile (v29/v30).
- **Temporal reference attention — TARA-H3 (v6.0).** Method by **Alisson Anjos** ([TARA-H3 technical report v0.1.2, 2026](https://github.com/alisson-anjos/ai-toolkit/tree/tara-h3-v0.1.2/research/tara-h3)). The reference video's temporal RoPE clock is aligned with the output and generated frames are softly penalised for attending to distant reference frames, so motion, mouth and timing follow the reference more closely. On SyncTile Guider: `temporal_reference = true` (+ `tara_*` settings). Our `tara.py` was written from the report, with no code copied from his repositories; it works per tile/window and accepts frame guides (keyframe rows are skipped), so it combines with "guide from previous window". His original node is [ComfyUI-BFSNodes](https://github.com/alisson-anjos/ComfyUI-BFSNodes/tree/feat/h3-native-temporal) (GPL-3.0) — use one or the other, not both.
- **`guide from previous window (1 frame)`** temporal mode (v5.6); carry mode now switches hard (no double exposure).
- **Face Crop / Face Stitch with SAM 3.1** (v5.7) to refine small faces with a face reference.
- **Background Plate 2D / 3D — experimental** (v5.8/v5.9): real camera motion from the source background applied to the new background photo; the 3D version uses MoGe depth and renders with parallax (CrossView-Warp / Meridian idea, without their LoRAs).

**中文**
- **流式解码 VIDEO 输出 + DLSS 5 后处理（v6.2）。** 流式解码把写出的文件作为基于文件的 `VIDEO` 输出；[RH DLSS5 Enhance](https://github.com/RH-RunningHub/ComfyUI-RH-DLSS5) 分块读取（600 帧 2K → 4K，不占满内存）。SyncTile 中的 Open-H3 Regenerate 2K（v29/v30）。
- **参考时间注意力 — TARA-H3（v6.0）。** 方法作者 **Alisson Anjos**（[TARA-H3 技术报告 v0.1.2，2026](https://github.com/alisson-anjos/ai-toolkit/tree/tara-h3-v0.1.2/research/tara-h3)）。把参考视频的时间 RoPE 与输出对齐，并在注意力中轻罚生成帧关注参考视频中较远的帧，使动作、口型和节奏更贴近参考。在 SyncTile Guider 中设 `temporal_reference = true`。我们的 `tara.py` 依据报告独立实现，未复制其仓库代码；按图块/窗口工作并兼容帧引导。其原始节点为 [ComfyUI-BFSNodes](https://github.com/alisson-anjos/ComfyUI-BFSNodes/tree/feat/h3-native-temporal)（GPL-3.0），二者择一使用。
- **`guide from previous window (1 frame)`** 时间模式（v5.6）；carry 模式改为直接切换（无重影）。
- **Face Crop / Face Stitch（SAM 3.1）**（v5.7），用人脸参考精修小脸。
- **Background Plate 2D / 3D — 实验功能**（v5.8/v5.9）：把源视频背景中的真实镜头运动应用到新背景照片；3D 版用 MoGe 深度并带视差渲染。

## Modelos / Models / 模型

| Pasta / Folder / 文件夹 | Arquivo / File / 文件 |
| --- | --- |
| `models/diffusion_models/` | [minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot](https://huggingface.co/MATLOWAI/minimax-h3-fused-turbo-int8-convrot/blob/main/diffusion_models/minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot.safetensors) (21 GB, turbo 4 steps) |
| `models/text_encoders/` | [qwen3vl_32b_minimax_h3_int8_convrot](https://huggingface.co/Comfy-Org/MiniMax-H3/blob/main/text_encoders/qwen3vl_32b_minimax_h3_int8_convrot.safetensors) (27 GB; nvfp4_awq 15.7 GB) |
| `models/vae/` | [minimax_h3_lynnreal_light_vae_int8_convrot](https://huggingface.co/Kijai/MiniMax-H3-experimental/blob/main/minimax_h3_lynnreal_light_vae_int8_convrot.safetensors) or [Comfy-Org video VAE](https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/vae) |
| `models/vae/` | [minimax_h3_audio_vae_fp32](https://huggingface.co/Comfy-Org/MiniMax-H3/blob/main/vae/minimax_h3_audio_vae_fp32.safetensors) |
| `models/loras/minimax/` | [Background Replace v3](https://huggingface.co/NyckM/Background_Replace_Minimax_H3/blob/main/Background%20Replace%20v3.safetensors) · [pdmd_4step](https://huggingface.co/Kijai/MiniMax-H3-experimental/blob/main/loras/minimax_h3_pdmd_4step_lora_avg_rank_57_bf16.safetensors) · [lms_v1.0_r64](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI/blob/main/loras/minimax_h3_lms_v1.0_r64.safetensors) |
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
| Distilação em 4 passos (LoRA opcional) · 4-step distillation (optional LoRA) · 4 步蒸馏（可选 LoRA） | Wang, Yuan, Wang et al. *PDMD: Projected Distribution Matching Distillation* (UC San Diego / ByteDance), 2026. [arXiv:2609.35768](https://arxiv.org/abs/2609.35768) · [pdmd2026](https://huggingface.co/pdmd2026) · conversão ComfyUI [Kijai](https://huggingface.co/Kijai/MiniMax-H3-experimental/tree/main/loras) | Pilha de LoRA 1 · LoRA stack 1 · LoRA 组 1 |
| Nitidez guiada pelo vídeo fonte · Source-guided sharpening · 源视频引导锐化 | [Alissonerdx / Minimax-H3-ComfyUI](https://huggingface.co/Alissonerdx/Minimax-H3-ComfyUI) (LMS v1.0 r64) | Pilha de LoRA 2 · LoRA stack 2 · LoRA 组 2 |
| Atenção temporal à referência (RoPE alinhado + viés temporal) · Temporal reference attention · 参考时间注意力 | **Anjos, A.** *TARA-H3: Temporally Aligned Reference Attention for Native Video Conditioning.* Technical report v0.1.2, 2026. [ai-toolkit/research/tara-h3](https://github.com/alisson-anjos/ai-toolkit/tree/tara-h3-v0.1.2/research/tara-h3) · node original [ComfyUI-BFSNodes](https://github.com/alisson-anjos/ComfyUI-BFSNodes/tree/feat/h3-native-temporal) (GPL-3.0) | `tara.py`, SyncTile Guider `temporal_reference` (implementação própria a partir do relatório · own implementation from the report · 依据报告自行实现) |
| Segmentação e tracking · Segmentation and tracking · 分割与跟踪 | Meta **SAM 3.1** via ComfyUI nativo · [Comfy-Org/sam3.1](https://huggingface.co/Comfy-Org/sam3.1) | Face Crop, Background Plate |
| Profundidade monocular · Monocular geometry · 单目几何 | **MoGe** (Microsoft) via ComfyUI nativo · [Comfy-Org/MoGe](https://huggingface.co/Comfy-Org/MoGe) | Background Plate 3D |
| Reprojeção por profundidade como guia · Depth-warp as guide · 深度重投影作为引导 | [Cseti — CrossView-Warp](https://huggingface.co/Cseti/MiniMax-H3_Ref2VA-LoRA-CrossView-Warp_v1) · [Viggle — Meridian](https://huggingface.co/Viggle/Meridian) | Ideia da placa 3D · idea of the 3D plate · 3D 背景板的思路 |
| Clipe-guia latente da janela anterior · Previous-window latent guide clip · 上一窗口潜变量引导片段 | Mohamed (**mo-akkakk**) — [ComfyUI-MiniMaxH3-TemporalWindow-SpatialTiles](https://github.com/mo-akkakk/ComfyUI-MiniMaxH3-TemporalWindow-SpatialTiles) (MIT) | `temporal_mode = guide from previous window (latent clip)` (ideia, implementação própria · idea, own implementation · 思路，自行实现) |
| LoRAs da mescla Background Replace v3 · LoRAs in the merge · 合并所用 LoRA | prithivMLmods, Akatz Labs, Lovis Odin / fal, Alissonerdx / Alisson Anjos (ver acima · see above · 见上文) | LoRA opcional · optional LoRA · 可选 LoRA |

O que é novo neste pack · What is new in this pack · 本节点包的新内容：mistura dentro de cada chamada do modelo (qualquer sampler) · blending inside every model call (any sampler) · 在每次模型调用内融合（任意采样器）；regiões espaço × tempo numa trajetória · space × time regions in one trajectory · 单一轨迹中的时空区域；conditioning por região com vídeo de referência fatiado/recortado e frames-guia por janela · per-region conditioning with sliced/cropped reference video and per-window frame guides · 逐区域条件（参考视频切片/裁切、按窗口放置帧引导）；troca estrutura → detalhe por sigma · structure → detail switch by sigma · 按 sigma 切换结构 → 细节；decode em streaming para arquivo · streaming decode to file · 流式解码写入文件。
| Pós-processo neural / upscale · Neural post-process / upscale · 神经后处理 / 放大 | NVIDIA **DLSS 5** via [RH-RunningHub/ComfyUI-RH-DLSS5](https://github.com/RH-RunningHub/ComfyUI-RH-DLSS5) (MIT; DLLs NVIDIA proprietárias, fornecidas pelo usuário · user-supplied proprietary NVIDIA DLLs) | Workflows v30 (2K → 4K) |
| Refino 2K · 2K regenerate · 2K 重生成 | **Open-H3 Regenerate 2K** LoRA (r128) · [MiniMax H3](https://huggingface.co/MiniMaxAI/MiniMax-H3) | Workflows v29/v30, estágio 2 · stage 2 |
