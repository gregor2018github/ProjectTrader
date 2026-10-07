"""Paint a forest floor of its own under a patch, leaves, grass and flowers.

The pinewood's floor is copies of one painting (``FLOOR_STAMP``). A patch
with ``painted_floor`` instead gets a floor made for exactly its shape: a
light wash of leaf litter and sunny moss that follows the patch's own depth,
so it fades out at the same wavy edge the trees thin out at, sprinkled with
small fallen leaves, and grass tufts and flowers cut out of the
``non_collision_deco`` motifs (plant_catalog.json) on the flowers layer
above it.

The motifs are not on the tile grid, so they cannot be copied tile by tile
without dragging pieces of their neighbours along; painted into the floor
they can stand anywhere. Everything is cut into tiles of a tileset of its own
(``woodland_floor`` by default) that only ever grows; the floor goes onto
the same layer as the pinewood's, so the game draws no extra layer.
"""

import json
import math
import os
import re
from typing import Dict, List, Optional, Tuple

import numpy as np
import pygame

from floor_baker import FloorBaker

DECO_CATALOG = "build_tools/Sprite_Manager/plant_catalog.json"
DECO_ATLAS = "assets/map_sprites/non_collision_deco/non_collision_deco.png"
COLUMNS = 64
#: Gids left free after the forest_floor_mix tileset, which keeps growing
#: as the pinewood's floor gets blended
MIX_HEADROOM = 6000

#: What a painted floor looks like; a patch's ``painted_floor`` dict may
#: override any of these
STYLE = dict(
    tileset="woodland_floor",
    # Leaf litter: warm straw, at most this opaque
    litter=(186, 162, 86), litter_alpha=78,
    # Sunny moss in patches
    moss=(176, 196, 84), moss_alpha=52,
    # A little humus deep in
    humus=(118, 98, 48), humus_alpha=34,
    # Fallen leaves per tile, deep in the wood
    leaves=9.0,
    leaf_colours=[(204, 156, 64), (184, 116, 48), (156, 146, 60), (218, 190, 100),
                  (140, 98, 46), (166, 176, 74), (196, 132, 54)],
    # Depth at which the floor starts, and at which it is at full strength
    edge=(-0.12, 0.35),
)


def _over(bottom: np.ndarray, top: np.ndarray) -> np.ndarray:
    """Straight-alpha "over" of two float RGBA arrays (0..1)."""
    ta, ba = top[..., 3:4], bottom[..., 3:4]
    out_a = ta + ba * (1 - ta)
    rgb = (top[..., :3] * ta + bottom[..., :3] * ba * (1 - ta)) / np.maximum(out_a, 1e-6)
    return np.concatenate([rgb, out_a], axis=-1)


def _upscale(grid: np.ndarray, size: Tuple[int, int]) -> np.ndarray:
    """A 2D float array (0..1) smoothly scaled to ``size`` (w, h)."""
    grey = (np.clip(grid, 0, 1) * 255).astype(np.uint8)
    surf = pygame.surfarray.make_surface(np.stack([grey.T] * 3, axis=-1))
    big = pygame.transform.smoothscale(surf, size)
    return pygame.surfarray.array3d(big)[..., 0].T.astype(np.float32) / 255


def _noise(rng: np.random.Generator, size: Tuple[int, int], cells: List[float]) -> np.ndarray:
    """Smooth value noise in 0..1: one octave per cell size in pixels."""
    w, h = size
    out = np.zeros((h, w), np.float32)
    total = 0.0
    for i, cell in enumerate(cells):
        weight = 0.55 ** i
        grid = rng.random((int(h / cell) + 2, int(w / cell) + 2)).astype(np.float32)
        out += weight * _upscale(grid, (w + int(2 * cell), h + int(2 * cell)))[:h, :w]
        total += weight
    out /= total
    # Spread it out again: averaging octaves pulls everything to the middle
    return np.clip((out - out.mean()) / (out.std() * 3.2) + 0.5, 0, 1)


def _smoothstep(lo: float, hi: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - lo) / (hi - lo), 0, 1)
    return t * t * (3 - 2 * t)


class FloorPainter:
    """Paints patches' floors and cuts them into tiles of one tileset."""

    def __init__(self, tmx, layer: str, deco_layer: str, tileset: str, baker: FloorBaker) -> None:
        """
        Args:
            tmx: The grow_forest ``Map``.
            layer: Name of the tile layer the floor goes on.
            deco_layer: The layer the grass and flowers go on, apart from
                the floor, since the Town Plan reads the floor as ground.
            tileset: Name of the tileset the painted tiles go into.
            baker: The run's baker of the pinewood floor, whose blended
                tileset must keep room to grow below this one.
        """
        self.tmx = tmx
        self.layer = layer
        self.deco_layer = deco_layer
        self.name = tileset
        self.ts = tmx.tile
        base_dir = os.path.dirname(tmx.path)
        self.path = os.path.join(base_dir, f"{tileset}.png")
        # The tiles already under the floor are read through a baker
        self.reader = FloorBaker(tmx, layer)
        own = next((t for t in self.reader.tilesets if t.name == tileset), None)
        self.tiles: List[pygame.Surface] = [own.tile_image(i) for i in range(own.count)] if own else []
        self.existing = own is not None
        if own:
            self.first_gid = own.first_gid
        else:
            self.first_gid = max([t.first_gid + t.count for t in self.reader.tilesets]
                                 + [baker.mix_first_gid + len(baker.mix_tiles)]) + MIX_HEADROOM
        self.known: Dict[bytes, int] = {pygame.image.tobytes(t, "RGBA"): i for i, t in enumerate(self.tiles)}
        self.added = 0
        self._motifs: Optional[List[dict]] = None

    # --- motifs -------------------------------------------------------------
    def motifs(self, kind: str, subcategories) -> List[pygame.Surface]:
        if self._motifs is None:
            with open(DECO_CATALOG, encoding="utf-8") as f:
                entries = json.load(f)["motifs"]["deco"]
            atlas = pygame.image.load(DECO_ATLAS).convert_alpha()
            self._motifs = [dict(e, image=atlas.subsurface(pygame.Rect(e["rect"])).copy()) for e in entries]
        return [m["image"] for m in self._motifs
                if m["kind"] == kind and (not subcategories or m["subcategory"] in subcategories)]

    # --- painting -----------------------------------------------------------
    def paint(self, forest, patch: dict, seed: int) -> int:
        """Paint one patch's floor into the layer; returns the tiles it covers."""
        style = {**STYLE, **(patch["painted_floor"] or {})}
        tmx, ts = self.tmx, self.ts
        rng = np.random.default_rng(seed)
        prng = forest.rng
        ax0, ay0, ax1, ay1 = patch["area"]
        x0, y0 = max(0, ax0 - 4), max(0, ay0 - 4)
        x1, y1 = min(tmx.width, ax1 + 4), min(tmx.height, ay1 + 4)
        tw, th = x1 - x0, y1 - y0
        size = (tw * ts, th * ts)

        # How far in each spot is, four samples a tile, and where it is dry
        sub = 4
        depth = np.array([[forest.depth(patch, x0 + (i + 0.5) / sub, y0 + (j + 0.5) / sub)
                           for i in range(tw * sub)] for j in range(th * sub)], np.float32)
        lo, hi = style["edge"]
        cover_grid = _smoothstep(lo, hi, depth)
        # Off the water itself, hard, as its tiles are drawn; faded towards it
        dry_tiles = np.array([[0.0 if forest.near_water(x, y, 0) or forest.kept_out(x, y) else 1.0
                               for x in range(x0, x1)] for y in range(y0, y1)], np.float32)
        wet = np.kron(dry_tiles, np.ones((ts, ts), np.float32)) < 0.5
        dry = _smoothstep(0.45, 1.0, _upscale(dry_tiles, size))
        dry[wet] = 0
        cover = _upscale(cover_grid, size) * dry
        deep = _upscale(np.clip(depth, 0, 1), size) * dry

        # The washes
        litter_n = _noise(rng, size, [ts * 5, ts * 2, ts * 0.7])
        moss_n = _noise(rng, size, [ts * 4, ts * 1.5, ts * 0.5])
        canvas = np.zeros((size[1], size[0], 4), np.float32)
        for colour, alpha in ((style["litter"], cover * style["litter_alpha"] / 255 * (0.45 + 0.75 * litter_n)),
                              (style["humus"], deep * style["humus_alpha"] / 255 * litter_n),
                              (style["moss"], cover * style["moss_alpha"] / 255 * _smoothstep(0.5, 0.8, moss_n))):
            layer = np.empty_like(canvas)
            layer[..., :3] = np.array(colour, np.float32) / 255
            layer[..., 3] = np.clip(alpha, 0, 1)
            canvas = _over(canvas, layer)

        # Fallen leaves, in drifts where the litter is thick
        leaves = pygame.Surface(size, pygame.SRCALPHA)
        count = int(style["leaves"] * float(cover.sum()) / (ts * ts))
        tried = 0
        while count > 0 and tried < count * 6:
            tried += 1
            px, py = prng.randrange(size[0]), prng.randrange(size[1])
            if prng.random() > cover[py, px] * (0.25 + 0.95 * litter_n[py, px]):
                continue
            count -= 1
            leaf = pygame.Surface((7, 7), pygame.SRCALPHA)
            r, g, b = prng.choice(style["leaf_colours"])
            j = prng.randint(-14, 14)
            colour = (max(0, min(255, r + j)), max(0, min(255, g + j)), max(0, min(255, b + j)),
                      prng.randint(150, 215))
            length, width = prng.choice((3, 4, 4, 5, 6)), prng.choice((2, 2, 3))
            pygame.draw.ellipse(leaf, colour, ((7 - length) // 2, (7 - width) // 2, length, width))
            leaf = pygame.transform.rotate(leaf, prng.choice((0, 30, 45, 60, 90, 120, 135, 150)))
            leaves.blit(leaf, (px - leaf.get_width() // 2, py - leaf.get_height() // 2))
        leaf_px = pygame.surfarray.pixels_alpha(leaves).T.astype(np.float32) / 255
        layer = np.dstack([pygame.surfarray.array3d(leaves).transpose(1, 0, 2).astype(np.float32) / 255,
                           leaf_px * np.clip(cover * 1.4, 0, 1)])
        canvas = _over(canvas, layer)

        # Grass and flowers, whole motifs
        deco = pygame.Surface(size, pygame.SRCALPHA)
        stems = [((forest.stem(t)[0] - x0) * ts, (t["y"] - y0) * ts) for t in forest.placed + forest.new]
        for kind, subcategories, number, where in patch["deco"]:
            images = self.motifs(kind, subcategories)
            if not images:
                print(f"No {kind} motifs {subcategories or ''} in {DECO_CATALOG}")
                continue
            placed = 0
            for _ in range(number * 40):
                if placed >= number:
                    break
                image = prng.choice(images)
                if prng.random() < 0.5:
                    image = pygame.transform.flip(image, True, False)
                w, h = image.get_size()
                px, py = prng.randrange(size[0] - w), prng.randrange(size[1] - h)
                foot = (px + w // 2, py + h - 2)
                f = forest.depth(patch, x0 + foot[0] / ts, y0 + foot[1] / ts)
                # Flowers want the light at the edge and in the gaps; grass grows anywhere
                if where == "light" and not 0.02 < f < 0.5:
                    continue
                if where != "light" and f < 0.05:
                    continue
                if (dry[py:py + h, px:px + w].min() < 0.99
                        or any(math.dist(foot, s) < ts * 1.2 for s in stems)):
                    continue
                # Tufts come in clumps of a few
                clump = prng.randint(1, 3) if kind != "flowers" else 1
                for k in range(clump):
                    ox, oy = (0, 0) if k == 0 else (prng.randint(-w, w), prng.randint(-h // 2, h // 2))
                    qx, qy = px + ox, py + oy
                    if 0 <= qx < size[0] - w and 0 <= qy < size[1] - h and dry[qy:qy + h, qx:qx + w].min() >= 0.99:
                        deco.blit(prng.choice(images) if k else image, (qx, qy))
                placed += 1
        flowers = np.dstack([pygame.surfarray.array3d(deco).transpose(1, 0, 2).astype(np.float32) / 255,
                             pygame.surfarray.pixels_alpha(deco).T.astype(np.float32) / 255])
        covered = self._cut(canvas, self.layer, x0, y0)
        self._cut(flowers, self.deco_layer, x0, y0)
        return covered

    def _cut(self, canvas: np.ndarray, layer: str, x0: int, y0: int) -> int:
        """Cut a canvas into tiles of a layer, over whatever it already has."""
        tmx, ts = self.tmx, self.ts
        pixels = np.clip(np.rint(canvas * 255), 0, 255).astype(np.uint8)
        data = tmx.layers[layer]
        covered = 0
        for ty in range(pixels.shape[0] // ts):
            for tx in range(pixels.shape[1] // ts):
                block = pixels[ty * ts:(ty + 1) * ts, tx * ts:(tx + 1) * ts]
                if block[..., 3].max() < 6:
                    continue
                spot = (y0 + ty) * tmx.width + x0 + tx
                if data[spot]:
                    below = np.frombuffer(pygame.image.tobytes(self._image(data[spot]), "RGBA"),
                                          np.uint8).reshape(ts, ts, 4).astype(np.float32) / 255
                    block = np.clip(np.rint(_over(below, block.astype(np.float32) / 255) * 255),
                                    0, 255).astype(np.uint8)
                data[spot] = self._gid(np.ascontiguousarray(block))
                covered += 1
        return covered

    def _image(self, gid: int) -> pygame.Surface:
        local = gid & 0x1FFFFFFF
        if self.first_gid <= local < self.first_gid + len(self.tiles):
            return self.tiles[local - self.first_gid]
        return self.reader._image(gid)

    def _gid(self, block: np.ndarray) -> int:
        key = block.tobytes()
        if key not in self.known:
            self.tiles.append(pygame.image.frombytes(key, (self.ts, self.ts), "RGBA"))
            self.known[key] = len(self.tiles) - 1
            self.added += 1
        return self.first_gid + self.known[key]

    # --- saving -------------------------------------------------------------
    def files(self) -> List[str]:
        return [self.path, self.path[:-4] + ".tsx"]

    def save(self) -> None:
        if not self.added:
            return
        ts = self.ts
        rows = -(-len(self.tiles) // COLUMNS)
        sheet = pygame.Surface((COLUMNS * ts, rows * ts), pygame.SRCALPHA)
        for i, image in enumerate(self.tiles):
            sheet.blit(image, ((i % COLUMNS) * ts, (i // COLUMNS) * ts))
        pygame.image.save(sheet, self.path)
        with open(self.path[:-4] + ".tsx", "w", encoding="utf-8", newline="\n") as f:
            f.write(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<tileset version="1.10" tiledversion="1.11.2" name="{self.name}" tilewidth="{ts}" '
                f'tileheight="{ts}" tilecount="{len(self.tiles)}" columns="{COLUMNS}">\n'
                f' <image source="{self.name}.png" width="{COLUMNS * ts}" height="{rows * ts}"/>\n'
                '</tileset>\n')
        if not self.existing:
            entry = f' <tileset firstgid="{self.first_gid}" source="{self.name}.tsx"/>\n'
            first_layer = re.search(r' <layer ', self.tmx.text).start()
            self.tmx.text = self.tmx.text[:first_layer] + entry + self.tmx.text[first_layer:]
            self.existing = True
