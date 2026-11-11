"""The speech bubbles a figurine on the map speaks in: its click menu, a line it
says, and a talk with the player's answers under the line.

A bubble is shown as ``game_state.info_window``, points its tail at the figurine
and, while open, holds an NPC still facing the player (``talking_to``). What the
bubbles are used for lives elsewhere: the click menu in figurine_click_menu.py,
the scripted talks in figurine_talks.py.
"""

import math
import os
from typing import Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

import pygame

from ...config.colors import DARK_BROWN, BLACK, GOLD
from ...config.constants import FONTS_PATH
from ..text_reveal import LetterReveal
from ..transaction_feedback import good_icon
from .house_click_menu import is_player_near

if TYPE_CHECKING:
    from ...models.figurines.figurine import Figurine
    from ...models.map import Camera
    from ...game_state import GameState


# Speech bubble styling
BUBBLE_FILL = (236, 222, 188)          # Light parchment, paler than the house menu
BUBBLE_BORDER = DARK_BROWN
BUBBLE_BORDER_WIDTH = 2
BUBBLE_RADIUS = 10
BUBBLE_PADDING = 8
BUBBLE_MIN_WIDTH = 120
TAIL_WIDTH = 16                        # Width of the tail where it meets the bubble
TAIL_HEIGHT = 10
TITLE_FONT_SIZE = 20
OPTION_FONT_SIZE = 20
OPTION_HEIGHT = 28
OPTION_HOVER_FILL = (218, 198, 154)    # Darker parchment tone behind the hovered option
SPEECH_MAX_TEXT_WIDTH = 280            # Speech bubbles wrap their text at this width
CLOSE_CROSS_SIZE = 10
SPEECH_TEXT_GAP = 5                    # Extra space between the title rule and spoken text
# How far the player may stray before a chat breaks off, in world pixels. A
# little beyond the reach needed to start one, so a step aside does not cut
# the conversation short, but far from having to leave the map view
SPEECH_BREAK_DISTANCE = 80             # About 2.5 tiles

ANSWER_GAP = 8                         # Between a conversation's line and its answers
ANSWER_MARK = "\u00bb "                # Before each of the player's answers
BADGE_GAP = 10                         # Between an answer and what it brings
BADGE_ICON_SIZE = 20                   # The icon of what an answer brings, square
BADGE_TEXT_COLOR = (46, 104, 46)       # A gain, "+3": a muted green on the parchment
LAUREL_GOLD_DARK = (150, 110, 20)      # The wreath's outline

#: An answer's badge: what it brings, as its amount ("+3") and an icon
Badge = Tuple[str, pygame.Surface]
_badge_icons: Dict[str, pygame.Surface] = {}


def good_badge_icon(good_name: str) -> pygame.Surface:
    """A good's picture at badge size: its cut-out icon, or its 30px one."""
    return good_icon(good_name, BADGE_ICON_SIZE)


def reputation_badge_icon() -> pygame.Surface:
    """Reputation at badge size: a small gold laurel wreath, open at the top."""
    if "reputation" not in _badge_icons:
        # Drawn at four times the size and smoothed down, so the little leaves stay soft
        big = BADGE_ICON_SIZE * 4
        surf = pygame.Surface((big, big), pygame.SRCALPHA)
        cx, cy, radius = big / 2, big / 2 + 2, big * 0.36
        for side in (-1, 1):
            stem = [(cx + side * radius * math.sin(math.radians(a)), cy + radius * math.cos(math.radians(a)))
                    for a in range(20, 150, 10)]
            pygame.draw.lines(surf, LAUREL_GOLD_DARK, False, stem, 4)
            for i in range(1, len(stem), 2):
                (px, py), (qx, qy) = stem[i], stem[i - 1]
                tx, ty = px - qx, py - qy
                n = math.hypot(tx, ty) or 1
                tx, ty = tx / n, ty / n
                for flip in (-1, 1):            # a leaf each side of the stem, pointing along it
                    nx, ny = -ty * flip, tx * flip
                    tip = (px + tx * 18 + nx * 14, py + ty * 18 + ny * 14)
                    mid = ((px + tip[0]) / 2, (py + tip[1]) / 2)
                    leaf = [(px, py), (mid[0] - ny * 6 * flip, mid[1] + nx * 6 * flip), tip,
                            (mid[0] + ny * 6 * flip, mid[1] - nx * 6 * flip)]
                    pygame.draw.polygon(surf, GOLD, leaf)
                    pygame.draw.polygon(surf, LAUREL_GOLD_DARK, leaf, 3)
        _badge_icons["reputation"] = pygame.transform.smoothscale(surf, (BADGE_ICON_SIZE, BADGE_ICON_SIZE))
    return _badge_icons["reputation"]


def figurine_screen_pos(figurine: 'Figurine', camera: 'Camera') -> Tuple[int, int]:
    """Top-left of the figurine's drawn sprite, relative to the map content area.

    Args:
        figurine: The figurine to place.
        camera: Camera for the world-to-screen transform.

    Returns:
        Rounded screen position, without the map view's own offset.
    """
    screen_x, screen_y = camera.apply(figurine.x, figurine.y)
    sprite_offset_x, sprite_offset_y = figurine.sprite_draw_offset
    # The sprite box can be larger than the logical box (see Human)
    return (round(screen_x + sprite_offset_x * camera.zoom),
            round(screen_y + sprite_offset_y * camera.zoom))


def figurine_screen_rect(figurine: 'Figurine', camera: 'Camera',
                         map_content_rect: pygame.Rect) -> pygame.Rect:
    """The figurine's drawn sprite in screen coordinates.

    Args:
        figurine: The figurine to place.
        camera: Camera for the world-to-screen transform.
        map_content_rect: The map's drawing area on screen.

    Returns:
        The sprite's screen rectangle.
    """
    draw_x, draw_y = figurine_screen_pos(figurine, camera)
    sprite = figurine._get_scaled_sprite(camera.zoom)
    return pygame.Rect(map_content_rect.x + draw_x, map_content_rect.y + draw_y,
                       sprite.get_width(), sprite.get_height())


class FigurineBubble:
    """Rounded parchment bubble with a tail pointing at a figurine, and a small title.

    Subclasses size their content, call _place(), and draw the content in
    _draw_content(). A bubble is shown as game_state.info_window.
    """

    def __init__(
        self,
        screen: pygame.Surface,
        figurine: 'Figurine',
        game_state: 'GameState',
        sprite_rect: pygame.Rect,
    ):
        """Set up what every bubble shares.

        Args:
            screen: Surface to draw on.
            figurine: The figurine the bubble belongs to.
            game_state: The current game state.
            sprite_rect: The figurine's drawn sprite, in screen coordinates.
        """
        self.screen = screen
        self.figurine = figurine
        self.house = figurine  # map_view's distance-based auto-close looks for .house
        self.game_state = game_state
        self.sprite_rect = sprite_rect

        # Whoever the bubble belongs to gives the player their attention: an
        # NPC stands still and faces them for as long as it is open. Game
        # holds the other end of this, and lets them go when it closes
        if hasattr(figurine, "talking_to"):
            figurine.talking_to = game_state.game.game_map.map_player

        try:
            self.title_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), TITLE_FONT_SIZE)
            self.text_font = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), OPTION_FONT_SIZE)
        except Exception:
            self.title_font = self.text_font = game_state.font

        self.title = figurine.display_name
        self.title_height = self.title_font.get_linesize()
        # Where the content starts, below the title and its rule
        self.content_top = BUBBLE_PADDING + self.title_height + BUBBLE_PADDING // 2

    def _place(self, width: int, height: int) -> None:
        """Position the bubble above the figurine, or below it if there is no room.

        Args:
            width: Bubble width.
            height: Bubble height, without the tail.
        """
        screen_w, screen_h = self.screen.get_size()
        sprite_rect = self.sprite_rect
        self.tail_up = sprite_rect.top - TAIL_HEIGHT - height < 0
        if self.tail_up:
            self.tip = sprite_rect.midbottom
            y = sprite_rect.bottom + TAIL_HEIGHT
        else:
            self.tip = sprite_rect.midtop
            y = sprite_rect.top - TAIL_HEIGHT - height
        x = max(0, min(self.tip[0] - width // 2, screen_w - width))
        y = max(0, min(y, screen_h - height))
        self.rect = pygame.Rect(x, y, width, height)

        # The tail stays clear of the rounded corners when the bubble is clamped at an edge
        half_tail = TAIL_WIDTH // 2
        self.tail_x = max(self.rect.left + BUBBLE_RADIUS + half_tail,
                          min(self.tip[0], self.rect.right - BUBBLE_RADIUS - half_tail))

    def close(self) -> None:
        """Close the bubble with the shared fade-out, and let the figurine go."""
        if getattr(self.figurine, "talking_to", None) is not None:
            self.figurine.talking_to = None
        self.game_state.menu_fade_window = self
        self.game_state.menu_fade_timer = self.game_state.menu_fade_duration
        self.game_state.info_window = None
        self.game_state.active_house_menu = None

    def draw(self, alpha_scale: float = 1.0) -> None:
        """Draw the bubble.

        Args:
            alpha_scale: Transparency scale from 0.0 to 1.0.
        """
        if alpha_scale <= 0:
            return

        # Draw onto a surface covering bubble and tail, so fading is one set_alpha
        bounds = self.rect.union(pygame.Rect(self.tip[0], self.tip[1], 1, 1))
        surf = pygame.Surface(bounds.size, pygame.SRCALPHA)
        offset = (-bounds.x, -bounds.y)
        body = self.rect.move(offset)

        # Tail: an outer triangle in the border colour, then the body, then an
        # inner triangle in the fill colour that erases the border where they join
        tip = (self.tip[0] + offset[0], self.tip[1] + offset[1])
        tail_x = self.tail_x + offset[0]
        base_y = body.top + BUBBLE_BORDER_WIDTH if self.tail_up else body.bottom - BUBBLE_BORDER_WIDTH - 1
        inset = BUBBLE_BORDER_WIDTH + 1
        pygame.draw.polygon(surf, BUBBLE_BORDER,
                            [(tail_x - TAIL_WIDTH // 2, base_y), tip, (tail_x + TAIL_WIDTH // 2, base_y)])
        pygame.draw.rect(surf, BUBBLE_BORDER, body, border_radius=BUBBLE_RADIUS)
        pygame.draw.rect(surf, BUBBLE_FILL, body.inflate(-2 * BUBBLE_BORDER_WIDTH, -2 * BUBBLE_BORDER_WIDTH),
                         border_radius=BUBBLE_RADIUS - BUBBLE_BORDER_WIDTH)
        inner_tip = (tip[0], tip[1] + inset if self.tail_up else tip[1] - inset)
        pygame.draw.polygon(surf, BUBBLE_FILL,
                            [(tail_x - TAIL_WIDTH // 2 + inset, base_y), inner_tip,
                             (tail_x + TAIL_WIDTH // 2 - inset, base_y)])

        # Title with a short rule underneath
        title_surf = self.title_font.render(self.title, True, DARK_BROWN)
        surf.blit(title_surf, title_surf.get_rect(
            center=(body.centerx, body.y + BUBBLE_PADDING + self.title_height // 2)))
        rule_y = body.y + self.content_top - BUBBLE_PADDING // 4
        rule_half = title_surf.get_width() // 2 + 10
        pygame.draw.line(surf, BUBBLE_BORDER, (body.centerx - rule_half, rule_y),
                         (body.centerx + rule_half, rule_y), 1)

        # Hover feedback only while fully shown, not during the fade-out
        mouse_pos = pygame.mouse.get_pos() if alpha_scale >= 1.0 else None
        self._draw_content(surf, offset, mouse_pos)

        if alpha_scale < 1.0:
            surf.set_alpha(int(255 * alpha_scale))
        self.screen.blit(surf, bounds.topleft)

    def _draw_content(self, surf: pygame.Surface, offset: Tuple[int, int],
                      mouse_pos: Optional[Tuple[int, int]]) -> None:
        """Draw what goes below the title.

        Args:
            surf: The bubble's surface.
            offset: Add to a screen position to get a position on surf.
            mouse_pos: Mouse position on screen, or None while fading out.
        """
        raise NotImplementedError


class FigurineMenu(FigurineBubble):
    """A small speech-bubble menu for figurine interactions.

    Sparser than HouseMenu: a rounded parchment bubble, a small title, plain
    text rows instead of framed buttons, and no close button. Clicking
    anywhere outside the bubble closes it.
    """

    def __init__(
        self,
        screen: pygame.Surface,
        figurine: 'Figurine',
        options: List[str],
        game_state: 'GameState',
        sprite_rect: pygame.Rect,
        callback: Optional[Callable[[str], None]] = None,
    ):
        """Lay out the options.

        Args:
            screen: Surface to draw on.
            figurine: The figurine the menu belongs to.
            options: Option labels, top to bottom.
            game_state: The current game state.
            sprite_rect: The figurine's drawn sprite, in screen coordinates.
            callback: Called with the chosen option's label.
        """
        super().__init__(screen, figurine, game_state, sprite_rect)
        self.options = options
        self.callback = callback

        content_width = max(
            [self.title_font.size(self.title)[0]]
            + [self.text_font.size(option)[0] + 2 * BUBBLE_PADDING for option in options]
        )
        width = max(BUBBLE_MIN_WIDTH, content_width + 2 * BUBBLE_PADDING)
        self._place(width, self.content_top + len(options) * OPTION_HEIGHT + BUBBLE_PADDING)

        self.buttons: List[Tuple[pygame.Rect, str]] = []
        row_y = self.rect.y + self.content_top
        for option in options:
            row = pygame.Rect(self.rect.x + BUBBLE_PADDING // 2, row_y, width - BUBBLE_PADDING, OPTION_HEIGHT)
            self.buttons.append((row, option))
            row_y += OPTION_HEIGHT

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        """Run the clicked option, or close when clicked outside. Returns True if handled."""
        if not self.rect.collidepoint(pos):
            self.close()
            return True
        for rect, option in self.buttons:
            if rect.collidepoint(pos):
                if self.callback:
                    self.callback(option)
                else:
                    self.close()
                return True
        return True  # Clicks on the title or padding are absorbed

    def _draw_content(self, surf: pygame.Surface, offset: Tuple[int, int],
                      mouse_pos: Optional[Tuple[int, int]]) -> None:
        """Options: plain text with a soft rounded highlight on hover."""
        for rect, text in self.buttons:
            row = rect.move(offset)
            if mouse_pos is not None and rect.collidepoint(mouse_pos):
                pygame.draw.rect(surf, OPTION_HOVER_FILL, row, border_radius=OPTION_HEIGHT // 2)
            text_surf = self.text_font.render(text, True, BLACK)
            surf.blit(text_surf, text_surf.get_rect(center=row.center))


class FigurineSpeech(FigurineBubble):
    """A speech bubble with a line the figurine says, closed with a small cross.

    Clicking outside the bubble closes it as well. The bubble follows the
    figurine as it walks, and closes by itself once the player has walked
    SPEECH_BREAK_DISTANCE away from the figurine, or it has left the map view.
    """

    def __init__(
        self,
        screen: pygame.Surface,
        figurine: 'Figurine',
        text: str,
        game_state: 'GameState',
        map_content_rect: pygame.Rect,
    ):
        """Wrap the text and lay out the bubble.

        Args:
            screen: Surface to draw on.
            figurine: The figurine speaking.
            text: What it says.
            game_state: The current game state.
            map_content_rect: The map's drawing area on screen, to follow the figurine in.
        """
        self.map_content_rect = map_content_rect
        self.camera = game_state.game.game_map.camera
        super().__init__(screen, figurine, game_state,
                         figurine_screen_rect(figurine, self.camera, map_content_rect))
        # Not the map view's interaction-range close; this bubble keeps its
        # own, more forgiving distance in draw()
        self.house = None
        # Rendered once; the text never changes while the bubble is open
        lines = _wrap_text(text, self.text_font, SPEECH_MAX_TEXT_WIDTH)
        self.line_surfs = [self.text_font.render(line, True, BLACK).convert_alpha()
                           for line in lines]
        # The figurine speaks: the line appears letter by letter
        self.reveal = LetterReveal(list(zip(self.line_surfs, lines)), self.text_font)
        # Measured, because RomanAntique reports a far too small get_linesize()
        self.line_height = self.text_font.size("Ag")[1]

        # The title is centred, so the cross's space is reserved on both sides
        cross_space = CLOSE_CROSS_SIZE + BUBBLE_PADDING
        content_width = max(
            [self.title_font.size(self.title)[0] + 2 * cross_space]
            + [line_surf.get_width() for line_surf in self.line_surfs]
        )
        self.width = max(BUBBLE_MIN_WIDTH, content_width + 2 * BUBBLE_PADDING)
        self.height = (self.content_top + SPEECH_TEXT_GAP
                       + len(self.line_surfs) * self.line_height + BUBBLE_PADDING)
        self._layout()

    def _layout(self) -> None:
        """Place the bubble at the figurine's current sprite, with the cross in its corner."""
        self._place(self.width, self.height)
        self.close_rect = pygame.Rect(
            self.rect.right - BUBBLE_PADDING - CLOSE_CROSS_SIZE,
            self.rect.y + BUBBLE_PADDING + (self.title_height - CLOSE_CROSS_SIZE) // 2,
            CLOSE_CROSS_SIZE,
            CLOSE_CROSS_SIZE,
        )
        # The cross is small, so it is a little easier to hit than it looks
        self.close_hit_rect = self.close_rect.inflate(8, 8)

    def draw(self, alpha_scale: float = 1.0) -> None:
        """Move along with the figurine, and close once the player has left it behind.

        Args:
            alpha_scale: Transparency scale from 0.0 to 1.0.
        """
        sprite_rect = figurine_screen_rect(self.figurine, self.camera, self.map_content_rect)
        player = self.game_state.game.game_map.map_player
        in_view = (self.game_state.is_map_visible and not self.figurine.is_hidden
                   and sprite_rect.colliderect(self.map_content_rect)
                   and is_player_near(player, self.figurine, SPEECH_BREAK_DISTANCE))
        if in_view:
            self.sprite_rect = sprite_rect
            self._layout()
        elif alpha_scale >= 1.0:
            # Fully opaque means still open. The fade-out then stays where the
            # figurine was last within earshot
            self.close()
            return
        super().draw(alpha_scale)

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        """Close on the cross or outside the bubble. Returns True if handled."""
        if self.close_hit_rect.collidepoint(pos) or not self.rect.collidepoint(pos):
            self.close()
        elif not self.reveal.is_complete:
            # Clicking the bubble itself finishes the line for an impatient player
            self.reveal.skip()
        return True

    def _draw_content(self, surf: pygame.Surface, offset: Tuple[int, int],
                      mouse_pos: Optional[Tuple[int, int]]) -> None:
        """The spoken lines, and the cross in the title row."""
        cross = self.close_rect.move(offset)
        if mouse_pos is not None and self.close_hit_rect.collidepoint(mouse_pos):
            pygame.draw.circle(surf, OPTION_HOVER_FILL, cross.center, CLOSE_CROSS_SIZE)
        pygame.draw.line(surf, DARK_BROWN, cross.topleft, cross.bottomright, 2)
        pygame.draw.line(surf, DARK_BROWN, cross.bottomleft, cross.topright, 2)

        # The bubble follows the figurine, so the lines are placed fresh each
        # frame and handed to the reveal rather than positioned once
        body = self.rect.move(offset)
        positions = []
        y = body.y + self.content_top + SPEECH_TEXT_GAP
        for line_surf in self.line_surfs:
            positions.append(line_surf.get_rect(midtop=(body.centerx, y)).topleft)
            y += self.line_height
        self.reveal.draw(surf, positions)


class FigurineConversation(FigurineSpeech):
    """A speech bubble with the player's answers under the line, as plain rows like a menu's.

    Clicking an answer calls back with its label; the cross or a click outside
    closes it, as for any speech bubble. Enter or Space finishes the line, then
    picks the first answer. An answer may have badges beside it, what it brings
    the player ("+3" and a log of wood).
    """

    def __init__(
        self,
        screen: pygame.Surface,
        figurine: 'Figurine',
        text: str,
        answers: List[str],
        on_answer: Callable[[str], None],
        game_state: 'GameState',
        map_content_rect: pygame.Rect,
        badges: Optional[Dict[str, List[Badge]]] = None,
    ):
        """Lay out the line and the answers under it.

        Args:
            screen: Surface to draw on.
            figurine: The figurine speaking.
            text: What it says.
            answers: The player's answers, top to bottom.
            on_answer: Called with the label of the answer picked.
            game_state: The current game state.
            map_content_rect: The map's drawing area on screen, to follow the figurine in.
            badges: By answer label, what that answer brings, shown beside it.
        """
        # Set before the bubble first lays itself out, which places the answers too
        self.answers = list(answers)
        self.badges = {label: list(items) for label, items in (badges or {}).items() if items}
        self.on_answer = on_answer
        self.answer_rows: List[Tuple[pygame.Rect, str]] = []
        self.text_bottom: Optional[int] = None
        super().__init__(screen, figurine, text, game_state, map_content_rect)
        self.badge_surfs = {label: [(self.text_font.render(amount, True, BADGE_TEXT_COLOR), icon)
                                     for amount, icon in items]
                            for label, items in self.badges.items()}
        answer_width = max((self._answer_width(answer) + 2 * BUBBLE_PADDING for answer in self.answers), default=0)
        self.width = max(self.width, answer_width + 2 * BUBBLE_PADDING)
        self.text_bottom = self.height - BUBBLE_PADDING
        self.height += ANSWER_GAP + len(self.answers) * OPTION_HEIGHT
        self._layout()

    def _badge_width(self, answer: str) -> int:
        """The width of an answer's badges, 0 without any."""
        items = self.badge_surfs.get(answer, [])
        return sum(BADGE_GAP + text.get_width() + 2 + icon.get_width() for text, icon in items)

    def _answer_width(self, answer: str) -> int:
        return self.text_font.size(ANSWER_MARK + answer)[0] + self._badge_width(answer)

    def _layout(self) -> None:
        super()._layout()
        if self.text_bottom is None:
            self.answer_rows = []
            return
        top = self.rect.y + self.text_bottom + ANSWER_GAP
        self.answer_rows = [
            (pygame.Rect(self.rect.x + BUBBLE_PADDING // 2, top + index * OPTION_HEIGHT,
                         self.width - BUBBLE_PADDING, OPTION_HEIGHT), answer)
            for index, answer in enumerate(self.answers)
        ]

    def handle_click(self, pos: Tuple[int, int]) -> bool:
        """An answer, the cross or outside the bubble. Returns True if handled."""
        for row, answer in self.answer_rows:
            if row.collidepoint(pos):
                self.on_answer(answer)
                return True
        return super().handle_click(pos)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Enter or Space: finish the line, then pick the first answer; Escape walks away."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.close()
            return True
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            if not self.reveal.is_complete:
                self.reveal.skip()
            elif self.answers:
                self.on_answer(self.answers[0])
            return True
        return False

    def _draw_content(self, surf: pygame.Surface, offset: Tuple[int, int],
                      mouse_pos: Optional[Tuple[int, int]]) -> None:
        """The line, then the answers below a rule, with a soft highlight on hover."""
        super()._draw_content(surf, offset, mouse_pos)
        if not self.answer_rows:
            return
        first = self.answer_rows[0][0].move(offset)
        rule_y = first.top - ANSWER_GAP // 2
        pygame.draw.line(surf, BUBBLE_BORDER, (first.left + BUBBLE_PADDING, rule_y),
                         (first.right - BUBBLE_PADDING, rule_y), 1)
        for rect, text in self.answer_rows:
            row = rect.move(offset)
            if mouse_pos is not None and rect.collidepoint(mouse_pos):
                pygame.draw.rect(surf, OPTION_HOVER_FILL, row, border_radius=OPTION_HEIGHT // 2)
            text_surf = self.text_font.render(ANSWER_MARK + text, True, BLACK)
            # The answer and its badges are centred together
            x = row.centerx - self._answer_width(text) // 2
            surf.blit(text_surf, text_surf.get_rect(midleft=(x, row.centery)))
            x += text_surf.get_width()
            for amount, icon in self.badge_surfs.get(text, []):
                x += BADGE_GAP
                surf.blit(amount, amount.get_rect(midleft=(x, row.centery)))
                x += amount.get_width() + 2
                surf.blit(icon, icon.get_rect(midleft=(x, row.centery)))
                x += icon.get_width()


def _wrap_text(text: str, font: pygame.font.Font, max_width: int) -> List[str]:
    """Break text into lines no wider than max_width (a single long word may exceed it).

    Args:
        text: The text to wrap.
        font: Font the text is rendered in.
        max_width: Maximum line width in pixels.

    Returns:
        The wrapped lines.
    """
    lines: List[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if current and font.size(candidate)[0] > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines
