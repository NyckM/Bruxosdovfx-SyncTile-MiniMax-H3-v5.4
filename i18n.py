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
                      "deles). guide from previous window (1 frame): janelas em sequência; o frame pronto onde cada janela começa vira o frame-guia (como o Add Guide) da janela seguinte, e a troca é seca nesse frame. guide from previous window (latent clip): igual, mas passa os carry_frames prontos (ex.: 22) direto em latent como um clipe-guia: sem VAE e levando também o movimento (ideia do mo-akkakk).",
                      "blend windows (joint): all windows move together and are blended at every step (old default). "
                      "carry previous frames (sequential): windows run one after another; the start of each window is "
                      "locked to the finished frames of the previous one (the model sees them and continues from them). "
                      "guide from previous window (1 frame): windows in sequence; the finished frame where each window starts becomes the next window's frame guide (like Add Guide), with a hard switch at that frame. guide from previous window (latent clip): same, but the finished carry_frames (e.g. 22) go in directly as a latent guide clip: no VAE round trip and the motion is carried too (idea by mo-akkakk).",
                      "blend windows (joint)：所有窗口同步去噪，每一步都融合（旧默认）。carry previous frames (sequential)："
                      "窗口依次运行；每个窗口的开头锁定为上一个窗口已完成的帧（模型能看到这些帧并接着生成）。"
                      "guide from previous window (1 frame)：窗口依次运行；每个窗口起始处已完成的帧作为下一个窗口的帧引导（类似 Add Guide），并在该帧处直接切换。guide from previous window (latent clip)：同上，但直接把已完成的 carry_frames 帧（如 22）以潜变量引导片段传入：无需 VAE，并带上动作（思路来自 mo-akkakk）。"),
    "carry_frames": ("Quantos frames do fim da janela anterior ficam presos no começo da próxima (só no modo carry). "
                     "Arredonda para o token do H3 (1, 5, 9, 13, 17, 21, 25…). 21 ≈ 0,9 s. Menos = mais liberdade, mais = mais "
                     "continuidade. Fica limitado pela window_overlap_frames.",
                     "How many frames from the end of the previous window are locked at the start of the next (carry mode "
                     "only). Rounds to the H3 token (1, 5, 9, 13, 17, 21, 25…). 21 ≈ 0.9 s. Fewer = more freedom, more = "
                     "more continuity. Capped by window_overlap_frames.",
                     "上一个窗口末尾有多少帧会锁定在下一个窗口开头（仅 carry 模式）。按 H3 token 取整（1、5、9、13、17、21、25…）。"
                     "21 ≈ 0.9 秒。越少越自由，越多越连贯。不超过 window_overlap_frames。"),
    "temporal_reference": ("TARA-H3 (Alisson Anjos, 2026): o relógio do vídeo de referência (<Video N>) é alinhado com o "
                           "vídeo gerado e cada frame gerado é levemente penalizado ao olhar frames distantes da referência. "
                           "O movimento, a boca e o ritmo seguem a referência com mais precisão. Funciona com frames-guia. "
                           "Precisa de cfg 1.0 e da referência com os mesmos frames da saída (24 fps).",
                           "TARA-H3 (Alisson Anjos, 2026): the reference video's (<Video N>) clock is aligned with the "
                           "output and each generated frame is softly penalised for attending to distant reference frames. "
                           "Motion, mouth and timing follow the reference more closely. Works with frame guides. Needs cfg "
                           "1.0 and a reference with the same frames as the output (24 fps).",
                           "TARA-H3（Alisson Anjos，2026）：把参考视频（<Video N>）的时钟与输出对齐，并在注意力中轻罚生成帧关注"
                           "参考视频中时间较远的帧。动作、口型和节奏更贴近参考。可与帧引导一起使用。需要 cfg 1.0，参考视频与"
                           "输出帧数相同（24 fps）。"),
    "tara_strength": ("Força da penalidade (λ). 2.0 = padrão do autor; 0 = só o alinhamento do relógio; 3–4 = segue mais.",
                      "Penalty strength (λ). 2.0 = author's default; 0 = clock alignment only; 3–4 = follows more.",
                      "惩罚强度（λ）。2.0 = 作者默认；0 = 只做时钟对齐；3–4 = 跟随更紧。"),
    "tara_window_seconds": ("Janela sem penalidade (s): frames da referência até essa distância são livres. Padrão 0.2.",
                            "Free window (s): reference frames up to this distance are not penalised. Default 0.2.",
                            "无惩罚窗口（秒）：在此距离内的参考帧不受惩罚。默认 0.2。"),
    "tara_falloff_seconds": ("Queda da penalidade (s) depois da janela. Padrão 0.25.",
                             "Penalty falloff (s) after the window. Default 0.25.", "窗口之后的惩罚衰减（秒）。默认 0.25。"),
    "tara_max_penalty": ("Penalidade máxima (teto). Padrão 6.0; frames distantes continuam visíveis, só pesam menos.",
                         "Maximum penalty (cap). Default 6.0; distant frames stay visible, they just weigh less.",
                         "最大惩罚（上限）。默认 6.0；远处的帧仍可见，只是权重更低。"),
    "tara_motion_video": ("Qual <Video N> é a referência de movimento (normalmente 1).",
                          "Which <Video N> is the motion reference (usually 1).", "哪个 <Video N> 是动作参考（通常为 1）。"),
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


# --------------------------------------------------------------------------- Face Crop / Face Stitch (SAM 3.1)
T["SyncTileFaceCropH3"] = {
    "_desc": ("Recorta o rosto seguindo a máscara do SAM 3.1 (Run SAM3 Video Track → SAM3 Track to Mask, prompt 'face') "
              "e amplia para um quadrado do mesmo tamanho em todos os frames: rosto pequeno vira rosto grande para o H3 "
              "refinar. Depois o Face Stitch cola de volta na posição e escala de cada frame.",
              "Crops the face following the SAM 3.1 mask (Run SAM3 Video Track → SAM3 Track to Mask, prompt 'face') and "
              "zooms it to a square of the same size in every frame: a small face becomes a large face for H3 to refine. "
              "Face Stitch then pastes it back at each frame's position and scale.",
              "按 SAM 3.1 的遮罩（Run SAM3 Video Track → SAM3 Track to Mask，提示词 'face'）裁出人脸，并在每一帧放大到同样大小的"
              "正方形：小脸变成大脸交给 H3 精修。之后由 Face Stitch 按每帧的位置和比例贴回。"),
    "images": ("Vídeo onde estão os rostos (ex.: a saída IMAGE do Stream Decode).",
               "Video holding the faces (e.g. the Stream Decode IMAGE output).",
               "包含人脸的视频（例如 Stream Decode 的 IMAGE 输出）。"),
    "mask": ("Máscara do rosto por frame, do SAM3 Track to Mask. Pode estar em resolução menor: é ampliada sozinha.",
             "Per-frame face mask from SAM3 Track to Mask. It may be smaller: it is resized automatically.",
             "来自 SAM3 Track to Mask 的逐帧人脸遮罩。分辨率可以更低，会自动缩放。"),
    "out_size": ("Tamanho do quadrado do rosto (px). 768 = rosto bem grande para o H3; 512 = mais rápido.",
                 "Size of the face square (px). 768 = a large face for H3; 512 = faster.",
                 "人脸正方形的尺寸（像素）。768 = 给 H3 的大脸；512 = 更快。"),
    "padding": ("Folga em volta do rosto (fração do tamanho do rosto). 0.45 inclui cabelo, queixo e um pouco de fundo.",
                "Margin around the face (fraction of the face size). 0.45 includes hair, chin and some background.",
                "人脸周围的留白（占人脸尺寸的比例）。0.45 包含头发、下巴和一点背景。"),
    "center_smooth": ("Suaviza a posição do recorte no tempo (frames). Evita tremor.",
                      "Smooths the crop position over time (frames). Avoids jitter.",
                      "在时间上平滑裁切位置（帧数），避免抖动。"),
    "size_smooth": ("Suaviza o tamanho do recorte (frames). Maior = o zoom não 'respira'.",
                    "Smooths the crop size (frames). Higher = the zoom does not 'breathe'.",
                    "平滑裁切尺寸（帧数）。越大缩放越不会“呼吸”。"),
    "mask_threshold": ("Limiar da máscara para medir o rosto.", "Mask threshold used to measure the face.",
                       "测量人脸时使用的遮罩阈值。"),
}
T["SyncTileFaceStitchH3"] = {
    "_desc": ("Cola o rosto refinado de volta no vídeo, na posição e escala de cada frame, com borda suave e ajuste de cor. "
              "Frames em que o SAM perdeu o rosto ficam com o original.",
              "Pastes the refined face back into the video at each frame's position and scale, with a soft edge and colour "
              "match. Frames where SAM lost the face keep the original.",
              "把精修后的人脸按每帧的位置和比例贴回视频，带柔和边缘和颜色匹配。SAM 丢失人脸的帧保持原样。"),
    "images": ("O mesmo vídeo ligado no Face Crop.", "The same video connected to Face Crop.", "与 Face Crop 相同的视频。"),
    "face_video": ("Vídeo do rosto já refinado (mesmo tamanho do face_video do Face Crop).",
                   "The refined face video (same size as Face Crop's face_video).",
                   "已精修的人脸视频（与 Face Crop 的 face_video 同尺寸）。"),
    "crop_data": ("Saída crop_data do Face Crop.", "crop_data output of Face Crop.", "Face Crop 的 crop_data 输出。"),
    "compose": ("silhouette: só o rosto/cabelo da máscara do SAM volta (recomendado). ellipse: elipse no recorte. "
                "rectangle: o quadrado inteiro.",
                "silhouette: only the face/hair from the SAM mask is pasted (recommended). ellipse: an ellipse inside the "
                "crop. rectangle: the whole square.",
                "silhouette：只贴回 SAM 遮罩中的脸/头发（推荐）。ellipse：裁切内的椭圆。rectangle：整个正方形。"),
    "mask_grow": ("Expande a máscara (px no recorte) para cobrir a borda do rosto.",
                  "Grows the mask (px in the crop) to cover the face edge.", "扩展遮罩（裁切内像素）以覆盖人脸边缘。"),
    "feather": ("Suavidade da borda (px).", "Edge softness (px).", "边缘柔和度（像素）。"),
    "colour_match": ("Casa cor e contraste do rosto novo com o original.", "Matches colour and contrast to the original.",
                     "让新脸的颜色和对比度与原始画面一致。"),
    "blend": ("1 = rosto novo inteiro; menos = mistura com o original.", "1 = full new face; lower = mix with the original.",
              "1 = 完全使用新脸；更低 = 与原始画面混合。"),
}


# --------------------------------------------------------------------------- Background Plate (experimental)
T["SyncTileBackgroundPlateH3"] = {
    "_desc": ("EXPERIMENTAL. Mede o movimento real da câmera no FUNDO do vídeo fonte (a pessoa é tirada pela máscara do "
              "SAM 3.1), aplica o mesmo movimento na imagem do novo ambiente e compõe a pessoa por cima. Ligue o "
              "'composite' no lugar do vídeo fonte: o H3 recebe o fundo já se movendo como a câmera real (<Video 1>). "
              "Só 2D: pan, tilt, zoom e rotação; sem paralaxe de profundidade.",
              "EXPERIMENTAL. Measures the real camera motion on the BACKGROUND of the source video (the person is removed "
              "with the SAM 3.1 mask), applies the same motion to the new environment image and composites the person on "
              "top. Connect 'composite' instead of the source video: H3 gets a background already moving like the real "
              "camera (<Video 1>). 2D only: pan, tilt, zoom and roll; no depth parallax.",
              "实验功能。在源视频的背景上测量真实的镜头运动（用 SAM 3.1 遮罩去掉人物），把同样的运动应用到新环境图片上，"
              "再把人物合成在上面。用 'composite' 代替源视频：H3 得到已经按真实镜头运动的背景（<Video 1>）。"
              "仅 2D：平移、俯仰、缩放和旋转；没有深度视差。"),
    "images": ("Vídeo fonte (o mesmo do Load Video Pro).", "Source video (same as Load Video Pro).", "源视频（与 Load Video Pro 相同）。"),
    "person_mask": ("Máscara da pessoa por frame (SAM3 Track to Mask com prompt 'person'). Ela é tirada da medição do "
                    "movimento e fica na frente da placa.",
                    "Per-frame person mask (SAM3 Track to Mask with prompt 'person'). It is excluded from the motion "
                    "measurement and stays in front of the plate.",
                    "逐帧人物遮罩（SAM3 Track to Mask，提示词 'person'）。测量运动时排除，并保持在背景板前面。"),
    "background": ("Imagem do novo fundo (ex.: a selva). De preferência sem pessoa; se tiver, ligue background_person_mask.",
                   "New background image (e.g. the jungle). Ideally without a person; if it has one, connect "
                   "background_person_mask.",
                   "新背景图片（例如丛林）。最好没有人物；如果有，请连接 background_person_mask。"),
    "background_person_mask": ("Opcional: máscara da pessoa NA IMAGEM de fundo (SAM3 Detect 'person'). A pessoa é apagada "
                               "(inpaint) para não andar junto com o fundo.",
                               "Optional: person mask ON the background image (SAM3 Detect 'person'). The person is erased "
                               "(inpaint) so it does not move with the background.",
                               "可选：背景图片中人物的遮罩（SAM3 Detect 'person'）。会把人物抹掉（修补），以免随背景移动。"),
    "motion_model": ("similarity: pan, zoom e rotação (mais estável, recomendado). affine: também cisalhamento. "
                     "homography: perspectiva (câmera girando muito); pode distorcer.",
                     "similarity: pan, zoom and roll (most stable, recommended). affine: adds shear. homography: "
                     "perspective (strong camera turns); may distort.",
                     "similarity：平移、缩放、旋转（最稳定，推荐）。affine：加上错切。homography：透视（镜头大幅转动）；可能变形。"),
    "plate_scale": ("Quanto a imagem de fundo é maior que o quadro, para sobrar imagem quando a câmera anda. Câmera andando "
                    "muito: 1.6–2.0 (as bordas são espelhadas quando acaba).",
                    "How much larger the background image is than the frame, so there is image left when the camera moves. "
                    "Big camera moves: 1.6–2.0 (edges are mirrored when it runs out).",
                    "背景图片比画面大多少，镜头移动时仍有画面。镜头移动很大：1.6–2.0（超出时边缘镜像）。"),
    "mask_grow": ("Margem (px) em volta da pessoa ignorada na medição (cabelo, sombra, borda).",
                  "Margin (px) around the person ignored when measuring (hair, shadow, edge).",
                  "测量时忽略的人物周围边距（像素：头发、阴影、边缘）。"),
    "smooth": ("Suaviza tremidas da medição (frames). 0 = segue exatamente; 3 = padrão.",
               "Smooths measurement jitter (frames). 0 = follow exactly; 3 = default.", "平滑测量抖动（帧数）。0 = 完全跟随；3 = 默认。"),
    "feather": ("Borda suave da pessoa no composite (px).", "Soft edge of the person in the composite (px).",
                "合成中人物边缘的柔化（像素）。"),
    "track_width": ("Largura usada só para medir o movimento (px). 640 é rápido e preciso.",
                    "Width used only to measure motion (px). 640 is fast and accurate.", "仅用于测量运动的宽度（像素）。640 快且准确。"),
}


T["SyncTileBackgroundPlate3DH3"] = {
    "_desc": ("EXPERIMENTAL. Versão 3D da placa de fundo, na linha do CrossView-Warp: o MoGe dá a profundidade do vídeo fonte "
              "e da foto do novo fundo; os pontos do fundo rastreados viram 3D e dão a rotação E a translação reais da "
              "câmera (PnP); a foto vira uma malha com profundidade e é renderizada dessa câmera, com paralaxe (perto passa "
              "mais rápido que longe). A pessoa é composta por cima e o 'composite' vira o <Video 1>.",
              "EXPERIMENTAL. 3D version of the background plate, in the CrossView-Warp spirit: MoGe gives the depth of the "
              "source video and of the new background photo; tracked background points become 3D and give the real camera "
              "rotation AND translation (PnP); the photo becomes a depth mesh rendered from that camera, with parallax (near "
              "moves faster than far). The person is composited on top and 'composite' becomes <Video 1>.",
              "实验功能。背景板的 3D 版本，思路同 CrossView-Warp：MoGe 给出源视频和新背景照片的深度；跟踪到的背景点提升为 3D，"
              "求出真实镜头的旋转和平移（PnP）；照片变成带深度的网格，从该镜头渲染，带视差（近处比远处移动更快）。"
              "人物合成在上面，'composite' 作为 <Video 1>。"),
    "images": ("Vídeo fonte.", "Source video.", "源视频。"),
    "person_mask": ("Máscara da pessoa por frame (SAM 3.1 'person'): fica fora da medição e na frente da placa.",
                    "Per-frame person mask (SAM 3.1 'person'): excluded from the measurement and kept in front of the plate.",
                    "逐帧人物遮罩（SAM 3.1 'person'）：不参与测量，并保持在背景板前面。"),
    "source_geometry": ("Run MoGe Inference no vídeo fonte (todos os frames, pode ser reduzido).",
                        "Run MoGe Inference on the source video (all frames, can be downscaled).",
                        "对源视频运行 Run MoGe Inference（所有帧，可缩小）。"),
    "background": ("Foto do novo fundo.", "New background photo.", "新背景照片。"),
    "background_geometry": ("Run MoGe Inference na foto do novo fundo.", "Run MoGe Inference on the new background photo.",
                            "对新背景照片运行 Run MoGe Inference。"),
    "background_person_mask": ("Opcional: pessoa na foto de fundo (SAM3 Detect 'person'); cor e profundidade dela são apagadas.",
                               "Optional: person in the background photo (SAM3 Detect 'person'); its colour and depth are erased.",
                               "可选：背景照片中的人物（SAM3 Detect 'person'）；其颜色和深度会被抹掉。"),
    "translation": ("relative: o deslocamento da câmera é escalado pela profundidade das duas cenas (a paralaxe parece a do "
                    "vídeo real). metric: usa a medida direta. off: só rotação (sem paralaxe).",
                    "relative: camera travel is scaled by the depth of both scenes (parallax looks like the real video). "
                    "metric: uses the measurement as is. off: rotation only (no parallax).",
                    "relative：按两个场景的深度缩放镜头位移（视差看起来像真实视频）。metric：直接使用测量值。off：只有旋转（无视差）。"),
    "motion_scale": ("Multiplica o deslocamento da câmera (mais = mais paralaxe).", "Multiplies camera travel (more = more parallax).",
                     "放大镜头位移（越大视差越大）。"),
    "plate_scale": ("Quanto da foto sobra fora do quadro para a câmera andar.", "How much of the photo lies outside the frame for the camera to move into.",
                    "画面外留出多少照片供镜头移动。"),
    "hole_fill": ("Áreas que a câmera revela e a foto não tem: inpaint (preenche), magenta (convenção do LoRA CrossView-Warp), "
                  "grey (como o Meridian). magenta/grey: o H3 inventa o conteúdo.",
                  "Areas the camera reveals that the photo lacks: inpaint (filled), magenta (CrossView-Warp LoRA convention), "
                  "grey (like Meridian). magenta/grey: H3 invents the content.",
                  "镜头揭示而照片中没有的区域：inpaint（填充）、magenta（CrossView-Warp LoRA 约定）、grey（类似 Meridian）。magenta/grey：由 H3 生成内容。"),
    "render_width": ("Largura em que a placa é renderizada (depois ampliada). 1024 basta, o H3 refaz os detalhes.",
                     "Width the plate is rendered at (then enlarged). 1024 is enough, H3 redoes the detail.",
                     "背景板的渲染宽度（之后放大）。1024 足够，细节由 H3 重绘。"),
    "mask_grow": ("Margem em volta da pessoa ignorada na medição (px).", "Margin around the person ignored when measuring (px).",
                  "测量时忽略的人物周围边距（像素）。"),
    "smooth": ("Suaviza a câmera medida (frames).", "Smooths the measured camera (frames).", "平滑测得的镜头（帧数）。"),
    "feather": ("Borda suave da pessoa (px).", "Soft edge of the person (px).", "人物边缘柔化（像素）。"),
    "track_width": ("Largura usada para rastrear (px).", "Width used for tracking (px).", "用于跟踪的宽度（像素）。"),
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
