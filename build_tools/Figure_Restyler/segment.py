"""Split a Bartholomew frame into materials, by colour and by place.

The colour thresholds were tuned on Bartholomew (middling_bartholomew): a
red cap and coat, a brown fur collar, cool dark hair, belt and boots, warm
dark outlines. Another figure needs its own thresholds.
"""
import numpy as np
from PIL import Image

MATS = ['none', 'skin', 'eye_white', 'cap', 'coat', 'fur', 'gold',
        'hair', 'belt', 'boots', 'outline']
ID = {n: i for i, n in enumerate(MATS)}


def hsv(rgb):
    rgb = rgb / 255.0
    mx = rgb.max(-1); mn = rgb.min(-1); d = mx - mn
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.zeros_like(mx)
    nz = d > 1e-6
    rm = nz & (mx == r); gm = nz & (mx == g) & ~rm; bm = nz & ~rm & ~gm
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = (b - r)[gm] / d[gm] + 2
    h[bm] = (r - g)[bm] / d[bm] + 4
    h *= 60
    s = np.where(mx > 0, d / np.maximum(mx, 1e-6), 0)
    return h, s, mx


def components(mask):
    """4-connected labels without scipy."""
    lab = np.zeros(mask.shape, int)
    n = 0
    H, W = mask.shape
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]:
            continue
        n += 1
        stack = [(y0, x0)]
        lab[y0, x0] = n
        while stack:
            y, x = stack.pop()
            for yy, xx in ((y+1, x), (y-1, x), (y, x+1), (y, x-1)):
                if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    stack.append((yy, xx))
    return lab, n


def mode_filter(labels, choices, r=3):
    """Each pixel among `choices` takes the commonest of them in its (2r+1)^2 box."""
    H, W = labels.shape
    counts = []
    for c in choices:
        m = (labels == c).astype(np.int32)
        p = np.pad(m, r)
        ii = p.cumsum(0).cumsum(1)
        ii = np.pad(ii, ((1, 0), (1, 0)))
        k = 2 * r + 1
        box = ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]
        counts.append(box)
    counts = np.stack(counts)
    best = np.array(choices)[counts.argmax(0)]
    out = labels.copy()
    sel = np.isin(labels, choices)
    out[sel] = best[sel]
    return out


def segment(a):
    rgb = a[..., :3].astype(float)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    alpha = a[..., 3]
    h, s, v = hsv(rgb)
    mat = np.zeros(alpha.shape, int)
    vis = alpha > 0
    gr = g / np.maximum(r, 1)
    cool = (b >= r - 6) | (s < 0.18)
    skin = vis & (v > 0.62) & (s < 0.62) & ((h <= 42) | (h >= 345))
    white = vis & (s < 0.12) & (v > 0.75)
    gold = vis & ~skin & (h > 33) & (h < 60) & (s > 0.45) & (v > 0.45)
    warm = vis & ~skin & ~white & ~gold & ~cool
    red = warm & (gr < 0.36) & (v >= 0.2)
    fur = warm & (gr >= 0.36) & (v >= 0.15)
    outline = warm & ~red & ~fur
    blackish = vis & (v < 0.05)
    greys = vis & cool & ~skin & ~white & ~blackish

    mat[outline | blackish] = ID['outline']
    mat[skin] = ID['skin']; mat[white] = ID['eye_white']; mat[gold] = ID['gold']
    mat[fur] = ID['fur']; mat[red] = ID['coat']
    # fur and cloth are noisy where they meet: smooth the boundary
    mat = mode_filter(mat, [ID['fur'], ID['coat']], 3)

    furm = mat == ID['fur']
    wide = np.nonzero(furm.sum(1) >= 30)[0]
    # the longest run of wide rows is the collar
    runs = np.split(wide, np.nonzero(np.diff(wide) > 3)[0] + 1)
    run = max(runs, key=len)
    collar_top, collar_bot = int(run.min()) - 4, int(run.max()) + 4
    ys0 = np.arange(a.shape[0])[:, None]
    mat[furm & (ys0 < collar_top)] = ID['outline']   # the face's brown edge
    mat[furm & (ys0 > collar_bot)] = ID['coat']
    collar_mid = (collar_top + collar_bot) // 2

    ys = np.arange(a.shape[0])[:, None] * np.ones((1, a.shape[1]), int)
    cloth = mat == ID['coat']
    mat[cloth & (ys < collar_mid)] = ID['cap']
    coat = mat == ID['coat']
    rows = np.nonzero(coat.sum(1) > 20)[0]
    coat_bottom = int(rows.max())
    mat[greys & (ys < collar_mid)] = ID['hair']
    mat[greys & (ys >= collar_mid) & (ys < coat_bottom - 8)] = ID['belt']
    mat[greys & (ys >= coat_bottom - 8)] = ID['boots']
    info = dict(collar_top=collar_top, collar_bot=collar_bot,
                collar_mid=collar_mid, coat_bottom=coat_bottom)
    return mat, info


