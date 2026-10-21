"""Trilingual help (Português / English / 中文) for every input of the bruxosdovfx • SyncTile nodes.

Each entry is (pt, en, zh). `apply()` wraps the nodes' INPUT_TYPES so every input gets a tooltip with the three
languages, and sets the node DESCRIPTION. Kept apart from the node logic on purpose.
"""

T = {}

# --------------------------------------------------------------------------- shared inputs
_TILE_W = ("Largura do tile em pixels. O canvas é dividido em tiles que se sobrepõem e são misturados a cada passo. "
           "1472x896 cabe em 24 GB. Valor maior que a imagem = sem divisão no espaço (ex.: 4096 no estágio 1).",
           "Tile width in pixels. The canvas is split into overlapping tiles blended at every step. 1472x896 fits "
           "24 GB. A value larger than the image = no spatial split (e.g. 4096 in stage 1).",
           "图块宽度（像素）。画面被切成相互重叠的图块，每一步都会融合。1472x896 适合 24 GB 显存。"
           "大于画面的数值 = 不做空间切分（例如第一阶段的 4096）。")
_TILE_H = ("Altura do tile em pixels. Use o mesmo valor no Guider e no Conditioning.",
           "Tile height in pixels. Use the same value on the Guider and the Conditioning node.",
           "图块高度（像素）。Guider 与 Conditioning 节点请使用相同的数值。")
_MIN_OV = ("Sobreposição mínima entre tiles, em células do latent (1 = 16 px). 16 é o padrão testado; não precisa mexer.",
           "Minimum overlap between tiles, in latent cells (1 = 16 px). 16 is the tested default; no need to change it.",
           "图块之间的最小重叠，单位为潜空间格（1 = 16 像素）。16 为已测试的默认值，一般无需修改。")
_WIN = ("Tamanho da janela no tempo, em frames (grade do H3: 17k+5 → 73, 90, 107, 124, 141, 243…). 0 = vídeo inteiro de "
        "uma vez. Vídeos longos são processados em janelas sobrepostas misturadas a cada passo: a VRAM depende da janela, "
        "não da duração. Faltou VRAM: 107 ou 90.",
        "Temporal window size in frames (H3 grid 17k+5 → 73, 90, 107, 124, 141, 243…). 0 = whole video in one pass. "
        "Long videos are processed as overlapping windows blended at every step: VRAM depends on the window, not on the "
        "length. Out of VRAM: 107 or 90.",
        "时间窗口长度（帧，H3 网格 17k+5 → 73、90、107、124、141、243…）。0 = 整段视频一次处理。长视频会切成相互重叠、"
        "每一步都融合的窗口：显存取决于窗口而不是视频长度。显存不足时用 107 或 90。")
_WIN_OV = ("Sobreposição entre janelas, em frames (vira 5, 22, 39, 56, 73 ou 90). Mais = transição mais suave entre janelas, "
           "mais lento. Costura ou cintilação a cada poucos segundos: 56 ou 73.",
           "Overlap between windows in frames (snaps to 5, 22, 39, 56, 73 or 90). More = smoother joins, slower. "
           "Seams or flicker every few seconds: 56 or 73.",
           "窗口之间的重叠帧数（取整为 5、22、39、56、73 或 90）。越大衔接越平滑，但更慢。每隔几秒出现接缝或闪烁时用 56 或 73。")
_CLIP = ("Text encoder do MiniMax H3 (Qwen3-VL 32B).", "MiniMax H3 text encoder (Qwen3-VL 32B).",
         "MiniMax H3 文本编码器（Qwen3-VL 32B）。")
_VAE = ("VAE de vídeo do MiniMax H3.", "MiniMax H3 video VAE.", "MiniMax H3 视频 VAE。")
_AVAE = ("VAE de áudio do MiniMax H3 (para o som do vídeo de referência).",
         "MiniMax H3 audio VAE (for the reference video's sound).",
         "MiniMax H3 音频 VAE（用于参考视频的声音）。")
_PROMPT = ("Prompt. Use as tags <Picture 1>, <Video 1>, <Audio 1> para citar as referências. Para vídeo longo, diga o que "
           "vale \"em todos os frames\": cada janela lê o prompt sozinha.",
           "Prompt. Use the tags <Picture 1>, <Video 1>, <Audio 1> to point at the references. For long videos, say what "
           "holds \"in every frame\": each window reads the prompt on its own.",
           "提示词。用 <Picture 1>、<Video 1>、<Audio 1> 标签指代参考素材。长视频请写明“每一帧都”要满足的内容："
           "每个窗口会单独读取提示词。")
_LATENT = ("Latent que o Guider vai processar. Conectado, ele define tamanho e duração, e os grids do Conditioning e do "
           "Guider sempre batem (width/height/length são ignorados).",
           "The latent the Guider will sample. When connected it sets size and length, so the Conditioning and Guider "
           "grids always match (width/height/length are ignored).",
           "Guider 将要采样的潜变量。连接后由它决定尺寸和时长，确保 Conditioning 与 Guider 的网格一致"
           "（此时忽略 width/height/length）。")

# --------------------------------------------------------------------------- SyncTile Guider
T["SyncTileGuiderH3"] = {
    "_desc": ("Substitui o Basic Guider. Processa um latent grande ou longo como regiões que se sobrepõem (tiles no espaço x "
              "janelas no tempo) e mistura as regiões a cada chamada do modelo. Uma trajetória só: sem emendas e sem colar "
              "clipes; a VRAM é a de uma região.",
              "Drop-in for Basic Guider. Denoises a large or long latent as overlapping regions (spatial tiles x temporal "
              "windows) blended at every model call. One trajectory: no seams and no chained clips; VRAM is one region's.",
              "替代 Basic Guider。把大尺寸或长时长的潜变量切成相互重叠的区域（空间图块 x 时间窗口），每次调用模型时都融合。"
              "只有一条去噪轨迹：没有接缝，也不拼接片段；显存只占一个区域。"),
    "model": ("Modelo MiniMax H3 (com LoRAs/attention já aplicados).", "MiniMax H3 model (LoRAs/attention already applied).",
              "MiniMax H3 模型（已加载 LoRA/注意力设置）。"),
    "tile_width": _TILE_W, "tile_height": _TILE_H, "min_overlap": _MIN_OV,
    "cfg": ("1.0 = igual ao Basic Guider (só o positivo). Modelos turbo usam 1.0. Acima de 1 usa o negativo e fica 2x mais lento.",
            "1.0 = same as Basic Guider (positive only). Turbo models use 1.0. Above 1 uses the negative and is 2x slower.",
            "1.0 = 与 Basic Guider 相同（只用正向条件）。Turbo 模型用 1.0。大于 1 会用到负向条件，速度慢一倍。"),
    "sync_mode": ("per model call: mistura dentro de cada chamada do modelo e usa o sampler conectado (recomendado). "
                  "SyncTile original: como o script do autor, cada região dá um passo de euler sozinha e depois mistura; "
                  "ignora o sampler conectado.",
                  "per model call: blends inside every model call and uses the connected sampler (recommended). "
                  "SyncTile original: like the author's script, each region takes one euler step alone, then they are "
                  "blended; the connected sampler is ignored.",
                  "per model call：在每次模型调用内部融合，使用所连接的采样器（推荐）。SyncTile original：与原作者脚本相同，"
                  "每个区域单独走一步 euler 再融合；忽略所连接的采样器。"),
    "use_refine_seed": ("Ligado: este passe usa o próprio ruído (refine_seed). Mude só essa seed para testar outro refino; o "
                        "estágio 1 e os conditionings ficam em cache.",
                        "On: this pass uses its own noise (refine_seed). Change only this seed to try another refine; "
                        "stage 1 and the conditionings stay cached.",
                        "开启：此阶段使用自己的噪声（refine_seed）。只改这个种子即可尝试不同的精修，第一阶段和条件编码会被缓存。"),
    "refine_seed": ("Seed do ruído do refino (só com use_refine_seed ligado).",
                    "Refine noise seed (only with use_refine_seed on).", "精修噪声种子（仅在开启 use_refine_seed 时生效）。"),
    "positive": ("Conditioning único para todas as regiões. Ignorado se tile_conditioning estiver conectado. Não use com "
                 "frames-guia/Add Guide em janelas: use o node de Conditioning.",
                 "One conditioning shared by every region. Ignored when tile_conditioning is connected. Do not use with "
                 "frame guides/Add Guide in windows: use the Conditioning node.",
                 "所有区域共用的条件。连接 tile_conditioning 时忽略。分窗口时不要配合帧引导/Add Guide 使用，请改用 Conditioning 节点。"),
    "negative": ("Negativo (só com cfg acima de 1).", "Negative (only with cfg above 1).", "负向条件（仅在 cfg 大于 1 时使用）。"),
    "tile_conditioning": ("Conditioning por região, do node SyncTile Conditioning. O grid (tiles e janelas) vem dele.",
                          "Per-region conditioning from a SyncTile Conditioning node. The grid (tiles and windows) comes from it.",
                          "来自 SyncTile Conditioning 节点的逐区域条件。网格（图块与窗口）由它决定。"),
    "tile_conditioning_detail": ("Opcional: segundo conditioning por região usado nos passos finais (sigma abaixo de "
                                 "detail_below_sigma), para trazer textura sem mudar a composição. Mesmo grid do primeiro.",
                                 "Optional second per-region conditioning used in the final steps (sigma below "
                                 "detail_below_sigma), to add texture without changing the composition. Same grid as the first.",
                                 "可选：第二套逐区域条件，用于最后几步（sigma 低于 detail_below_sigma），在不改变构图的情况下增加纹理。"
                                 "网格须与第一套一致。"),
    "detail_below_sigma": ("Ponto de troca estrutura → detalhe. Com sigmas 0.878/0.8/0.6316: 0.85 = 1 passo estrutura + 2 "
                           "detalhe (equilíbrio); 0.7 = mais seguro; 1.0 = tudo detalhe; 0 = tudo estrutura.",
                           "Structure → detail switch point. With sigmas 0.878/0.8/0.6316: 0.85 = 1 structure + 2 detail "
                           "steps (balanced); 0.7 = safer; 1.0 = all detail; 0 = all structure.",
                           "结构 → 细节的切换点。使用 sigma 0.878/0.8/0.6316 时：0.85 = 1 步结构 + 2 步细节（平衡）；"
                           "0.7 = 更稳；1.0 = 全部细节；0 = 全部结构。"),
    "window_frames": tuple(x + y for x, y in zip(_WIN, (" Só usado com 'positive'; com tile_conditioning as janelas vêm do Conditioning.",
                                                       " Only used with 'positive'; with tile_conditioning the windows come from the Conditioning node.",
                                                       " 仅在使用 positive 时生效；连接 tile_conditioning 时窗口由 Conditioning 节点决定。"))),
    "window_overlap_frames": _WIN_OV,
    "temporal_mode": ("blend windows (joint): todas as janelas andam juntas e se misturam a cada passo (padrão antigo). "
                      "carry previous frames (sequential): as janelas rodam uma depois da outra; o começo de cada janela "
                      "fica preso aos frames já prontos da anterior (o modelo enxerga esses frames e continua a partir "
                      "deles). Evita fantasma/dupla exposição nas transições e segura melhor o movimento de câmera.",
                      "blend windows (joint): all windows move together and are blended at every step (old default). "
                      "carry previous frames (sequential): windows run one after another; the start of each window is "
                      "locked to the finished frames of the previous one (the model sees them and continues from them). "
                      "Avoids ghosting/double exposure at the joins and keeps camera motion better.",
                      "blend windows (joint)：所有窗口同步去噪，每一步都融合（旧默认）。carry previous frames (sequential)："
                      "窗口依次运行；每个窗口的开头锁定为上一个窗口已完成的帧（模型能看到这些帧并接着生成）。"
                      "可避免衔接处的重影/双重曝光，更好地保持镜头运动。"),
    "carry_frames": ("Quantos frames do fim da janela anterior ficam presos no começo da próxima (só no modo carry). "
                     "Arredonda para o token do H3 (1, 5, 9, 13, 17, 21, 25…). 21 ≈ 0,9 s. Menos = mais liberdade, mais = mais "
                     "continuidade. Fica limitado pela window_overlap_frames.",
                     "How many frames from the end of the previous window are locked at the start of the next (carry mode "
                     "only). Rounds to the H3 token (1, 5, 9, 13, 17, 21, 25…). 21 ≈ 0.9 s. Fewer = more freedom, more = "
                     "more continuity. Capped by window_overlap_frames.",
                     "上一个窗口末尾有多少帧会锁定在下一个窗口开头（仅 carry 模式）。按 H3 token 取整（1、5、9、13、17、21、25…）。"
                     "21 ≈ 0.9 秒。越少越自由，越多越连贯。不超过 window_overlap_frames。"),
}

# --------------------------------------------------------------------------- SyncTile Ref2VA Conditioning
_GIMG = ("Imagem-guia: ancora a imagem num frame do vídeo (como o Add Guide). Vai para a janela que contém esse frame e é "
         "recortada por tile. Use um frame do vídeo fonte com o resultado desejado (mesmo enquadramento).",
         "Guide image: anchors the image at one frame (like Add Guide). It goes to the window holding that frame and is "
         "cropped per tile. Use a source frame showing the wanted result (same framing).",
         "引导图：把图像锚定到某一帧（类似 Add Guide）。它会放进包含该帧的窗口，并按图块裁切。"
         "请使用源视频中该帧、呈现目标效果的图片（构图一致）。")
T["SyncTileRef2VAConditioningH3"] = {
    "_desc": ("Roda o MiniMax H3 Reference to Video uma vez por região: o vídeo de referência é fatiado para cada janela no "
              "tempo e recortado para cada tile; os frames-guia caem na janela certa.",
              "Runs MiniMax H3 Reference to Video once per region: the reference video is sliced for each temporal window "
              "and cropped for each tile; frame guides land in the right window.",
              "对每个区域运行一次 MiniMax H3 Reference to Video：参考视频按时间窗口切片、按图块裁切；帧引导会放进对应的窗口。"),
    "clip": _CLIP, "prompt": _PROMPT, "latent": _LATENT, "vae": _VAE, "audio_vae": _AVAE,
    "width": ("Largura do canvas (só sem latent conectado).", "Canvas width (only without a connected latent).",
              "画布宽度（仅在未连接 latent 时使用）。"),
    "height": ("Altura do canvas (só sem latent conectado).", "Canvas height (only without a connected latent).",
               "画布高度（仅在未连接 latent 时使用）。"),
    "length": ("Duração em frames (só sem latent conectado). Normalmente vem do Load Video.",
               "Length in frames (only without a connected latent). Usually comes from the video loader.",
               "时长（帧，仅在未连接 latent 时使用）。通常来自视频加载节点。"),
    "tile_width": _TILE_W, "tile_height": _TILE_H, "min_overlap": _MIN_OV,
    "ref_video_mode": ("crop: cada tile vê só o seu pedaço do vídeo de referência (mais detalhe, evita personagem repetido; "
                       "1 passada do text encoder por tile). full: 1 passada por janela, todo tile vê o quadro inteiro (rápido).",
                       "crop: each tile sees only its part of the reference video (more detail, avoids repeated characters; "
                       "one text-encoder pass per tile). full: one pass per window, every tile sees the whole frame (fast).",
                       "crop：每个图块只看参考视频中对应的部分（细节更多，可避免人物重复；每个图块运行一次文本编码器）。"
                       "full：每个窗口运行一次，所有图块看到完整画面（更快）。"),
    "ref_image_size": ("match: a imagem de referência é reduzida ao tamanho da geração. max: até 2048 px (mais fiel, mais tokens, "
                       "mais lento).",
                       "match: the reference image is scaled to the generation size. max: up to 2048 px (more faithful, "
                       "more tokens, slower).",
                       "match：参考图缩放到生成尺寸。max：最大 2048 像素（更忠实、token 更多、更慢）。"),
    "ref_image_0": ("Imagem de referência 1 = <Picture 1> no prompt.", "Reference image 1 = <Picture 1> in the prompt.",
                    "参考图 1 = 提示词中的 <Picture 1>。"),
    "ref_image_1": ("Imagem de referência 2 = <Picture 2>.", "Reference image 2 = <Picture 2>.", "参考图 2 = <Picture 2>。"),
    "ref_image_2": ("Imagem de referência 3 = <Picture 3>.", "Reference image 3 = <Picture 3>.", "参考图 3 = <Picture 3>。"),
    "ref_video_0": ("Vídeo de referência = <Video 1>, em 24 fps e alinhado frame a frame com a saída. Fatiado por janela e "
                    "recortado por tile automaticamente.",
                    "Reference video = <Video 1>, at 24 fps and frame-aligned with the output. Sliced per window and "
                    "cropped per tile automatically.",
                    "参考视频 = <Video 1>，24 fps，并与输出逐帧对齐。会自动按窗口切片、按图块裁切。"),
    "ref_video_audio_0": ("Som do vídeo de referência (fatiado junto com o vídeo).",
                          "Soundtrack of the reference video (sliced with the video).", "参考视频的声音（与视频一起切片）。"),
    "ref_audio_0": ("Áudio de referência avulso = <Audio 1> (não é fatiado).", "Standalone reference audio = <Audio 1> (not sliced).",
                    "独立参考音频 = <Audio 1>（不切片）。"),
    "window_frames": _WIN, "window_overlap_frames": _WIN_OV,
    "guide_image_1": _GIMG,
    "guide_frame_1": ("Frame do vídeo inteiro onde vai o guide_image_1. 1 costuma prender melhor que 0. -1 = último frame.",
                      "Frame of the whole video for guide_image_1. 1 usually holds better than 0. -1 = last frame.",
                      "guide_image_1 在整段视频中的帧号。1 通常比 0 锚定得更好。-1 = 最后一帧。"),
    "guide_image_2": _GIMG,
    "guide_frame_2": ("Frame do guide_image_2 (-1 = último).", "Frame for guide_image_2 (-1 = last).", "guide_image_2 的帧号（-1 = 最后一帧）。"),
    "guide_images": ("Lote de imagens-guia (quantas quiser). A imagem k vai para o k-ésimo número de guide_frames. Junte os "
                     "stills com Image Batch (mesmo tamanho). Um guia a cada ~4-5 s segura o visual no vídeo inteiro.",
                     "Batch of guide images (any number). Image k goes to the k-th number in guide_frames. Batch the stills "
                     "with Image Batch (same size). One guide every ~4-5 s holds the look through the whole video.",
                     "引导图批次（数量不限）。第 k 张图对应 guide_frames 中的第 k 个数字。用 Image Batch 合并（尺寸一致）。"
                     "每 4-5 秒放一张引导图，可在整段视频中保持画面一致。"),
    "guide_frames": ("Frames do lote, na mesma ordem, separados por vírgula. Ex.: 1, 150, 300, 450 (-1 = último). "
                     "Nº de imagens = nº de frames, ou 1 imagem = a mesma em todos.",
                     "Frames for the batch, same order, comma separated. E.g. 1, 150, 300, 450 (-1 = last). "
                     "Number of images = number of frames, or 1 image = the same at each frame.",
                     "批次对应的帧号，顺序一致，用逗号分隔。例如 1, 150, 300, 450（-1 = 最后一帧）。"
                     "图片数量 = 帧号数量；或只给 1 张图 = 每个帧号都用这张图。"),
}

# --------------------------------------------------------------------------- SyncTile I2V Conditioning
T["SyncTileI2VConditioningH3"] = {
    "_desc": ("Image to Video (primeiro/último frame) para SyncTile: a imagem é ampliada para o canvas e cada região recebe o "
              "seu recorte como keyframe, na janela que contém aquele frame. Sem imagens = texto para vídeo.",
              "Image to Video (first/last frame) for SyncTile: the image is scaled to the canvas and each region gets its "
              "own crop as keyframe, in the window holding that frame. No images = text to video.",
              "用于 SyncTile 的图生视频（首帧/尾帧）：图像缩放到画布大小，每个区域在包含该帧的窗口中获得自己的裁切作为关键帧。"
              "不接图像 = 文生视频。"),
    "clip": _CLIP, "vae": _VAE, "prompt": _PROMPT, "latent": _LATENT,
    "tile_width": _TILE_W, "tile_height": _TILE_H, "min_overlap": _MIN_OV,
    "qwen_view": ("O que o text encoder vê junto com o prompt. full: a imagem inteira, 1 passada (rápido). crop: o recorte de "
                  "cada tile, 1 passada por tile (lento).",
                  "What the text encoder sees with the prompt. full: the whole image, one pass (fast). crop: each tile's "
                  "crop, one pass per tile (slow).",
                  "文本编码器随提示词看到的内容。full：整张图，运行一次（快）。crop：每个图块的裁切，每个图块运行一次（慢）。"),
    "first_frame": ("Primeiro frame. Use a imagem em alta resolução: ela é recortada por tile no tamanho do canvas.",
                    "First frame. Use the full-resolution image: it is cropped per tile at canvas size.",
                    "首帧。请使用高分辨率原图：它会按画布尺寸逐图块裁切。"),
    "last_frame": ("Último frame (opcional).", "Last frame (optional).", "尾帧（可选）。"),
    "window_frames": _WIN, "window_overlap_frames": _WIN_OV,
}

# --------------------------------------------------------------------------- SyncTile Stream Decode
T["SyncTileStreamDecodeVideoH3"] = {
    "_desc": ("Decodifica o latent de vídeo do MiniMax H3 bloco a bloco e grava os frames direto no arquivo, sem montar o "
              "vídeo inteiro na RAM. Saída IMAGE opcional para outros nodes de salvar.",
              "Decodes a MiniMax H3 video latent block by block and writes the frames straight into a file, without "
              "building the whole video in RAM. Optional IMAGE output for other save nodes.",
              "逐块解码 MiniMax H3 视频潜变量，并把帧直接写入文件，不会把整段视频放进内存。可选 IMAGE 输出，供其他保存节点使用。"),
    "samples": ("Latent de vídeo (ou áudio+vídeo) vindo do sampler.", "Video (or audio+video) latent from the sampler.",
                "来自采样器的视频（或音视频）潜变量。"),
    "vae": _VAE,
    "filename_prefix": ("Pasta/nome dentro de output/. Ex.: SyncTile/long", "Folder/name inside output/. E.g. SyncTile/long",
                        "output/ 下的文件夹/文件名。例如 SyncTile/long"),
    "fps": ("Quadros por segundo. O H3 gera a 24 fps: deixe 24.", "Frames per second. H3 generates at 24 fps: keep 24.",
            "帧率。H3 以 24 fps 生成：保持 24。"),
    "codec": ("h265 10-bit: menor e sem banding (recebe 16 bits do VAE). h264 8-bit: abre em qualquer lugar. ProRes 422 HQ: "
              "para finalização/VFX. Sem o encoder no seu ffmpeg, troca sozinho e avisa.",
              "h265 10-bit: smaller, no banding (gets 16-bit frames from the VAE). h264 8-bit: plays anywhere. ProRes 422 "
              "HQ: for finishing/VFX. If your ffmpeg lacks the encoder it switches by itself and says so.",
              "h265 10-bit：体积小、无色带（直接接收 VAE 的 16 位帧）。h264 8-bit：兼容性最好。ProRes 422 HQ：用于后期/特效。"
              "若 ffmpeg 缺少该编码器，会自动切换并提示。"),
    "crf": ("Qualidade do h264/h265 (menor = melhor e maior). 14 já é alta; 4 é quase sem perda. Ignorado no ProRes.",
            "h264/h265 quality (lower = better and bigger). 14 is already high; 4 is near lossless. Ignored for ProRes.",
            "h264/h265 质量（越小越好、文件越大）。14 已经很高；4 接近无损。ProRes 忽略此项。"),
    "audio": ("Trilha para juntar no arquivo, ex.: o áudio do vídeo fonte. Cortada no tamanho do vídeo.",
              "Soundtrack to mux into the file, e.g. the source video's audio. Cut to the video length.",
              "要合并进文件的音轨，例如源视频的音频。会裁到视频长度。"),
    "image_output": ("Também devolve os frames como IMAGE (ex.: para o Save Video Pro). Custa RAM: frames x L x A x 12 bytes "
                     "(600 frames em 2208x2848 ≈ 45 GB; half = 1/4). Se não couber, cai para half e depois off, e avisa; "
                     "o arquivo é gravado mesmo assim.",
                     "Also return the frames as IMAGE (e.g. for Save Video Pro). Costs RAM: frames x W x H x 12 bytes "
                     "(600 frames at 2208x2848 ≈ 45 GB; half = 1/4). If it does not fit it falls back to half, then off, "
                     "and says so; the file is written anyway.",
                     "同时以 IMAGE 输出帧（例如接 Save Video Pro）。占用内存：帧数 x 宽 x 高 x 12 字节"
                     "（600 帧 2208x2848 ≈ 45 GB；half = 1/4）。内存不够时会降为 half，再降为 off 并提示；文件照常写入。"),
    "write_video": ("Grava o arquivo de vídeo. Desligado = só a saída IMAGE (sem ffmpeg).",
                    "Write the video file. Off = only the IMAGE output (no ffmpeg).",
                    "写出视频文件。关闭 = 只输出 IMAGE（不调用 ffmpeg）。"),
}


def tooltip(pt, en, zh):
    return f"PT: {pt}\nEN: {en}\n中文: {zh}"


def apply(mappings):
    """Wrap INPUT_TYPES of every mapped node so each input carries the trilingual tooltip; set DESCRIPTION."""
    for key, cls in mappings.items():
        tips = T.get(key)
        if not tips:
            continue
        if "_desc" in tips:
            cls.DESCRIPTION = tooltip(*tips["_desc"])
        original = cls.INPUT_TYPES.__func__

        def wrapped(c, _orig=original, _tips=tips):
            spec = _orig(c)
            for section in ("required", "optional"):
                for name, value in spec.get(section, {}).items():
                    if name in _tips:
                        typ = value[0]
                        opts = dict(value[1]) if len(value) > 1 else {}
                        opts["tooltip"] = tooltip(*_tips[name])
                        spec[section][name] = (typ, opts)
            return spec
        cls.INPUT_TYPES = classmethod(wrapped)
