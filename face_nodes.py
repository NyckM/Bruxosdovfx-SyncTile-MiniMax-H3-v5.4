"""bruxosdovfx • Face Crop / Face Stitch for small faces (SAM 3.1).

Based on the Bruxos Tracked Crop / Tracked Stitch and FaceStitchUpscale nodes (same author), adapted to:
  * take the MASK from ComfyUI's native SAM 3.1 video tracker (SAM3_VideoTrack -> SAM3_TrackToMask),
    at any resolution (it is resized to the frames);
  * long videos: the original video is NOT stored inside crop_data (the stitch receives it again), so a
    600-frame 4K clip is not kept twice in RAM;
  * frames where SAM lost the face fade out instead of pasting a stale crop;
  * a `best_face` output (largest detected face) that can be used as a face reference.

Flow:  video -> SAM 3.1 ("face") -> Face Crop (zoom, square) -> H3 refine with a face reference
       -> Face Stitch (silhouette / ellipse / rectangle) -> video.
"""
import math

import torch
import torch.nn.functional as F

CAT = "bruxosdovfx/SyncTile"


def _resize(t, w, h):
    """t: [B,H,W,C] float -> [B,h,w,C]; area when shrinking, bicubic when enlarging."""
    if t.shape[1] == h and t.shape[2] == w:
        return t
    x = t.movedim(-1, 1)
    mode = "area" if (h < t.shape[1] and w < t.shape[2]) else "bicubic"
    kw = {} if mode == "area" else {"align_corners": False}
    return F.interpolate(x, size=(h, w), mode=mode, **kw).movedim(1, -1).clamp(0, 1)


def _mask_full(mask, T, H, W):
    if mask is None:
        return None
    m = mask.float()
    if m.ndim == 4:                       # IMAGE given as mask
        m = m[..., 0]
    if m.ndim == 2:
        m = m.unsqueeze(0)
    if m.shape[0] < T:
        m = torch.cat([m, m[-1:].repeat(T - m.shape[0], 1, 1)], 0)
    m = m[:T]
    if m.shape[1:] != (H, W):
        m = F.interpolate(m.unsqueeze(1), size=(H, W), mode="bilinear", align_corners=False)[:, 0]
    return m.clamp(0, 1)


def _bbox(m2d, thr=0.3):
    ys, xs = torch.nonzero(m2d > thr, as_tuple=True)
    if ys.numel() == 0:
        return None
    return float(xs.min()), float(ys.min()), float(xs.max()) + 1, float(ys.max()) + 1


def _smooth(vals, win):
    win = int(win)
    if win <= 1 or len(vals) < 3:
        return list(vals)
    if win % 2 == 0:
        win += 1
    r = win // 2
    sig = max(win / 6.0, 0.5)
    k = torch.exp(-((torch.arange(win, dtype=torch.float32) - r) ** 2) / (2 * sig * sig))
    k /= k.sum()
    v = F.pad(torch.tensor(vals, dtype=torch.float32).view(1, 1, -1), (r, r), mode="replicate")
    return F.conv1d(v, k.view(1, 1, -1))[0, 0].tolist()


def _blur(m, px):
    """m: [h,w] -> gaussian blur with sigma ~ px/2."""
    if px <= 0:
        return m
    sig = max(0.5, px / 2.0)
    r = max(1, int(math.ceil(sig * 3)))
    k = torch.exp(-((torch.arange(2 * r + 1, dtype=torch.float32) - r) ** 2) / (2 * sig * sig))
    k = (k / k.sum()).to(m)
    x = m.view(1, 1, *m.shape)
    x = F.conv2d(F.pad(x, (r, r, 0, 0), mode="replicate"), k.view(1, 1, 1, -1))
    x = F.conv2d(F.pad(x, (0, 0, r, r), mode="replicate"), k.view(1, 1, -1, 1))
    return x[0, 0]


def _grow(m, px):
    px = int(px)
    if px == 0:
        return m
    x = m.view(1, 1, *m.shape)
    if px > 0:
        x = F.max_pool2d(x, 2 * px + 1, stride=1, padding=px)
    else:
        x = -F.max_pool2d(-x, 2 * (-px) + 1, stride=1, padding=-px)
    return x[0, 0]


def _ellipse(h, w, inset=0.08):
    yy = torch.linspace(-1, 1, h).view(-1, 1)
    xx = torch.linspace(-1, 1, w).view(1, -1)
    r = 1.0 - float(inset)
    return ((yy / r) ** 2 + (xx / r) ** 2 <= 1.0).float()


class SyncTileFaceCrop:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "mask": ("MASK",),
            },
            "optional": {
                "out_size": ("INT", {"default": 768, "min": 256, "max": 2048, "step": 32}),
                "padding": ("FLOAT", {"default": 0.45, "min": 0.0, "max": 3.0, "step": 0.05}),
                "center_smooth": ("INT", {"default": 21, "min": 0, "max": 241, "step": 2}),
                "size_smooth": ("INT", {"default": 51, "min": 0, "max": 301, "step": 2}),
                "mask_threshold": ("FLOAT", {"default": 0.3, "min": 0.01, "max": 0.99, "step": 0.01}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "SYNCTILE_FACE_CROP", "IMAGE", "STRING")
    RETURN_NAMES = ("face_video", "face_mask", "crop_data", "best_face", "info")
    FUNCTION = "crop"
    CATEGORY = CAT

    def crop(self, images, mask, out_size=768, padding=0.45, center_smooth=21, size_smooth=51, mask_threshold=0.3):
        T, H, W = int(images.shape[0]), int(images.shape[1]), int(images.shape[2])
        m = _mask_full(mask, T, H, W)
        if m is None:
            raise ValueError("SyncTile Face Crop: connect the face MASK (SAM3 Track to Mask).")
        cx, cy, side, det = [], [], [], []
        last = None
        for t in range(T):
            bb = _bbox(m[t], float(mask_threshold))
            if bb is None:
                det.append(0.0)
                if last is None:
                    cx.append(None); cy.append(None); side.append(None)
                    continue
                x0, y0, x1, y1 = last
            else:
                det.append(1.0)
                x0, y0, x1, y1 = bb
                last = bb
            cx.append((x0 + x1) / 2); cy.append((y0 + y1) / 2); side.append(max(x1 - x0, y1 - y0, 8.0))
        found = int(sum(det))
        if found == 0:
            raise ValueError("SyncTile Face Crop: SAM found no face in any frame. Check the SAM3 prompt ('face') "
                             "and the detection_threshold.")
        first = next(i for i, v in enumerate(cx) if v is not None)
        for i in range(first):                             # frames before the first detection: hold it
            cx[i], cy[i], side[i] = cx[first], cy[first], side[first]
        cx, cy = _smooth(cx, center_smooth), _smooth(cy, center_smooth)
        side = _smooth(side, size_smooth)
        size = int(out_size) // 32 * 32
        windows, crops, mcrops = [], [], []
        for t in range(T):
            s = min(side[t] * (1.0 + 2 * float(padding)), H, W)
            si = max(8, int(round(s)))
            x0 = int(round(cx[t] - si / 2)); y0 = int(round(cy[t] - si / 2))
            x0 = max(0, min(W - si, x0)); y0 = max(0, min(H - si, y0))
            windows.append((x0, y0, si, si))
            crops.append(_resize(images[t:t + 1, y0:y0 + si, x0:x0 + si, :3].float(), size, size)[0])
            mcrops.append(_resize(m[t:t + 1, y0:y0 + si, x0:x0 + si, None], size, size)[0, ..., 0])
        face_video = torch.stack(crops).contiguous()
        face_mask = torch.stack(mcrops).contiguous()
        alpha = [min(1.0, max(0.0, v)) for v in _smooth(det, 9)]       # fade where SAM lost the face
        best = max((i for i in range(T) if det[i] > 0), key=lambda i: side[i])
        sides = [side[i] for i in range(T) if det[i] > 0]
        crop_data = {"windows": windows, "size": size, "H": H, "W": W, "T": T, "mask_crop": face_mask.cpu(),
                     "alpha": alpha, "face_px": sides}
        info = (f"Face Crop: {found}/{T} frames with a face | face {min(sides):.0f}-{max(sides):.0f} px | "
                f"crop {size}x{size} (zoom up to {size / max(1.0, min(w[2] for w in windows)):.1f}x) | "
                f"best face at frame {best}")
        print(f"[bruxosdovfx • SyncTile] {info}", flush=True)
        return (face_video, face_mask, crop_data, face_video[best:best + 1].clone(), info)


class SyncTileFaceStitch:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "face_video": ("IMAGE",),
                "crop_data": ("SYNCTILE_FACE_CROP",),
            },
            "optional": {
                "compose": (["silhouette (SAM mask)", "ellipse", "rectangle"], {"default": "silhouette (SAM mask)"}),
                "mask_grow": ("INT", {"default": 12, "min": -128, "max": 256, "step": 1}),
                "feather": ("INT", {"default": 16, "min": 0, "max": 256, "step": 1}),
                "colour_match": ("BOOLEAN", {"default": True}),
                "blend": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05}),
            },
        }

    RETURN_TYPES = ("IMAGE", "MASK", "STRING")
    RETURN_NAMES = ("images", "stitch_mask", "info")
    FUNCTION = "stitch"
    CATEGORY = CAT

    def stitch(self, images, face_video, crop_data, compose="silhouette (SAM mask)", mask_grow=12, feather=16,
               colour_match=True, blend=1.0):
        T, H, W = crop_data["T"], crop_data["H"], crop_data["W"]
        if images.shape[1] != H or images.shape[2] != W:
            raise ValueError(f"SyncTile Face Stitch: images are {images.shape[2]}x{images.shape[1]} but the crop was "
                             f"made on {W}x{H}. Connect the same video to Face Crop and Face Stitch.")
        out = images[..., :3].clone()                       # never modify the upstream (cached) tensor
        n = min(int(out.shape[0]), T)
        fv = face_video.float()
        if fv.shape[0] < n:
            fv = torch.cat([fv, fv[-1:].repeat(n - fv.shape[0], 1, 1, 1)], 0)
        mask_out = torch.zeros(out.shape[0], H, W)
        mcrop = crop_data.get("mask_crop")
        alpha_t = crop_data.get("alpha") or [1.0] * T
        for t in range(n):
            a_t = float(alpha_t[t]) * float(blend)
            if a_t <= 0.001:
                continue
            x0, y0, w, h = crop_data["windows"][t]
            piece = _resize(fv[t:t + 1, ..., :3], w, h)[0]
            if compose.startswith("silhouette") and mcrop is not None:
                a = _resize(mcrop[min(t, mcrop.shape[0] - 1)][None, ..., None], w, h)[0, ..., 0]
                a = _grow((a > 0.3).float(), int(round(mask_grow * w / crop_data["size"])) if mask_grow else 0)
            elif compose == "ellipse":
                a = _ellipse(h, w)
            else:
                a = torch.ones(h, w)
            a = _blur(a, int(feather)).clamp(0, 1) * a_t
            region = out[t, y0:y0 + h, x0:x0 + w, :]
            if colour_match:
                wsum = a.sum().clamp_min(1e-4)
                aw = a[..., None]
                pm = (piece * aw).sum((0, 1)) / wsum
                rm = (region * aw).sum((0, 1)) / wsum
                ps = (((piece - pm) ** 2 * aw).sum((0, 1)) / wsum).sqrt().clamp_min(1e-4)
                rs = (((region - rm) ** 2 * aw).sum((0, 1)) / wsum).sqrt().clamp_min(1e-4)
                piece = ((piece - pm) * (rs / ps).clamp(0.5, 2.0) + rm).clamp(0, 1)
            out[t, y0:y0 + h, x0:x0 + w, :] = region * (1 - a[..., None]) + piece * a[..., None]
            mask_out[t, y0:y0 + h, x0:x0 + w] = torch.maximum(mask_out[t, y0:y0 + h, x0:x0 + w], a)
        info = f"Face Stitch: {n} frames, compose={compose}, grow={mask_grow}px, feather={feather}px"
        print(f"[bruxosdovfx • SyncTile] {info}", flush=True)
        return (out, mask_out, info)


NODE_CLASS_MAPPINGS = {"SyncTileFaceCropH3": SyncTileFaceCrop, "SyncTileFaceStitchH3": SyncTileFaceStitch}
NODE_DISPLAY_NAME_MAPPINGS = {"SyncTileFaceCropH3": "bruxosdovfx • Face Crop (SAM 3.1)",
                              "SyncTileFaceStitchH3": "bruxosdovfx • Face Stitch"}
