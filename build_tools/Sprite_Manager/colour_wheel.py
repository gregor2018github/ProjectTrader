"""A colour wheel to pick a colour with the mouse: hue around, saturation outwards, brightness beside it."""

import colorsys
import math

import pygame

from theme import DIALOG_LINE, TEXT

BAR_W = 22               # the brightness bar beside the wheel
BAR_GAP = 16
MARK_R = 6               # the ring marking the chosen colour


def _wheel(radius):
    """The full-brightness wheel, see-through outside the circle."""
    size = 2 * radius + 1
    wheel = pygame.Surface((size, size), pygame.SRCALPHA)
    for y in range(size):
        for x in range(size):
            dx, dy = x - radius, y - radius
            distance = math.hypot(dx, dy)
            if distance <= radius:
                hue = (math.atan2(-dy, dx) / (2 * math.pi)) % 1
                r, g, b = colorsys.hsv_to_rgb(hue, distance / radius, 1)
                wheel.set_at((x, y), (round(r * 255), round(g * 255), round(b * 255), 255))
    return wheel


class ColourWheel:
    def __init__(self, colour):
        self.hsv = colorsys.rgb_to_hsv(*(c / 255 for c in colour))
        self.radius = 0
        self.wheel = None
        self.dimmed = None          # the wheel at the chosen brightness
        self.dimmed_value = None
        self.centre = (0, 0)
        self.bar = pygame.Rect(0, 0, 0, 0)
        self.dragging = None        # 'wheel' or 'bar' while the mouse is held on it

    @property
    def colour(self):
        return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(*self.hsv))

    @colour.setter
    def colour(self, rgb):
        self.hsv = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))

    def layout(self, rect):
        """Fit wheel and bar into `rect`."""
        radius = max(20, min((rect.w - BAR_W - BAR_GAP) // 2, rect.h // 2) - 2)
        if radius != self.radius:
            self.radius = radius
            self.wheel = _wheel(radius)
            self.dimmed_value = None
        width = 2 * radius + BAR_GAP + BAR_W
        left = rect.x + (rect.w - width) // 2
        self.centre = (left + radius, rect.centery)
        self.bar = pygame.Rect(left + 2 * radius + BAR_GAP, rect.centery - radius, BAR_W, 2 * radius)

    def draw(self, screen):
        h, s, v = self.hsv
        if self.dimmed_value != v:
            self.dimmed = self.wheel.copy()
            shade = round(v * 255)
            self.dimmed.fill((shade, shade, shade, 255), special_flags=pygame.BLEND_RGBA_MULT)
            self.dimmed_value = v
        screen.blit(self.dimmed, self.dimmed.get_rect(center=self.centre))
        pygame.draw.circle(screen, DIALOG_LINE, self.centre, self.radius + 1, 2)

        # Brightness bar: the chosen hue and saturation from black to full
        for y in range(self.bar.h):
            value = 1 - y / max(1, self.bar.h - 1)
            r, g, b = colorsys.hsv_to_rgb(h, s, value)
            pygame.draw.line(screen, (round(r * 255), round(g * 255), round(b * 255)),
                             (self.bar.x, self.bar.y + y), (self.bar.right - 1, self.bar.y + y))
        pygame.draw.rect(screen, DIALOG_LINE, self.bar, 2)
        mark_y = self.bar.y + round((1 - v) * (self.bar.h - 1))
        pygame.draw.rect(screen, TEXT, (self.bar.x - 3, mark_y - 2, self.bar.w + 6, 5), 2)

        angle = h * 2 * math.pi
        mark = (self.centre[0] + math.cos(angle) * s * self.radius,
                self.centre[1] - math.sin(angle) * s * self.radius)
        outline = (0, 0, 0) if v > 0.5 else (255, 255, 255)
        pygame.draw.circle(screen, outline, mark, MARK_R, 2)

    # --- mouse --------------------------------------------------------------

    def press(self, pos):
        """A click; True if it picked a colour."""
        if math.dist(pos, self.centre) <= self.radius + 2:
            self.dragging = 'wheel'
        elif self.bar.inflate(8, 4).collidepoint(pos):
            self.dragging = 'bar'
        else:
            return False
        self.drag(pos)
        return True

    def drag(self, pos):
        h, s, v = self.hsv
        if self.dragging == 'wheel':
            dx, dy = pos[0] - self.centre[0], pos[1] - self.centre[1]
            h = (math.atan2(-dy, dx) / (2 * math.pi)) % 1
            s = min(1.0, math.hypot(dx, dy) / self.radius)
        elif self.dragging == 'bar':
            v = min(1.0, max(0.0, 1 - (pos[1] - self.bar.y) / max(1, self.bar.h - 1)))
        self.hsv = (h, s, v)

    def release(self):
        """End of a drag; True if one was going on."""
        was = self.dragging is not None
        self.dragging = None
        return was
