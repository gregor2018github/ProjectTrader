"""Lay forest floor copies over each other without seams.

The forest floor is one painting cut into tiles, so a tile only matches the
neighbours it was painted next to. Filling only the empty cells of a layer
with a second copy puts tiles from different spots of the painting side by
side, and each such pair shows as a hard square corner.

Instead every copy is laid down whole, over whatever is there, and each cell
covered more than once gets a new tile: its layers alpha-composited, bottom
first. A copy fades out at its own soft edge, so the overlap fades with it.
The new tiles go into a tileset of their own (``forest_floor_mix``), which the
map gains the first time it is needed and which only ever grows, so tiles
already in use keep their gids. The game still draws a single layer, at no
extra cost.
"""

import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import pygame

MIX_NAME = "forest_floor_mix"
MIX_COLUMNS = 32
FLIP_H, FLIP_V, FLIP_D = 0x80000000, 0x40000000, 0x20000000
GID_MASK = 0x1FFFFFFF


class Tileset:
    """One tileset of the map, enough to cut its tiles out."""

    def __init__(self, first_gid: int, element: ET.Element, base_dir: str) -> None:
        self.first_gid = first_gid
        self.source = element.get("source")
        if self.source:
            path = os.path.join(base_dir, self.source)
            element = ET.parse(path).getroot()
            base_dir = os.path.dirname(path)
        self.name = element.get("name")
        self.tile = int(element.get("tilewidth"))
        self.count = int(element.get("tilecount"))
        self.columns = int(element.get("columns"))
        self.spacing = int(element.get("spacing", 0))
        self.margin = int(element.get("margin", 0))
        self.image_path = os.path.join(base_dir, element.find("image").get("source"))
        self._image: Optional[pygame.Surface] = None

    def tile_image(self, local_id: int) -> pygame.Surface:
        if self._image is None:
            self._image = pygame.image.load(self.image_path).convert_alpha()
        step = self.tile + self.spacing
        x = self.margin + (local_id % self.columns) * step
        y = self.margin + (local_id // self.columns) * step
        return self._image.subsurface(pygame.Rect(x, y, self.tile, self.tile)).copy()


def _over(bottom: bytearray, top: bytes) -> None:
    """Composite one RGBA tile over another, in place, with straight alpha."""
    for i in range(0, len(top), 4):
        ta = top[i + 3]
        if not ta:
            continue
        ba = bottom[i + 3]
        if ta == 255 or not ba:
            bottom[i:i + 4] = top[i:i + 4]
            continue
        # out = top + bottom * (1 - top alpha), colours weighted by alpha
        keep = ba * (255 - ta) / 255
        out = ta + keep
        for c in range(3):
            bottom[i + c] = round((top[i + c] * ta + bottom[i + c] * keep) / out)
        bottom[i + 3] = round(out)


class FloorBaker:
    """Collects floor copies for one layer, then bakes the overlaps."""

    def __init__(self, tmx, layer: str) -> None:
        """
        Args:
            tmx: The grow_forest ``Map``.
            layer: Name of the tile layer the floor lives on.
        """
        self.tmx = tmx
        self.layer = layer
        base_dir = os.path.dirname(tmx.path)
        self.tilesets = [Tileset(int(t.get("firstgid")), t, base_dir) for t in tmx.root.findall("tileset")]
        self.mix = next((t for t in self.tilesets if t.name == MIX_NAME), None)
        self.mix_path = os.path.join(base_dir, f"{MIX_NAME}.png")
        self.mix_first_gid = (self.mix.first_gid if self.mix else
                              max(t.first_gid + t.count for t in self.tilesets))
        self.mix_tiles: List[pygame.Surface] = []
        if self.mix:
            for i in range(self.mix.count):
                self.mix_tiles.append(self.mix.tile_image(i))
        self.stacks: Dict[Tuple[int, int], List[int]] = {}

    def add(self, cells) -> None:
        """Lay a copy down: (x, y, gid) cells, painted over what is there."""
        data = self.tmx.layers[self.layer]
        width = self.tmx.width
        for x, y, gid in cells:
            stack = self.stacks.get((x, y))
            if stack is None:
                below = data[y * width + x]
                stack = self.stacks[(x, y)] = [below] if below else []
            stack.append(gid)

    def _image(self, gid: int) -> pygame.Surface:
        local = gid & GID_MASK
        if self.mix_first_gid <= local < self.mix_first_gid + len(self.mix_tiles):
            image = self.mix_tiles[local - self.mix_first_gid].copy()
        else:
            tileset = max((t for t in self.tilesets if t.first_gid <= local), key=lambda t: t.first_gid)
            image = tileset.tile_image(local - tileset.first_gid)
        if gid & FLIP_D:
            image = pygame.transform.rotate(pygame.transform.flip(image, True, False), 90)
        return pygame.transform.flip(image, bool(gid & FLIP_H), bool(gid & FLIP_V))

    def bake(self) -> int:
        """Write every cell into the layer; returns how many new tiles it took."""
        data = self.tmx.layers[self.layer]
        width = self.tmx.width
        made: Dict[Tuple[int, ...], int] = {}
        before = len(self.mix_tiles)
        for (x, y), stack in self.stacks.items():
            if len(stack) == 1:
                data[y * width + x] = stack[0]
                continue
            key = tuple(stack)
            if key not in made:
                pixels = bytearray(pygame.image.tobytes(self._image(stack[0]), "RGBA"))
                for gid in stack[1:]:
                    _over(pixels, pygame.image.tobytes(self._image(gid), "RGBA"))
                size = self._image(stack[0]).get_size()
                self.mix_tiles.append(pygame.image.frombytes(bytes(pixels), size, "RGBA"))
                made[key] = self.mix_first_gid + len(self.mix_tiles) - 1
            data[y * width + x] = made[key]
        self.stacks.clear()
        # Tilesets after this one (a painted floor's) start a little further on
        ceiling = min((t.first_gid for t in self.tilesets if t.first_gid > self.mix_first_gid), default=None)
        if ceiling is not None and self.mix_first_gid + len(self.mix_tiles) > ceiling:
            raise SystemExit(f"{MIX_NAME} has grown into the gids of the next tileset; give that one a higher firstgid")
        if len(self.mix_tiles) > before:
            self._save_tileset()
        return len(self.mix_tiles) - before

    def _save_tileset(self) -> None:
        tile = self.tilesets[0].tile
        rows = -(-len(self.mix_tiles) // MIX_COLUMNS)
        sheet = pygame.Surface((MIX_COLUMNS * tile, rows * tile), pygame.SRCALPHA)
        for i, image in enumerate(self.mix_tiles):
            sheet.blit(image, ((i % MIX_COLUMNS) * tile, (i // MIX_COLUMNS) * tile))
        pygame.image.save(sheet, self.mix_path)
        base_dir = os.path.dirname(self.tmx.path)
        with open(os.path.join(base_dir, f"{MIX_NAME}.tsx"), "w", encoding="utf-8", newline="\n") as f:
            f.write(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<tileset version="1.10" tiledversion="1.11.2" name="{MIX_NAME}" tilewidth="{tile}" '
                f'tileheight="{tile}" tilecount="{len(self.mix_tiles)}" columns="{MIX_COLUMNS}">\n'
                f' <image source="{MIX_NAME}.png" width="{MIX_COLUMNS * tile}" height="{rows * tile}"/>\n'
                '</tileset>\n')
        if not self.mix:
            entry = f' <tileset firstgid="{self.mix_first_gid}" source="{MIX_NAME}.tsx"/>\n'
            first_layer = re.search(r' <layer ', self.tmx.text).start()
            self.tmx.text = self.tmx.text[:first_layer] + entry + self.tmx.text[first_layer:]
