"""Letter-by-letter reveal for text that has already been rendered.

Shared by the dialogue window and the speech bubbles on the map, so both
reveal their text with the same timing and feel.

Text is rendered in whole segments - a word for the dialogue window, a
wrapped line for a speech bubble - and every letter is kept as a column
slice of its segment's surface. Blitting all the slices of a segment
reproduces it pixel for pixel, whereas rendering each letter on its own
would lose the antialiasing between neighbours and come out a few pixels
wider than the same text drawn in one piece.
"""

from typing import Dict, List, Sequence, Tuple

import pygame

#: Delay between one letter starting to appear and the next.
LETTER_INTERVAL_MS: float = 18.0
#: How long a single letter takes to fade from invisible to solid.
FADE_MS: float = 180.0
#: How far a letter drifts up into place while it fades in.
RISE_PX: int = 6
#: Extra pauses so the reveal breathes where a speaker would.
PUNCTUATION_PAUSE_MS: Dict[str, float] = {
    ",": 70.0, ";": 70.0, ":": 70.0,
    ".": 150.0, "!": 150.0, "?": 150.0,
}


class LetterReveal:
    """Reveals pre-rendered text segments one letter at a time.

    Several neighbouring letters are always mid-fade, so a line arrives as a
    soft wave rather than behind a hard typewriter cursor.

    The caller owns where the text sits: positions are passed to draw(), so a
    bubble that follows a walking figurine can move between frames.
    """

    def __init__(
        self,
        segments: Sequence[Tuple[pygame.Surface, str]],
        font: pygame.font.Font,
        letter_interval_ms: float = LETTER_INTERVAL_MS,
        fade_ms: float = FADE_MS,
        rise_px: int = RISE_PX,
    ) -> None:
        """Slice every segment into letters and work out when each one starts.

        Args:
            segments: The rendered surface and its text, in reading order.
            font: The font the segments were rendered with, used to measure
                where each letter starts inside its segment.
            letter_interval_ms: Delay between consecutive letters.
            fade_ms: How long one letter takes to fade in.
            rise_px: How far a letter drifts up while fading in.
        """
        self.surfaces: List[pygame.Surface] = [surface for surface, _ in segments]
        self.fade_ms = fade_ms
        self.rise_px = rise_px

        # (segment index, slice x, slice width, start time in ms)
        self._slices: List[Tuple[int, int, int, float]] = []
        delay: float = 0.0

        for index, (surface, text) in enumerate(segments):
            width = surface.get_width()
            first_of_segment = len(self._slices)
            pending_x: int = -1  # columns waiting to join the next letter

            for i, char in enumerate(text):
                slice_x = font.size(text[:i])[0]
                # The last letter takes the remainder, so any overhang is kept
                slice_end = width if i == len(text) - 1 else font.size(text[:i + 1])[0]

                if char.isspace() or slice_end <= slice_x:
                    # A space is not revealed on its own, but its columns must
                    # still be drawn: a neighbouring glyph's ink can overhang
                    # into them, and skipping them would lose those pixels.
                    if len(self._slices) > first_of_segment:
                        prev_index, prev_x, prev_w, prev_delay = self._slices[-1]
                        self._slices[-1] = (prev_index, prev_x,
                                            max(prev_w, slice_end - prev_x), prev_delay)
                    elif pending_x < 0:
                        pending_x = slice_x
                else:
                    start_x = slice_x if pending_x < 0 else pending_x
                    self._slices.append((index, start_x, slice_end - start_x, delay))
                    pending_x = -1

                delay += letter_interval_ms
                delay += PUNCTUATION_PAUSE_MS.get(char, 0.0)

            # The gap between two segments reads as a space
            delay += letter_interval_ms

        self.total_ms: float = delay + fade_ms
        self.start_ticks: int = pygame.time.get_ticks()

    @property
    def elapsed_ms(self) -> float:
        """Milliseconds since the reveal started."""
        return pygame.time.get_ticks() - self.start_ticks

    @property
    def is_complete(self) -> bool:
        """True once every letter has finished fading in."""
        return self.elapsed_ms >= self.total_ms

    def skip(self) -> None:
        """Show all the text at once, for a player who does not want to wait."""
        self.start_ticks = pygame.time.get_ticks() - int(self.total_ms)

    def restart(self) -> None:
        """Start the reveal again from the first letter."""
        self.start_ticks = pygame.time.get_ticks()

    def draw(self, target: pygame.Surface,
             positions: Sequence[Tuple[int, int]]) -> None:
        """Draw every letter that has started, fading and drifting into place.

        Args:
            target: Surface to draw on.
            positions: Top-left of each segment, in target coordinates, in the
                same order as the segments given to the constructor.
        """
        now: float = self.elapsed_ms

        for index, slice_x, slice_w, start in self._slices:
            progress: float = (now - start) / self.fade_ms
            if progress <= 0.0:
                # Start times only increase, so nothing later has begun either
                break

            surface = self.surfaces[index]
            area = pygame.Rect(slice_x, 0, slice_w, surface.get_height())
            x, y = positions[index]

            if progress >= 1.0:
                surface.set_alpha(255)
                target.blit(surface, (x + slice_x, y), area)
                continue

            eased: float = 1.0 - (1.0 - progress) ** 3  # ease-out cubic
            surface.set_alpha(int(255 * eased))
            target.blit(
                surface,
                (x + slice_x, y + int((1.0 - eased) * self.rise_px)),
                area,
            )
