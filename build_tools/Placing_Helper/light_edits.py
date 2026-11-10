"""Changes to the map's window lights, kept until they are written into Map1.tmx.

The scene's lights are the game's own objects (map_scene.Scene.lights, and
the shaped windows of Scene.light_groups), so a light moved or resized here
is drawn at once as the game would draw it. LightEdits remembers each
light's place before its first change, so one can be put back, and writes
only what changed into the TMX by the light's object id, as text, touching
nothing else (Map1.tmx is LF; its line endings are kept): a rectangle gets
its x, y, width and height, a shaped window (a polygon) only its x and y,
and a removed light's object is taken out.
"""

import re

from map_scene import TMX, BuildingLight

MIN_SIZE_PX = 2      # a window light keeps at least this width and height


def geometry(light):
    """(x, y, width, height) of a light: its rectangle, or a shaped window's bounding box."""
    if isinstance(light, BuildingLight):
        return light.bbox_x, light.bbox_y, light.width, light.height
    return light.x, light.y, light.width, light.height


def _fmt(value):
    return f'{round(value, 2):g}'


class LightEdits:
    def __init__(self, scene, tmx_path=TMX):
        self.scene = scene
        self.tmx_path = tmx_path
        self.original = {}       # {obj_id: (x, y, width, height)} before the first change
        self.removed = {}        # {obj_id: light} taken out of the scene

    # ----- changing

    def set_geometry(self, light, x, y, width, height):
        """Move a light, and resize it if it is a rectangle (a shaped window only moves)."""
        self.original.setdefault(light.obj_id, geometry(light))
        if isinstance(light, BuildingLight):
            dx, dy = x - light.bbox_x, y - light.bbox_y
            light.x += dx
            light.y += dy
            light.bbox_x += dx
            light.bbox_y += dy
            light.y_sort += dy
        else:
            light.x, light.y = x, y
            light.width, light.height = max(MIN_SIZE_PX, width), max(MIN_SIZE_PX, height)
            light.y_sort = light.y + light.height
        light._surface_cache.clear()

    def remove(self, light):
        self.original.setdefault(light.obj_id, geometry(light))
        if isinstance(light, BuildingLight):
            light.group.lights.remove(light)
        else:
            self.scene.lights.remove(light)
        self.removed[light.obj_id] = light

    def reset(self, light):
        """Put a light back where it was when the helper started."""
        if light.obj_id in self.original:
            self.set_geometry(light, *self.original.pop(light.obj_id))

    # ----- what changed

    def changed_ids(self):
        moved = {i for i, g in self.original.items()
                 if i not in self.removed and g != geometry(self._light(i))}
        return moved | set(self.removed)

    @property
    def count(self):
        return len(self.changed_ids())

    def is_changed(self, light):
        return light.obj_id in self.original and self.original[light.obj_id] != geometry(light)

    def _light(self, obj_id):
        for light in self.scene.lights:
            if light.obj_id == obj_id:
                return light
        for group in self.scene.light_groups.values():
            for light in group.lights:
                if light.obj_id == obj_id:
                    return light
        return self.removed.get(obj_id)

    # ----- writing

    def save(self, path=None):
        """Write the changes into the TMX (Map1.tmx unless told); returns (lights written, ids no longer in the file)."""
        path = path or self.tmx_path
        text = open(path, encoding='utf-8', newline='').read()
        written, missing = 0, []
        for obj_id in sorted(self.changed_ids()):
            element = re.search(rf'[ \t]*<object id="{obj_id}" [^>]*?(?:/>|>.*?</object>)', text, re.S)
            if not element:
                missing.append(obj_id)
                continue
            if obj_id in self.removed:
                # The element with its indent and the line break before it
                start = element.start()
                if text[start - 2:start] == '\r\n':
                    start -= 2
                elif text[start - 1:start] == '\n':
                    start -= 1
                text = text[:start] + text[element.end():]
            else:
                light = self._light(obj_id)
                xml = element.group(0)
                if isinstance(light, BuildingLight):
                    values = {'x': light.x, 'y': light.y}
                else:
                    values = {'x': light.x, 'y': light.y, 'width': light.width, 'height': light.height}
                for key, value in values.items():
                    xml = re.sub(rf' {key}="[^"]*"', f' {key}="{_fmt(value)}"', xml, count=1)
                text = text[:element.start()] + xml + text[element.end():]
            written += 1
        open(path, 'w', encoding='utf-8', newline='').write(text)
        self.original.clear()
        self.removed.clear()
        return written, missing
