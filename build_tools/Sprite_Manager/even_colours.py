"""Evening out the colours of a direction's frames, so the walk does not flicker.

Every frame is drawn by the image model on its own, and each comes back a
little lighter, darker or warmer here and there than the one before. Played
as a walk, that shows as flicker. This pulls each frame's colours back onto
one reference sprite - the direction's standing sprite, else the front one -
material by material:

1. The reference's colours are grouped into REFERENCE_CLUSTERS clusters in
   Lab colour space (k-means): the skin, the dress, the hair, the shoes ...
2. Every pixel of a frame belongs to the clusters near it, softly, so a
   shading gradient is never cut in two.
3. Per cluster, the frame's mean colour is compared with the reference's;
   the difference is the cluster's shift. Each pixel moves by the shifts of
   its clusters, weighted as it belongs to them. Assigning and measuring is
   repeated a few times, because a frame that is off assigns some of its
   pixels to the wrong cluster at first.

The shading inside each material stays the frame's own; only its overall
colour moves. A shift is capped at MAX_SHIFT and pixels far from every
cluster of the reference (something the reference does not have) are left
nearly alone, so a real difference is not painted over. Alpha is not
touched. It needs numpy (build_tools/requirements.txt).
"""

from collections import namedtuple

import pygame

try:
    import numpy as np
    NUMPY_ERROR = ''
except ImportError:
    np = None
    NUMPY_ERROR = 'needs numpy: pip install -r build_tools/requirements.txt'

REFERENCE_CLUSTERS = 12
SAMPLE_PIXELS = 8000       # reference pixels the clusters are found on
KMEANS_ROUNDS = 20
MATCH_ROUNDS = 5           # assign pixels, measure shifts, repeat
SOFTNESS = 8.0             # Lab distance over which a pixel's belonging fades from one cluster to the next
FAR = 25.0                 # pixels this far from every cluster get only a little of the shift
MAX_SHIFT = 18.0           # the largest a cluster may move, in Lab units (about 2.3 is a just visible difference)
MIN_SHARE = 0.002          # a cluster needs this share of the frame's pixels to be measured
SOLID_ALPHA = 128          # pixels at least this opaque are measured; all visible ones are moved
SEED = 0

Change = namedtuple('Change', 'path mean peak')   # how much a frame moved: mean and largest pixel change


# ---------------------------------------------------------------------------
# sRGB <-> Lab (D65)
# ---------------------------------------------------------------------------

_RGB_TO_XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                        [0.2126729, 0.7151522, 0.0721750],
                        [0.0193339, 0.1191920, 0.9503041]]) if np else None
_WHITE = np.array([0.95047, 1.0, 1.08883]) if np else None


def rgb_to_lab(rgb):
    """(n, 3) sRGB 0..255 -> (n, 3) Lab."""
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ _RGB_TO_XYZ.T / _WHITE
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1)


def lab_to_rgb(lab):
    """(n, 3) Lab -> (n, 3) sRGB 0..255 as uint8."""
    fy = (lab[:, 0] + 16) / 116
    f = np.stack([fy + lab[:, 1] / 500, fy, fy - lab[:, 2] / 200], axis=1)
    xyz = np.where(f ** 3 > 216 / 24389, f ** 3, (116 * f - 16) / (24389 / 27)) * _WHITE
    c = xyz @ np.linalg.inv(_RGB_TO_XYZ).T
    c = np.where(c > 0.0031308, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055, 12.92 * c)
    return np.clip(np.rint(c * 255), 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------
# Clusters
# ---------------------------------------------------------------------------

def read_sprite(path):
    """(rgb (w, h, 3) uint8, alpha (w, h) uint8) of a sprite file.

    Raises:
        pygame.error, OSError: If the file cannot be read.
    """
    surface = pygame.image.load(str(path))
    return pygame.surfarray.array3d(surface), pygame.surfarray.array_alpha(surface)


def find_clusters(lab, rng):
    """REFERENCE_CLUSTERS centres of the colours in `lab` (k-means, k-means++ start)."""
    if len(lab) > SAMPLE_PIXELS:
        lab = lab[rng.choice(len(lab), SAMPLE_PIXELS, replace=False)]
    k = min(REFERENCE_CLUSTERS, len(lab))
    centres = [lab[rng.integers(len(lab))]]
    for _ in range(k - 1):
        d2 = ((lab[:, None] - np.array(centres)[None]) ** 2).sum(2).min(1)
        centres.append(lab[rng.choice(len(lab), p=d2 / d2.sum())] if d2.sum() else lab[0])
    centres = np.array(centres)
    for _ in range(KMEANS_ROUNDS):
        nearest = ((lab[:, None] - centres[None]) ** 2).sum(2).argmin(1)
        for i in range(k):
            members = lab[nearest == i]
            if len(members):
                centres[i] = members.mean(0)
    return centres


def belonging(lab, centres):
    """(n, k) how much each pixel belongs to each cluster; rows sum to at most 1.

    Soft within SOFTNESS, and fading out for pixels far from every cluster.
    """
    d2 = ((lab[:, None] - centres[None]) ** 2).sum(2)
    nearest = d2.min(1, keepdims=True)
    weights = np.exp(-(d2 - nearest) / (2 * SOFTNESS ** 2))
    weights /= weights.sum(1, keepdims=True)
    return weights * np.exp(-nearest / (2 * FAR ** 2))


def cluster_means(lab, weights):
    """(k, 3) weighted mean colour per cluster and (k,) the weight it rests on."""
    total = weights.sum(0)
    return (weights.T @ lab) / np.maximum(total, 1e-9)[:, None], total


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

class Reference:
    """A sprite's colour clusters, which frames are matched to."""

    def __init__(self, path):
        """
        Raises:
            pygame.error, OSError: If the file cannot be read.
            ValueError: If the sprite has no solid pixels.
        """
        rgb, alpha = read_sprite(path)
        solid = alpha.reshape(-1) >= SOLID_ALPHA
        if not solid.any():
            raise ValueError(f'{path.name} is empty')
        lab = rgb_to_lab(rgb.reshape(-1, 3)[solid].astype(float))
        self.path = path
        self.centres = find_clusters(lab, np.random.default_rng(SEED))
        self.means, _ = cluster_means(lab, belonging(lab, self.centres))

    def match(self, rgb, alpha):
        """The frame's rgb with its colours pulled onto the reference's, and the change per pixel."""
        flat = rgb.reshape(-1, 3).astype(float)
        visible = alpha.reshape(-1) > 0
        solid = alpha.reshape(-1)[visible] >= SOLID_ALPHA
        lab = rgb_to_lab(flat[visible])
        moved = np.zeros_like(lab)
        min_weight = MIN_SHARE * max(1, solid.sum())
        for _ in range(MATCH_ROUNDS):
            weights = belonging(lab + moved, self.centres)
            means, total = cluster_means(lab[solid], weights[solid])
            shifts = self.means - means
            length = np.linalg.norm(shifts, axis=1, keepdims=True)
            shifts *= np.minimum(1, MAX_SHIFT / np.maximum(length, 1e-9))
            shifts[total < min_weight] = 0
            moved = weights @ shifts
        out = flat.copy()
        out[visible] = lab_to_rgb(lab + moved)
        change = np.zeros(len(flat))
        change[visible] = np.linalg.norm(moved, axis=1)
        return out.astype(np.uint8).reshape(rgb.shape), change[visible]


def write_sprite(path, rgb, alpha):
    """Save rgb and alpha arrays (as surfarray gives them) as a PNG."""
    surface = pygame.Surface(rgb.shape[:2], pygame.SRCALPHA, 32)
    pygame.surfarray.pixels3d(surface)[...] = rgb
    pygame.surfarray.pixels_alpha(surface)[...] = alpha
    pygame.image.save(surface, str(path))


def even_out(reference_path, frame_paths, backup_dir):
    """Pull every frame's colours onto the reference sprite, saving over the frames.

    Each frame is copied into `backup_dir` first, under its own name.

    Returns:
        [Change] per frame.

    Raises:
        RuntimeError: Without numpy.
        pygame.error, OSError: If a file cannot be read or written.
        ValueError: If the reference is empty.
    """
    if NUMPY_ERROR:
        raise RuntimeError(NUMPY_ERROR)
    reference = Reference(reference_path)
    backup_dir.mkdir(parents=True, exist_ok=True)
    changes = []
    for path in frame_paths:
        rgb, alpha = read_sprite(path)
        write_sprite(backup_dir / path.name, rgb, alpha)
        matched, change = reference.match(rgb, alpha)
        write_sprite(path, matched, alpha)
        changes.append(Change(path, float(change.mean()) if len(change) else 0.0,
                              float(change.max()) if len(change) else 0.0))
    return changes
