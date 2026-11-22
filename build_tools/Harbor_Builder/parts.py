"""The stones and boards of a laid surface, found and coloured one by one.

Pieces are painted in their material's neutral colours. Once a surface is
laid, every connected stone, board and beam (a run of pixels of one kind,
between joints and gaps) is found, wherever tile edges cut it, and given its
own colour, keyed by where it lies: so a cobble straddling two tiles is one
cobble, and two piers laid from the same pieces are not copies.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import pier_materials as pm
from pier_materials import BEAM, BOARD, COBBLE, FLAGSTONE, colour, jitter, rng_for

# Each board and stone its own colour
BOARD_TONES = (0.88, 1.08)
BOARD_BLEACHED = 0.10             # share of boards worn pale
BOARD_DARK = 0.08                 # and of boards gone dark
BEAM_TONES = (0.93, 1.04)
BRICK_SHARE = 0.025               # now and then a brick bat among the cobbles
KERB_RED_SHARE = 0.04
WEATHERED = (1 / 10, 0.94)        # share of flagstones weathered darker, and how much
COBBLE_SPREAD = 0.03              # kept small: the paving is ground, not a wall to look at


def label(solid: np.ndarray) -> np.ndarray:
    """Number the 4-connected parts of a mask: each pixel gets its part's lowest pixel index, -1 outside."""
    h, w = solid.shape
    n = h * w
    flat = solid.ravel()
    labels = np.append(np.where(flat, np.arange(n), n), n)       # n: outside, pointing at itself
    index = np.arange(n).reshape(h, w)
    across = solid[:, :-1] & solid[:, 1:]
    down = solid[:-1] & solid[1:]
    a = np.concatenate([index[:, :-1][across], index[:-1][down]])
    b = np.concatenate([index[:, 1:][across], index[1:][down]])
    while True:
        low = np.minimum(labels[a], labels[b])
        new = labels.copy()
        np.minimum.at(new, a, low)
        np.minimum.at(new, b, low)
        new = new[new[new]]                                       # jump along the chains
        if np.array_equal(new, labels):
            break
        labels = new
    out = labels[:n].reshape(h, w)
    out[~solid] = -1
    return out


@dataclass
class Parts:
    """The stones and boards of a laid surface: which part each pixel is, and where each part lies."""

    labels: np.ndarray            # (h, w): the part's number (0..n-1), -1 for joints and gaps
    centres: np.ndarray           # (n, 2): each part's middle, x and y
    kinds: np.ndarray             # (n,): COBBLE, FLAGSTONE, BOARD or BEAM


def find_parts(kind: np.ndarray) -> Parts:
    raw = label(kind > 0)
    solid = raw >= 0
    _, inverse = np.unique(raw[solid], return_inverse=True)
    inverse = inverse.ravel()
    n = int(inverse.max()) + 1 if inverse.size else 0
    labels = np.full(kind.shape, -1)
    labels[solid] = inverse
    ys, xs = np.nonzero(solid)
    size = np.bincount(inverse, minlength=n)
    centres = np.stack([np.bincount(inverse, xs + 0.5, n), np.bincount(inverse, ys + 0.5, n)], 1) / size[:, None]
    kinds = np.zeros(n, np.uint8)
    np.maximum.at(kinds, inverse, kind[solid])
    return Parts(labels, centres, kinds)


def _part_colour(kind: int, rng: np.random.Generator) -> np.ndarray:
    """What a part's neutral colour is multiplied by: its own stone, brick, or board's tone."""
    if kind == COBBLE:
        stone = pm.STONE.brick if rng.random() < BRICK_SHARE else \
            pm.STONE.cobbles[rng.integers(len(pm.STONE.cobbles))]
        return jitter(colour(stone), rng, COBBLE_SPREAD) / colour(pm.COBBLE_NEUTRAL)
    if kind == FLAGSTONE:
        stone = pm.STONE.kerb_red if rng.random() < KERB_RED_SHARE else pm.STONE.kerb
        k = WEATHERED[1] if rng.random() < WEATHERED[0] else 1.0
        return jitter(colour(stone), rng, 0.04) * k / colour(pm.KERB_NEUTRAL)
    if kind == BOARD:
        roll = rng.random()
        if roll < BOARD_BLEACHED:
            return colour(pm.WOOD.oak_bleached) / colour(pm.WOOD.oak)
        tone = rng.uniform(*BOARD_TONES) * (0.85 if roll > 1 - BOARD_DARK else 1.0)
        return np.full(3, tone)
    return np.full(3, rng.uniform(*BEAM_TONES))


def colour_parts(albedo: np.ndarray, parts: Parts, key: str, origin: tuple = (0, 0)) -> None:
    """Give every stone and board its own colour, the same wherever it is cut across tiles.

    Args:
        albedo: Coloured in place.
        parts: Its stones and boards.
        key: Names the surface.
        origin: Where the canvas lies in the world, px; the colours are keyed
            by world position, so a surface laid larger keeps its stones' colours.
    """
    ox, oy = origin
    factors = np.array([_part_colour(k, rng_for(key, round(x + ox, 1), round(y + oy, 1)))
                        for (x, y), k in zip(parts.centres, parts.kinds)]).reshape(-1, 3)
    solid = parts.labels >= 0
    albedo[solid] *= factors[parts.labels[solid]]
