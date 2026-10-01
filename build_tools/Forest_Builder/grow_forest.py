"""Grow a forest on the map: tree objects, Tiled preview tiles, forest floor.

Trees in this game live in two places at once, and this script writes both:

* the "Trees" *object* layer, which is what the game loads (one point per
  tree, at the bottom-left corner of its sprite, with ``File_name``,
  ``Stem_Position``, ``Stem_Thick`` and an optional ``Scale``), and
* the "Trees 2" ... "Trees N" *tile* layers, which the game never draws but
  Tiled does, so a tree can be seen while planning the map. Each tree gets the
  tiles of its sprite from the Trees.png tileset, stamped with the bottom-left
  tile just above its object point.

It also spreads forest floor (``Ground_High_Plus``) and flowers
(``Ground_Flowers_Mushrooms``) under the new trees; those *are* drawn in game.

Everything about where the forest goes is in the ``FOREST`` block below; see
README.md next to this file for the steps. Run from the project root, with
Tiled closed::

    python build_tools/Forest_Builder/grow_forest.py --preview   # look first
    python build_tools/Forest_Builder/grow_forest.py             # then write

Existing trees are respected: new ones keep their distance from them, and
their preview tiles are fitted around theirs. Running twice over the same area
fills the gaps that are left rather than planting on top.
"""

import argparse
import math
import os
import random
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Dict, List, Tuple

os.environ["SDL_VIDEODRIVER"] = "dummy"
import pygame  # noqa: E402

pygame.init()
pygame.display.set_mode((1, 1))
sys.path.insert(0, ".")
from src.models.map import TMXMap  # noqa: E402

TMX = "assets/tiles/Map1.tmx"
PREVIEW_TMX = "assets/tiles/_forest_preview.tmx"
OUTPUT_DIR = "build_tools/output/forest"
TREE_SPRITES = "assets/map_sprites/trees"

# ---------------------------------------------------------------------------
# The forest. All positions are in tiles (32 px). Ellipses are
# (centre x, centre y, radius x, radius y).
# ---------------------------------------------------------------------------
FOREST = {
    # Tiles a tree's object point may land on: x0, y0, x1, y1 (exclusive)
    "area": (18, 145, 95, 187),
    # The forest is the union of these, with a wavy edge added
    "shapes": [(51, 168, 25, 16.5), (79, 161, 9.5, 6)],
    # Kept free of trees: yards, the way out of doors, glades
    "clearings": [(82, 174.5, 8.5, 6.5), (44, 171, 4.2, 3.2)],
    # Rectangles x0, y0, x1, y1 nothing may go into: roads, paths
    "keep_out": [(70, 185, 300, 300)],
    # How many broadleaves (Tree_23) to plant before the pines
    "oaks": 2,
    # A region of Ground_High_Plus holding one forest floor blob to copy...
    "floor_source": (70, 155, 112, 190),
    # ...and where to centre each copy (alternate copies are mirrored)
    "floor_spots": [(38, 168), (55, 162), (57, 177), (70, 166)],
    # A region of Ground_Flowers_Mushrooms whose patches get scattered
    "flowers_source": (60, 140, 120, 195),
    "flower_patches": 14,
}

#: Size range a tree is drawn at, around its sprite's own size
SCALE_RANGE = (0.82, 1.18)
SCALE_SPREAD = 0.08

#: Stems stand at least this far apart, in tiles, or this share of the two
#: sprites' widths, whichever is more
MIN_STEM_GAP = 1.7
GAP_SHARE = 0.43

#: Tile layers the preview tiles go on, bottom to top. When every one of them
#: is taken under a tree, up to MAX_EXTRA_LAYERS more are added above.
TREE_LAYERS = ["Trees 2", "Trees 3", "Trees 4", "Trees 5", "Trees 6", "Trees 7"]
MAX_EXTRA_LAYERS = 2

# ---------------------------------------------------------------------------
# The sprites. Tree_<n>.png -> (left, top of the sprite in Trees.png in
# pixels, stem centre from the left in tiles, stem width in tiles).
# 12-22 are 1-11 mirrored; 23 is the broadleaf.
# ---------------------------------------------------------------------------
SPRITES: Dict[int, Tuple[int, int, float, float]] = {
    1: (0, 16, 3.0, 1.2), 2: (480, 127, 2.0, 1.0), 3: (608, 211, 1.0, 0.3),
    4: (672, 72, 1.55, 0.6), 5: (768, 129, 2.0, 0.6), 6: (896, 95, 1.5, 0.6),
    7: (992, 128, 2.0, 0.8), 8: (1120, 60, 1.6, 0.4), 9: (1216, 150, 2.0, 0.4),
    10: (1344, 203, 1.5, 0.6), 11: (1440, 100, 2.0, 0.7),
    12: (32, 475, 2.0, 0.7), 13: (160, 578, 1.4, 0.6), 14: (256, 525, 2.0, 0.4),
    15: (384, 435, 1.5, 0.4), 16: (480, 503, 2.0, 0.6), 17: (608, 470, 1.5, 0.6),
    18: (704, 504, 2.0, 0.7), 19: (832, 447, 1.5, 0.8), 20: (928, 586, 1.0, 0.3),
    21: (992, 502, 2.0, 1.0), 22: (1408, 391, 3.0, 1.2),
    23: (32, 786, 3.7, 2.2),
}
BROADLEAF = 23
#: Small and young trees, favoured at the forest's edge
YOUNG = [3, 20, 10, 13, 9, 14]

FLIP_H = 0x80000000
GID_MASK = 0x1FFFFFFF


class Map:
    """The TMX file as text plus its tile layers as flat gid lists."""

    def __init__(self, path: str) -> None:
        self.text = open(path, encoding="utf-8").read()
        self.root = ET.fromstring(self.text)
        self.width = int(self.root.get("width"))
        self.height = int(self.root.get("height"))
        self.tile = int(self.root.get("tilewidth"))
        self.layer_names = [L.get("name") for L in self.root.findall("layer")]
        self.layers: Dict[str, List[int]] = {
            L.get("name"): [int(v) for v in L.find("data").text.replace("\n", "").split(",") if v.strip()]
            for L in self.root.findall("layer")
        }
        self.new_layers: List[str] = []
        tileset = next(t for t in self.root.findall("tileset") if t.get("name") == "Trees")
        self.trees_first_gid = int(tileset.get("firstgid"))
        self.trees_columns = int(tileset.get("columns"))

    def order(self, name: str) -> int:
        """Drawing order of a tile layer; later is drawn on top."""
        if name in self.new_layers:
            return len(self.layer_names) + self.new_layers.index(name)
        return self.layer_names.index(name)

    def add_layer(self, name: str) -> None:
        self.new_layers.append(name)
        self.layers[name] = [0] * (self.width * self.height)

    def csv(self, data: List[int]) -> str:
        w = self.width
        return ",\n".join(",".join(map(str, data[r * w:(r + 1) * w])) for r in range(self.height)) + "\n"

    def save(self, path: str, tree_objects: List[str]) -> None:
        text = self.text
        for name in self.layer_names:
            pattern = re.compile(r'(<layer id="\d+" name="' + re.escape(name)
                                 + r'"[^>]*>\s*<data encoding="csv">\n)(.*?)(</data>)', re.S)
            text, found = pattern.subn(lambda mo: mo.group(1) + self.csv(self.layers[name]) + mo.group(3),
                                       text, count=1)
            assert found == 1, name
        next_layer = int(re.search(r'nextlayerid="(\d+)"', text).group(1))
        trees_group = re.search(r' <objectgroup id="\d+" name="Trees">', text).group(0)
        for name in self.new_layers:
            xml = (f' <layer id="{next_layer}" name="{name}" width="{self.width}" height="{self.height}">\n'
                   f'  <data encoding="csv">\n{self.csv(self.layers[name])}</data>\n </layer>\n')
            text = text.replace(trees_group, xml + trees_group, 1)
            next_layer += 1
        text = re.sub(r'nextlayerid="\d+"', f'nextlayerid="{next_layer}"', text, count=1)

        next_obj = int(re.search(r'nextobjectid="(\d+)"', text).group(1))
        objects = [obj.replace("{ID}", str(next_obj + i)) for i, obj in enumerate(tree_objects)]
        start = text.index(trees_group)
        end = text.index(" </objectgroup>", start)
        text = text[:end] + "".join(objects) + text[end:]
        text = re.sub(r'nextobjectid="\d+"', f'nextobjectid="{next_obj + len(objects)}"', text, count=1)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


def load_sprites(tmx: Map) -> Tuple[Dict[int, Tuple[int, int]], Dict[int, list]]:
    """Each sprite's size, and the preview tiles it is stamped with.

    Also checks every entry of SPRITES against its PNG, since a wrong position
    there would put the wrong picture in Tiled.

    Returns:
        Tuple: {sprite: (w, h)} and {sprite: [(dx, dy, gid), ...]} with dy
        counted up from the bottom tile row (0, -1, ...).
    """
    ts = tmx.tile
    sheet = pygame.image.load(os.path.join(TREE_SPRITES, "Trees.png")).convert_alpha()
    sizes, blocks, wrong = {}, {}, []
    for n, (px, py, _, _) in SPRITES.items():
        image = pygame.image.load(os.path.join(TREE_SPRITES, f"Tree_{n:02d}.png")).convert_alpha()
        w, h = image.get_size()
        sizes[n] = (w, h)
        samples = [(x, y) for x in range(0, w, 7) for y in range(0, h, 7) if image.get_at((x, y)).a > 220]
        off = sum(1 for x, y in samples
                  if sum(abs(a - b) for a, b in zip(image.get_at((x, y))[:3], sheet.get_at((px + x, py + y))[:3])) > 30)
        if not samples or off > len(samples) * 0.05:
            wrong.append(n)
        col, bottom = px // ts, round((py + h) / ts) - 1
        blocks[n] = [
            (c - col, r - bottom, tmx.trees_first_gid + r * tmx.trees_columns + c)
            for r in range(max(0, py // ts), bottom + 1)
            for c in range(col, col + math.ceil(w / ts))
            if pygame.mask.from_surface(sheet.subsurface(pygame.Rect(c * ts, r * ts, ts, ts)), 8).count()
        ]
    if wrong:
        sys.exit(f"SPRITES does not match Trees.png for Tree_{wrong}: fix their positions first.")
    return sizes, blocks


class Forest:
    """Places the trees and everything under them."""

    def __init__(self, tmx: Map, game_map: TMXMap, seed: int) -> None:
        self.tmx = tmx
        self.game_map = game_map
        self.ts = tmx.tile
        self.rng = random.Random(seed)
        self.sizes, self.blocks = load_sprites(tmx)
        self.phases = [self.rng.uniform(0, 2 * math.pi) for _ in range(5)]
        self.houses = [h for h in game_map.houses if h.image is not None]
        self.placed = self._existing_trees()
        self.new: List[dict] = []

    # --- shape --------------------------------------------------------------
    @staticmethod
    def _ellipse(x, y, cx, cy, rx, ry) -> float:
        return 1 - ((x - cx) / rx) ** 2 - ((y - cy) / ry) ** 2

    def depth(self, x: float, y: float) -> float:
        """Above 0 inside the forest, and the larger the deeper in."""
        p = self.phases
        f = max(self._ellipse(x, y, *e) for e in FOREST["shapes"])
        f += (0.13 * math.sin(x * 0.31 + p[0]) + 0.11 * math.sin(y * 0.37 + p[1])
              + 0.09 * math.sin((x + y) * 0.23 + p[2]) + 0.07 * math.sin((x - y) * 0.53 + p[3])
              + 0.06 * math.sin(x * 0.71 + y * 0.19 + p[4]))
        for clearing in FOREST["clearings"]:
            if self._ellipse(x, y, *clearing) > -0.05:
                return min(f, -0.2)
        return f

    @staticmethod
    def kept_out(x: float, y: float) -> bool:
        return any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in FOREST["keep_out"])

    # --- trees --------------------------------------------------------------
    def _existing_trees(self) -> List[dict]:
        tmx, ts = self.tmx, self.ts
        group = next(g for g in tmx.root.findall("objectgroup") if g.get("name") == "Trees")
        trees = []
        for obj in group.findall("object"):
            props = {p.get("name"): p.get("value") for p in obj.iter("property")}
            number = int(re.findall(r"\d+", props.get("File_name", "0"))[0] or 0)
            if number not in SPRITES:
                continue
            tree = dict(x=int(float(obj.get("x")) // ts), y=int(float(obj.get("y")) // ts),
                        sprite=number, scale=float(props.get("Scale", 1.0)))
            tree["cells"] = self.cells(tree)
            # Whichever layer holds its bottom-left preview tile
            dx, dy, gid = self.blocks[number][-1]
            spot = (tree["y"] - 1) * tmx.width + tree["x"] + dx
            tree["layer"] = next((n for n in tmx.layer_names if tmx.layers[n][spot] & GID_MASK == gid), None)
            trees.append(tree)
        return trees

    def cells(self, tree: dict) -> set:
        return {(tree["x"] + dx, tree["y"] - 1 + dy) for dx, dy, _ in self.blocks[tree["sprite"]]}

    def stem(self, tree: dict) -> Tuple[float, float]:
        return tree["x"] + SPRITES[tree["sprite"]][2] * tree["scale"], tree["y"]

    def house_box(self, house) -> Tuple[int, int, int, int]:
        ts = self.ts
        return (int(house.x // ts), int((house.y - house.image.get_height()) // ts),
                int((house.x + house.image.get_width() - 1) // ts), int((house.y - 1) // ts))

    def ground_ok(self, x: int, y: int, sprite: int, scale: float) -> bool:
        """Whether a tree's stem can stand here without getting in anyone's way."""
        ts = self.ts
        _, _, stem_pos, stem_thick = SPRITES[sprite]
        stem_x = x + stem_pos * scale
        if self.kept_out(stem_x, y):
            return False
        width = max(stem_thick * scale * ts, 8)
        # The stem, with a tile to spare all round
        box = pygame.Rect(int(stem_x * ts - width / 2) - ts, int(y * ts - ts / 2) - ts, int(width) + 2 * ts, 2 * ts)
        if self.game_map.check_scenery_collision(box):
            return False
        water = self.game_map.water_tiles
        if any((tx, ty) in water for tx in range(x - 2, x + 8) for ty in range(y - 3, y + 3)):
            return False
        for house in self.houses:
            x0, y0, x1, y1 = self.house_box(house)
            if x0 - 1 <= stem_x <= x1 + 1 and y0 <= y <= y1 + 3:
                return False
        return all(math.dist((stem_x * ts, y * ts), door.step) >= 4 * ts for door in self.game_map.doors)

    def room_for(self, tree: dict, gap=None) -> bool:
        stem = self.stem(tree)
        width = self.sizes[tree["sprite"]][0] / self.ts * tree["scale"]
        for other in self.placed + self.new:
            other_width = self.sizes[other["sprite"]][0] / self.ts * other["scale"]
            needed = gap or max(MIN_STEM_GAP, GAP_SHARE * (width + other_width))
            if math.dist(stem, self.stem(other)) < needed:
                return False
        return True

    def plant(self) -> None:
        x0, y0, x1, y1 = FOREST["area"]
        spots = [(x, y) for x in range(x0, x1) for y in range(y0, y1)]
        self.rng.shuffle(spots)
        rng = self.rng

        # A few broadleaves first, well apart, so the pines grow around them
        oaks = 0
        for x, y in spots:
            if oaks >= FOREST["oaks"]:
                break
            tree = dict(x=x, y=y, sprite=BROADLEAF, scale=round(rng.uniform(0.85, 1.0), 2))
            if self.depth(x, y) >= 0.3 and self.ground_ok(x, y, BROADLEAF, tree["scale"]) and self.room_for(tree, 12):
                self.new.append(tree)
                oaks += 1

        pines = [n for n in SPRITES if n != BROADLEAF]
        weights = [0.8 if n in YOUNG[:4] else 1.0 for n in pines]
        for x, y in spots:
            f = self.depth(x, y)
            if f <= 0:
                if not (f > -0.25 and rng.random() < 0.05):  # a few strays outside
                    continue
            elif f < 0.25 and rng.random() > 0.35 + 2.6 * f:  # thinner at the edge
                continue
            sprite = rng.choices(pines, weights)[0]
            if f < 0.15 and rng.random() < 0.5:
                sprite = rng.choice(YOUNG)
            scale = round(min(SCALE_RANGE[1], max(SCALE_RANGE[0], rng.gauss(1.0, SCALE_SPREAD))), 2)
            tree = dict(x=x, y=y, sprite=sprite, scale=scale)
            if self.ground_ok(x, y, sprite, scale) and self.room_for(tree):
                self.new.append(tree)
        for tree in self.new:
            tree["cells"] = self.cells(tree)

    # --- Tiled preview ------------------------------------------------------
    def stamp_previews(self) -> Tuple[int, int]:
        """Put every new tree's tiles on a tree layer.

        A tile layer holds one tile per cell, so trees that overlap need
        different layers, and the one in front a later layer. A dense forest
        overlaps too deeply to always manage that, so each tree takes the free
        layer that draws the fewest of its cells in the wrong order -- which
        only shows in Tiled; the game sorts trees itself.

        Returns:
            Tuple: Trees dropped for want of any free layer, and cells drawn in
            the wrong order.
        """
        tmx = self.tmx
        house_layers = [tmx.order(n) for n in tmx.layer_names if n.startswith("Houses")]
        last_house = max(house_layers) if house_layers else -1
        layers = [n for n in TREE_LAYERS if n in tmx.layers]
        occupied = {n: {(i % tmx.width, i // tmx.width) for i, g in enumerate(tmx.layers[n]) if g} for n in layers}

        def misordered(tree, layer):
            bad = 0
            for other in self.placed:
                shared = len(tree["cells"] & other["cells"]) if other.get("layer") else 0
                if shared:
                    behind = other["y"] <= tree["y"]
                    if behind != (tmx.order(other["layer"]) <= tmx.order(layer)):
                        bad += shared
            for house in self.houses:
                x0, y0, x1, y1 = self.house_box(house)
                if any(x0 <= cx <= x1 and y0 <= cy <= y1 for cx, cy in tree["cells"]):
                    if (house.y <= tree["y"] * self.ts) != (tmx.order(layer) > last_house):
                        bad += 1000
            return bad

        dropped, wrong = [], 0
        for tree in sorted(self.new, key=lambda t: (t["y"], t["x"])):
            free = [n for n in layers if not tree["cells"] & occupied[n]]
            if not free and len(tmx.new_layers) < MAX_EXTRA_LAYERS:
                name = f"Trees {max(int(re.findall(r'\d+', n)[0]) for n in layers) + 1}"
                tmx.add_layer(name)
                layers.append(name)
                occupied[name] = set()
                free = [name]
            if not free:
                dropped.append(tree)
                continue
            layer = min(free, key=lambda n: (misordered(tree, n), tmx.order(n)))
            wrong += misordered(tree, layer)
            tree["layer"] = layer
            occupied[layer] |= tree["cells"]
            for dx, dy, gid in self.blocks[tree["sprite"]]:
                tmx.layers[layer][(tree["y"] - 1 + dy) * tmx.width + tree["x"] + dx] = gid
            self.placed.append(tree)
        self.new = [t for t in self.new if t not in dropped]
        return len(dropped), wrong

    # --- ground -------------------------------------------------------------
    def _blobs(self, layer: str, region) -> List[list]:
        """Connected patches of painted cells in a region, as stamps."""
        tmx = self.tmx
        x0, y0, x1, y1 = region
        data = tmx.layers[layer]
        src = {(x, y): data[y * tmx.width + x] for y in range(y0, y1) for x in range(x0, x1)
               if data[y * tmx.width + x]}
        blobs, seen = [], set()
        for start in src:
            if start in seen:
                continue
            blob, stack = [], [start]
            seen.add(start)
            while stack:
                cx, cy = stack.pop()
                blob.append((cx, cy))
                for nb in ((cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)):
                    if nb in src and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            bx, by = min(c[0] for c in blob), min(c[1] for c in blob)
            blobs.append([(cx - bx, cy - by, src[(cx, cy)]) for cx, cy in blob])
        return blobs

    def _stamp(self, layer, stamp, ox, oy, flip, whole) -> None:
        """Copy a stamp into the empty cells of a layer.

        Args:
            whole: Only place it if every one of its cells is free, so that
                small patches never get cut in half.
        """
        tmx = self.tmx
        data = tmx.layers[layer]
        width = max(c[0] for c in stamp) + 1
        cells = []
        for dx, dy, gid in stamp:
            if flip:
                dx, gid = width - 1 - dx, gid ^ FLIP_H
            x, y = ox + dx, oy + dy
            free = (0 <= x < tmx.width and 0 <= y < tmx.height and not data[y * tmx.width + x]
                    and not self.kept_out(x, y))
            if not free and whole:
                return
            if free:
                cells.append((x, y, gid))
        for x, y, gid in cells:
            data[y * tmx.width + x] = gid

    def cover_ground(self) -> None:
        blobs = sorted(self._blobs("Ground_High_Plus", FOREST["floor_source"]), key=len)
        if blobs:
            floor = blobs[-1]
            w, h = max(c[0] for c in floor) + 1, max(c[1] for c in floor) + 1
            for i, (cx, cy) in enumerate(FOREST["floor_spots"]):
                self._stamp("Ground_High_Plus", floor, cx - w // 2, cy - h // 2, i % 2 == 0, whole=False)
        patches = self._blobs("Ground_Flowers_Mushrooms", FOREST["flowers_source"])
        x0, y0, x1, y1 = FOREST["area"]
        inside = [(x, y) for x in range(x0, x1) for y in range(y0, y1) if self.depth(x, y) > 0.05]
        for _ in range(FOREST["flower_patches"] if patches and inside else 0):
            x, y = self.rng.choice(inside)
            self._stamp("Ground_Flowers_Mushrooms", self.rng.choice(patches), x, y,
                        self.rng.random() < 0.5, whole=True)

    def objects(self) -> List[str]:
        out = []
        for tree in sorted(self.new, key=lambda t: (t["y"], t["x"])):
            n = tree["sprite"]
            _, _, stem_pos, stem_thick = SPRITES[n]
            scale = (f'    <property name="Scale" type="float" value="{tree["scale"]}"/>\n'
                     if tree["scale"] != 1.0 else "")
            out.append(
                f'  <object id="{{ID}}" name="Tree_{n:02d}" type="Pine_Tree" '
                f'x="{tree["x"] * self.ts}" y="{tree["y"] * self.ts}">\n'
                f'   <properties>\n'
                f'    <property name="File_name" value="Tree_{n:02d}.png"/>\n'
                f'{scale}'
                f'    <property name="Stem_Position" type="float" value="{stem_pos:g}"/>\n'
                f'    <property name="Stem_Thick" type="float" value="{stem_thick:g}"/>\n'
                f'    <property name="Tiles_to_right" type="int" value="{math.ceil(self.sizes[n][0] / self.ts)}"/>\n'
                f'   </properties>\n   <point/>\n  </object>\n')
        return out


def render(path: str, out_dir: str, region, scale: float = 0.3) -> None:
    """Save how a region looks in game and in Tiled, side by side as two PNGs."""
    import pytmx
    game_map = TMXMap(path)
    ts = game_map.tile_size
    x0, y0, x1, y1 = region
    for name, tiled in (("game", False), ("tiled", True)):
        surf = pygame.Surface(((x1 - x0) * ts, (y1 - y0) * ts))
        for layer in game_map.tmx_data.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer) and (tiled or layer.name.startswith("Ground")):
                for x, y, img in layer.tiles():
                    if x0 <= x < x1 and y0 <= y < y1:
                        surf.blit(img, ((x - x0) * ts, (y - y0) * ts))
        if not tiled:
            things = [t for t in game_map.trees + game_map.houses if t.image is not None]
            for t in sorted(things, key=lambda t: t.y_sort):
                surf.blit(t.image, (t.x - x0 * ts, t.y - y0 * ts - t.image.get_height()))
        size = (int(surf.get_width() * scale), int(surf.get_height() * scale))
        pygame.image.save(pygame.transform.smoothscale(surf, size), os.path.join(out_dir, f"forest_{name}.png"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seed", type=int, default=7, help="another seed, another forest")
    parser.add_argument("--preview", action="store_true",
                        help="only render the result to build_tools/output/forest/, leave the map alone")
    args = parser.parse_args()

    tmx = Map(TMX)
    game_map = TMXMap(TMX)
    doors_before = len(game_map.doors)
    forest = Forest(tmx, game_map, args.seed)
    forest.plant()
    dropped, wrong = forest.stamp_previews()
    forest.cover_ground()

    target = PREVIEW_TMX if args.preview else TMX
    tmx.save(target, forest.objects())
    print(f"{len(forest.new)} trees planted (seed {args.seed}), {dropped} dropped for want of a layer, "
          f"{wrong} preview cells in the wrong order")
    if tmx.new_layers:
        print("New tile layers:", ", ".join(tmx.new_layers))
    print("Sprites:", dict(sorted(Counter(t["sprite"] for t in forest.new).items())))

    # Nothing the forest did may cost a door its way out
    after = TMXMap(target)
    if len(after.doors) != doors_before:
        print(f"WARNING: {doors_before - len(after.doors)} door(s) lost their step -- see above")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    x0, y0, x1, y1 = FOREST["area"]
    render(target, OUTPUT_DIR, (max(0, x0 - 6), max(0, y0 - 8), x1 + 12, y1 + 8))
    print(f"Pictures in {OUTPUT_DIR}/ (forest_game.png, forest_tiled.png)")
    if args.preview:
        os.remove(PREVIEW_TMX)


if __name__ == "__main__":
    main()
