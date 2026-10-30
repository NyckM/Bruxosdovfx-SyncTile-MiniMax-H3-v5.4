"""Temporally aligned reference attention for MiniMax H3 (TARA-H3 policy), implemented for SyncTile.

Method by Alisson Anjos — "TARA-H3: Temporally Aligned Reference Attention for Native Video Conditioning",
technical report v0.1.2, 2026: https://github.com/alisson-anjos/ai-toolkit/tree/tara-h3-v0.1.2/research/tara-h3
This file is an independent implementation written from the report's description (no code copied from his
repositories). Policy:

  1. Shared temporal RoPE clock: the motion reference video's temporal coordinates are translated so its first
     frame coincides with the target video's first frame. Spatial coordinates and image references stay native.
  2. Bounded temporal bias, only for target-video queries attending to motion-video keys:
        logit -= min(cap, strength * (max(0, |t_q - t_k| - window) / falloff) ** 2)       (t in seconds)

Differences from the reference ComfyUI node: it works per SyncTile region (each tile/window has its own layout),
and keyframe rows (Add Guide / SyncTile frame guides / guide-from-previous-window) are skipped instead of being
rejected, so the policy can be combined with frame guides. Exact attention: non-target queries in one call,
target queries one latent frame at a time with that frame's key bias.
"""
import copy
import logging

import torch
import torch.nn.functional as F

log = logging.getLogger("SyncTile")
UNITS_PER_SECOND = 40.0           # H3 RoPE time: FRAME_RESCALE (5/3) per pixel frame at 24 fps


class TaraContext:
    def __init__(self, seq_len, target, frames, motion, key_t, params):
        self.seq_len = seq_len
        self.target = target              # (start, stop) rows of the target video segment
        self.frames = frames              # [(row_start, row_stop, time_seconds)] per target latent frame
        self.motion = motion              # bool [S]
        self.key_t = key_t                # float [S] seconds (after alignment)
        self.strength, self.window, self.falloff, self.cap = params
        self._bias = {}

    def bias(self, device, dtype):
        key = (device, dtype)
        if key not in self._bias:
            kt = self.key_t.to(device=device, dtype=torch.float32)
            km = self.motion.to(device)
            out = []
            for _, _, tf in self.frames:
                d = (kt - tf).abs()
                p = torch.clamp(self.strength * (torch.clamp(d - self.window, min=0) / self.falloff) ** 2, max=self.cap)
                out.append(torch.where(km, -p, torch.zeros_like(p)).to(dtype))
            self._bias = {key: torch.stack(out)}          # [frames, S]
        return self._bias[key]


def build(layout, refs, video_index=1, strength=2.0, window=0.2, falloff=0.25, cap=6.0):
    """Returns (aligned_layout, TaraContext) or (None, reason)."""
    segs = list(getattr(layout, "segments", []))
    if not segs or not hasattr(layout, "position_ids"):
        return None, "this ComfyUI has no H3 PackedLayout segments"
    order = [s for s in segs if s[2] not in ("text", "cond", "cond_audio", "audio", "video")]
    pos = 0
    videos = 0
    motion = None
    for blk in refs or ():
        kind = blk.get("kind")
        if kind == "image":
            pos += 1
        elif kind == "audio":
            pos += 1 if blk.get("ref_audio_t", 0) > 0 else 0
        elif kind in ("video", "video_audio"):
            pos += 1 if blk.get("ref_audio_t", 0) > 0 else 0
            videos += 1
            if pos >= len(order) or order[pos][2] != "ref_img":
                return None, "unexpected H3 reference packing"
            if videos == int(video_index):
                motion = order[pos]
            pos += 1
        else:
            return None, f"unknown H3 reference kind {kind}"
    if motion is None:
        return None, f"no <Video {video_index}> reference in this region's conditioning"
    target = next((s for s in segs if s[2] == "video"), None)
    if target is None:
        return None, "no target video segment"
    new = copy.copy(layout)
    new.position_ids = layout.position_ids.clone()
    ma, mb, _ = motion
    ta, tb, _ = target
    shift = float(layout.position_ids[ta, 0] - layout.position_ids[ma, 0])
    new.position_ids[ma:mb, 0] += shift
    mt = torch.unique_consecutive(new.position_ids[ma:mb, 0])
    tt = torch.unique_consecutive(new.position_ids[ta:tb, 0])
    if mt.shape != tt.shape or not torch.allclose(mt, tt, atol=1e-6):
        return None, (f"motion video and output have different temporal grids ({mt.numel()} vs {tt.numel()} latent "
                      "frames); use the same frames and 24 fps")
    S = int(layout.seq_len)
    motion_mask = torch.zeros(S, dtype=torch.bool)
    motion_mask[ma:mb] = True
    key_t = (new.position_ids[:, 0] / UNITS_PER_SECOND).float()
    t_rows = new.position_ids[ta:tb, 0]
    frames, start = [], ta
    for i in range(1, tb - ta + 1):
        if i == tb - ta or t_rows[i] != t_rows[i - 1]:
            frames.append((start, ta + i, float(t_rows[i - 1]) / UNITS_PER_SECOND))
            start = ta + i
    ctx = TaraContext(S, (ta, tb), frames, motion_mask, key_t, (float(strength), float(window), float(falloff), float(cap)))
    return new, ctx


# ----------------------------------------------------------------------------------------------- fast exact path
# Decomposition (exact): for a target query, motion-key weights exp(-p) = exp(-cap) + (exp(-p) - exp(-cap)).
#   base term   : ALL keys, key-only bias (0 for non-motion keys, -cap for motion keys)  -> one attention call
#   correction  : only the motion keys near that frame's time (where exp(-p) > exp(-cap)), bias log(exp(-p)-exp(-cap))
# A key-only bias is folded into one extra head dimension (q' = [q, 1/scale], k' = [k, bias]), so both terms run on
# the fast unmasked kernels (FlashAttention / memory-efficient with log-sum-exp). Results merge with their LSE.
_PAD = 8


def _attn_lse(q, k, v, scale):
    """(out, lse[B,H,N]) without any mask; tries the fastest kernel available."""
    if q.is_cuda:
        if q.dtype in (torch.float16, torch.bfloat16):
            try:
                r = torch.ops.aten._scaled_dot_product_flash_attention(q, k, v, 0.0, False, False, scale=scale)
                return r[0], r[1][..., :q.shape[2]]
            except Exception:
                pass
        try:
            r = torch.ops.aten._scaled_dot_product_efficient_attention(q, k, v, None, True, 0.0, False, scale=scale)
            return r[0], r[1][..., :q.shape[2]]
        except Exception:
            pass
    elif q.device.type == "cpu":
        try:
            r = torch.ops.aten._scaled_dot_product_flash_attention_for_cpu(q, k, v, 0.0, False, scale=scale)
            return r[0], r[1]
        except Exception:
            pass
    s = torch.matmul(q.float(), k.float().transpose(-1, -2)) * scale        # small fallback (tests / tiny inputs)
    lse = torch.logsumexp(s, dim=-1)
    return torch.matmul(torch.exp(s - lse[..., None]), v.float()).to(q.dtype), lse


def _attn_keybias_lse(q, k, v, kbias, scale):
    """Attention with an additive key-only bias [S] folded into an extra head dimension."""
    B, H, _, D = q.shape
    qe = torch.zeros(B, H, q.shape[2], _PAD, dtype=q.dtype, device=q.device)
    ke = torch.zeros(B, H, k.shape[2], _PAD, dtype=k.dtype, device=k.device)
    qe[..., 0] = 1.0 / scale
    ke[..., 0] = kbias.to(k.dtype)
    ve = torch.zeros(B, H, v.shape[2], _PAD, dtype=v.dtype, device=v.device)
    out, lse = _attn_lse(torch.cat([q, qe], -1), torch.cat([k, ke], -1), torch.cat([v, ve], -1), scale)
    return out[..., :D], lse


def _merge(parts):
    lses = torch.stack([p[1].float() for p in parts])
    L = torch.logsumexp(lses, dim=0)
    out = sum(torch.exp(p[1].float() - L)[..., None] * p[0].float() for p in parts)
    return out


class _Plan:
    def __init__(self, ctx, device, dtype):
        kt = ctx.key_t.to(device=device, dtype=torch.float32)
        km = ctx.motion.to(device)
        cap = ctx.cap if ctx.strength > 0 else 0.0               # strength 0 = clock alignment only, no bias
        self.base_bias = torch.where(km, torch.full_like(kt, -cap), torch.zeros_like(kt))
        rows = torch.nonzero(km).reshape(-1)
        self.m0, self.m1 = int(rows.min()), int(rows.max()) + 1          # motion rows are one contiguous segment
        mt = kt[self.m0:self.m1]
        reach = ctx.window + ctx.falloff * (ctx.cap / ctx.strength) ** 0.5 if ctx.strength > 0 else 0.0
        self.corr = []
        for _, _, tf in ctx.frames:
            d = (mt - tf).abs()
            near = torch.nonzero(d < reach - 1e-9).reshape(-1) if ctx.cap > 0 and ctx.strength > 0 else d[:0].long()
            if near.numel() == 0:
                self.corr.append(None)
                continue
            a, b = int(near.min()), int(near.max()) + 1
            p = torch.clamp(ctx.strength * (torch.clamp(d[a:b] - ctx.window, min=0) / ctx.falloff) ** 2, max=ctx.cap)
            w = torch.exp(-p) - torch.exp(torch.tensor(-ctx.cap, device=device))
            logw = torch.where(w > 0, torch.log(w.clamp_min(1e-30)), torch.full_like(w, -1e4))
            self.corr.append((self.m0 + a, self.m0 + b, logw))


def make_override(ctx, previous=None):
    def override(func, q, k, v, heads, mask=None, skip_reshape=False, skip_output_reshape=False, **kwargs):
        n = q.shape[2] if skip_reshape else q.shape[1]
        nk = k.shape[2] if skip_reshape else k.shape[1]
        if n != ctx.seq_len or nk != n or mask is not None:       # token refiner, other attention
            if previous is not None:
                return previous(func, q, k, v, heads, mask=mask, skip_reshape=skip_reshape,
                                skip_output_reshape=skip_output_reshape, **kwargs)
            return func(q, k, v, heads, mask=mask, skip_reshape=skip_reshape, skip_output_reshape=skip_output_reshape,
                        **kwargs)
        if not skip_reshape:
            b = q.shape[0]
            q, k, v = (t.view(b, -1, heads, t.shape[-1] // heads).transpose(1, 2) for t in (q, k, v))
        scale = kwargs.get("scale") or q.shape[-1] ** -0.5
        key = (q.device, q.dtype)
        plan = ctx._bias.get(("plan",) + key)
        if plan is None:
            plan = ctx._bias[("plan",) + key] = _Plan(ctx, q.device, q.dtype)
        out = torch.empty_like(q)
        ta, tb = ctx.target
        if ta > 0:
            out[:, :, :ta] = F.scaled_dot_product_attention(q[:, :, :ta], k, v, scale=scale)
        if tb < n:
            out[:, :, tb:] = F.scaled_dot_product_attention(q[:, :, tb:], k, v, scale=scale)
        o_b, l_b = _attn_keybias_lse(q[:, :, ta:tb], k, v, plan.base_bias, scale)
        for i, (s, e, _) in enumerate(ctx.frames):
            c = plan.corr[i]
            qs = slice(s - ta, e - ta)
            if c is None:
                out[:, :, s:e] = o_b[:, :, qs].to(q.dtype)
                continue
            a, b2, logw = c
            o_c, l_c = _attn_keybias_lse(q[:, :, s:e], k[:, :, a:b2], v[:, :, a:b2], logw, scale)
            out[:, :, s:e] = _merge([(o_b[:, :, qs], l_b[:, :, qs]), (o_c, l_c)]).to(q.dtype)
        if skip_output_reshape:
            return out
        return out.transpose(1, 2).reshape(out.shape[0], -1, out.shape[1] * out.shape[3])
    return override


def patch_conds(conds, video_index, params):
    """Align the motion reference and attach a TaraContext to a processed SyncTile conds dict (in place)."""
    import comfy.conds
    if not conds:
        return conds, None
    ctx, reason = None, None
    for name in ("positive", "negative"):
        for c in conds.get(name) or []:
            mc = c.get("model_conds", {})
            p = mc.get("minimax_payload")
            payload = getattr(p, "cond", None)
            if not isinstance(payload, dict) or payload.get("layout") is None:
                reason = "no H3 layout in the conditioning"
                continue
            new, cx = build(payload["layout"], payload.get("refs"), video_index, *params)
            if new is None:
                reason = cx
                continue
            mc["minimax_payload"] = comfy.conds.CONDConstant(dict(payload, layout=new))
            if name == "positive":
                ctx = cx
    conds["_tara"] = ctx
    return conds, (None if ctx is not None else reason)
