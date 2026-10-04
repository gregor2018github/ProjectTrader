"""Place a Sprite Manager building into assets/tiles/Map1.tmx.

Run from the repo root. Subcommands:

  near X Y [RADIUS]
      List Houses/Trees/Bridges/Doors objects within RADIUS px (default 600)
      of world point X,Y, and which "Houses N" preview layers have tiles there.

  render X0 Y0 X1 Y1 OUT.png [--figure X,Y ...]
      Draw that world rect the way the game sees it (Ground layers, then
      houses/trees/bridges y-sorted, red collision boxes with margins) with a
      player-sized figure standing on each X,Y for scale. Doors are drawn as
      blue dots, window lights as yellow boxes, smoke outlets as cyan bars.

  place SPRITE X Y [--replace ID | --name NAME] [--layer "Houses 6"]
        [--prop KEY=VALUE ...] [--no-preview] [--dry-run]
        [--door SX,SY,FACING ...] [--light SX,SY,W,H ...] [--smoke SX,SY,W ...]
      SPRITE is the catalog key's file, e.g. House_26.png. X,Y is the
      object's point (bottom-left of the sprite), snapped to the tile grid
      unless --no-snap (then no Tiled preview: it needs whole tiles).
      Object properties come from the catalog's "tiled" block, then --prop
      (ints/floats are typed automatically; an empty VALUE drops the key).
      --replace rewrites an existing Houses object in place and keeps its id
      (saves remember warehouses by id); otherwise a new object is appended
      with the map's nextobjectid. The sprite's atlas cells are stamped into
      the given Houses tile layer so Tiled shows it; that fails if any of
      those cells is already used on that layer.

      --door/--light/--smoke add the building's Doors point (FACING: the way
      one faces walking out: down/up/left/right), Lights "Light_rectangle"s
      and Smoke outlets, in SPRITE PIXELS (x right, y down from the PNG's
      top-left, before Scale); they are moved and scaled with the building.
      Smoke is named Smoke_<NAME>[_<k>], and the game only reads smoke whose
      building is called House_<n>. On --replace, the old door/lights/smoke
      are removed when new ones are given, else left alone; to move a
      building use `move` instead.

  move ID X Y [--dry-run]
      Move a Houses object to a new X,Y (snapped to tiles) with what belongs
      to it: Doors points inside its collision rect, the Light_rectangles the
      game hands to it (nearest base below, as TMXMap._load_lights does),
      Smoke_<name>[_k], and its Tiled preview cells. Check the "moved" list:
      lights it takes at the old spot are the ones the game gave it there.

Map1.tmx is LF (git shows CRLF warnings on Windows; ignore them). This
keeps whatever line ending the file has and touches nothing else.
"""
import argparse
import json
import os
import re
import sys

TMX = 'assets/tiles/Map1.tmx'
CATALOG = 'build_tools/Sprite_Manager/building_catalog.json'
TILE = 32
HOUSES_FIRSTGID = 18837      # <tileset firstgid=... source="Houses.tsx"/>
ATLAS_COLUMNS = 125          # Houses.tsx: 4000 px / 32
LAYER_RE = re.compile(
    r'(<layer id="\d+" name="([^"]+)" width="(\d+)" height="(\d+)">\s*'
    r'<data encoding="csv">\s*)(.*?)(\s*</data>)', re.S)


# --------------------------------------------------------------- TMX text I/O

def load_tmx():
    text = open(TMX, encoding='utf-8', newline='').read()
    layers = {}
    for m in LAYER_RE.finditer(text):
        w = int(m.group(3))
        nums = [int(v) for v in m.group(5).replace('\r', '').replace('\n', '').split(',')]
        layers[m.group(2)] = [nums[i * w:(i + 1) * w] for i in range(len(nums) // w)]
    return text, layers


def save_tmx(text, layers):
    nl = '\r\n' if '\r\n' in text else '\n'

    def rep(m):
        rows = layers[m.group(2)]
        return m.group(1) + (',' + nl).join(','.join(map(str, r)) for r in rows) + m.group(6)
    open(TMX, 'w', encoding='utf-8', newline='').write(LAYER_RE.sub(rep, text))


def _typed(value):
    if isinstance(value, bool):
        return 'bool', 'true' if value else 'false'
    if isinstance(value, int):
        return 'int', str(value)
    if isinstance(value, float):
        return 'float', repr(value)
    s = str(value)
    if re.fullmatch(r'-?\d+', s):
        return 'int', s
    if re.fullmatch(r'-?\d+\.\d*', s):
        return 'float', s
    return None, s


def object_xml(obj_id, name, cls, x, y, props, nl):
    lines = [f' <object id="{obj_id}" name="{name}" type="{cls}" x="{x}" y="{y}">', '   <properties>']
    for key in sorted(props):
        kind, val = _typed(props[key])
        val = val.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')
        lines.append(f'    <property name="{key}"' + (f' type="{kind}"' if kind else '') + f' value="{val}"/>')
    lines += ['   </properties>', '   <point/>', '  </object>']
    return nl.join(lines)


def _atlas_gids(rect, cols, rows_up):
    """Houses-tileset gids of a sprite's atlas cells, row by row.

    The catalog rect is the sprite's own box, bottom-aligned in a
    tile-aligned slot, so its slot ends on the tile row its bottom reaches.
    """
    ax, ay, aw, ah = rect
    acol = ax // TILE
    arow = -(-(ay + ah) // TILE) - rows_up
    return [[HOUSES_FIRSTGID + (arow + dy) * ATLAS_COLUMNS + acol + dx for dx in range(cols)]
            for dy in range(rows_up)]


def _png_size(path):
    with open(path, 'rb') as f:
        head = f.read(24)
    return int.from_bytes(head[16:20], 'big'), int.from_bytes(head[20:24], 'big')


def _clear_old_preview(obj_xml, cat, layers):
    """Take the replaced object's own preview cells off every Houses layer."""
    def prop(key):
        m = re.search(rf'<property name="{key}"[^>]*value="([^"]*)"', obj_xml)
        return m and m.group(1)
    entry = cat.get(f'houses/{prop("File_name")}')
    if not entry or not prop('Tiles_to_right'):
        return
    cols, rows_up = int(prop('Tiles_to_right')), int(prop('Tiles_up'))
    x = int(float(re.search(r' x="([^"]+)"', obj_xml).group(1))) // TILE
    y = int(float(re.search(r' y="([^"]+)"', obj_xml).group(1))) // TILE
    gids = _atlas_gids(entry['rect'], cols, rows_up)
    cleared = 0
    on_layers = []
    for name, grid in layers.items():
        if name.startswith('Houses'):
            for dy in range(rows_up):
                for dx in range(cols):
                    if grid[y - rows_up + dy][x + dx] == gids[dy][dx]:
                        grid[y - rows_up + dy][x + dx] = 0
                        cleared += 1
                        if name not in on_layers:
                            on_layers.append(name)
    if cleared:
        print(f'cleared {cleared} preview cells of the old {prop("File_name")}')
    return on_layers


def _obj_props(obj_xml):
    return {k: v for k, v in re.findall(r'<property name="([^"]+)"[^>]*value="([^"]*)"', obj_xml)}


def _collision_rect(x, y, props):
    """The game's House.collision_rect, as (left, top, right, bottom)."""
    s = float(props.get('Scale', 1))
    g = lambda k: float(props.get(k, 0)) * s
    w, h = g('Collision_to_right') * TILE, g('Collision_up') * TILE
    left = x - g('Col_margin_left_pixel')
    bottom = y + g('Col_margin_down_pixel')
    return (left, bottom - (h + g('Col_margin_up_pixel') + g('Col_margin_down_pixel')),
            left + w + g('Col_margin_left_pixel') + g('Col_margin_right_pixel'), bottom)


def _shift_object(text, xml, dx, dy):
    def rep(m):
        return f' {m.group(1)}="{round(float(m.group(2)) + (dx if m.group(1) == "x" else dy), 2):g}"'
    new = re.sub(r' (x|y)="([^"]+)"', rep, xml, count=2)
    return text.replace(xml, new)


# ------------------------------------------------------------------ commands

def _attached(text, obj_id):
    """XML of the Doors, Lights and Smoke objects that belong to a building.

    Doors: points inside its collision rect. Lights: the ones the game gives
    it (TMXMap._load_lights): of the buildings whose zone -- x within the
    collision rect, y up to 5 tiles above it -- holds the light, the one with
    the nearest base. Smoke: Smoke_<name>[_k].
    """
    xml = re.search(rf' <object id="{obj_id}" [^>]*>.*?</object>', text, re.S).group(0)
    name = re.search(r'name="([^"]*)"', xml).group(1)
    ox = float(re.search(r' x="([^"]+)"', xml).group(1))
    oy = float(re.search(r' y="([^"]+)"', xml).group(1))
    left, top, right, bottom = _collision_rect(ox, oy, _obj_props(xml))

    houses_grp = re.search(r'<objectgroup [^>]*name="Houses"[^>]*>(.*?)</objectgroup>', text, re.S).group(1)
    rects = {}
    for h in re.finditer(r'<object id="(\d+)"[^>]* x="([^"]+)" y="([^"]+)"[^>]*>.*?</object>', houses_grp, re.S):
        hp = _obj_props(h.group(0))
        if 'Collision_to_right' in hp:
            rects[int(h.group(1))] = _collision_rect(float(h.group(2)), float(h.group(3)), hp)

    def light_owner(cx, cy):
        zone = [(r[3], i) for i, r in rects.items() if r[0] <= cx <= r[2] and r[1] - 5 * TILE <= cy <= r[3]]
        return min(zone)[1] if zone else None

    found = []
    for group in ('Doors', 'Lights', 'Smoke'):
        grp = re.search(rf'<objectgroup [^>]*name="{group}"[^>]*>(.*?)</objectgroup>', text, re.S)
        for o in re.finditer(r'<object id="\d+" name="([^"]*)" x="([^"]+)" y="([^"]+)"(?: width="([^"]+)" height="([^"]+)")?[^>]*?/?>(?:\s*<point/>\s*</object>)?', grp.group(1)):
            oname, px, py = o.group(1), float(o.group(2)), float(o.group(3))
            cx, cy = px + float(o.group(4) or 0) / 2, py + float(o.group(5) or 0) / 2
            if group == 'Doors':
                hit = left <= px <= right and top <= py <= bottom
            elif group == 'Lights':
                hit = oname == 'Light_rectangle' and light_owner(cx, cy) == obj_id
            else:
                hit = re.fullmatch(rf'Smoke_{re.escape(name)}(_\d+)?', oname) is not None
            if hit:
                found.append(o.group(0))
    return found


def cmd_move(a):
    cat = json.load(open(CATALOG, encoding='utf-8'))['files']
    text, layers = load_tmx()
    m = re.search(rf' <object id="{a.id}" name="([^"]*)"[^>]*>.*?</object>', text, re.S)
    if not m:
        sys.exit(f'no object with id {a.id}')
    xml, name = m.group(0), m.group(1)
    props = _obj_props(xml)
    ox = float(re.search(r' x="([^"]+)"', xml).group(1))
    oy = float(re.search(r' y="([^"]+)"', xml).group(1))
    x, y = round(a.x / TILE) * TILE, round(a.y / TILE) * TILE
    if a.no_snap:
        x, y = round(a.x, 2), round(a.y, 2)
    dx, dy = x - ox, y - oy
    if not dx and not dy:
        sys.exit('already there')
    moving = _attached(text, a.id)
    for o in moving:
        text = _shift_object(text, o, dx, dy)
        print(f'moved {o.split(" x=")[0].strip()}')
    text = _shift_object(text, xml, dx, dy)

    preview_layers = _clear_old_preview(xml, cat, layers)
    if preview_layers and (x % TILE or y % TILE):
        sys.exit('it has Tiled preview tiles, which need a tile-aligned spot; drop --no-snap')
    entry = cat.get(f'houses/{props.get("File_name")}')
    for lname in preview_layers:
        gids = _atlas_gids(entry['rect'], int(props['Tiles_to_right']), int(props['Tiles_up']))
        t, l = y // TILE - len(gids), x // TILE
        for r, row in enumerate(gids):
            for c, gid in enumerate(row):
                if layers[lname][t + r][l + c] not in (0, gid):
                    sys.exit(f'{lname} cell ({l + c},{t + r}) is taken at the new spot; nothing written')
                layers[lname][t + r][l + c] = gid
        print(f'preview moved on "{lname}"')
    print(f'object {a.id} "{name}" ({ox:g},{oy:g}) -> ({x},{y}), {len(moving)} attached objects with it')
    if a.dry_run:
        print('dry run, nothing written')
    else:
        save_tmx(text, layers)
        print('written', TMX)


def cmd_place(a):
    cat = json.load(open(CATALOG, encoding='utf-8'))['files']
    entry = cat.get(f'houses/{a.sprite}')
    if not entry:
        sys.exit(f'{a.sprite} is not in {CATALOG}')
    tiled = dict(entry['tiled'])
    if tiled.get('layer', 'Houses') != 'Houses':
        sys.exit(f'{a.sprite} belongs on the {tiled["layer"]} layer, not Houses; place it by hand')
    cls = tiled.pop('class', 'House_Frontal')
    for kv in a.prop:
        k, _, v = kv.partition('=')
        if v == '':
            tiled.pop(k, None)
        else:
            tiled[k] = v
    x, y = round(a.x / TILE) * TILE, round(a.y / TILE) * TILE
    if a.no_snap:
        x, y = round(a.x, 2), round(a.y, 2)

    text, layers = load_tmx()
    nl = '\r\n' if '\r\n' in text else '\n'
    if a.replace:
        m = re.search(rf' <object id="{a.replace}" name="([^"]*)".*?</object>', text, re.S)
        if not m:
            sys.exit(f'no object with id {a.replace}')
        name = a.name or m.group(1)
        _clear_old_preview(m.group(0), cat, layers)
        if a.door or a.light or a.smoke:
            # New ones are given, so the old ones go
            for o in _attached(text, a.replace):
                if (nl + '  ' + o) not in text:
                    sys.exit(f'cannot find {o[:60]} to remove')
                text = text.replace(nl + '  ' + o, '', 1)
                print(f'removed {o.split(" x=")[0].strip()}')
        text = text.replace(m.group(0), object_xml(a.replace, name, cls, x, y, tiled, nl))
        obj_id = a.replace
    else:
        nxt = re.search(r'nextobjectid="(\d+)"', text)
        obj_id = int(nxt.group(1))
        name = a.name or os.path.splitext(a.sprite)[0]
        text = text.replace(nxt.group(0), f'nextobjectid="{obj_id + 1}"', 1)
        grp = re.search(r'<objectgroup [^>]*name="Houses"[^>]*>.*?(\s*</objectgroup>)', text, re.S)
        cut = grp.start(1)
        text = text[:cut] + nl + ' ' + object_xml(obj_id, name, cls, x, y, tiled, nl) + text[cut:]

    if (x % TILE or y % TILE) and not a.no_preview:
        print('off the tile grid: no Tiled preview stamped')
        a.no_preview = True
    if float(tiled.get('Scale', 1)) != 1 and not a.no_preview:
        print('Scale is set: Tiled previews are native size only, so none is stamped')
        a.no_preview = True
    if not a.no_preview:
        cols, rows_up = int(tiled['Tiles_to_right']), int(tiled['Tiles_up'])
        gids = _atlas_gids(entry['rect'], cols, rows_up)
        grid = layers[a.layer]
        top, left = y // TILE - rows_up, x // TILE
        for dy in range(rows_up):
            for dx in range(cols):
                gid = gids[dy][dx]
                cur = grid[top + dy][left + dx]
                if cur not in (0, gid):
                    sys.exit(f'{a.layer} cell ({left + dx},{top + dy}) is taken; pick another Houses layer')
                grid[top + dy][left + dx] = gid
        first = gids[0][0] - HOUSES_FIRSTGID
        print(f'preview: atlas tile ({first % ATLAS_COLUMNS},{first // ATLAS_COLUMNS}) -> map cells {left}..{left + cols - 1} x {top}..{top + rows_up - 1} on "{a.layer}"')

    print(f'object {obj_id} "{name}" {cls} at ({x},{y}): {tiled}')

    if a.door or a.light or a.smoke:
        scale = float(tiled.get('Scale', 1))
        top = y - _png_size(f'assets/map_sprites/houses/{a.sprite}')[1] * scale

        def world(sx, sy):
            return round(x + float(sx) * scale, 2), round(top + float(sy) * scale, 2)
        added = []
        for spec in a.door:
            sx, sy, facing = spec.split(',')
            if facing not in ('down', 'up', 'left', 'right'):
                sys.exit(f'door facing must be down/up/left/right, not {facing}')
            wx, wy = world(sx, sy)
            added.append(('Doors', f'<object id="{{id}}" name="{facing}" x="{wx}" y="{wy}">{nl}   <point/>{nl}  </object>'))
        for spec in a.light:
            sx, sy, w, h = spec.split(',')
            wx, wy = world(sx, sy)
            added.append(('Lights', f'<object id="{{id}}" name="Light_rectangle" x="{wx}" y="{wy}" '
                                    f'width="{round(float(w) * scale, 2)}" height="{round(float(h) * scale, 2)}"/>'))
        for k, spec in enumerate(a.smoke):
            sx, sy, w = spec.split(',')
            wx, wy = world(sx, sy)
            smoke_name = f'Smoke_{name}' + (f'_{k + 1}' if k else '')
            added.append(('Smoke', f'<object id="{{id}}" name="{smoke_name}" x="{wx}" y="{wy}" '
                                   f'width="{round(float(w) * scale, 2)}" height="1"/>'))
        if a.smoke and not re.fullmatch(r'House_\d+', name):
            print(f'WARNING: the game only reads Smoke_House_<n>; "{name}" will not smoke')
        for group, xml in added:
            nxt = re.search(r'nextobjectid="(\d+)"', text)
            new_id = int(nxt.group(1))
            text = text.replace(nxt.group(0), f'nextobjectid="{new_id + 1}"', 1)
            grp = re.search(rf'<objectgroup [^>]*name="{group}"[^>]*>.*?(\s*</objectgroup>)', text, re.S)
            text = text[:grp.start(1)] + nl + '  ' + xml.format(id=new_id) + text[grp.start(1):]
            print(f'{group}: {xml.format(id=new_id)}'.replace(nl, ' '))
    if a.dry_run:
        print('dry run, nothing written')
    else:
        save_tmx(text, layers)
        print('written', TMX)


def cmd_near(a):
    import pytmx
    m = pytmx.TiledMap(TMX)
    for layer in m.layers:
        if isinstance(layer, pytmx.TiledObjectGroup) and layer.name in ('Houses', 'Trees', 'Bridges', 'Doors'):
            for o in layer:
                if abs(o.x - a.x) < a.radius and abs(o.y - a.y) < a.radius:
                    p = o.properties
                    print(f'{layer.name:8} id={o.id:<4} {o.name!s:18} ({o.x:.0f},{o.y:.0f}) '
                          f'{p.get("File_name", "")} {p.get("Tiles_to_right", "")}x{p.get("Tiles_up", "")} '
                          f'{p.get("Display_name", "")} {"buy " + str(p["Buy_price"]) if "Buy_price" in p else ""}')
    _, layers = load_tmx()
    cx, cy, r = int(a.x // TILE), int(a.y // TILE), int(a.radius // TILE)
    for name, grid in layers.items():
        if name.startswith('Houses'):
            n = sum(1 for yy in range(max(0, cy - r), min(len(grid), cy + r))
                    for xx in range(max(0, cx - r), min(len(grid[0]), cx + r)) if grid[yy][xx])
            print(f'tile layer {name!r}: {n} cells used nearby')


def cmd_render(a):
    os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
    import pygame
    import pytmx
    pygame.init()
    pygame.display.set_mode((1, 1))
    x0, y0, x1, y1 = a.x0, a.y0, a.x1, a.y1
    m = pytmx.load_pygame(TMX)
    surf = pygame.Surface((x1 - x0, y1 - y0))
    surf.fill((40, 40, 40))
    for layer in m.visible_layers:
        if isinstance(layer, pytmx.TiledTileLayer) and layer.name.startswith('Ground'):
            for tx, ty, img in layer.tiles():
                px, py = tx * TILE - x0, ty * TILE - y0
                if -TILE < px < x1 - x0 and -TILE < py < y1 - y0:
                    surf.blit(img, (px, py))
    items = []
    for layer in m.visible_layers:
        if isinstance(layer, pytmx.TiledObjectGroup) and layer.name in ('Houses', 'Trees', 'Bridges'):
            for o in layer:
                f = o.properties.get('File_name')
                path = f'assets/map_sprites/{"trees" if layer.name == "Trees" else "houses"}/{f}'
                if not f or not os.path.exists(path):
                    continue
                im = pygame.image.load(path).convert_alpha()
                sc = float(o.properties.get('Scale', 1.0))
                if sc != 1:
                    im = pygame.transform.smoothscale(im, (round(im.get_width() * sc), round(im.get_height() * sc)))
                base = o.y + (o.height if layer.name == 'Bridges' else 0)
                items.append((base, im, o))
    for base, im, o in sorted(items, key=lambda t: t[0]):
        surf.blit(im, (o.x - x0, base - im.get_height() - y0))
        p = o.properties
        if p.get('Collision_to_right'):
            sc = float(p.get('Scale', 1.0))
            ml, mr = p.get('Col_margin_left_pixel', 0) * sc, p.get('Col_margin_right_pixel', 0) * sc
            mu, md = p.get('Col_margin_up_pixel', 0) * sc, p.get('Col_margin_down_pixel', 0) * sc
            w, h = p['Collision_to_right'] * TILE * sc, p['Collision_up'] * TILE * sc
            pygame.draw.rect(surf, (255, 0, 0), (o.x - ml - x0, o.y - h - mu - y0, w + ml + mr, h + mu + md), 1)
    for layer in m.visible_layers:
        if isinstance(layer, pytmx.TiledObjectGroup) and layer.name in ('Doors', 'Lights', 'Smoke'):
            for o in layer:
                if layer.name == 'Doors':
                    pygame.draw.circle(surf, (40, 120, 255), (o.x - x0, o.y - y0), 4)
                elif o.name == 'Light_rectangle' or layer.name == 'Smoke':
                    colour = (255, 230, 0) if layer.name == 'Lights' else (0, 255, 255)
                    pygame.draw.rect(surf, colour, (o.x - x0, o.y - y0, max(1, o.width), max(2, o.height)), 1)
    font = pygame.font.SysFont(None, 20)
    for g in range(-(-x0 // 320) * 320, x1, 320):
        surf.blit(font.render(f'{g // TILE}', True, (255, 255, 255)), (g - x0 + 2, 0))
    for g in range(-(-y0 // 320) * 320, y1, 320):
        surf.blit(font.render(f'{g // TILE}', True, (255, 255, 255)), (0, g - y0 + 2))
    fig = pygame.image.load('assets/map_sprites/figurines/humans/player/player_front_static.png').convert_alpha()
    fig = pygame.transform.smoothscale(fig, (TILE, round(TILE * fig.get_height() / fig.get_width())))
    for spot in a.figure:
        fx, fy = map(int, spot.split(','))
        surf.blit(fig, (fx - x0 - TILE // 2, fy - y0 - fig.get_height()))
    pygame.image.save(surf, a.out)
    print('saved', a.out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('near')
    p.add_argument('x', type=float); p.add_argument('y', type=float)
    p.add_argument('radius', type=float, nargs='?', default=600)
    p = sub.add_parser('render')
    for k in ('x0', 'y0', 'x1', 'y1'):
        p.add_argument(k, type=int)
    p.add_argument('out'); p.add_argument('--figure', action='append', default=[])
    p = sub.add_parser('place')
    p.add_argument('sprite'); p.add_argument('x', type=float); p.add_argument('y', type=float)
    p.add_argument('--replace', type=int); p.add_argument('--name')
    p.add_argument('--layer', default='Houses 6')
    p.add_argument('--prop', action='append', default=[])
    p.add_argument('--no-preview', action='store_true'); p.add_argument('--dry-run', action='store_true')
    p.add_argument('--no-snap', action='store_true', help='keep X,Y as given, off the tile grid')
    p.add_argument('--door', action='append', default=[])
    p.add_argument('--light', action='append', default=[])
    p.add_argument('--smoke', action='append', default=[])
    p = sub.add_parser('move')
    p.add_argument('id', type=int); p.add_argument('x', type=float); p.add_argument('y', type=float)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--no-snap', action='store_true', help='keep X,Y as given, off the tile grid')
    a = ap.parse_args()
    {'near': cmd_near, 'render': cmd_render, 'place': cmd_place, 'move': cmd_move}[a.cmd](a)


if __name__ == '__main__':
    main()
