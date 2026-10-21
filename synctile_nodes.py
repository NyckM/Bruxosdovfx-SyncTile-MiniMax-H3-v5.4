"""SyncTile for MiniMax H3 as ComfyUI nodes.

Idea from alaintural/synctile-h3 (MIT): refine a large MiniMax H3 latent as
overlapping tiles that are blended after every sampling step, so all tiles agree
before the next step (MultiDiffusion, Bar-Tal et al. 2023).

Here the blending happens inside the sampler: the guider cuts the latent into
tiles on every model call, runs the model one tile at a time, and blends the
tiles' predictions with linear overlap ramps. The sampler only ever sees the
full canvas, so any sampler/scheduler works and the whole thing lives in one graph.

v5: regions are spatial tiles x temporal windows, so long videos (e.g. 600 frames) are denoised
as overlapping windows in one trajectory, and VRAM depends on the window, not on the length.

Nodes
  SyncTile Guider (MiniMax H3)              -> GUIDER, drop-in for BasicGuider
  SyncTile Ref2VA Conditioning (H3)         -> one conditioning per region (ref video sliced/cropped)
  SyncTile I2V Conditioning (H3)            -> first/last frame keyframes per region
  SyncTile Stream Decode to Video (H3)      -> chunked VAE decode straight into ffmpeg
"""
import logging
import math

import torch

import comfy.model_management
import comfy.model_patcher
import comfy.patcher_extension
import comfy.sampler_helpers
import comfy.samplers
import comfy.utils

log = logging.getLogger("SyncTile")
STRIDE = 16  # MiniMax H3 spatial latent downscale
MODE_PER_CALL = "per model call"
MODE_ORIGINAL = "SyncTile original (euler, per step)"
TEMPORAL_BLEND = "blend windows (joint)"
TEMPORAL_CARRY = "carry previous frames (sequential)"


def _pack(parts):
    """Pack video(+audio) streams the way the sampler carries them; a lone video latent stays as is."""
    return parts[0] if len(parts) == 1 else comfy.utils.pack_latents(parts)[0]


def _unpack(x, shapes):
    return [x] if len(shapes) == 1 else comfy.utils.unpack_latents(x, shapes)


# --------------------------------------------------------------------------- grid (space x time)
FPS = 24
AUDIO_HZ = 40


def positions(length, tile, min_overlap):
    if tile >= length:
        return [0]
    n = max(2, math.ceil((length - min_overlap) / (tile - min_overlap)))
    return [round(i * (length - tile) / (n - 1)) for i in range(n)]


def ramp_spans(spans, i):
    """1D weight for span i of a sorted list of (start, length): 0->1 ramps where it overlaps its neighbours."""
    s, n = spans[i]
    w = torch.ones(n)
    if i > 0:
        ps, pn = spans[i - 1]
        o = min(n, ps + pn - s)
        if o > 0:
            w[:o] = torch.linspace(0, 1, o + 2)[1:-1]
    if i < len(spans) - 1:
        ns, _ = spans[i + 1]
        o = min(n, s + n - ns)
        if o > 0:
            w[-o:] = torch.minimum(w[-o:], torch.linspace(1, 0, o + 2)[1:-1])
    return w


def ramp(p, tile, all_pos):
    """Spatial 1D weight (kept for compatibility)."""
    spans = [(q, tile) for q in sorted(all_pos)]
    return ramp_spans(spans, spans.index((p, tile)))


def tokens_for_frames(frames):
    """MiniMax H3 latent length for a 17k+5 frame count (rounded down to the grid)."""
    return 2 + 5 * max(0, (int(frames) - 5) // 17)


def frames_for_tokens(tokens):
    return 5 if tokens <= 2 else (tokens - 2) // 5 * 17 + 5


def audio_ticks(frames):
    return round(frames / FPS * AUDIO_HZ)


def time_windows(T, window_frames=0, overlap_frames=39):
    """Windows over the latent time axis: (start_token, length_tokens).

    Every window starts on a 5-token boundary (a 1-frame token, like a clip start) and is 5j+2 tokens
    long, so it is a valid MiniMax H3 clip of 17j+5 frames. Overlap snaps to 17q+5 frames.
    """
    if not window_frames or window_frames <= 0:
        return [(0, T)]
    L = tokens_for_frames(max(22, window_frames))
    if L >= T:
        return [(0, T)]
    O = 2 + 5 * max(0, round((int(overlap_frames) - 5) / 17))
    O = max(2, min(O, L - 5))
    n = max(2, math.ceil((T - O) / (L - O)))
    starts = sorted({min(T - L, int(round(i * (T - L) / (n - 1) / 5)) * 5) for i in range(n)})
    return [(s, L) for s in starts]


def make_grid(lat_h, lat_w, tile_px_w, tile_px_h, min_overlap, T=None, A=None, window_frames=0, overlap_frames=39):
    """Regions in latent units: spatial box x temporal window, with their blend weights.

    Each region: box (x, y, w, h), t (t0, tn) in latent tokens, a (a0, an) in audio ticks or None,
    weight (h, w) spatial, tw (tn,) temporal, aw (an,) audio.
    """
    tw_, th_ = min(tile_px_w // STRIDE, lat_w), min(tile_px_h // STRIDE, lat_h)
    xs, ys = positions(lat_w, tw_, min_overlap), positions(lat_h, th_, min_overlap)
    xspans, yspans = [(x, tw_) for x in xs], [(y, th_) for y in ys]
    if T is None:                                   # space only: the guider fills in the full time span
        return [{"box": (x, y, tw_, th_), "t": None, "a": None, "window": 0,
                 "weight": ramp_spans(yspans, yi)[:, None] * ramp_spans(xspans, xi)[None, :], "tw": None, "aw": None}
                for yi, y in enumerate(ys) for xi, x in enumerate(xs)]
    windows = time_windows(T, window_frames, overlap_frames)
    total_frames = frames_for_tokens(T)
    a_spans = []
    for (t0, tn) in windows:
        if A is None:
            a_spans.append(None)
            continue
        if len(windows) == 1:
            a_spans.append((0, A))
            continue
        f0, fw = 17 * (t0 // 5), frames_for_tokens(tn)
        an = min(A, audio_ticks(fw))
        a0 = max(0, min(audio_ticks(f0), A - an))
        a_spans.append((a0, an))
    regions = []
    for wi, (t0, tn) in enumerate(windows):
        tw = ramp_spans(windows, wi)
        aw = ramp_spans(a_spans, wi) if a_spans[wi] is not None else None
        for yi, y in enumerate(ys):
            for xi, x in enumerate(xs):
                regions.append({"box": (x, y, tw_, th_), "t": (t0, tn), "a": a_spans[wi], "window": wi,
                                "weight": ramp_spans(yspans, yi)[:, None] * ramp_spans(xspans, xi)[None, :],
                                "tw": tw, "aw": aw})
    return regions


def region_frames(r):
    """Pixel frames covered by a region: (first_frame, frame_count)."""
    t0, tn = r.get("t", (0, None)) if r.get("t") else (0, None)
    return 17 * (t0 // 5), (frames_for_tokens(tn) if tn else None)


def _grid_signature(regions):
    return [(r["box"], r.get("t")) for r in regions]


# --------------------------------------------------------------------------- guider
class SyncTileGuiderImpl(comfy.samplers.CFGGuider):
    def __init__(self, model_patcher, tile_w, tile_h, min_overlap, tile_conds=None):
        super().__init__(model_patcher)
        self.tile_w, self.tile_h, self.min_overlap = tile_w, tile_h, min_overlap
        self.tile_conds = tile_conds  # None -> every region uses the shared positive/negative
        self.mode = MODE_PER_CALL
        self.refine_seed = None       # int -> own noise for this pass instead of the sampler's
        self.active_tile = None       # set while the original mode samples one region
        self.detail_conds = None      # SYNCTILE_CONDS used once sigma drops below detail_sigma
        self.detail_sigma = 0.85
        self.window_frames, self.window_overlap = 0, 39
        self.temporal_mode, self.carry_frames = TEMPORAL_BLEND, 21

    # ---- grid for the latent being sampled
    def _grid(self, latent_shapes):
        if latent_shapes is None or len(latent_shapes[0]) != 5:
            raise ValueError("SyncTile expects a MiniMax H3 video latent [B, C, T, H, W] (audio+video AV latent).")
        T, lat_h, lat_w = latent_shapes[0][2], latent_shapes[0][3], latent_shapes[0][4]
        A = latent_shapes[1][-1] if len(latent_shapes) > 1 else None
        if self.tile_conds is not None:
            tc = self.tile_conds
            if tuple(tc["canvas"]) != (lat_h, lat_w):
                ch, cw = tc["canvas"]
                raise ValueError(f"SyncTile: the tile conditioning was built for a {cw * STRIDE}x{ch * STRIDE} canvas, "
                                 f"but the latent is {lat_w * STRIDE}x{lat_h * STRIDE}. Set the same width/height on both.")
            if tc.get("T") is not None and tc["T"] != T:
                raise ValueError(f"SyncTile: the tile conditioning was built for {frames_for_tokens(tc['T'])} frames, "
                                 f"but the latent has {frames_for_tokens(T)}. Connect the same latent to both.")
            regions = tc["tiles"]
            if any(r.get("t") is None for r in regions):       # conditioning from an older, space-only node
                regions = [dict(r, t=(0, T), a=(0, A) if A is not None else None, tw=torch.ones(T),
                                aw=torch.ones(A) if A is not None else None) for r in regions]
            return regions
        return make_grid(lat_h, lat_w, self.tile_w, self.tile_h, self.min_overlap, T, A,
                         getattr(self, "window_frames", 0), getattr(self, "window_overlap", 39))

    @staticmethod
    def _tile_shapes(latent_shapes, r):
        if not isinstance(r, dict):                 # old call style: a bare box
            r = {"box": r}
        x, y, w, h = r["box"]
        v = latent_shapes[0]
        tn = r["t"][1] if r.get("t") else v[2]
        shapes = [torch.Size([v[0], v[1], tn, h, w])]
        for s in latent_shapes[1:]:
            an = r["a"][1] if r.get("a") else s[-1]
            shapes.append(torch.Size(list(s[:-1]) + [an]))
        return shapes

    @staticmethod
    def _crop_pack(packed, latent_shapes, r):
        if not isinstance(r, dict):
            r = {"box": r}
        x, y, w, h = r["box"]
        parts = _unpack(packed, latent_shapes)
        if r.get("t"):
            t0, tn = r["t"]
            parts[0] = parts[0][:, :, t0:t0 + tn, y:y + h, x:x + w]
        else:
            parts[0] = parts[0][..., y:y + h, x:x + w]
        if r.get("a"):
            a0, an = r["a"]
            parts[1:] = [p[..., a0:a0 + an] for p in parts[1:]]
        return _pack(parts)

    # ---- size the VRAM estimate by one region, not by the whole canvas
    def outer_sample(self, noise, latent_image, sampler, sigmas, denoise_mask=None, callback=None,
                     disable_pbar=False, seed=None, latent_shapes=None):
        self.grid = self._grid(latent_shapes)
        sizes = [self._tile_shapes(latent_shapes, r) for r in self.grid]
        largest = max(sizes, key=lambda sh: sum(math.prod(s[1:]) for s in sh))
        tile_shape = ([noise.shape[0], 1, sum(math.prod(s[1:]) for s in largest)] if len(latent_shapes) > 1
                      else list(largest[0]))
        original = comfy.sampler_helpers.prepare_sampling

        def prepare_for_tile(model, noise_shape, conds, *args, **kwargs):
            return original(model, tile_shape, conds, *args, **kwargs)

        comfy.sampler_helpers.prepare_sampling = prepare_for_tile
        try:
            return super().outer_sample(noise, latent_image, sampler, sigmas, denoise_mask, callback,
                                        disable_pbar, seed, latent_shapes=latent_shapes)
        finally:
            comfy.sampler_helpers.prepare_sampling = original

    # ---- process the conditioning once per region, at region size
    def inner_sample(self, noise, latent_image, device, sampler, sigmas, denoise_mask, callback, disable_pbar,
                     seed, latent_shapes=None):
        if denoise_mask is not None:
            log.warning("SyncTile: denoise masks are not supported and will be ignored.")
        self.inner_model.latent_shapes = latent_shapes
        if latent_image is not None and torch.count_nonzero(latent_image) > 0:
            latent_image = self.inner_model.process_latent_in(latent_image)

        self.full_shapes = latent_shapes
        self._device, self._seed = device, seed
        n_windows = len({r.get("t") for r in self.grid})
        self.tiles = []
        for i, r in enumerate(self.grid):
            shapes = self._tile_shapes(latent_shapes, r)
            if self.tile_conds is not None:
                raw = {"positive": comfy.sampler_helpers.convert_cond(self.tile_conds["conds"][i])}
                if "negative" in self.conds:
                    raw["negative"] = [c.copy() for c in self.conds["negative"]]
            else:
                raw = {k: [c.copy() for c in v] for k, v in self.conds.items()}
                _check_shared_keyframes(raw, r["box"], n_windows)
            tnoise, timage = self._crop_pack(noise, latent_shapes, r), self._crop_pack(latent_image, latent_shapes, r)
            tconds = comfy.samplers.process_conds(self.inner_model, tnoise, raw, device, timage, None, seed,
                                                  latent_shapes=shapes)
            dconds, draw = None, None
            if getattr(self, "detail_conds", None) is not None:
                draw = {"positive": comfy.sampler_helpers.convert_cond(self.detail_conds["conds"][i])}
                if "negative" in raw:
                    draw["negative"] = [c.copy() for c in raw["negative"]]
                dconds = comfy.samplers.process_conds(self.inner_model, tnoise, draw, device, timage, None, seed,
                                                      latent_shapes=shapes)
            t0, tn = r["t"]
            w3 = r["tw"].view(-1, 1, 1) * r["weight"][None]
            self.tiles.append({"box": r["box"], "t": (t0, tn), "a": r.get("a"), "shapes": shapes,
                               "raw": raw, "draw": draw if dconds is not None else None,
                               "conds": tconds, "conds_detail": dconds,
                               "w3": w3.to(device=device, dtype=torch.float32),
                               "w2": r["weight"].to(device=device, dtype=torch.float32),
                               "aw": r["aw"].to(device=device, dtype=torch.float32) if r.get("aw") is not None else None})
        self.conds = self.tiles[0]["conds"]  # what generic code paths see; predict_noise uses per-region conds

        if self.refine_seed is not None:
            gen = torch.Generator().manual_seed(self.refine_seed)
            noise = torch.randn(noise.shape, generator=gen, dtype=torch.float32).to(noise.device, noise.dtype)
        n_tiles = len(self.tiles) // max(1, n_windows)
        log.info("SyncTile: %d regions (%d tiles x %d windows) on a %dx%d canvas, %d frames, mode=%s, noise=%s",
                 len(self.tiles), n_tiles, n_windows, latent_shapes[0][4] * STRIDE, latent_shapes[0][3] * STRIDE,
                 frames_for_tokens(latent_shapes[0][2]), self.mode,
                 f"refine_seed {self.refine_seed}" if self.refine_seed is not None else "sampler")

        extra_model_options = comfy.model_patcher.create_model_options_clone(self.model_options)
        extra_model_options.setdefault("transformer_options", {})["sample_sigmas"] = sigmas
        extra_args = {"model_options": extra_model_options, "seed": seed}
        carry = getattr(self, "temporal_mode", TEMPORAL_BLEND) == TEMPORAL_CARRY and n_windows > 1
        if carry:
            if self.mode == MODE_ORIGINAL:
                log.warning("SyncTile: 'carry previous frames' uses the connected sampler; sync_mode original is ignored.")
            samples = self._sample_carry(noise, latent_image, sampler, sigmas, extra_args, callback, disable_pbar)
        elif self.mode == MODE_ORIGINAL:
            samples = self._sample_original(noise, latent_image, sigmas, extra_args, callback)
        else:
            executor = comfy.patcher_extension.WrapperExecutor.new_class_executor(
                sampler.sample, sampler,
                comfy.patcher_extension.get_all_wrappers(comfy.patcher_extension.WrappersMP.SAMPLER_SAMPLE,
                                                         extra_args["model_options"], is_model_options=True))
            samples = executor.execute(self, sigmas, extra_args, callback, noise, latent_image, None, disable_pbar)
        return self.inner_model.process_latent_out(samples.to(torch.float32))

    # ---- sequential windows: each window starts from the finished frames of the previous one
    def _sample_carry(self, noise, latent_image, sampler, sigmas, extra_args, callback, disable_pbar):
        """Windows run one after another. The first carry tokens of window k are locked (inpaint mask) to the
        finished result of window k-1, so the model sees those frames as context and continues from them;
        the rest of the overlap is cross-faded between the two (consistent) results. Spatial tiles inside a
        window are still blended at every model call."""
        full_shapes, all_tiles = self.full_shapes, self.tiles
        old_ls = getattr(self.inner_model, "latent_shapes", None)
        windows = sorted({(r["t"], r["a"]) for r in all_tiles}, key=lambda w: w[0][0])
        carry_tok = 1 + math.ceil((max(1, int(getattr(self, "carry_frames", 21))) - 1) / 4)
        canvas = [p.clone() for p in _unpack(latent_image, full_shapes)]
        noise_parts = _unpack(noise, full_shapes)
        v = full_shapes[0]
        steps = len(sigmas) - 1
        prev = None

        def window_slice(parts, t, a):
            out = [parts[0][:, :, t[0]:t[0] + t[1]]]
            if len(parts) > 1:
                out += [p[..., a[0]:a[0] + a[1]] for p in parts[1:]]
            return out

        try:
            for k, (t, a) in enumerate(windows):
                t0, tn = t
                wshapes = [torch.Size([v[0], v[1], tn, v[3], v[4]])]
                wshapes += [torch.Size(list(sh[:-1]) + [a[1]]) for sh in full_shapes[1:]]
                self.tiles = [dict(r, t=(0, tn), a=(0, a[1]) if a else None,
                                   w3=r["w2"][None].expand(tn, -1, -1),
                                   aw=torch.ones(a[1], device=r["w2"].device) if a else None)
                              for r in all_tiles if r["t"] == t]
                self.full_shapes = wshapes
                self.inner_model.latent_shapes = wshapes
                wnoise = _pack(window_slice(noise_parts, t, a))
                wlat = _pack(window_slice(canvas, t, a))
                mask, c, ac = None, 0, 0
                if prev is not None:
                    (pt0, ptn), pa = prev
                    ov = max(0, min(tn, pt0 + ptn - t0))
                    c = min(carry_tok, ov, tn - 1)
                    mparts = [torch.ones(wshapes[0], dtype=noise.dtype, device=noise.device)]
                    mparts[0][:, :, :c] = 0
                    if a:
                        aov = max(0, pa[0] + pa[1] - a[0])
                        ac = min(audio_ticks(1 + 4 * (c - 1)), aov) if c > 0 else 0
                        for sh in wshapes[1:]:
                            m = torch.ones(sh, dtype=noise.dtype, device=noise.device)
                            m[..., :ac] = 0
                            mparts.append(m)
                    mask = _pack(mparts)
                    # H3 runs masked (locked) tokens at its conditioning timestep only when the conds carry the
                    # mask, so rebuild this window's conds with it (the sampler then injects those tokens clean)
                    for tr in self.tiles:
                        loc = {"box": tr["box"], "t": (0, tn), "a": (0, a[1]) if a else None}
                        rn = self._crop_pack(wnoise, wshapes, loc)
                        ri = self._crop_pack(wlat, wshapes, loc)
                        rm = self._crop_pack(mask, wshapes, loc)
                        raw = {k2: [c.copy() for c in v2] for k2, v2 in tr["raw"].items()}
                        tr["conds"] = comfy.samplers.process_conds(self.inner_model, rn, raw, self._device, ri, rm,
                                                                   self._seed, latent_shapes=tr["shapes"])
                        if tr.get("draw") is not None:
                            draw = {k2: [c.copy() for c in v2] for k2, v2 in tr["draw"].items()}
                            tr["conds_detail"] = comfy.samplers.process_conds(self.inner_model, rn, draw, self._device,
                                                                              ri, rm, self._seed,
                                                                              latent_shapes=tr["shapes"])

                def cb(i, x0, x, total, t=t, a=a):
                    if callback is None:
                        return
                    full = [p.clone() for p in canvas]
                    w = _unpack(x0, wshapes)
                    full[0][:, :, t[0]:t[0] + t[1]] = w[0].to(full[0].dtype)
                    for j in range(1, len(full)):
                        full[j][..., a[0]:a[0] + a[1]] = w[j].to(full[j].dtype)
                    fp = _pack(full)
                    callback(i, fp, fp, total)

                log.info("SyncTile carry: window %d/%d, frames %d-%d, %d locked tokens (~%d frames) from the previous window",
                         k + 1, len(windows), 17 * (t0 // 5), 17 * (t0 // 5) + frames_for_tokens(tn) - 1, c,
                         0 if c == 0 else 1 + 4 * (c - 1))
                executor = comfy.patcher_extension.WrapperExecutor.new_class_executor(
                    sampler.sample, sampler,
                    comfy.patcher_extension.get_all_wrappers(comfy.patcher_extension.WrappersMP.SAMPLER_SAMPLE,
                                                             extra_args["model_options"], is_model_options=True))
                wargs = {"model_options": extra_args["model_options"], "seed": extra_args.get("seed")}
                res = _unpack(executor.execute(self, sigmas, wargs, cb, wnoise, wlat, mask, disable_pbar), wshapes)

                # write back: locked tokens stay, the rest of the overlap cross-fades, the remainder is new
                if prev is None:
                    canvas[0][:, :, t0:t0 + tn] = res[0].to(canvas[0].dtype)
                    for j in range(1, len(canvas)):
                        canvas[j][..., a[0]:a[0] + a[1]] = res[j].to(canvas[j].dtype)
                else:
                    (pt0, ptn), pa = prev
                    ov = max(0, min(tn, pt0 + ptn - t0))
                    fade = torch.ones(tn, device=canvas[0].device)
                    fade[:c] = 0
                    if ov > c:
                        fade[c:ov] = torch.linspace(0, 1, ov - c + 2, device=fade.device)[1:-1]
                    f = fade.view(1, 1, -1, 1, 1).to(canvas[0].dtype)
                    seg = canvas[0][:, :, t0:t0 + tn]
                    canvas[0][:, :, t0:t0 + tn] = seg * (1 - f) + res[0].to(seg.dtype) * f
                    if a:
                        aov = max(0, pa[0] + pa[1] - a[0])
                        af = torch.ones(a[1], device=canvas[0].device)
                        af[:ac] = 0
                        if aov > ac:
                            af[ac:aov] = torch.linspace(0, 1, aov - ac + 2, device=af.device)[1:-1]
                        for j in range(1, len(canvas)):
                            sg = canvas[j][..., a[0]:a[0] + a[1]]
                            canvas[j][..., a[0]:a[0] + a[1]] = sg * (1 - af.to(sg.dtype)) + res[j].to(sg.dtype) * af.to(sg.dtype)
                prev = (t, a)
                comfy.model_management.throw_exception_if_processing_interrupted()
        finally:
            self.tiles, self.full_shapes = all_tiles, full_shapes
            self.inner_model.latent_shapes = old_ls
        out = _pack(canvas)
        if callback is not None:
            callback(steps - 1, out, out, steps)
        return out

    # ---- shared region loop: run fn on every region, blend video (space x time) and audio (time)
    def _blend_regions(self, x, fn):
        parts = _unpack(x, self.full_shapes)
        video = parts[0]
        acc = torch.zeros_like(video, dtype=torch.float32)
        wsum = torch.zeros(video.shape[2:], device=video.device, dtype=torch.float32)
        audio = parts[1:]
        aacc = [torch.zeros_like(p, dtype=torch.float32) for p in audio]
        asum = torch.zeros(audio[0].shape[-1], device=video.device, dtype=torch.float32) if audio else None
        for r in self.tiles:
            bx, by, bw, bh = r["box"]
            t0, tn = r["t"]
            vsl = (slice(None), slice(None), slice(t0, t0 + tn), slice(by, by + bh), slice(bx, bx + bw))
            sub = [video[vsl]]
            if audio:
                a0, an = r["a"]
                sub += [p[..., a0:a0 + an] for p in audio]
            out = _unpack(fn(r, _pack(sub)), r["shapes"])
            acc[vsl] += out[0].float() * r["w3"]
            wsum[t0:t0 + tn, by:by + bh, bx:bx + bw] += r["w3"]
            if audio:
                for k, o in enumerate(out[1:]):
                    aacc[k][..., a0:a0 + an] += o.float() * r["aw"]
                asum[a0:a0 + an] += r["aw"]
            comfy.model_management.throw_exception_if_processing_interrupted()
        blended = [acc / wsum.clamp(min=1e-6)]
        blended += [a / asum.clamp(min=1e-6) for a in aacc]
        return _pack([b.to(x.dtype) for b in blended])

    # ---- SyncTile original: each region takes one euler step on its own, then all regions are blended
    def _sample_original(self, noise, latent_image, sigmas, extra_args, callback):
        """Same loop as alaintural/synctile-h3: shared canvas noise, one euler step per region,
        blend the regions' states after every step."""
        ms = self.inner_model.model_sampling
        euler = comfy.samplers.sampler_object("euler")
        # sampler convention: the state is carried as y = x / (1 - sigma); KSAMPLER re-applies (1 - sigma)
        y = ms.inverse_noise_scaling(sigmas[0], ms.noise_scaling(sigmas[0], noise, latent_image))
        steps = len(sigmas) - 1
        pbar = comfy.utils.ProgressBar(steps * len(self.tiles))

        for s in range(steps):
            def one_step(r, ty, s=s):
                self.active_tile = r
                try:
                    return euler.sample(self, sigmas[s:s + 2], extra_args, None, torch.zeros_like(ty), ty, None, True)
                finally:
                    self.active_tile = None
                    pbar.update(1)
            y = self._blend_regions(y, one_step)
            if callback is not None:
                callback(s, y, y, steps)
        return y

    # ---- every model call: run each region, blend the predictions
    def _conds_for(self, t, timestep):
        """Structure conditioning while the composition is still open, detail conditioning below detail_sigma."""
        if t["conds_detail"] is not None and float(timestep.max()) < self.detail_sigma:
            return t["conds_detail"]
        return t["conds"]

    def _run(self, r, x, timestep, model_options, seed):
        c = self._conds_for(r, timestep)
        return comfy.samplers.sampling_function(self.inner_model, x, timestep, c.get("negative"), c.get("positive"),
                                                self.cfg, model_options=model_options, seed=seed)

    def predict_noise(self, x, timestep, model_options={}, seed=None):
        if self.active_tile is not None:  # original mode: x is one region
            return self._run(self.active_tile, x, timestep, model_options, seed)
        return self._blend_regions(x, lambda r, tx: self._run(r, tx, timestep, model_options, seed))


WINDOW_TIP = ("Temporal window in frames (17k+5: 124 = 5.2 s, 243 = 10.1 s). 0 = whole clip in one pass. "
              "Long videos are denoised as overlapping windows blended at every model call (one trajectory, "
              "no chained clips), so VRAM depends on the window, not on the total length.")
OVERLAP_TIP = "Overlap between windows in frames, snapped to 17k+5 (5, 22, 39, 56, 73, 90). More = smoother, slower."


class SyncTileGuider:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "tile_width": ("INT", {"default": 1472, "min": 256, "max": 8192, "step": 32,
                                       "tooltip": "Tile size in pixels. 1472x896 is what SyncTile measured on 24 GB. "
                                                  "A tile larger than the canvas = no spatial tiling."}),
                "tile_height": ("INT", {"default": 896, "min": 256, "max": 8192, "step": 32}),
                "min_overlap": ("INT", {"default": 16, "min": 2, "max": 64,
                                        "tooltip": "Minimum overlap between tiles, in latent cells (x16 px)."}),
                "cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 30.0, "step": 0.1,
                                  "tooltip": "1.0 = like BasicGuider (positive only). Above 1 uses the negative."}),
                "sync_mode": ([MODE_PER_CALL, MODE_ORIGINAL], {"default": MODE_PER_CALL, "tooltip":
                              "per model call: regions blended inside every model call; uses the sampler you connected.\n"
                              "SyncTile original: like the script, each region takes one euler step alone, then the "
                              "regions are blended; the connected sampler is ignored (always euler)."}),
                "use_refine_seed": ("BOOLEAN", {"default": False, "tooltip":
                                    "On: this pass uses its own noise from refine_seed. Change only this seed to try new "
                                    "refines while the first stage and the tile conditionings stay cached."}),
                "refine_seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": True}),
            },
            "optional": {
                "positive": ("CONDITIONING", {"tooltip": "Shared conditioning for every region (ignored when tile_conditioning is connected)."}),
                "negative": ("CONDITIONING",),
                "tile_conditioning": ("SYNCTILE_CONDS", {"tooltip": "Per-region conditioning from a SyncTile conditioning node. Its grid (tiles and windows) is used."}),
                "tile_conditioning_detail": ("SYNCTILE_CONDS", {"tooltip":
                    "Optional second per-region conditioning used once sigma < detail_below_sigma (the detail steps). "
                    "Same grid as tile_conditioning."}),
                "detail_below_sigma": ("FLOAT", {"default": 0.85, "min": 0.0, "max": 1.0, "step": 0.005, "tooltip":
                    "Switch point. Steps that start at sigma >= this use tile_conditioning (structure), lower ones use "
                    "tile_conditioning_detail. With 0.878/0.8/0.6316: 0.85 = 1 structure + 2 detail steps (balanced), "
                    "0.7 = 2 + 1 (safer), 1.0 = all detail."}),
                "window_frames": ("INT", {"default": 0, "min": 0, "max": 3600, "step": 1, "tooltip":
                                  WINDOW_TIP + " Only used with 'positive'; with tile_conditioning the windows come from that node."}),
                "window_overlap_frames": ("INT", {"default": 39, "min": 5, "max": 1000, "step": 17, "tooltip": OVERLAP_TIP}),
                "temporal_mode": ([TEMPORAL_BLEND, TEMPORAL_CARRY], {"default": TEMPORAL_BLEND}),
                "carry_frames": ("INT", {"default": 21, "min": 1, "max": 200, "step": 4}),
            },
        }

    RETURN_TYPES = ("GUIDER",)
    FUNCTION = "get_guider"
    CATEGORY = "bruxosdovfx/SyncTile"
    DESCRIPTION = ("MiniMax H3 SyncTile: denoises a large or long latent as overlapping regions (spatial tiles x "
                   "temporal windows) blended after every model call.")

    def get_guider(self, model, tile_width, tile_height, min_overlap, cfg, sync_mode=None, use_refine_seed=False,
                   refine_seed=0, positive=None, negative=None, tile_conditioning=None,
                   tile_conditioning_detail=None, detail_below_sigma=0.85, window_frames=0, window_overlap_frames=39,
                   temporal_mode=TEMPORAL_BLEND, carry_frames=21):
        if positive is None and tile_conditioning is None:
            raise ValueError("SyncTile Guider: connect either positive or tile_conditioning.")
        if tile_conditioning_detail is not None:
            if tile_conditioning is None:
                raise ValueError("SyncTile Guider: tile_conditioning_detail needs tile_conditioning too.")
            if (tuple(tile_conditioning_detail["canvas"]) != tuple(tile_conditioning["canvas"])
                    or _grid_signature(tile_conditioning_detail["tiles"]) != _grid_signature(tile_conditioning["tiles"])):
                raise ValueError("SyncTile Guider: the two tile conditionings use different grids. Set the same "
                                 "tile size, overlap, window_frames and latent on both.")
        g = SyncTileGuiderImpl(model, tile_width, tile_height, min_overlap, tile_conditioning)
        g.detail_conds, g.detail_sigma = tile_conditioning_detail, float(detail_below_sigma)
        g.mode = sync_mode or MODE_PER_CALL
        g.refine_seed = int(refine_seed) if use_refine_seed else None
        g.window_frames, g.window_overlap = int(window_frames or 0), int(window_overlap_frames)
        g.temporal_mode, g.carry_frames = temporal_mode or TEMPORAL_BLEND, int(carry_frames)
        conds = {"positive": positive if positive is not None else tile_conditioning["conds"][0]}
        if negative is not None and cfg != 1.0:
            conds["negative"] = negative
        g.inner_set_conds(conds)
        g.set_cfg(cfg)
        return (g,)


# --------------------------------------------------------------------------- shared helpers for the conditioning nodes
def _center_crop_box(src_w, src_h, aspect):
    """Region of the source that a center crop to `aspect` keeps."""
    if src_w / src_h > aspect:
        w = round(src_h * aspect)
        return (src_w - w) // 2, 0, w, src_h
    h = round(src_w / aspect)
    return 0, (src_h - h) // 2, src_w, h


def _canvas_from_latent(latent):
    s = latent["samples"]
    parts = s.unbind() if getattr(s, "is_nested", False) else [s]
    v = parts[0]
    A = parts[1].shape[-1] if len(parts) > 1 else None
    return v.shape[-2], v.shape[-1], v.shape[2], A          # lat_h, lat_w, latent_t, audio ticks


def _frames_from_latent_t(t):
    return frames_for_tokens(t)


def _canvas(latent, width, height, length):
    """(lat_h, lat_w, T, A, total_frames) from the latent, or from the widgets when no latent is connected."""
    if latent is not None:
        lat_h, lat_w, T, A = _canvas_from_latent(latent)
    else:
        lat_h, lat_w = height // STRIDE, width // STRIDE
        T = tokens_for_frames(length)
        A = audio_ticks(frames_for_tokens(T))
    return lat_h, lat_w, T, A, frames_for_tokens(T)


def _slice_frames(frames, f0, n):
    """frames[f0:f0+n], padded by holding the last frame when the source is shorter."""
    if frames is None:
        return None
    part = frames[f0:f0 + n]
    if part.shape[0] == 0:
        part = frames[-1:]
    if part.shape[0] < n:
        part = torch.cat([part, part[-1:].repeat(n - part.shape[0], 1, 1, 1)], dim=0)
    return part


def _slice_audio(audio, f0, n):
    if audio is None:
        return None
    sr = audio["sample_rate"]
    a, b = round(f0 / FPS * sr), round((f0 + n) / FPS * sr)
    wav = audio["waveform"][..., a:b]
    if wav.shape[-1] < 1:
        return None
    return {"waveform": wav, "sample_rate": sr}


def _guide_keyframes(guides, regions, width, height, total_frames, vae):
    """Frame guides (image, frame index) placed in every region whose window contains that frame,
    cropped to the region's tile. Returns one keyframe list per region."""
    from comfy_extras.nodes_minimax_h3 import _resize
    out = [[] for _ in regions]
    if not guides:
        return out
    if vae is None:
        raise ValueError("SyncTile: frame guides need the vae input.")
    cache = {}
    for gi, (image, frame_idx) in enumerate(guides):
        f = frame_idx if frame_idx >= 0 else total_frames + frame_idx
        if not 0 <= f < total_frames:
            raise ValueError(f"SyncTile: guide frame {frame_idx} is outside the video's {total_frames} frames.")
        canvas_img = _resize(image[:1], width, height, "center")          # same geometry as MiniMaxH3AddGuide
        for ri, r in enumerate(regions):
            f0, fw = region_frames(r)
            fw = fw if fw is not None else total_frames
            if not f0 <= f < f0 + fw:
                continue
            x, y, w, h = (v * STRIDE for v in r["box"])
            key = (gi, r["box"])            # gi = guide index
            if key not in cache:
                cache[key] = vae.encode(canvas_img[:, y:y + h, x:x + w, :])
            out[ri].append({"resolved_frame_index": f - f0, "latent": cache[key]})
    return out


def _with_keyframes(cond, keyframes):
    if not keyframes:
        return cond
    import node_helpers
    existing = list(cond[0][1].get("minimax_keyframes", [])) if cond else []
    return node_helpers.conditioning_set_values(cond, {"minimax_keyframes": existing + keyframes})


def _guides_from(img1, f1, img2, f2):
    return [(im, int(f)) for im, f in ((img1, f1), (img2, f2)) if im is not None]


GUIDE_INPUTS = {
    "guide_image_1": ("IMAGE", {"tooltip": "Frame guide (like Add Guide for MiniMax H3). Placed in the window that "
                                           "contains guide_frame_1, cropped per tile."}),
    "guide_frame_1": ("INT", {"default": 1, "min": -9999, "max": 9999, "tooltip": "Frame of the whole video. -1 = last."}),
    "guide_image_2": ("IMAGE",),
    "guide_frame_2": ("INT", {"default": -1, "min": -9999, "max": 9999}),
    "guide_images": ("IMAGE", {"tooltip": "Batch of frame guides (any number). Image k goes to the k-th frame in "
                                          "guide_frames. Batch the stills with an Image Batch node."}),
    "guide_frames": ("STRING", {"default": "", "tooltip": "Frames for guide_images, in order, e.g. '1, 150, 300, 450' "
                                                          "(-1 = last frame). One image + several frames = the same "
                                                          "image at each frame."}),
}


def _parse_guide_frames(text):
    import re
    try:
        return [int(x) for x in re.split(r"[,;\s]+", (text or "").strip()) if x]
    except ValueError:
        raise ValueError(f"SyncTile: guide_frames must be whole numbers separated by commas, got '{text}'.")


def _guides_batch(images, frames_text):
    frames = _parse_guide_frames(frames_text)
    if images is None:
        if frames:
            log.warning("SyncTile: guide_frames is set but guide_images is not connected; ignored.")
        return []
    if not frames:
        raise ValueError(f"SyncTile: guide_images has {images.shape[0]} image(s) but guide_frames is empty. "
                         "Type one frame per image, e.g. '1, 150, 300'.")
    n = images.shape[0]
    if n == 1:
        return [(images[:1], f) for f in frames]
    if n != len(frames):
        raise ValueError(f"SyncTile: guide_images has {n} images but guide_frames lists {len(frames)} frames "
                         f"({frames}). Give one frame per image.")
    return [(images[i:i + 1], f) for i, f in enumerate(frames)]


# --------------------------------------------------------------------------- per-region ref2va conditioning
class SyncTileRef2VAConditioning:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP",),
                "prompt": ("STRING", {"multiline": True, "default": "", "forceInput": True}),
                "width": ("INT", {"default": 3840, "min": 256, "max": 16384, "step": 16,
                                  "tooltip": "Canvas width the tiles will be sampled at (the upscaled latent)."}),
                "height": ("INT", {"default": 2160, "min": 256, "max": 16384, "step": 16}),
                "length": ("INT", {"default": 124, "min": 5, "max": 3600}),
                "tile_width": ("INT", {"default": 1472, "min": 256, "max": 8192, "step": 32}),
                "tile_height": ("INT", {"default": 896, "min": 256, "max": 8192, "step": 32}),
                "min_overlap": ("INT", {"default": 16, "min": 2, "max": 64}),
                "ref_video_mode": (["crop", "full"], {"default": "crop",
                                   "tooltip": "crop: each tile sees the matching region of the reference video. "
                                              "full: one encode per window, every tile sees the whole frame."}),
                "ref_image_size": (["match", "max"], {"default": "match"}),
            },
            "optional": {
                "latent": ("LATENT", {"tooltip": "The latent the guider will sample. When connected, its size and "
                                                 "length replace width/height/length so the grids always match."}),
                "vae": ("VAE",),
                "audio_vae": ("VAE",),
                "ref_image_0": ("IMAGE",),
                "ref_image_1": ("IMAGE",),
                "ref_image_2": ("IMAGE",),
                "ref_video_0": ("IMAGE", {"tooltip": "Reference video frames at 24 fps, frame-aligned with the output. "
                                                     "Sliced per window and cropped per tile."}),
                "ref_video_audio_0": ("AUDIO",),
                "ref_audio_0": ("AUDIO",),
                "window_frames": ("INT", {"default": 0, "min": 0, "max": 3600, "step": 1, "tooltip": WINDOW_TIP}),
                "window_overlap_frames": ("INT", {"default": 39, "min": 5, "max": 1000, "step": 17, "tooltip": OVERLAP_TIP}),
                **GUIDE_INPUTS,
            },
        }

    RETURN_TYPES = ("SYNCTILE_CONDS",)
    RETURN_NAMES = ("tile_conditioning",)
    FUNCTION = "encode"
    CATEGORY = "bruxosdovfx/SyncTile"
    DESCRIPTION = ("Runs MiniMax H3 Reference to Video once per SyncTile region: the reference video is sliced to "
                   "each temporal window and cropped to each tile; frame guides land in the right window.")

    def encode(self, clip, prompt, width, height, length, tile_width, tile_height, min_overlap, ref_video_mode,
               ref_image_size, latent=None, vae=None, audio_vae=None, ref_image_0=None, ref_image_1=None,
               ref_image_2=None, ref_video_0=None, ref_video_audio_0=None, ref_audio_0=None,
               window_frames=0, window_overlap_frames=39, guide_image_1=None, guide_frame_1=1,
               guide_image_2=None, guide_frame_2=-1, guide_images=None, guide_frames=""):
        from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo

        lat_h, lat_w, T, A, total_frames = _canvas(latent, width, height, length)
        width, height = lat_w * STRIDE, lat_h * STRIDE
        regions = make_grid(lat_h, lat_w, tile_width, tile_height, min_overlap, T, A,
                            window_frames, window_overlap_frames)
        images = {f"ref_image_{i}": im for i, im in enumerate([ref_image_0, ref_image_1, ref_image_2]) if im is not None}
        audios = {"ref_audio_0": ref_audio_0} if ref_audio_0 is not None else None
        tw, th = regions[0]["box"][2] * STRIDE, regions[0]["box"][3] * STRIDE
        windowed = len({r["t"] for r in regions}) > 1

        if ref_video_0 is not None:
            src_h, src_w = ref_video_0.shape[1], ref_video_0.shape[2]
            cx, cy, cw, ch = _center_crop_box(src_w, src_h, width / height)
            sx, sy = cw / width, ch / height

        cache = {}

        def run(r):
            f0, fw = region_frames(r)
            fw = fw or total_frames
            crop = ref_video_mode == "crop" and ref_video_0 is not None
            key = (r["t"], r["box"] if crop else None)
            if key in cache:
                return cache[key]
            video, v_audio = None, ref_video_audio_0
            if ref_video_0 is not None:
                video = _slice_frames(ref_video_0, f0, fw) if windowed else ref_video_0
                if windowed:
                    v_audio = _slice_audio(ref_video_audio_0, f0, fw)
                if crop:
                    x, y, w, h = (v * STRIDE for v in r["box"])
                    x0, y0 = cx + round(x * sx), cy + round(y * sy)
                    x1, y1 = min(cx + round((x + w) * sx), src_w), min(cy + round((y + h) * sy), src_h)
                    video = video[:, y0:y1, x0:x1, :]
            out = MiniMaxH3ReferenceToVideo.execute(
                clip=clip, prompt=prompt, width=tw, height=th, length=fw, ref_image_size=ref_image_size,
                vae=vae, audio_vae=audio_vae, ref_images=images or None,
                ref_videos={"ref_video_0": video} if video is not None else None,
                ref_video_audios={"ref_video_audio_0": v_audio} if (video is not None and v_audio is not None) else None,
                ref_audios=audios)
            cache[key] = out.args[0]
            pbar.update(1)
            return cache[key]

        pbar = comfy.utils.ProgressBar(len(regions))
        conds = [run(r) for r in regions]
        guide_list = (_guides_from(guide_image_1, guide_frame_1, guide_image_2, guide_frame_2)
                      + _guides_batch(guide_images, guide_frames))
        guides = _guide_keyframes(guide_list, regions, width, height, total_frames, vae)
        conds = [_with_keyframes(c, k) for c, k in zip(conds, guides)]
        n_win = len({r["t"] for r in regions})
        log.info("SyncTile: %d region conditionings (%d tiles x %d windows, %s, %d encodes), canvas %dx%d, %d frames",
                 len(regions), len(regions) // n_win, n_win, ref_video_mode, len(cache), width, height, total_frames)
        if guide_list:
            per_win = {}
            for r, k in zip(regions, guides):
                per_win.setdefault(r["t"], len(k))
            log.info("SyncTile: %d frame guide(s) at %s; guides per window: %s", len(guide_list),
                     [f for _, f in guide_list], list(per_win.values()))
        return ({"canvas": (lat_h, lat_w), "T": T, "A": A, "tiles": regions, "conds": conds},)


def _check_shared_keyframes(raw, box, n_windows=1):
    """img2video keyframe latents sit on the video's grid, so a stage-1 keyframe cannot ride on a tile or a window."""
    _, _, w, h = box
    for cs in raw.values():
        for c in cs:
            for kf in c.get("minimax_keyframes") or []:
                lat = kf.get("latent")
                if lat is not None and (tuple(lat.shape[-2:]) != (h, w) or n_windows > 1):
                    raise ValueError(
                        "SyncTile: this conditioning has frame guides / img2video keyframes, which are tied to one "
                        "canvas and one clip, but the guider is splitting it into tiles or windows. Use a SyncTile "
                        "conditioning node (its guide_image inputs, or SyncTile I2V Conditioning) and connect "
                        "tile_conditioning instead of positive.")


# --------------------------------------------------------------------------- per-region t2v / i2v conditioning
class SyncTileI2VConditioning:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "clip": ("CLIP",),
                "vae": ("VAE",),
                "prompt": ("STRING", {"multiline": True, "default": "", "forceInput": True}),
                "latent": ("LATENT", {"tooltip": "The latent the guider will sample (sets canvas size and length)."}),
                "tile_width": ("INT", {"default": 1472, "min": 256, "max": 8192, "step": 32}),
                "tile_height": ("INT", {"default": 896, "min": 256, "max": 8192, "step": 32}),
                "min_overlap": ("INT", {"default": 16, "min": 2, "max": 64}),
                "qwen_view": (["full", "crop"], {"default": "full", "tooltip":
                              "What the text encoder sees with the prompt.\n"
                              "full: the whole first/last frame, encoded once for all regions (fast).\n"
                              "crop: each tile's own crop, one text-encoder pass per tile (slow)."}),
            },
            "optional": {
                "first_frame": ("IMAGE", {"tooltip": "Use the full-resolution image (it is cropped per tile at canvas size)."}),
                "last_frame": ("IMAGE",),
                "window_frames": ("INT", {"default": 0, "min": 0, "max": 3600, "step": 1, "tooltip": WINDOW_TIP}),
                "window_overlap_frames": ("INT", {"default": 39, "min": 5, "max": 1000, "step": 17, "tooltip": OVERLAP_TIP}),
            },
        }

    RETURN_TYPES = ("SYNCTILE_CONDS",)
    RETURN_NAMES = ("tile_conditioning",)
    FUNCTION = "encode"
    CATEGORY = "bruxosdovfx/SyncTile"
    DESCRIPTION = ("MiniMax H3 Image to Video for SyncTile: the first/last frame is scaled to the canvas and each "
                   "region gets its own crop as keyframe, in the window that holds that frame. Without frames it is "
                   "plain text-to-video.")

    def encode(self, clip, vae, prompt, latent, tile_width, tile_height, min_overlap, qwen_view,
               first_frame=None, last_frame=None, window_frames=0, window_overlap_frames=39):
        from comfy_extras.nodes_minimax_h3 import _resize

        lat_h, lat_w, T, A = _canvas_from_latent(latent)
        width, height = lat_w * STRIDE, lat_h * STRIDE
        frame_count = frames_for_tokens(T)
        regions = make_grid(lat_h, lat_w, tile_width, tile_height, min_overlap, T, A,
                            window_frames, window_overlap_frames)
        tw, th = regions[0]["box"][2] * STRIDE, regions[0]["box"][3] * STRIDE
        out = {"canvas": (lat_h, lat_w), "T": T, "A": A, "tiles": regions}

        # same geometry as MiniMaxH3ImageToVideo, at canvas size: first = stretch, last = cover-crop
        frames = []
        if first_frame is not None:
            frames.append((0, _resize(first_frame[:1], width, height, "disabled")))
        if last_frame is not None:
            frames.append((frame_count - 1, _resize(last_frame[:1], width, height, "center")))

        def text_cond(images):
            return clip.encode_from_tokens_scheduled(clip.tokenize(prompt, images=images))

        if not frames:
            cond = text_cond([])
            log.info("SyncTile I2V: no frames, text-to-video conditioning shared by %d regions", len(regions))
            return (dict(out, conds=[cond] * len(regions)),)

        shared = None
        if qwen_view == "full":
            # whole frame for the text encoder, at the tile's pixel budget and the canvas aspect
            s = math.sqrt(tw * th / (width * height))
            qw, qh = max(32, round(width * s / 32) * 32), max(32, round(height * s / 32) * 32)
            shared = text_cond([_resize(img, qw, qh, "disabled") for _, img in frames])

        conds, text_cache, lat_cache = [], {}, {}
        pbar = comfy.utils.ProgressBar(len(regions))
        for r in regions:
            x, y, w, h = (v * STRIDE for v in r["box"])
            f0, fw = region_frames(r)
            fw = fw or frame_count
            crops = [(idx, img[:, y:y + h, x:x + w, :]) for idx, img in frames]
            if shared is not None:
                cond = shared
            else:
                if r["box"] not in text_cache:
                    text_cache[r["box"]] = text_cond([c for _, c in crops])
                cond = text_cache[r["box"]]
            keyframes = []
            for k, (idx, c) in enumerate(crops):
                if f0 <= idx < f0 + fw:
                    if (k, r["box"]) not in lat_cache:
                        lat_cache[(k, r["box"])] = vae.encode(c)
                    keyframes.append({"resolved_frame_index": idx - f0, "latent": lat_cache[(k, r["box"])]})
            conds.append(_with_keyframes(cond, keyframes))
            pbar.update(1)
        log.info("SyncTile I2V: %d regions (%d frame(s), qwen_view=%s), canvas %dx%d, %d frames",
                 len(regions), len(frames), qwen_view, width, height, frame_count)
        return (dict(out, conds=conds),)


# --------------------------------------------------------------------------- streaming decode -> video file
def _ffmpeg_exe():
    import os
    import shutil
    path = os.environ.get("FFMPEG_PATH") or os.environ.get("FFMPEG")
    if path and os.path.exists(path):
        return path
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    path = shutil.which("ffmpeg")
    if path:
        return path
    raise RuntimeError("SyncTile Stream Decode: ffmpeg not found. Install it, set FFMPEG_PATH, or "
                       "pip install imageio-ffmpeg with ComfyUI's Python.")


_ENCODERS = {}


def _ffmpeg_encoders(exe):
    """Video encoders this ffmpeg build actually has (cached)."""
    if exe not in _ENCODERS:
        import subprocess
        try:
            out = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30).stdout
            _ENCODERS[exe] = {ln.split()[1] for ln in out.splitlines() if len(ln.split()) > 1 and ln.strip()[:1] == "V"}
        except Exception:
            _ENCODERS[exe] = None                      # unknown: try as asked
    return _ENCODERS[exe]


def _pick_codec(codec, exe):
    """The asked codec if this ffmpeg can encode it, else the closest one it can (with a note)."""
    enc = _ffmpeg_encoders(exe)
    if enc is None:
        return codec, None
    need = {"h264 8-bit (.mp4)": "libx264", "h265 10-bit (.mp4)": "libx265", "prores 422 HQ 10-bit (.mov)": "prores_ks"}
    if need[codec] in enc:
        return codec, None
    for alt in ("h265 10-bit (.mp4)", "prores 422 HQ 10-bit (.mov)", "h264 8-bit (.mp4)"):
        if need[alt] in enc:
            return alt, f"this ffmpeg ({exe}) has no {need[codec]}; writing {alt} instead"
    raise RuntimeError(f"SyncTile Stream Decode: this ffmpeg ({exe}) has none of libx265 / prores_ks / libx264. "
                       "Point FFMPEG_PATH to a full build, or pip install imageio-ffmpeg with ComfyUI's Python.")


CODECS = {
    "h264 8-bit (.mp4)": (".mp4", ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium"], "rgb24", "aac"),
    "h265 10-bit (.mp4)": (".mp4", ["-c:v", "libx265", "-pix_fmt", "yuv420p10le", "-preset", "medium", "-tag:v", "hvc1",
                            "-x265-params", "log-level=error"],
                           "rgb48le", "aac"),
    "prores 422 HQ 10-bit (.mov)": (".mov", ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"],
                                     "rgb48le", "pcm_s16le"),
}


class _FrameSink:
    """Stands in for the VAE's output buffer: every finished temporal chunk goes to ffmpeg (and/or into an
    IMAGE tensor), never into one big float buffer of the whole video."""

    def __init__(self, shape, proc, pix_fmt, pbar, keep=None, scale=1):
        self.shape = tuple(shape)
        self.proc, self.pix_fmt, self.pbar = proc, pix_fmt, pbar
        self.keep, self.scale = keep, scale         # keep: preallocated [N, H, W, 3] float32 tensor or None
        self.written = 0
        self.broken = False

    def write(self, part):
        frames = part[0].permute(1, 2, 3, 0).clamp_(0, 1)            # [n, H, W, 3]
        n = frames.shape[0]
        if self.keep is not None:
            img = frames
            if self.scale > 1:
                img = torch.nn.functional.interpolate(frames.permute(0, 3, 1, 2).float(), scale_factor=1 / self.scale,
                                                      mode="area").permute(0, 2, 3, 1)
            end = min(self.written + n, self.keep.shape[0])
            self.keep[self.written:end].copy_(img[:end - self.written].float().cpu())
        if self.proc is not None and not self.broken:
            if self.pix_fmt == "rgb48le":
                data = (frames * 65535.0 + 0.5).to(torch.int32).cpu().numpy().astype("<u2")
            else:
                data = (frames * 255.0 + 0.5).to(torch.uint8).cpu().numpy()
            try:
                for f in data:
                    self.proc.stdin.write(f.tobytes())
            except (BrokenPipeError, OSError):
                self.broken = True                      # ffmpeg stopped; its stderr says why (read in decode)
                if self.keep is None:
                    raise
        self.written += n
        self.pbar.update(n)

    def copy_(self, part):                                            # single-latent path writes the whole buffer
        self.write(part)
        return self

    def __getitem__(self, key):
        sink = self

        class _Slice:
            def copy_(self, part):
                sink.write(part)
                return self
        return _Slice()


def _available_ram():
    try:
        import psutil
        return psutil.virtual_memory().available
    except Exception:
        return None


def _write_wav(audio, path):
    import wave
    wav = audio["waveform"][0].float().clamp(-1, 1)                  # [C, N]
    pcm = (wav.T * 32767.0).round().to(torch.int16).cpu().numpy()
    with wave.open(path, "wb") as f:
        f.setnchannels(pcm.shape[1])
        f.setsampwidth(2)
        f.setframerate(int(audio["sample_rate"]))
        f.writeframes(pcm.tobytes())


IMAGE_MODES = ("off", "full resolution", "half resolution")


class SyncTileStreamDecodeVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "samples": ("LATENT",),
                "vae": ("VAE", {"tooltip": "MiniMax H3 video VAE."}),
                "filename_prefix": ("STRING", {"default": "SyncTile/long"}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 120.0, "step": 0.001}),
                "codec": (list(CODECS), {"default": "h265 10-bit (.mp4)", "tooltip":
                          "10-bit codecs receive 16-bit frames straight from the VAE (no 8-bit banding step)."}),
                "crf": ("INT", {"default": 14, "min": 0, "max": 51, "tooltip": "Quality for h264/h265 (lower = better). Ignored by ProRes."}),
            },
            "optional": {
                "audio": ("AUDIO", {"tooltip": "Soundtrack to mux, e.g. the source video's audio. Cut to the video length."}),
                "image_output": (list(IMAGE_MODES), {"default": "off", "tooltip":
                                 "Also return the frames as IMAGE (e.g. for Save Video Pro). Costs RAM: frames x W x H x 12 "
                                 "bytes (600 frames at 2208x2848 = ~45 GB; half resolution = 1/4). The RAM is checked "
                                 "before decoding; if it does not fit it falls back to half, then off, and says so."}),
                "write_video": ("BOOLEAN", {"default": True, "tooltip":
                                "Write the video file. Off = only the IMAGE output (no ffmpeg)."}),
            },
        }

    RETURN_TYPES = ("STRING", "IMAGE")
    RETURN_NAMES = ("filepath", "images")
    FUNCTION = "decode"
    OUTPUT_NODE = True
    CATEGORY = "bruxosdovfx/SyncTile"
    DESCRIPTION = ("Decodes a MiniMax H3 video latent chunk by chunk and writes the frames straight into a video "
                   "file, so a long 4K video never has to fit in RAM. Optional IMAGE output (full or half resolution).")

    def decode(self, samples, vae, filename_prefix, fps, codec, crf, audio=None, image_output="off", write_video=True):
        import os
        import subprocess
        import tempfile
        import folder_paths

        s = samples["samples"]
        z = s.unbind()[0] if getattr(s, "is_nested", False) else s
        if z.ndim != 5:
            raise ValueError("SyncTile Stream Decode expects a video latent [B, C, T, H, W].")
        fsm = vae.first_stage_model
        if not hasattr(fsm, "decode_output_shape"):
            raise ValueError("SyncTile Stream Decode needs the MiniMax H3 video VAE.")
        z = z[:1]
        out_shape = fsm.decode_output_shape(z.shape)
        n_frames, H, W = out_shape[2], out_shape[3], out_shape[4]

        # ---- IMAGE output: check RAM first, fall back instead of crashing after a long render
        notes = []
        mode = image_output if image_output in IMAGE_MODES else "off"
        keep, scale = None, 1
        if not write_video and mode == "off":
            raise ValueError("SyncTile Stream Decode: write_video is off and image_output is off; nothing to do.")
        free = _available_ram()
        order = {"full resolution": ["full resolution", "half resolution", "off"],
                 "half resolution": ["half resolution", "off"], "off": ["off"]}[mode]
        for m in order:
            if m == "off":
                mode = m
                break
            sc = 2 if m == "half resolution" else 1
            need = n_frames * (H // sc) * (W // sc) * 3 * 4
            if free is None or need < free * 0.8:
                mode, scale = m, sc
                break
            notes.append(f"{m} needs {need / 2**30:.1f} GB, only {free / 2**30:.1f} GB RAM free")
        if mode == "off" and image_output != "off":
            if not write_video:
                raise MemoryError("SyncTile Stream Decode: " + "; ".join(notes) + ". Turn write_video on.")
            notes.append("IMAGE output turned off, the video file is still written")
        if mode != "off":
            keep = torch.empty((n_frames, H // scale, W // scale, 3), dtype=torch.float32)
        for n in notes:
            log.warning("SyncTile Stream Decode: %s", n)

        proc, path, filename, subfolder, wav = None, "", "", "", None
        if write_video:
            exe = _ffmpeg_exe()
            codec, note = _pick_codec(codec, exe)
            if note:
                notes.append(note)
                log.warning("SyncTile Stream Decode: %s", note)
        ext, vargs, pix_fmt, acodec = CODECS[codec]
        stderr_lines = []
        if write_video:
            out_dir = folder_paths.get_output_directory()
            full_dir, name, counter, subfolder, _ = folder_paths.get_save_image_path(filename_prefix, out_dir, W, H)
            filename = f"{name}_{counter:05}_{ext}"
            path = os.path.join(full_dir, filename)
            cmd = [exe, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", pix_fmt,
                   "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
            if audio is not None:
                wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
                _write_wav(audio, wav)
                cmd += ["-i", wav]
            cmd += vargs
            if "prores" not in codec:
                cmd += ["-crf", str(crf)]
            if wav:
                cmd += ["-c:a", acodec, "-shortest"]
            cmd += [path]
            import threading
            log.info("SyncTile Stream Decode: %s", " ".join(f'"{c}"' if " " in c else c for c in cmd))
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            drain = threading.Thread(target=lambda: stderr_lines.extend(
                ln.decode(errors="replace") for ln in iter(proc.stderr.readline, b"")), daemon=True)
            drain.start()

        chunk_shape = (1, z.shape[1], min(z.shape[2], 7), z.shape[3], z.shape[4])
        comfy.model_management.load_models_gpu([vae.patcher], memory_required=vae.memory_used_decode(chunk_shape, vae.vae_dtype))
        sink = _FrameSink(out_shape, proc, pix_fmt, comfy.utils.ProgressBar(n_frames), keep, scale)
        try:
            with torch.inference_mode():
                fsm.decode(z.to(device=vae.device, dtype=vae.vae_dtype), output_buffer=sink)
            if proc is not None:
                try:
                    proc.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
                code = proc.wait()
                drain.join(timeout=10)
                if code != 0 or sink.broken:
                    err = "".join(stderr_lines).strip()[-1500:] or f"exit code {code}"
                    if keep is None:
                        raise RuntimeError(f"SyncTile Stream Decode: ffmpeg stopped while writing {path}: {err}")
                    notes.append(f"video file NOT written (ffmpeg: {err}); IMAGE output is complete")
                    log.warning("SyncTile Stream Decode: %s", notes[-1])
                    path = ""
        except (BrokenPipeError, OSError) as e:
            if proc is not None:
                proc.kill()
                drain.join(timeout=10)
            err = "".join(stderr_lines).strip()[-1500:]
            raise RuntimeError(f"SyncTile Stream Decode: ffmpeg stopped while writing {path}: {err or e}") from e
        except Exception:
            if proc is not None:
                proc.kill()
            raise
        finally:
            if wav and os.path.exists(wav):
                os.remove(wav)

        images = keep if keep is not None else torch.zeros((1, 64, 64, 3))
        log.info("SyncTile Stream Decode: %d frames %dx%d%s%s", sink.written, W, H,
                 f" -> {path}" if path else "", f", IMAGE {mode}" if keep is not None else "")
        ui = {"text": notes} if notes else {}
        if path:
            ui.update({"images": [{"filename": filename, "subfolder": subfolder, "type": "output"}], "animated": (True,)})
        return {"ui": ui, "result": (path, images)}


NODE_CLASS_MAPPINGS = {
    "SyncTileGuiderH3": SyncTileGuider,
    "SyncTileRef2VAConditioningH3": SyncTileRef2VAConditioning,
    "SyncTileI2VConditioningH3": SyncTileI2VConditioning,
    "SyncTileStreamDecodeVideoH3": SyncTileStreamDecodeVideo,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "SyncTileGuiderH3": "bruxosdovfx • SyncTile Guider (H3)",
    "SyncTileRef2VAConditioningH3": "bruxosdovfx • SyncTile Ref2VA Conditioning (H3)",
    "SyncTileI2VConditioningH3": "bruxosdovfx • SyncTile I2V Conditioning (H3)",
    "SyncTileStreamDecodeVideoH3": "bruxosdovfx • SyncTile Stream Decode (H3)",
}


# trilingual tooltips (PT / EN / 中文) for every input and node description
try:
    from . import i18n as _i18n
except ImportError:                                   # loaded as a plain module (tests)
    import importlib as _il
    _i18n = _il.import_module(__name__.rsplit(".", 1)[0] + ".i18n") if "." in __name__ else None
if _i18n is not None:
    _i18n.apply(NODE_CLASS_MAPPINGS)
