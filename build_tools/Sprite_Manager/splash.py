"""The splash screen shown while the Sprite Manager reads its sprites.

Three random sprites - a person, a plant and a building, one for each area of
the tool - are held fanned out like cards in a hand, under the tool's name,
with a spinner turning below them. The reading runs on a worker thread
(Splash.run_while()) so the window keeps drawing; when it is done the splash
fades softly into the start page (Splash.fade_out()).
"""

import math
import random
import threading
import time

import pygame

from images import pixel_fit, trim
from theme import BG, DONE_COLOR, HUMANS_DIR, ROOT, TEXT, TEXT_DIM, window_size

FPS = 60
MIN_SECONDS = 0.8        # shown at least this long, so a quick start does not flash
FADE_SECONDS = 0.7

CARD_SIZE = (200, 280)
CARD_RADIUS = 14
CARD_FACE = (238, 228, 204)
CARD_INNER = (196, 178, 140)
CARD_SHADOW = (0, 0, 0, 90)
FAN_ANGLE = 21           # degrees between neighbouring cards
FAN_RADIUS = 480         # how far below the cards the hand holding them is
GLOW = (64, 58, 50)

SPINNER_DOTS = 12
SPINNER_RADIUS = 16
SPINNER_TURNS_PER_SECOND = 0.9

SPRITES = ROOT / 'assets' / 'map_sprites'
CARDS = (                # (label, folder, file pattern), left to right
    ('Humans', HUMANS_DIR, '*/*/*_front_static.png'),
    ('Plants', SPRITES / 'trees', 'Tree_*.png'),
    ('Buildings', SPRITES / 'houses', 'House_*.png'),
)


def _ease(x):
    """Smooth start and end, for 0..1."""
    return x * x * (3 - 2 * x)


class Splash:
    def __init__(self):
        self.title_font = pygame.font.SysFont('georgia', 56, bold=True)
        self.over_font = pygame.font.SysFont('georgia', 17, bold=True)
        self.label_font = pygame.font.SysFont('georgia', 17, bold=True)
        self.small_font = pygame.font.SysFont('segoeui', 16)
        self.cards = [self._card(label, folder, pattern) for label, folder, pattern in CARDS]
        self.started = time.monotonic()
        self._glow = None    # (size, surface), remade when the window is resized

    # --- running ----------------------------------------------------------

    def run_while(self, work):
        """Animate until `work()`, run on a worker thread, is done; returns its result.

        Closing the window meanwhile exits the program; an error in `work`
        is raised here.
        """
        outcome = {}

        def worker():
            try:
                outcome['result'] = work()
            except BaseException as exc:   # handed over to the main thread
                outcome['error'] = exc

        thread = threading.Thread(target=worker, name='sprite-manager-loading', daemon=True)
        thread.start()
        clock = pygame.time.Clock()
        while thread.is_alive() or time.monotonic() - self.started < MIN_SECONDS:
            self._pump()
            self.draw(pygame.display.get_surface())
            pygame.display.flip()
            clock.tick(FPS)
        if 'error' in outcome:
            raise outcome['error']
        return outcome.get('result')

    def fade_out(self, draw_app):
        """Blend the splash away over the app, which `draw_app()` draws without flipping."""
        clock = pygame.time.Clock()
        start = time.monotonic()
        while (elapsed := time.monotonic() - start) < FADE_SECONDS:
            self._pump()
            screen = pygame.display.get_surface()
            fade = _ease(elapsed / FADE_SECONDS)
            layer = pygame.Surface(screen.get_size())
            self.draw(layer, lift=fade)
            draw_app()
            layer.set_alpha(round(255 * (1 - fade)))
            screen.blit(layer, (0, 0))
            pygame.display.flip()
            clock.tick(FPS)

    @staticmethod
    def _pump():
        """Keep the window responsive; nothing but closing it counts yet."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit

    # --- drawing ----------------------------------------------------------

    def draw(self, surface, lift=0.0):
        """One frame; `lift` (0..1) raises the cards and spreads the fan as it fades."""
        t = time.monotonic() - self.started
        width, height = surface.get_size()
        surface.fill(BG)
        surface.blit(self.glow((width, height)), (0, 0))

        intro = _ease(min(1.0, t / 0.6))           # the fan opens as the splash appears
        centre_x = width // 2
        cards_y = int(height * 0.5 - 40 * lift)
        self.draw_title(surface, centre_x, int(height * 0.17))
        self.draw_fan(surface, centre_x, cards_y, t, intro * (1 + 0.25 * lift))
        self.draw_spinner(surface, centre_x, int(height * 0.83), t)

    def glow(self, size):
        """A soft light behind the cards, in the middle of the window."""
        if self._glow is None or self._glow[0] != size:
            glow = pygame.Surface(size, pygame.SRCALPHA)
            centre = (size[0] // 2, int(size[1] * 0.5))
            largest = int(max(size) * 0.55)
            for step in range(24, 0, -1):
                radius = largest * step // 24
                alpha = int(70 * (1 - step / 24) ** 1.5) + 4
                pygame.draw.circle(glow, (*GLOW, alpha), centre, radius)
            self._glow = (size, glow)
        return self._glow[1]

    def draw_title(self, surface, x, y):
        over = self.over_font.render("M E R C H A N T ' S   R I S E", True, DONE_COLOR)
        surface.blit(over, over.get_rect(midbottom=(x, y - 34)))
        title = self.title_font.render('Sprite Manager', True, TEXT)
        shadow = self.title_font.render('Sprite Manager', True, (0, 0, 0))
        rect = title.get_rect(center=(x, y))
        shadow.set_alpha(120)
        surface.blit(shadow, rect.move(3, 3))
        surface.blit(title, rect)
        line_y = rect.bottom + 12
        pygame.draw.line(surface, DONE_COLOR, (x - 140, line_y), (x - 12, line_y), 2)
        pygame.draw.line(surface, DONE_COLOR, (x + 12, line_y), (x + 140, line_y), 2)
        pygame.draw.circle(surface, DONE_COLOR, (x, line_y), 4)

    def draw_fan(self, surface, x, y, t, spread):
        """The cards fanned out around a hand below them, swaying gently."""
        pivot = (x, y + FAN_RADIUS)
        middle = (len(self.cards) - 1) / 2
        for index, card in enumerate(self.cards):
            offset = index - middle
            sway = 1.6 * math.sin(t * 1.3 + index * 0.9)
            angle = offset * FAN_ANGLE * spread + sway      # degrees, clockwise on screen
            bob = 6 * math.sin(t * 2.0 + index * 1.7)
            radians = math.radians(angle)
            reach = FAN_RADIUS + bob - (abs(offset) * 14)
            centre = (pivot[0] + reach * math.sin(radians), pivot[1] - reach * math.cos(radians))
            turned = pygame.transform.rotozoom(card, -angle, 1)
            surface.blit(turned, turned.get_rect(center=(round(centre[0]), round(centre[1]))))

    def draw_spinner(self, surface, x, y, t):
        """A ring of dots chasing round, and what is going on beside it."""
        head = t * SPINNER_TURNS_PER_SECOND * SPINNER_DOTS
        size = SPINNER_RADIUS * 2 + 12
        ring = pygame.Surface((size, size), pygame.SRCALPHA)
        for dot in range(SPINNER_DOTS):
            behind = (head - dot) % SPINNER_DOTS
            strength = max(0.0, 1 - behind / SPINNER_DOTS) ** 2
            angle = 2 * math.pi * dot / SPINNER_DOTS - math.pi / 2
            centre = (size / 2 + SPINNER_RADIUS * math.cos(angle), size / 2 + SPINNER_RADIUS * math.sin(angle))
            pygame.draw.circle(ring, (*DONE_COLOR, int(40 + 215 * strength)), centre, 2 + 2 * strength)
        dots = '.' * (int(t * 2.5) % 4)
        text = self.small_font.render('Gathering the sprites' + dots, True, TEXT_DIM)
        width = size + 14 + self.small_font.size('Gathering the sprites...')[0]
        left = x - width // 2
        surface.blit(ring, ring.get_rect(midleft=(left, y)))
        surface.blit(text, text.get_rect(midleft=(left + size + 14, y)))

    # --- the cards --------------------------------------------------------

    def _card(self, label, folder, pattern):
        """A card with a random sprite of the area on it, and the area's name."""
        w, h = CARD_SIZE
        pad = 6
        card = pygame.Surface((w + 2 * pad, h + 2 * pad), pygame.SRCALPHA)
        body = pygame.Rect(pad, pad, w, h)
        pygame.draw.rect(card, CARD_SHADOW, body.move(4, 5), border_radius=CARD_RADIUS)
        pygame.draw.rect(card, CARD_FACE, body, border_radius=CARD_RADIUS)
        pygame.draw.rect(card, DONE_COLOR, body, 3, border_radius=CARD_RADIUS)
        inner = body.inflate(-16, -16)
        pygame.draw.rect(card, CARD_INNER, inner, 1, border_radius=CARD_RADIUS - 6)

        picture = pygame.Rect(inner.x + 8, inner.y + 10, inner.w - 16, inner.h - 52)
        sprite = self._random_sprite(folder, pattern)
        if sprite:
            image = pixel_fit(sprite, picture.size)
            card.blit(image, image.get_rect(midbottom=picture.midbottom))
        name = self.label_font.render(label, True, (92, 70, 40))
        card.blit(name, name.get_rect(midbottom=(inner.centerx, inner.bottom - 10)))
        for corner in (inner.topleft, inner.topright, inner.bottomleft, inner.bottomright):   # pips
            cx = corner[0] + (10 if corner[0] == inner.x else -10)
            cy = corner[1] + (10 if corner[1] == inner.y else -10)
            pygame.draw.circle(card, DONE_COLOR, (cx, cy), 3)
        return card

    @staticmethod
    def _random_sprite(folder, pattern):
        """A sprite of the folder, trimmed, or None if there is none to read."""
        paths = sorted(folder.glob(pattern))
        random.shuffle(paths)
        for path in paths[:5]:
            try:
                image = pygame.image.load(str(path)).convert_alpha()
            except (pygame.error, OSError):
                continue
            if image.get_bounding_rect().w:
                return trim(image)
        return None
