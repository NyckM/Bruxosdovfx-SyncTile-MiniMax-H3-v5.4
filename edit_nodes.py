"""bruxosdovfx • SyncTile Edit Conditioning (H3) — Viggle Remake / WepeNerd Ripple on SyncTile windows.

One node that rebuilds, PER REGION (spatial tile x temporal window = context window), the conditioning that
two H3 video-edit recipes feed the FL2VA model:

  mode "remake"  ComfyUI-Viggle-Remake: the source clip as <Video 1> (+ its 2 fps time labels), every edited
                 image as <Picture N> and, with edit_frames, also as a keyframe at that real frame.
  mode "ripple"  ComfyUI-WepeNerd H3 Ripple: plain prompt, the source window as a guide at its first frame and
                 every edited image as a guide at its frame.

Each window gets its own slice of the source (so a 600-frame clip is edited in context windows), every tile its
own crop, and only the edits that fall inside that window. Combine with the carry / latent-clip modes of the
SyncTile Guider so windows without an edit still follow the ones that have one.
"""
import logging

import torch

import comfy.utils
import node_helpers

log = logging.getLogger("bruxosdovfx.synctile")
CAT = "bruxosdovfx/SyncTile"
FPS = 24


def _st():
    try:
        from . import synctile_nodes as st
    except ImportError:                                     # loaded as a plain module (tests)
        import importlib
        st = importlib.import_module(__name__.rsplit(".", 1)[0] + ".synctile_nodes")
    return st


def stamps(nf):
    """The conditioner's 2 fps block labels for an nf-frame clip (same as ComfyUI-Viggle-Remake)."""
    idx, cursor = [], 0.0
    while round(cursor) < nf:
        if not idx or round(cursor) > idx[-1]:
            idx.append(round(cursor))
        cursor += FPS / 2
    t = [i / 2 for i in range(len(idx))]
    t += t[-1:] * (len(t) % 2)
    return [(t[i] + t[i + 1]) / 2 for i in range(0, len(t), 2)]


def _to_canvas(frames, width, height):
    frames = frames[..., :3]
    if tuple(frames.shape[1:3]) == (height, width):
        return frames
    return comfy.utils.common_upscale(frames.movedim(-1, 1), width, height, "bicubic", "center").movedim(1, -1)


def _from_ripple(ripple, latent):
    """Source window, empty AV latent and (edited image, frame) pairs from a WepeNerd Ripple Clip."""
    import sys
    mod = next((m for k, m in list(sys.modules.items())
                if k.endswith("ripple_node") and hasattr(m, "load_input_image") and hasattr(m, "edit_to_canvas")), None)
    if mod is None:
        raise RuntimeError("SyncTile Edit: the `ripple` input needs the ComfyUI-WepeNerd node pack.")
    rc = mod.rc
    length, geometry = ripple["length"], ripple["geometry"]
    markers, _ = rc.parse_markers(ripple["markers"], length)
    edits = []
    for m in markers:
        if not m.get("edited"):
            raise ValueError(f"SyncTile Edit: Ripple marker at frame {m['frame'] + 1} has no edited image. Upload, drop "
                             "or paste one on its Ripple Clip card.")
        img = mod.edit_to_canvas(mod.load_input_image(m["edited"]), geometry)
        edits.append((img, int(m["frame"])))
    if latent is None:
        from comfy_extras.nodes_minimax_h3 import _empty_av_latent
        latent, n = _empty_av_latent(ripple["width"], ripple["height"], length)
        if n != length:
            raise ValueError(f"SyncTile Edit: window length {length} is not a valid H3 length (17n+5).")
    return ripple["window"], latent, edits


class SyncTileEditConditioning:
    @classmethod
    def INPUT_TYPES(cls):
        st = _st()
        return {
            "required": {
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "prompt": ("STRING", {"multiline": True, "default": "", "forceInput": True,
                                      "tooltip": "remake: the six-section prompt, used verbatim. ripple: leave the "
                                                 "Ripple default prompt."}),
                "mode": (["remake", "ripple"], {"default": "remake"}),
                "tile_width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 32,
                                       "tooltip": "0 = AUTO from the canvas."}),
                "tile_height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 32}),
                "min_overlap": ("INT", {"default": 16, "min": 2, "max": 64}),
            },
            "optional": {
                "source": ("IMAGE", {"tooltip": "The source clip at 24 fps. Resized to the latent's canvas and sliced "
                                                "per context window. Not needed when `ripple` is connected."}),
                "latent": ("LATENT", {"tooltip": "The latent the guider will sample (sets canvas and length). Not "
                                                 "needed when `ripple` is connected: it is built from the Ripple Clip."}),
                "ripple": ("WN_RIPPLE", {"tooltip": "From WepeNerd 'Ripple Clip': the source window, the markers and "
                                                    "the edits you attached to them. Replaces source / edit_images / "
                                                    "edit_frames / latent."}),
                "edit_images": ("IMAGE", {"tooltip": "The edited / painted frames, as a batch (remake: <Picture 1..4>; "
                                                     "ripple: the edited frames)."}),
                "edit_frames": ("STRING", {"default": "", "tooltip": "Output frame of each edit image, 0-based, "
                                                                     "e.g. '12, 190' (-1 = last). Required for ripple; "
                                                                     "for remake it also pins them as keyframes."}),
                "window_frames": ("INT", {"default": 0, "min": 0, "max": 3600, "step": 1, "tooltip": st.WINDOW_TIP}),
                "window_overlap_frames": ("INT", {"default": 39, "min": 5, "max": 1000, "step": 17,
                                                  "tooltip": st.OVERLAP_TIP}),
            },
        }

    RETURN_TYPES = ("SYNCTILE_CONDS", "LATENT")
    RETURN_NAMES = ("tile_conditioning", "latent")
    FUNCTION = "encode"
    CATEGORY = CAT
    DESCRIPTION = ("Viggle Remake / H3 Ripple conditioning per SyncTile region: source slice per context window, "
                   "crop per tile, edits placed in the window that contains their frame.")

    def encode(self, clip, vae, prompt, mode, tile_width, tile_height, min_overlap, source=None, latent=None,
               ripple=None, edit_images=None, edit_frames="", window_frames=0, window_overlap_frames=39):
        st = _st()
        ripple_edits = None
        if ripple is not None:
            source, latent, ripple_edits = _from_ripple(ripple, latent)
        if source is None or latent is None:
            raise ValueError("SyncTile Edit: connect `source` and `latent`, or a Ripple Clip on `ripple`.")
        lat_h, lat_w, T, A, total = st._canvas(latent, 0, 0, 0)
        width, height = lat_w * st.STRIDE, lat_h * st.STRIDE
        regions = st.make_grid(lat_h, lat_w, tile_width, tile_height, min_overlap, T, A, window_frames,
                               window_overlap_frames)
        frames = st._parse_guide_frames(edit_frames)
        edits = []
        if ripple_edits is not None:
            edits = [(im, f) for im, f in ripple_edits]
        elif edit_images is not None:
            n = edit_images.shape[0]
            if frames and len(frames) not in (1, n) and n != 1:
                raise ValueError(f"SyncTile Edit: {n} edit image(s) but {len(frames)} frame(s) in edit_frames.")
            if not frames and mode == "ripple":
                raise ValueError("SyncTile Edit (ripple): type the frame of each edited image in edit_frames.")
            if n == 1 and len(frames) > 1:
                edits = [(edit_images[:1], f) for f in frames]
            else:
                edits = [(edit_images[i:i + 1], frames[i] if frames else None) for i in range(n)]
        edits = [(im, (f if f is None or f >= 0 else total + f)) for im, f in edits]
        for _, f in edits:
            if f is not None and not 0 <= f < total:
                raise ValueError(f"SyncTile Edit: frame {f} is outside the video's {total} frames.")
        if mode == "remake" and len(edits) > 4:
            raise ValueError("SyncTile Edit (remake): at most 4 edit images (<Picture 1..4>).")

        canvas_edits = [(_to_canvas(im, width, height), f) for im, f in edits]
        if source.shape[0] < total:
            log.warning("SyncTile Edit: the source has %d frames, the latent needs %d; the last frame is held.",
                        source.shape[0], total)
        win_cache = {}

        def window_frames_of(t, f0, fw):
            """Source frames of one window on the canvas (resized per window, not the whole clip at once)."""
            if t not in win_cache:
                win_cache.clear()
                win_cache[t] = _to_canvas(st._slice_frames(source, f0, fw), width, height)
            return win_cache[t]

        text_cache, enc_cache = {}, {}

        def text(fw):
            key = fw if mode == "remake" else 0
            if key not in text_cache:
                if mode == "remake":
                    segs = ["<Video 1>: ", *["<%.1f seconds>" % s for s in stamps(fw)],
                            *["<Picture %d>: " % (i + 1) for i in range(len(edits))], prompt]
                    toks = {"qwen3vl_32b": [[t for s in segs for t in clip.tokenize(s)["qwen3vl_32b"][0]]]}
                    text_cache[key] = clip.encode_from_tokens_scheduled(toks)
                else:
                    text_cache[key] = clip.encode_from_tokens_scheduled(clip.tokenize(prompt))
            return text_cache[key]

        def enc(tag, img, box):
            key = (tag, box)
            if key not in enc_cache:
                enc_cache[key] = vae.encode(img)
            return enc_cache[key]

        pbar = comfy.utils.ProgressBar(len(regions))
        conds, per_win = [], {}
        for r in regions:
            f0, fw = st.region_frames(r)
            fw = fw or total
            x, y, w, h = (v * st.STRIDE for v in r["box"])
            src = window_frames_of(r["t"], f0, fw)[:, y:y + h, x:x + w, :]
            cond = text(fw)
            keyframes, refs = [], []
            if mode == "remake":
                z = enc(("src", r["t"]), src, r["box"] + (r["t"],))
                refs.append({"kind": "video", "latent_t": z.shape[2], "latent_h": h // st.STRIDE,
                             "latent_w": w // st.STRIDE, "ref_audio_t": 0, "latent": z, "audio_latent": None})
                for i, (im, f) in enumerate(canvas_edits):
                    crop = im[:, y:y + h, x:x + w, :]
                    refs.append({"kind": "image", "latent_h": h // st.STRIDE, "latent_w": w // st.STRIDE,
                                 "latent": enc(("pic", i), crop, r["box"] + (i,))})
                    if f is not None and f0 <= f < f0 + fw:
                        keyframes.append({"resolved_frame_index": f - f0,
                                          "latent": enc(("kf", i), crop, r["box"] + (i,))})
                values = {"minimax_refs": refs}
            else:
                keyframes.append({"resolved_frame_index": 0,
                                  "latent": enc(("src", r["t"]), src, r["box"] + (r["t"],))})
                for i, (im, f) in enumerate(canvas_edits):
                    if f0 <= f < f0 + fw:
                        keyframes.append({"resolved_frame_index": f - f0,
                                          "latent": enc(("kf", i), im[:, y:y + h, x:x + w, :], r["box"] + (i,))})
                values = {}
            if keyframes:
                values["minimax_keyframes"] = keyframes
            cond = node_helpers.conditioning_set_values(cond, values)
            conds.append(cond)
            per_win.setdefault(r["t"], sum(1 for k in keyframes if k["resolved_frame_index"] >= 0) - (mode == "ripple"))
            pbar.update(1)
        n_win = len({r["t"] for r in regions})
        log.info("SyncTile Edit (%s): %d regions (%d tiles x %d windows), canvas %dx%d, %d frames, edits per window %s",
                 mode, len(regions), len(regions) // n_win, n_win, width, height, total, list(per_win.values()))
        return ({"canvas": (lat_h, lat_w), "T": T, "A": A, "tiles": regions, "conds": conds, "vae": vae}, latent)


NODE_CLASS_MAPPINGS = {"SyncTileEditConditioningH3": SyncTileEditConditioning}
NODE_DISPLAY_NAME_MAPPINGS = {"SyncTileEditConditioningH3": "bruxosdovfx • SyncTile Edit Conditioning (Remake / Ripple, H3)"}
