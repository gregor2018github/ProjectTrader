"""The overview above the plants or the buildings: four panels in one row.

    Sprites       how many there are, big, and how full each collection is
    By kind       one bar split by kind, with its legend
    Newest        the sprites made last, as small pictures
    Work          made today, unfinished new ones, answers waiting
"""

import datetime
from dataclasses import dataclass, field

import pygame

import pose_review
from daily_progress import created
from images import pixel_fit
from pose_review import ReviewStore
from sprite_library import REFERENCE, TILE, UNSORTED
from theme import BAR_BG, DONE_COLOR, PANEL_GAP, STATUS_COLORS, TEXT, TEXT_DIM, THUMB_BG
from widgets import draw_panel, fit_text, progress_color

SUMMARY_H = 112
PAD = 14
COUNT_W = 240
WORK_W = 250
NEWEST_SHARE = 0.32      # of what the two fixed panels leave
NEWEST = 60              # the newest sprites kept, for the start page's gallery
KIND_BAR_H = 14
LEGEND_ROW = 19
SWATCH = 10
FILL_BAR_H = 5
MINI = 58                # the pictures of the newest sprites
MINI_GAP = 8
UNSORTED_COLOR = (120, 114, 104)
# One colour per kind, in the order of the domain's kinds: muted, to sit on the dark panels
KIND_COLORS = ((122, 170, 96), (86, 140, 110), (196, 168, 82), (208, 120, 140), (186, 92, 86),
               (120, 150, 190), (150, 120, 180), (170, 140, 100))


@dataclass
class Stats:
    total: int = 0
    singles: int = 0
    motifs: int = 0
    kinds: list = field(default_factory=list)      # [(title, count, colour)]
    fills: list = field(default_factory=list)      # [(tileset name, share of its tiles used)]
    newest: list = field(default_factory=list)     # [LibrarySprite], newest first
    today: int = 0
    unfinished: int = 0
    waiting: int = 0


def atlas_fill(path):
    """Share of a collection's tiles holding anything, 0..1; None if it cannot be read."""
    try:
        image = pygame.image.load(str(path)).convert_alpha()
    except (pygame.error, OSError):
        return None
    w, h = image.get_size()
    cols, rows = max(1, w // TILE), max(1, h // TILE)
    tiles = pygame.mask.from_surface(image, 1).scale((cols, rows))
    return tiles.count() / (cols * rows)


def gather(domain, sprites, jobs, fills):
    """The numbers of the overview.

    Args:
        fills: {collection key: share used}, filled in here once per
            collection and kept by the caller, since reading a collection
            takes a moment.
    """
    stats = Stats()
    listed = [s for s in sprites if s.kind != REFERENCE]
    stats.total = len(listed)
    stats.singles = sum(1 for s in listed if s.path)
    stats.motifs = stats.total - stats.singles
    for index, kind in enumerate(domain.kinds):
        stats.kinds.append((kind.title, sum(1 for s in listed if s.kind == kind.key),
                            KIND_COLORS[index % len(KIND_COLORS)]))
    unsorted = sum(1 for s in listed if s.kind == UNSORTED)
    if unsorted:
        stats.kinds.append(('Unsorted', unsorted, UNSORTED_COLOR))

    for atlas in domain.atlases.values():
        if atlas.key not in fills:
            fills[atlas.key] = atlas_fill(atlas.path)
        if fills[atlas.key] is not None:
            stats.fills.append((atlas.tileset, fills[atlas.key]))

    midnight = datetime.datetime.combine(datetime.date.today(), datetime.time()).timestamp()
    dated = []
    for sprite in listed:
        if sprite.path:
            try:
                born = created(sprite.path.stat())
            except OSError:
                continue
            dated.append((born, sprite))
            stats.today += born >= midnight
    dated.sort(key=lambda d: -d[0])
    stats.newest = [sprite for _, sprite in dated[:NEWEST]]

    open_jobs = [job for job in jobs if not job.accepted]
    stats.unfinished = len(open_jobs)
    stats.waiting = sum(len(ReviewStore(job.out_dir).pending()) for job in open_jobs)
    return stats


def mini(sprite):
    """A small picture of a sprite, made once and kept on it."""
    if getattr(sprite, 'mini', None) is None:
        tile = pygame.Surface((MINI, MINI))
        tile.fill(THUMB_BG)
        image = pixel_fit(sprite.surface, (MINI - 6, MINI - 6))
        tile.blit(image, image.get_rect(center=tile.get_rect().center))
        sprite.mini = tile
    return sprite.mini


def draw_summary(screen, fonts, rect, stats, noun):
    """The four panels in `rect`."""
    count = pygame.Rect(rect.x, rect.y, COUNT_W, rect.h)
    work = pygame.Rect(rect.right - WORK_W, rect.y, WORK_W, rect.h)
    middle = work.x - PANEL_GAP - (count.right + PANEL_GAP)
    newest_w = max(MINI + 2 * PAD, int(middle * NEWEST_SHARE))
    newest = pygame.Rect(work.x - PANEL_GAP - newest_w, rect.y, newest_w, rect.h)
    kinds = pygame.Rect(count.right + PANEL_GAP, rect.y, newest.x - PANEL_GAP - count.right - PANEL_GAP, rect.h)
    _draw_count(screen, fonts, count, stats, noun)
    _draw_kinds(screen, fonts, kinds, stats)
    _draw_newest(screen, fonts, newest, stats)
    _draw_work(screen, fonts, work, stats)


def _draw_count(screen, fonts, panel, stats, noun):
    """How many sprites, big, and under it how full each collection is."""
    draw_panel(screen, fonts, panel, f'{noun.capitalize()} sprites')
    big = fonts.title.render(str(stats.total), True, TEXT)
    parts = [f'{stats.singles} files'] + ([f'{stats.motifs} cut out'] if stats.motifs else [])
    line = fonts.small.render(', '.join(parts), True, TEXT_DIM)
    x = panel.x + PAD
    screen.blit(big, (x, panel.y + 4))
    screen.blit(line, line.get_rect(bottomleft=(x + big.get_width() + 10, panel.y + 4 + big.get_height() - 8)))
    y = panel.y + 4 + big.get_height() + 2
    bar_w = panel.w - 2 * PAD
    for name, share in stats.fills:
        percent = fonts.small.render(f'{round(share * 100)}% full', True, TEXT_DIM)
        name_w = bar_w - percent.get_width() - 10
        label = fonts.small.render(fit_text(fonts.small, name, name_w), True, TEXT_DIM)
        screen.blit(label, (x, y))
        screen.blit(percent, percent.get_rect(topright=(x + bar_w, y)))
        y += label.get_height()
        bar = pygame.Rect(x, y, bar_w, FILL_BAR_H)
        pygame.draw.rect(screen, BAR_BG, bar, border_radius=3)
        # Green while there is room, turning red as the collection fills up
        if round(bar.w * share):
            filled = (bar.x, bar.y, max(FILL_BAR_H, round(bar.w * share)), bar.h)
            pygame.draw.rect(screen, progress_color(1 - share), filled, border_radius=3)
        y += FILL_BAR_H + 4


def _draw_kinds(screen, fonts, panel, stats):
    """One bar split by kind, and a legend of swatches with their counts."""
    draw_panel(screen, fonts, panel, 'By kind')
    inner = panel.inflate(-2 * PAD, -2 * PAD)
    total = sum(n for _, n, _ in stats.kinds) or 1
    bar = pygame.Rect(inner.x, inner.y, inner.w, KIND_BAR_H)
    pygame.draw.rect(screen, BAR_BG, bar, border_radius=KIND_BAR_H // 2)
    x = bar.x
    shown = [(title, n, color) for title, n, color in stats.kinds if n]
    clip = screen.get_clip()
    screen.set_clip(bar)
    for index, (title, n, color) in enumerate(shown):
        width = bar.right - x if index == len(shown) - 1 else round(bar.w * n / total)
        pygame.draw.rect(screen, color, (x, bar.y, width, bar.h))
        x += width
    screen.set_clip(clip)

    # Legend: swatch, title and count, flowing into rows
    x, y = inner.x, bar.bottom + 10
    for title, n, color in stats.kinds:
        text = fonts.small.render(f'{title} {n}', True, TEXT if n else TEXT_DIM)
        width = SWATCH + 6 + text.get_width()
        if x > inner.x and x + width > inner.right:
            x, y = inner.x, y + LEGEND_ROW
        if y + LEGEND_ROW > panel.bottom:
            break
        pygame.draw.rect(screen, color if n else BAR_BG, (x, y + 5, SWATCH, SWATCH), border_radius=2)
        screen.blit(text, (x + SWATCH + 6, y))
        x += width + 16


def _draw_newest(screen, fonts, panel, stats):
    """The sprites made last, newest on the left, as many as fit."""
    draw_panel(screen, fonts, panel, 'Newest')
    fit = max(1, (panel.w - 2 * PAD + MINI_GAP) // (MINI + MINI_GAP))
    x = panel.x + PAD
    y = panel.y + 10
    for sprite in stats.newest[:fit]:
        screen.blit(mini(sprite), (x, y))
        name = fonts.small.render(fit_text(fonts.small, sprite.path.stem, MINI + MINI_GAP - 2), True, TEXT_DIM)
        screen.blit(name, name.get_rect(midtop=(x + MINI // 2, y + MINI + 4)))
        x += MINI + MINI_GAP


def _draw_work(screen, fonts, panel, stats):
    """Three big numbers: made today, unfinished, answers waiting."""
    draw_panel(screen, fonts, panel, 'Work')
    third = panel.w // 3
    numbers = ((stats.today, 'new today', STATUS_COLORS[pose_review.ACCEPTED]),
               (stats.unfinished, 'unfinished', DONE_COLOR),
               (stats.waiting, 'to review', STATUS_COLORS[pose_review.PENDING]))
    for index, (number, label, color) in enumerate(numbers):
        centre = panel.x + third * index + third // 2
        big = fonts.title.render(str(number), True, color if number else TEXT_DIM)
        text = fonts.small.render(label, True, TEXT_DIM)
        y = panel.centery - (big.get_height() + text.get_height()) // 2
        screen.blit(big, big.get_rect(midtop=(centre, y)))
        screen.blit(text, text.get_rect(midtop=(centre, y + big.get_height())))
        if index:
            pygame.draw.line(screen, BAR_BG, (panel.x + third * index, panel.y + PAD),
                             (panel.x + third * index, panel.bottom - PAD), 2)
