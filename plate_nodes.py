"""bruxosdovfx • Background Plate (camera match) — EXPERIMENTAL.

Estimates the real camera motion from the BACKGROUND of the source video (person masked out by SAM 3.1),
applies the same motion to a still background image (the new environment) and composites the person on top.
The result goes to H3 as <Video 1>, so the generated background follows the real camera instead of inventing one.

Motion: sparse optical flow (Shi-Tomasi + pyramidal Lucas-Kanade) on background pixels, a robust per-frame
transform (RANSAC), chained from frame 0. 2D only: pan / tilt / zoom / roll follow the camera, there is no real
depth parallax in the plate (H3 adds some in the refine).
"""
import json
import math

import numpy as np
import torch
import torch.nn.functional as F

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

CAT = "bruxosdovfx/SyncTile"
MODELS = ["similarity (pan, zoom, roll)", "affine", "homography (perspective)"]


def _mask_full(mask, T, H, W):
    if mask is None:
        return torch.zeros(T, H, W)
    m = mask.float()
    if m.ndim == 4:
        m = m[..., 0]
    if m.ndim == 2:
        m = m.unsqueeze(0)
    if m.shape[0] < T:
        m = torch.cat([m, m[-1:].repeat(T - m.shape[0], 1, 1)], 0)
    m = m[:T]
    if m.shape[1:] != (H, W):
        m = F.interpolate(m.unsqueeze(1), size=(H, W), mode="bilinear", align_corners=False)[:, 0]
    return m.clamp(0, 1)


def _smooth_mats(mats, win):
    """Light temporal smoothing of the chained 3x3 matrices (element-wise gaussian), keeps frame 0 fixed."""
    win = int(win)
    if win <= 1 or len(mats) < 3:
        return mats
    if win % 2 == 0:
        win += 1
    r = win // 2
    sig = max(win / 6.0, 0.5)
    k = np.exp(-((np.arange(win) - r) ** 2) / (2 * sig * sig))
    k /= k.sum()
    a = np.stack(mats)                                  # [T,3,3]
    pad = np.concatenate([np.repeat(a[:1], r, 0), a, np.repeat(a[-1:], r, 0)], 0)
    out = np.stack([np.tensordot(k, pad[i:i + win], axes=(0, 0)) for i in range(len(mats))])
    out = out / out[:, 2:3, 2:3]
    return list(out)


def estimate_camera(frames_u8, bg_masks, model=MODELS[0], track_width=640, min_points=24):
    """frames_u8: list of HxWx3 uint8; bg_masks: list of HxW bool (True = background usable).
    Returns per-frame 3x3 matrices mapping frame-0 pixel coords to frame-t coords, and a quality list."""
    H, W = frames_u8[0].shape[:2]
    s = min(1.0, float(track_width) / W)
    S = np.diag([s, s, 1.0])
    Si = np.diag([1 / s, 1 / s, 1.0])
    small = lambda im: cv2.resize(im, (max(8, int(W * s)), max(8, int(H * s))), interpolation=cv2.INTER_AREA)
    prev = cv2.cvtColor(small(frames_u8[0]), cv2.COLOR_RGB2GRAY)
    acc = np.eye(3)
    mats, quality = [np.eye(3)], [1.0]
    for t in range(1, len(frames_u8)):
        cur = cv2.cvtColor(small(frames_u8[t]), cv2.COLOR_RGB2GRAY)
        m_prev = small(bg_masks[t - 1].astype(np.uint8) * 255)
        pts = cv2.goodFeaturesToTrack(prev, maxCorners=600, qualityLevel=0.01, minDistance=7, mask=m_prev, blockSize=7)
        step = np.eye(3)
        q = 0.0
        if pts is not None and len(pts) >= min_points:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, pts, None, winSize=(21, 21), maxLevel=3,
                                                  criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
            ok = st.reshape(-1) == 1
            if ok.sum() >= min_points:
                a, b = pts.reshape(-1, 2)[ok], nxt.reshape(-1, 2)[ok]
                inl = None
                if model.startswith("homography"):
                    Hm, inl = cv2.findHomography(a, b, cv2.RANSAC, 2.0)
                    if Hm is not None:
                        step = Hm
                else:
                    fn = cv2.estimateAffinePartial2D if model.startswith("similarity") else cv2.estimateAffine2D
                    A, inl = fn(a, b, method=cv2.RANSAC, ransacReprojThreshold=2.0)
                    if A is not None:
                        step = np.vstack([A, [0, 0, 1]])
                if inl is not None:
                    q = float(inl.sum()) / max(1, len(a))
        acc = (Si @ step @ S) @ acc
        mats.append(acc.copy())
        quality.append(q)
        prev = cur
    return mats, quality


def _inpaint(bg_u8, mask_u8):
    if mask_u8 is None or not mask_u8.any():
        return bg_u8
    m = cv2.dilate(mask_u8, np.ones((15, 15), np.uint8))
    return cv2.inpaint(bg_u8, m, 9, cv2.INPAINT_TELEA)


class SyncTileBackgroundPlate:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "person_mask": ("MASK",),
                "background": ("IMAGE",),
            },
            "optional": {
                "background_person_mask": ("MASK",),
                "motion_model": (MODELS, {"default": MODELS[0]}),
                "plate_scale": ("FLOAT", {"default": 1.3, "min": 1.0, "max": 3.0, "step": 0.05}),
                "mask_grow": ("INT", {"default": 24, "min": 0, "max": 256, "step": 1}),
                "smooth": ("INT", {"default": 3, "min": 0, "max": 61, "step": 1}),
                "feather": ("INT", {"default": 6, "min": 0, "max": 128, "step": 1}),
                "track_width": ("INT", {"default": 640, "min": 160, "max": 2048, "step": 32}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("composite", "plate", "camera_path", "info")
    FUNCTION = "build"
    CATEGORY = CAT

    def build(self, images, person_mask, background, background_person_mask=None, motion_model=MODELS[0],
              plate_scale=1.3, mask_grow=24, smooth=3, feather=6, track_width=640):
        if cv2 is None:
            raise RuntimeError("SyncTile Background Plate needs opencv-python (pip install opencv-python).")
        T, H, W = int(images.shape[0]), int(images.shape[1]), int(images.shape[2])
        pm = _mask_full(person_mask, T, H, W)
        frames = [(images[t, ..., :3].clamp(0, 1).numpy() * 255).astype(np.uint8) for t in range(T)]
        k = max(1, int(mask_grow)) * 2 + 1
        ker = np.ones((k, k), np.uint8)
        bgm = []
        for t in range(T):
            person = (pm[t].numpy() > 0.3).astype(np.uint8)
            person = cv2.dilate(person, ker) if mask_grow > 0 else person
            m = person == 0
            border = max(4, min(H, W) // 40)                 # ignore frame borders (rolling shutter, vignette)
            m[:border] = m[-border:] = False
            m[:, :border] = m[:, -border:] = False
            bgm.append(m)
        mats, quality = estimate_camera(frames, bgm, motion_model, track_width)
        mats = _smooth_mats(mats, smooth)

        # background image -> plate image (person removed if a mask is given), sized to cover the frame * plate_scale
        bg = (background[0, ..., :3].clamp(0, 1).numpy() * 255).astype(np.uint8)
        if background_person_mask is not None:
            bm = background_person_mask[0] if background_person_mask.ndim == 3 else background_person_mask
            bm = F.interpolate(bm.float()[None, None], size=bg.shape[:2], mode="bilinear")[0, 0].numpy()
            bg = _inpaint(bg, (bm > 0.3).astype(np.uint8) * 255)
        bh, bw = bg.shape[:2]
        cover = max(W * float(plate_scale) / bw, H * float(plate_scale) / bh)
        # B maps background pixels -> frame-0 pixels (centered, scaled to cover)
        B = np.array([[cover, 0, W / 2 - cover * bw / 2], [0, cover, H / 2 - cover * bh / 2], [0, 0, 1]])
        plates, comps = [], []
        for t in range(T):
            M = mats[t] @ B
            plate = cv2.warpPerspective(bg, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
            a = pm[t].numpy()
            if feather > 0:
                a = cv2.GaussianBlur(a, (0, 0), max(0.5, feather / 2.0))
            a = np.clip(a, 0, 1)[..., None]
            comp = frames[t].astype(np.float32) * a + plate.astype(np.float32) * (1 - a)
            plates.append(plate)
            comps.append(comp)
        plate_t = torch.from_numpy(np.stack(plates)).float() / 255.0
        comp_t = torch.from_numpy(np.stack(comps)).float().clamp(0, 255) / 255.0

        # camera path summary: translation (px), zoom, roll (deg) relative to frame 0
        path = []
        for t, Mx in enumerate(mats):
            zoom = math.sqrt(abs(Mx[0, 0] * Mx[1, 1] - Mx[0, 1] * Mx[1, 0]))
            roll = math.degrees(math.atan2(Mx[1, 0], Mx[0, 0]))
            path.append({"frame": t, "tx": round(float(Mx[0, 2]), 1), "ty": round(float(Mx[1, 2]), 1),
                         "zoom": round(zoom, 4), "roll": round(roll, 2), "quality": round(quality[t], 2)})
        low = sum(1 for q in quality[1:] if q < 0.3)
        last = path[-1]
        info = (f"Background Plate (experimental): {T} frames, {motion_model} | camera moved "
                f"{last['tx']:+.0f}px x / {last['ty']:+.0f}px y, zoom {last['zoom']:.2f}, roll {last['roll']:+.1f}° "
                f"by the last frame | {low} frames with weak tracking (<30% inliers)")
        print(f"[bruxosdovfx • SyncTile] {info}", flush=True)
        return (comp_t, plate_t, json.dumps(path), info)


NODE_CLASS_MAPPINGS = {"SyncTileBackgroundPlateH3": SyncTileBackgroundPlate}
NODE_DISPLAY_NAME_MAPPINGS = {"SyncTileBackgroundPlateH3": "bruxosdovfx • Background Plate (camera match, experimental)"}


# =============================================================================================== 3D (MoGe) plate
HOLE_FILLS = ["inpaint", "magenta (CrossView LoRA)", "grey (Meridian style)"]
TRANSLATIONS = ["relative to scene depth", "metric (as measured)", "off (rotation only)"]


def _k_pixels(k_norm, w, h):
    k = np.array(k_norm, dtype=np.float64).copy()
    return np.array([[k[0, 0] * w, 0, k[0, 2] * w], [0, k[1, 1] * h, k[1, 2] * h], [0, 0, 1]])


def _moge(geom, i):
    pts = geom["points"][min(i, geom["points"].shape[0] - 1)].float().cpu().numpy()
    m = geom.get("mask")
    m = m[min(i, m.shape[0] - 1)].cpu().numpy().astype(bool) if m is not None else np.ones(pts.shape[:2], bool)
    m &= np.isfinite(pts).all(-1) & (pts[..., 2] > 1e-4)
    k = geom["intrinsics"][min(i, geom["intrinsics"].shape[0] - 1)].float().cpu().numpy()
    return pts, m, k


def estimate_camera_3d(frames_u8, bg_masks, geom, track_width=640, min_points=24):
    """Real camera motion (rotation + translation) from background points lifted to 3D with MoGe.

    Keyframe tracking: features detected on a keyframe are lifted to 3D (in camera-0 coordinates) and followed
    with optical flow; every frame is solved directly against them with PnP (no frame-to-frame chaining, so no
    drift). A new keyframe starts when too many tracks are lost. Returns 4x4 matrices camera-0 -> camera-t,
    per-frame quality and the median background depth."""
    H, W = frames_u8[0].shape[:2]
    s = min(1.0, float(track_width) / W)
    ws, hs = max(8, int(W * s)), max(8, int(H * s))
    small = lambda im: cv2.resize(im, (ws, hs), interpolation=cv2.INTER_AREA)
    lk = dict(winSize=(21, 21), maxLevel=3, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
    grays = [cv2.cvtColor(small(f), cv2.COLOR_RGB2GRAY) for f in frames_u8]
    poses, quality, depths = [np.eye(4)], [1.0], []

    def new_keyframe(t, pose):
        pts3, valid, _ = _moge(geom, t)
        ph, pw = pts3.shape[:2]
        m = cv2.resize(bg_masks[t].astype(np.uint8) * 255, (ws, hs), interpolation=cv2.INTER_NEAREST)
        feats = cv2.goodFeaturesToTrack(grays[t], maxCorners=1000, qualityLevel=0.005, minDistance=5, mask=m, blockSize=7)
        if feats is None:
            return None, None
        uv = feats.reshape(-1, 2)
        ui = np.clip((uv[:, 0] / ws * pw).astype(int), 0, pw - 1)
        vi = np.clip((uv[:, 1] / hs * ph).astype(int), 0, ph - 1)
        ok = valid[vi, ui]
        if ok.sum() < min_points:
            return None, None
        Xk = pts3[vi[ok], ui[ok]].astype(np.float64)
        depths.append(float(np.median(Xk[:, 2])))
        inv = np.linalg.inv(pose)
        X0 = Xk @ inv[:3, :3].T + inv[:3, 3]                          # keyframe camera -> camera 0
        return X0, uv[ok].astype(np.float32).reshape(-1, 1, 2)

    X0, tracks = new_keyframe(0, np.eye(4))
    n_start = 0 if X0 is None else len(X0)
    rv = tv = None
    for t in range(1, len(frames_u8)):
        pose, q = poses[-1].copy(), 0.0
        if X0 is not None:
            nxt, st, _ = cv2.calcOpticalFlowPyrLK(grays[t - 1], grays[t], tracks, None, **lk)
            back, st2, _ = cv2.calcOpticalFlowPyrLK(grays[t], grays[t - 1], nxt, None, **lk)
            good = (st.reshape(-1) == 1) & (st2.reshape(-1) == 1) & \
                   (np.linalg.norm((back - tracks).reshape(-1, 2), axis=1) < 1.0)
            X0, tracks = X0[good], nxt[good]
            _, _, kn = _moge(geom, t)
            K = _k_pixels(kn, ws, hs)
            if len(X0) >= min_points:
                guess = rv is not None
                res = cv2.solvePnPRansac(X0, tracks.reshape(-1, 2).astype(np.float64), K, None,
                                         rvec=rv, tvec=tv, useExtrinsicGuess=guess, iterationsCount=300,
                                         reprojectionError=1.5, confidence=0.999,
                                         flags=cv2.SOLVEPNP_ITERATIVE if guess else cv2.SOLVEPNP_EPNP)
                if res[0] and res[3] is not None and len(res[3]) >= min_points // 2:
                    inl = res[3].reshape(-1)
                    rv, tv = cv2.solvePnPRefineLM(X0[inl], tracks.reshape(-1, 2)[inl].astype(np.float64), K, None,
                                                  res[1], res[2])
                    pose = np.eye(4)
                    pose[:3, :3] = cv2.Rodrigues(rv)[0]
                    pose[:3, 3] = tv.reshape(-1)
                    q = len(inl) / float(len(X0))
        poses.append(pose)
        quality.append(q)
        if X0 is None or len(X0) < max(min_points * 2, 0.5 * n_start):
            X0, tracks = new_keyframe(t, pose)
            n_start = 0 if X0 is None else len(X0)
    return poses, quality, (float(np.median(depths)) if depths else 1.0)


def _smooth_poses(mats, win):
    win = int(win)
    if win <= 1 or len(mats) < 3:
        return mats
    rv = np.stack([cv2.Rodrigues(m[:3, :3])[0].reshape(-1) for m in mats])
    tv = np.stack([m[:3, 3] for m in mats])
    r = win // 2
    sig = max(win / 6.0, 0.5)
    k = np.exp(-((np.arange(2 * r + 1) - r) ** 2) / (2 * sig * sig)); k /= k.sum()
    def sm(a):
        p = np.concatenate([np.repeat(a[:1], r, 0), a, np.repeat(a[-1:], r, 0)], 0)
        return np.stack([np.tensordot(k, p[i:i + 2 * r + 1], axes=(0, 0)) for i in range(len(a))])
    rv, tv = sm(rv), sm(tv)
    out = []
    for i in range(len(mats)):
        m = np.eye(4); m[:3, :3] = cv2.Rodrigues(rv[i])[0]; m[:3, 3] = tv[i]
        out.append(m)
    out[0] = np.eye(4)
    return out


def _fill_depth(depth, hole):
    """Fill depth inside `hole` from its surroundings (person erased from the background photo)."""
    if not hole.any():
        return depth
    d = depth.copy()
    good = ~hole & np.isfinite(d)
    lo, hi = np.percentile(d[good], 1), np.percentile(d[good], 99)
    d16 = (np.clip((np.nan_to_num(d, nan=hi) - lo) / max(hi - lo, 1e-6), 0, 1) * 65535).astype(np.uint16)
    hole8 = cv2.dilate(hole.astype(np.uint8) * 255, np.ones((15, 15), np.uint8))
    try:
        f = cv2.inpaint(d16, hole8, 15, cv2.INPAINT_TELEA).astype(np.float32)
    except cv2.error:                                   # older OpenCV without 16-bit inpaint
        f = cv2.inpaint((d16 >> 8).astype(np.uint8), hole8, 15, cv2.INPAINT_TELEA).astype(np.float32) * 257
    out = np.where(hole8 > 0, lo + f / 65535.0 * (hi - lo), d)
    return out


class SyncTileBackgroundPlate3D:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "person_mask": ("MASK",),
                "source_geometry": ("MOGE_GEOMETRY",),
                "background": ("IMAGE",),
                "background_geometry": ("MOGE_GEOMETRY",),
            },
            "optional": {
                "background_person_mask": ("MASK",),
                "translation": (TRANSLATIONS, {"default": TRANSLATIONS[0]}),
                "motion_scale": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 5.0, "step": 0.05}),
                "plate_scale": ("FLOAT", {"default": 1.25, "min": 1.0, "max": 3.0, "step": 0.05}),
                "hole_fill": (HOLE_FILLS, {"default": HOLE_FILLS[0]}),
                "render_width": ("INT", {"default": 1024, "min": 256, "max": 4096, "step": 32}),
                "mask_grow": ("INT", {"default": 24, "min": 0, "max": 256, "step": 1}),
                "smooth": ("INT", {"default": 5, "min": 0, "max": 61, "step": 1}),
                "feather": ("INT", {"default": 6, "min": 0, "max": 128, "step": 1}),
                "track_width": ("INT", {"default": 640, "min": 160, "max": 2048, "step": 32}),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE", "MASK", "STRING", "STRING")
    RETURN_NAMES = ("composite", "plate", "holes", "camera_path", "info")
    FUNCTION = "build"
    CATEGORY = CAT

    def build(self, images, person_mask, source_geometry, background, background_geometry, background_person_mask=None,
              translation=TRANSLATIONS[0], motion_scale=1.0, plate_scale=1.25, hole_fill=HOLE_FILLS[0],
              render_width=1024, mask_grow=24, smooth=5, feather=6, track_width=640):
        if cv2 is None:
            raise RuntimeError("SyncTile Background Plate 3D needs opencv-python.")
        for g, name in ((source_geometry, "source_geometry"), (background_geometry, "background_geometry")):
            if "points" not in g or "intrinsics" not in g:
                raise ValueError(f"SyncTile Background Plate 3D: {name} needs points and intrinsics "
                                 "(use Run MoGe Inference on a perspective image).")
        T, H, W = int(images.shape[0]), int(images.shape[1]), int(images.shape[2])
        if source_geometry["points"].shape[0] not in (1, T):
            raise ValueError(f"SyncTile Background Plate 3D: source_geometry has {source_geometry['points'].shape[0]} "
                             f"frames but the video has {T}. Run MoGe on the same frames.")
        pm = _mask_full(person_mask, T, H, W)
        frames = [(images[t, ..., :3].clamp(0, 1).numpy() * 255).astype(np.uint8) for t in range(T)]
        ker = np.ones((max(1, int(mask_grow)) * 2 + 1,) * 2, np.uint8)
        bgm = []
        for t in range(T):
            person = (pm[t].numpy() > 0.3).astype(np.uint8)
            m = (cv2.dilate(person, ker) if mask_grow > 0 else person) == 0
            b = max(4, min(H, W) // 40)
            m[:b] = m[-b:] = False; m[:, :b] = m[:, -b:] = False
            bgm.append(m)
        mats, quality, src_depth = estimate_camera_3d(frames, bgm, source_geometry, track_width)
        mats = _smooth_poses(mats, smooth)

        # ---- background scene: colours + 3D points from MoGe, the person (if any) erased in both
        pts, valid, kb = _moge(background_geometry, 0)
        hb, wb = pts.shape[:2]
        col = (F.interpolate(background[:1, ..., :3].movedim(-1, 1).float(), size=(hb, wb), mode="bilinear",
                             align_corners=False)[0].movedim(0, -1).clamp(0, 1).numpy() * 255).astype(np.uint8)
        depth = np.where(valid, pts[..., 2], np.nan).astype(np.float32)
        if background_person_mask is not None:
            bm = background_person_mask[0] if background_person_mask.ndim == 3 else background_person_mask
            hole = F.interpolate(bm.float()[None, None], size=(hb, wb), mode="bilinear")[0, 0].numpy() > 0.3
            col = _inpaint(col, hole.astype(np.uint8) * 255)
            depth = _fill_depth(depth, hole)
        far = np.nanpercentile(depth, 99) if np.isfinite(depth).any() else 10.0
        depth = np.where(np.isfinite(depth), depth, far)          # sky / invalid: push to the far plane
        Kb = _k_pixels(kb, wb, hb)
        uu, vv = np.meshgrid(np.arange(wb) + 0.5, np.arange(hb) + 0.5)
        P = np.stack([(uu - Kb[0, 2]) / Kb[0, 0] * depth, (vv - Kb[1, 2]) / Kb[1, 1] * depth, depth], -1).reshape(-1, 3)
        C = col.reshape(-1, 3)
        # depth discontinuities: drop the stretched points so disocclusions become holes, not smears
        gy, gx = np.gradient(np.log(np.maximum(depth, 1e-4)))
        edge = (np.abs(gx) + np.abs(gy)).reshape(-1) > 0.08
        P, C = P[~edge], C[~edge]
        bg_depth = float(np.median(depth))

        # ---- render camera: at frame 0 it shows the background photo centred, covering the frame * plate_scale
        Wr = int(render_width) // 2 * 2
        Hr = int(round(Wr * H / W)) // 2 * 2
        cover = max(Wr * float(plate_scale) / wb, Hr * float(plate_scale) / hb)
        Kr = np.array([[Kb[0, 0] * cover, 0, Wr / 2 + (Kb[0, 2] - wb / 2) * cover],
                       [0, Kb[1, 1] * cover, Hr / 2 + (Kb[1, 2] - hb / 2) * cover], [0, 0, 1]])
        tscale = {TRANSLATIONS[0]: bg_depth / max(src_depth, 1e-4), TRANSLATIONS[1]: 1.0, TRANSLATIONS[2]: 0.0}[translation]
        tscale *= float(motion_scale)
        Pt = torch.from_numpy(P).double()
        Ct = torch.from_numpy(C)
        plates, holes = [], []
        for t in range(T):
            R = torch.from_numpy(mats[t][:3, :3]); tv = torch.from_numpy(mats[t][:3, 3]) * tscale
            X = Pt @ R.T + tv
            z = X[:, 2]
            ok = z > 1e-3
            u = (Kr[0, 0] * X[:, 0] / z + Kr[0, 2]).floor().long()
            v = (Kr[1, 1] * X[:, 1] / z + Kr[1, 2]).floor().long()
            ok &= (u >= 0) & (u < Wr) & (v >= 0) & (v < Hr)
            idx = (v * Wr + u)[ok]
            zz = z[ok].float()
            zbuf = torch.full((Hr * Wr,), float("inf")).scatter_reduce(0, idx, zz, reduce="amin")
            win = zz <= zbuf[idx] + 1e-6
            img = torch.zeros(Hr * Wr, 3, dtype=torch.uint8)
            img[idx[win]] = Ct[ok][win]
            hole = torch.isinf(zbuf).view(Hr, Wr).numpy().astype(np.uint8)
            img = img.view(Hr, Wr, 3).numpy().copy()
            # tiny splat gaps (zoom / forward motion): close them; real disocclusions stay holes
            small_holes = hole & (cv2.morphologyEx(hole, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)) == 0)
            if small_holes.any():
                img = cv2.inpaint(img, small_holes * 255, 3, cv2.INPAINT_TELEA)
            big = hole & ~small_holes.astype(bool)
            if big.any():
                if hole_fill.startswith("magenta"):
                    img[big.astype(bool)] = (255, 0, 255)
                elif hole_fill.startswith("grey"):
                    img[big.astype(bool)] = (128, 128, 128)
                else:
                    img = cv2.inpaint(img, big.astype(np.uint8) * 255, 7, cv2.INPAINT_TELEA)
            plates.append(cv2.resize(img, (W, H), interpolation=cv2.INTER_CUBIC))
            holes.append(cv2.resize(big.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR))
        comps = []
        for t in range(T):
            a = pm[t].numpy()
            if feather > 0:
                a = cv2.GaussianBlur(a, (0, 0), max(0.5, feather / 2.0))
            a = np.clip(a, 0, 1)[..., None]
            comps.append(frames[t].astype(np.float32) * a + plates[t].astype(np.float32) * (1 - a))
        comp_t = torch.from_numpy(np.stack(comps)).float().clamp(0, 255) / 255.0
        plate_t = torch.from_numpy(np.stack(plates)).float() / 255.0
        holes_t = torch.from_numpy(np.stack(holes)).float()

        path = []
        for t, Mx in enumerate(mats):
            ang = np.degrees(cv2.Rodrigues(Mx[:3, :3])[0].reshape(-1))
            path.append({"frame": t, "pitch": round(float(ang[0]), 2), "yaw": round(float(ang[1]), 2),
                         "roll": round(float(ang[2]), 2), "tx": round(float(Mx[0, 3]), 3), "ty": round(float(Mx[1, 3]), 3),
                         "tz": round(float(Mx[2, 3]), 3), "quality": round(quality[t], 2)})
        low = sum(1 for q in quality[1:] if q < 0.3)
        e = path[-1]
        info = (f"Background Plate 3D (experimental): {T} frames | camera yaw {e['yaw']:+.1f}° pitch {e['pitch']:+.1f}° "
                f"roll {e['roll']:+.1f}°, move ({e['tx']:+.2f}, {e['ty']:+.2f}, {e['tz']:+.2f}) | depth source "
                f"{src_depth:.2f} / background {bg_depth:.2f} -> translation x{tscale:.2f} ({translation}) | "
                f"{low} frames with weak tracking | holes {float(holes_t.mean()) * 100:.1f}% ({hole_fill})")
        print(f"[bruxosdovfx • SyncTile] {info}", flush=True)
        return (comp_t, plate_t, holes_t, json.dumps(path), info)


NODE_CLASS_MAPPINGS["SyncTileBackgroundPlate3DH3"] = SyncTileBackgroundPlate3D
NODE_DISPLAY_NAME_MAPPINGS["SyncTileBackgroundPlate3DH3"] = "bruxosdovfx • Background Plate 3D (MoGe, experimental)"
