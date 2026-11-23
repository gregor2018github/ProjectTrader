"""Konrad: Bartholomew's walk with a new head and new clothes, made by code.

Body: Bartholomew's frames repainted material by material (shading kept).
Head: drawn once per direction on the standing frame (cap taken off, a
bowl-cut dome of ginger hair, a beard), then pasted onto every frame at
the shift Bartholomew's own head has there; right is left mirrored.
"""
import os
import sys
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from segment import ID, components, segment  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
NPCS = os.path.join(ROOT, 'assets', 'map_sprites', 'figurines', 'humans', 'npcs')
SRC = os.path.join(NPCS, 'middling_bartholomew')
DEST = os.path.join(NPCS, 'middling_konrad')
DIRS = ['front', 'back', 'left', 'right']
FRAMES = ['static'] + ['move%d' % i for i in range(1, 7)]


def lum(rgb):
    return rgb[..., 0] * 0.3 + rgb[..., 1] * 0.59 + rgb[..., 2] * 0.11

def ramp(colours, t):
    c = np.array(colours, float)
    t = np.clip(t, 0, 1) * (len(c) - 1)
    i = np.minimum(t.astype(int), len(c) - 2)
    f = (t - i)[..., None]
    return c[i] * (1 - f) + c[i + 1] * f

def grow_labels(mat, sources, steps=8):
    """Give each pixel the nearest label among `sources` (by repeated dilation)."""
    near = np.where(np.isin(mat, sources), mat, 0)
    for _ in range(steps):
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(near, (dy, dx), (0, 1))
            near = np.where((near == 0) & (sh != 0), sh, near)
    return near

def load_all():
    out = {}
    for d in DIRS:
        for f in FRAMES:
            a = np.array(Image.open(os.path.join(SRC, f'bartholomew_{d}_{f}.png')).convert('RGBA'))
            mat, info = segment(a)
            out[(d, f)] = (a, mat, info)
    return out

def ranges(frames):
    """Each material's brightness range over every frame, so no frame flickers."""
    acc = {}
    for a, mat, _ in frames.values():
        L = lum(a[..., :3].astype(float))
        for name, i in ID.items():
            sel = (mat == i) & (a[..., 3] > 128)
            if sel.any():
                acc.setdefault(name, []).append(L[sel])
    return {n: (np.percentile(np.concatenate(v), 3), np.percentile(np.concatenate(v), 97))
            for n, v in acc.items()}

def hash2(x, y, seed=0):
    h = (x * 374761393 + y * 668265263 + seed * 2147483647) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    return (h & 0xFFFF) / 65535.0

HEADCLS = [ID['cap'], ID['hair'], ID['skin'], ID['eye_white'], ID['outline']]

def head_mask(mat, info):
    H, W = mat.shape
    ys = np.arange(H)[:, None]
    return np.isin(mat, HEADCLS) & (ys < info['collar_top'] - 2)

def best_shift(ref, m, r=14):
    best = (-1, 0, 0)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            sh = np.roll(m, (-dy, -dx), (0, 1))
            inter = (sh & ref).sum(); uni = (sh | ref).sum()
            iou = inter / uni
            if iou > best[0]:
                best = (iou, dy, dx)
    return best


GX, GY = 2, 0          # the pseudo-pixels' grid phase
BEARD, TRIM, CAPE, HAIR = 102, 103, 104, 105

PAL = {
    'cape': [(70, 46, 14), (128, 92, 30), (176, 134, 52), (212, 176, 92)],
    'coat': [(16, 40, 34), (28, 70, 54), (44, 100, 72), (70, 132, 92)],
    'skin': [(170, 100, 72), (212, 148, 110), (232, 182, 146), (243, 206, 174)],
    'gold': [(110, 110, 118), (170, 172, 180), (225, 228, 235)],
    'belt': [(34, 20, 10), (78, 48, 24), (118, 78, 42)],
    'boots': [(28, 18, 12), (66, 42, 24), (104, 70, 40)],
    'hair': [(64, 26, 10), (118, 50, 20), (164, 80, 32), (204, 118, 52), (232, 158, 88)],
}
HAIR_INK = np.array((44, 18, 8), float)
INK = {k: np.array(v[0], float) * 0.55 for k, v in PAL.items()}
INK['hair'] = HAIR_INK


def dilate(m, n=1):
    for _ in range(n):
        m = m | np.roll(m, 1, 0) | np.roll(m, -1, 0) | np.roll(m, 1, 1) | np.roll(m, -1, 1)
    return m


def largest(mask):
    lab, n = components(mask)
    if not n:
        return mask & False
    sizes = np.bincount(lab.ravel())[1:]
    return lab == 1 + int(np.argmax(sizes))


# ---------------------------------------------------------------- body
def repaint_body(a, mat, info, R):
    """Every material repainted; returns colours and the new labels."""
    rgb = a[..., :3].astype(float)
    H, W = mat.shape
    ys, xs = np.mgrid[0:H, 0:W]
    L = lum(rgb)
    lab = mat.copy()
    cb = info['collar_bot']
    skin = mat == ID['skin']

    # the collar becomes a woollen shoulder cape with a dagged hem
    cape = mat == ID['fur']
    if cape.any():
        cx0 = xs[cape].min()
        for x in np.nonzero(cape.any(0))[0]:
            bottom = np.nonzero(cape[:, x])[0].max()
            ph = ((x - cx0) % 16) / 16.0
            depth = int(round(7 * (1 - np.sin(np.pi * ph))))
            lab[(ys[:, x] > bottom - depth) & cape[:, x], x] = ID['coat']
        lab[lab == ID['fur']] = CAPE

    # a band of the cape's cloth along the coat's hem, and cuffs
    coat = lab == ID['coat']
    for x in range(W):
        col = np.nonzero(coat[:, x] & (ys[:, x] > cb + 40))[0]
        if len(col):
            bottom = col.max()
            lab[(ys[:, x] > bottom - 12) & coat[:, x], x] = TRIM
    hands = skin & (ys > cb)
    lab[dilate(hands, 6) & (lab == ID['coat'])] = TRIM

    out = rgb.copy()

    def paint(sel, pal, lo, hi, squeeze=1.0, centre=0.5):
        if sel.any():
            t = (L[sel] - lo) / max(hi - lo, 1)
            out[sel] = ramp(pal, centre + (t - 0.5) * squeeze)

    paint(lab == CAPE, PAL['cape'], *R['fur'], 0.6, 0.55)
    paint(lab == ID['coat'], PAL['coat'], *R['coat'])
    paint(lab == TRIM, PAL['cape'], *R['coat'], 0.5, 0.62)
    paint(lab == ID['skin'], PAL['skin'], *R['skin'])
    paint(lab == ID['gold'], PAL['gold'], *R['gold'])
    paint(lab == ID['belt'], PAL['belt'], *R['belt'])
    paint(lab == ID['boots'], PAL['boots'], *R['boots'])
    paint(lab == ID['hair'], PAL['hair'], *R['hair'], 0.7, 0.66)
    paint(lab == ID['cap'], PAL['hair'], *R['cap'], 0.9, 0.45)

    groups = {CAPE: 'cape', TRIM: 'cape', ID['coat']: 'coat', ID['belt']: 'belt',
              ID['boots']: 'boots', ID['hair']: 'hair', ID['cap']: 'hair'}
    near = grow_labels(lab, list(groups) + [ID['skin'], ID['eye_white'], ID['gold']], 10)
    ol = lab == ID['outline']
    for k, name in groups.items():
        sel = ol & (near == k)
        if sel.any():
            kk = np.clip(L[sel] / 40.0, 0.35, 1.0)[:, None]
            out[sel] = INK[name] * kk * 0.85 + rgb[sel] * 0.15
    return out, lab, near


# ---------------------------------------------------------------- head
HEADS = {
    # dome: centre and radii in pseudo-pixels; fringe: the row its edge
    # hangs to; face_front: which side the face looks (for the parting)
    'front': dict(cx=23.5, cy=21.0, rx=17.0, ry=12.0, fringe=19, kind='front'),
    'back': dict(cx=25.0, cy=21.0, rx=18.0, ry=13.0, fringe=None, kind='back', ear_cover=4, reach=9),
    'left': dict(cx=24.5, cy=21.0, rx=15.5, ry=12.0, fringe=19, kind='left'),
}


def head_region(mat, info):
    """Bartholomew's head pixels: cap, hair, face, ears, eyes and their outlines."""
    H, W = mat.shape
    ys = np.arange(H)[:, None] * np.ones((1, W), int)
    ct = info['collar_top']
    skin = mat == ID['skin']
    lab, n = components(skin)
    head_skin = np.zeros_like(skin)
    for k in range(1, n + 1):
        comp = lab == k
        if ys[comp].min() < ct:
            head_skin |= comp
    core = np.isin(mat, [ID['cap'], ID['hair'], ID['eye_white']]) | head_skin
    core &= ys < ct + 14
    ring = dilate(core, 3) & (mat == ID['outline']) & (ys < ct + 6)
    return fill_holes(core | ring), head_skin


def fill_holes(m):
    """Pixels shut in by the mask (the pupils) belong to it."""
    outside = np.zeros_like(m)
    outside[0, :] = ~m[0, :]; outside[-1, :] = ~m[-1, :]
    outside[:, 0] |= ~m[:, 0]; outside[:, -1] |= ~m[:, -1]
    while True:
        grown = dilate(outside, 1) & ~m
        if (grown == outside).all():
            return m | ~outside
        outside = grown


def build_head(d, frames, R):
    a, mat, info = frames[(d, 'static')]
    body, lab, near = repaint_body(a, mat, info, R)
    H, W = mat.shape
    ys, xs = np.mgrid[0:H, 0:W]
    region, head_skin = head_region(mat, info)
    ct = info['collar_top']
    spec = HEADS[d]

    # start from the parts kept: face, ears, eyes with their own outlines,
    # and the old hair away from the cap (its rim is hair-coloured too)
    cap_m = mat == ID['cap']
    near_cap = dilate(cap_m, 18)
    skinish = head_skin | (mat == ID['eye_white'])
    own_ink = region & (mat == ID['outline']) & np.isin(near, [ID['skin'], ID['eye_white']])
    own_ink |= region & (mat == ID['outline']) & (near == ID['hair']) & ~near_cap
    old_hair = region & (mat == ID['hair']) & ~near_cap
    keep = (region & skinish) | own_ink | old_hair
    keep |= fill_holes(keep) & region      # the pupils
    col = np.zeros((H, W, 3)); alpha = np.zeros((H, W), bool)
    col[keep] = body[keep]; alpha[keep] = True

    # the face, and where the eyes are
    face = largest(head_skin & (ys < ct)) if d != 'back' else head_skin & False
    ew = (mat == ID['eye_white'])
    eye_bot = ys[ew].max() if ew.any() else None

    # ---- the dome, in pseudo-pixels ----
    cols, rows = W // 4 + 1, H // 4 + 1
    gx = np.arange(cols)[None, :] + 0.5
    gy = np.arange(rows)[:, None] + 0.5
    nx = (gx - spec['cx']) / spec['rx']
    ny = (gy - spec['cy']) / spec['ry']
    inside = nx ** 2 + ny ** 2 <= 1.0
    # the dome only above the ears' middle; below it the old hair stays
    dome = inside & (gy < spec['cy'] + spec.get('reach', 2))
    # the ears stay in front of the hair
    ears = head_skin & ~face
    ear_zone = dilate(ears, 6) & (keep | ears)
    # fringe: hangs over the forehead in uneven locks
    face_l = np.zeros((rows, cols), bool)
    for r in range(rows):
        for c in range(cols):
            x0, y0 = c * 4 + GX, r * 4 + GY
            if 0 <= y0 + 2 < H and 0 <= x0 + 2 < W:
                face_l[r, c] = face[y0 + 2, x0 + 2]
    if spec['fringe'] is not None:
        locks = [0, 1, 1, 2, 1, 0, 1, 2, 2, 1, 0, 1, 1, 2, 1, 1, 0]
        for c in range(cols):
            edge = spec['fringe'] + locks[c % len(locks)]
            if spec['kind'] == 'left':
                # swept back: longer at the front, then up to the ear
                edge = spec['fringe'] + (2 if c < 13 else 1 if c < 17 else 0) - (c % 3 == 2)
            dome[:, c] &= ~(face_l[:, c] & (gy[:, 0] >= edge))
    else:
        pass
    # shading: light from the top left; quantised like pixel art
    shade = 0.62 - 0.30 * ny - 0.16 * nx
    if spec['kind'] == 'back':
        shade = 0.60 - 0.30 * ny - 0.10 * nx
    # strands: arcs from the crown, a pseudo-pixel darker
    ang = np.arctan2(gy - (spec['cy'] - spec['ry'] * 0.9), gx - spec['cx'])
    strand = (np.floor(ang * 7.0) % 3 == 0) & (ny > -0.55)
    shade = shade - strand * 0.14
    # a shine across the crown
    shine = (np.abs(nx * nx + (ny + 0.15) ** 2 - 0.42) < 0.07) & (ny < -0.1) & (nx < 0.35)
    shade = shade + shine * 0.22
    levels = np.clip(np.round(shade * 4) / 4, 0, 1)
    dome_rgb = ramp(PAL['hair'], levels)
    # outline: the dome's outer pseudo-pixels against nothing above
    up = np.roll(dome, 1, 0); dn = np.roll(dome, -1, 0)
    lf = np.roll(dome, 1, 1); rt = np.roll(dome, -1, 1)
    rim = dome & ~(up & dn & lf & rt)
    # the fringe's lower edge sits on the face: darker, not black
    on_face = rim & np.roll(face_l, -1, 0)
    # no ink where the old hair goes on below the dome
    kept_l = np.zeros((rows, cols), bool)
    for r in range(rows):
        for c in range(cols):
            x0, y0 = c * 4 + GX, r * 4 + GY
            if 0 <= y0 + 2 < H and 0 <= x0 + 2 < W:
                kept_l[r, c] = keep[y0 + 2, x0 + 2]
    rim &= ~(np.roll(kept_l, -1, 0) & ~np.roll(dome, -1, 0) & (gy > spec['cy']))
    dome_px = np.zeros((H, W), bool)
    for r, c in zip(*np.nonzero(dome)):
        dome_px[r * 4 + GY:r * 4 + GY + 4, c * 4 + GX:c * 4 + GX + 4] = True
    for r in range(rows):
        for c in range(cols):
            if not dome[r, c]:
                continue
            x0, y0 = c * 4 + GX, r * 4 + GY
            if y0 >= H or x0 >= W:
                continue
            blk = ear_zone[y0:y0 + 4, x0:x0 + 4]
            # the hair falls over the ears' tops, the rest of them shows
            if blk.mean() > 0.5 and r >= spec['cy'] + spec.get('ear_cover', 0):
                continue
            if rim[r, c] and not on_face[r, c]:
                cc = HAIR_INK
            elif on_face[r, c]:
                cc = np.array(PAL['hair'][0], float)
            else:
                cc = dome_rgb[r, c]
            col[y0:y0 + 4, x0:x0 + 4] = cc
            alpha[y0:y0 + 4, x0:x0 + 4] = True

    # ---- the beard: the face below the eyes, sideburns up to the hair ----
    if face.any() and eye_bot is not None:
        fy0 = ys[face].min()
        beard = face & (ys > eye_bot + 6)
        fx = xs[face]
        if spec['kind'] == 'front':
            l, r = fx.min(), fx.max()
            side = face & ((xs < l + 8) | (xs > r - 8)) & (ys > fy0 + 30)
        else:
            # in front of the ear: the face's back edge
            back = fx.max()
            side = face & (xs > back - 14) & (ys > fy0 + 22)
        beard |= side
        # it hangs over the collar, longest at the chin
        cols_b = np.nonzero(beard.any(0))[0]
        c0, c1 = cols_b.min(), cols_b.max()
        for x in cols_b:
            bottom = ys[:, x][beard[:, x]].max()
            u = (x - c0) / max(c1 - c0, 1)
            if spec['kind'] == 'front':
                drop = 14 * max(0.0, 1 - (2 * u - 1) ** 2) ** 0.6
            else:
                drop = 16 * max(0.0, 1.2 - 1.6 * u)
            drop = int(drop) // 4 * 4
            if drop:
                beard[bottom + 1:bottom + 1 + drop, x] = True
        # a mouth: a dark dash in the middle of the beard, front only
        bt = beard.copy()
        b_rgb = np.zeros((H, W, 3))
        by0 = ys[bt].min(); bx0 = xs[bt].min()
        L = lum(a[..., :3].astype(float))
        t = (L - R['skin'][0]) / max(R['skin'][1] - R['skin'][0], 1)
        n1 = np.zeros((H, W))
        for (y, x) in zip(*np.nonzero(bt)):
            n1[y, x] = hash2((x - bx0) // 4, (y - by0) // 8 + ((x - bx0) // 4) % 2, 5)
        tt = 0.45 + (t - 0.5) * 0.6 + (n1 - 0.5) * 0.35
        b_rgb[bt] = ramp(PAL['hair'][:4], np.clip(tt[bt], 0, 1))
        col[bt] = b_rgb[bt]
        over = bt & ~alpha
        alpha[bt] = True
        # the beard's rim: darker where it meets skin or the outline
        ed = bt & ~(np.roll(bt, 1, 0) & np.roll(bt, -1, 0) & np.roll(bt, 1, 1) & np.roll(bt, -1, 1))
        col[ed & ~np.roll(face & ~bt, 1, 0)] *= 0.8
        if spec['kind'] == 'front':
            cx = int(round(xs[face].mean()))
            my = int(eye_bot + 22)
            col[my:my + 4, cx - 8:cx + 8] = (70, 30, 22)
            col[my - 4:my, cx - 12:cx + 12] = ramp(PAL['hair'], np.array(0.75))

    # tidy up: no thin dark spikes, one piece, no holes, an inked edge
    def erode(m, n):
        for _ in range(n):
            m = m & np.roll(m, 1, 0) & np.roll(m, -1, 0) & np.roll(m, 1, 1) & np.roll(m, -1, 1)
        return m
    if spec['kind'] == 'back':
        # the ears' tips, which the cap hid, would stick up like an elf's
        ear_top = ys[ears].min() if ears.any() else 0
        tips = dilate(ears, 4) & (ys < ear_top + 6) & ~dome_px & (lum(col) < 90)
        alpha &= ~tips
    opened = dilate(erode(alpha, 5), 5)
    spike = alpha & ~opened & (lum(col) < 90)
    alpha &= ~spike
    main = largest(alpha)
    alpha &= main
    holes = fill_holes(alpha) & ~alpha
    col[holes] = PAL['hair'][1]
    alpha |= holes
    border = alpha & dilate(~alpha, 3)
    darkish = lum(col) < 70
    hairy = border & ~darkish & ~dilate(skinish, 1) | (border & ~darkish & ~head_skin & ~(mat == ID['eye_white']))
    col[hairy] = HAIR_INK
    rgba = np.dstack([np.clip(col, 0, 255), alpha * 255]).astype(np.uint8)
    if face.any() and eye_bot is not None:
        rgba[over, 3] = 254
    return rgba, region


def compose(frames, R):
    heads = {d: build_head(d, frames, R) for d in ('front', 'back', 'left')}
    out = {}
    for d in ('front', 'back', 'left'):
        a0, m0, i0 = frames[(d, 'static')]
        ref = head_mask(m0, i0)
        head, _ = heads[d]
        for f in FRAMES:
            a, mat, info = frames[(d, f)]
            body, lab, near = repaint_body(a, mat, info, R)
            alpha = a[..., 3].copy()
            _, dy, dx = best_shift(ref, head_mask(mat, info), 24)
            region, _ = head_region(mat, info)
            # take Bartholomew's head off ...
            alpha[region] = 0
            alpha[:max(info['collar_top'] - 12, 0)] = 0
            # ... and put the new one where his was
            hd = np.roll(head, (dy, dx), (0, 1))
            under = np.isin(lab, [CAPE, ID['coat'], TRIM, ID['gold'], ID['belt']])
            put = (hd[..., 3] > 0) & (~under | (hd[..., 3] == 254))
            res = np.dstack([np.clip(body, 0, 255), alpha]).astype(np.uint8)
            res[put] = hd[put]
            res[put, 3] = 255
            # a hole left between the chin and the collar: fill with ink
            hole = region & ~put & dilate(put, 2) & dilate(under, 2)
            res[hole] = (40, 22, 14, 255)
            out[(d, f)] = res
    for f in FRAMES:
        out[('right', f)] = out[('left', f)][:, ::-1].copy()
    return out


def sheet(frames, path, scale=2):
    W, H = 208, 336
    s = Image.new('RGBA', (W * 7, H * 4), (190, 200, 190, 255))
    for r, d in enumerate(DIRS):
        for c, f in enumerate(FRAMES):
            s.alpha_composite(Image.fromarray(frames[(d, f)]), (c * W, r * H))
    s.resize((s.width // scale, s.height // scale), Image.NEAREST).save(path)


def zoom(frames, keys, path):
    z = Image.new('RGBA', (208 * len(keys), 336), (190, 200, 190, 255))
    for i, k in enumerate(keys):
        z.alpha_composite(Image.fromarray(frames[k]), (i * 208, 0))
    z.resize((z.width * 2, z.height * 2), Image.NEAREST).save(path)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--preview', help='write a contact sheet here instead of the sprites')
    args = p.parse_args()
    frames = load_all()
    R = ranges(frames)
    res = compose(frames, R)
    if args.preview:
        sheet(res, args.preview)
    else:
        os.makedirs(DEST, exist_ok=True)
        for (d, f), img in res.items():
            Image.fromarray(img).save(os.path.join(DEST, f'konrad_{d}_{f}.png'))
        print(f'wrote {len(res)} frames to {DEST}')
