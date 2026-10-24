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


def _sdpa(q, k, v, bias=None):
    """Exact attention with an optional additive key bias [1,1,1,S]; avoids the dense S x S fallback."""
    if bias is None:
        return F.scaled_dot_product_attention(q, k, v)
    try:
        from torch.nn.attention import sdpa_kernel, SDPBackend
        with sdpa_kernel([SDPBackend.EFFICIENT_ATTENTION, SDPBackend.CUDNN_ATTENTION]):
            return F.scaled_dot_product_attention(q, k, v, attn_mask=bias.expand(q.shape[0], q.shape[1], q.shape[2], -1))
    except Exception:
        pass
    out = torch.empty_like(q)                                  # chunked manual fallback (CPU / old GPUs)
    scale = q.shape[-1] ** -0.5
    step = max(1, int(2 ** 28 // max(1, q.shape[2] * k.shape[2])))
    for h in range(0, q.shape[1], step):
        s = torch.matmul(q[:, h:h + step].float(), k[:, h:h + step].float().transpose(-1, -2)) * scale + bias.float()
        out[:, h:h + step] = torch.matmul(torch.softmax(s, dim=-1), v[:, h:h + step].float()).to(q.dtype)
    return out


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
        out = torch.empty_like(q)
        ta, tb = ctx.target
        if ta > 0:
            out[:, :, :ta] = _sdpa(q[:, :, :ta], k, v)
        if tb < n:
            out[:, :, tb:] = _sdpa(q[:, :, tb:], k, v)
        biases = ctx.bias(q.device, q.dtype)
        for i, (s, e, _) in enumerate(ctx.frames):
            out[:, :, s:e] = _sdpa(q[:, :, s:e], k, v, biases[i].view(1, 1, 1, -1))
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
