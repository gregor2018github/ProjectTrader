import pygame
import random
from typing import List, Optional, Tuple, Any, TYPE_CHECKING
from ...config.colors import *
from ...config.constants import MUSIC_VOLUME

if TYPE_CHECKING:
    from ...game import Game

_SLIDER_WIDTH = 24
_SLIDER_HEIGHT = 120
_HANDLE_HEIGHT = 14
_NEXT_BTN_SIZE = 28
_NEXT_BTN_GAP = 4


class SoundControl:
    """A UI component to toggle background music and manage the playlist.

    Attributes:
        font: The font used for text rendering.
        button_image: The icon for the music button.
        playing: Boolean state of background music playback.
        current_song: Key of the currently playing song.
        last_played_song: Key of the previous song played.
        play_queue: List of songs waiting to be played.
        button_size: Target size for the control button.
        control_rect: Rectangular area for the background panel.
        button_rect: Rectangular area for the interactive button.
        MUSIC_END_EVENT: Custom event ID for song completion.
        volume: Current music volume (0.0 – 1.0).
        show_slider: Whether the volume slider is visible.
        dragging_slider: Whether the user is currently dragging the slider handle.
    """

    def __init__(self, screen_width: int, screen_height: int, font: pygame.font.Font, button_image: pygame.Surface) -> None:
        self.font: pygame.font.Font = font
        self.button_image: pygame.Surface = button_image
        self.playing: bool = False
        self.current_song: Optional[str] = None
        self.last_played_song: Optional[str] = None
        self.play_queue: List[str] = []
        self.volume: float = MUSIC_VOLUME
        self.show_slider: bool = False
        self.dragging_slider: bool = False

        self.button_size: int = 45

        if button_image.get_height() > self.button_size or button_image.get_width() > self.button_size:
            aspect_ratio = button_image.get_width() / button_image.get_height()
            new_height = self.button_size
            new_width = int(new_height * aspect_ratio)
            self.button_image = pygame.transform.scale(button_image, (new_width, new_height))

        padding: int = 3
        panel_width: int = self.button_image.get_width() + padding * 2
        panel_height: int = 50

        button_x: int = screen_width - 400

        self.control_rect: pygame.Rect = pygame.Rect(
            button_x - padding,
            screen_height - 55,
            panel_width,
            panel_height
        )

        self.button_rect: pygame.Rect = pygame.Rect(
            self.control_rect.x + (self.control_rect.width - self.button_image.get_width()) // 2,
            self.control_rect.y + (self.control_rect.height - self.button_image.get_height()) // 2,
            self.button_image.get_width(),
            self.button_image.get_height()
        )

        # Slider panel positioned above the button panel with a gap
        slider_x = self.control_rect.x + (self.control_rect.width - _SLIDER_WIDTH) // 2
        slider_panel_y = self.control_rect.y - _SLIDER_HEIGHT - 16
        self.slider_panel_rect: pygame.Rect = pygame.Rect(
            slider_x - 6,
            slider_panel_y,
            _SLIDER_WIDTH + 12,
            _SLIDER_HEIGHT + 12,
        )
        # The draggable track inside the panel
        self.slider_track_rect: pygame.Rect = pygame.Rect(
            slider_x + _SLIDER_WIDTH // 2 - 2,
            slider_panel_y + 6,
            4,
            _SLIDER_HEIGHT,
        )

        # Next-song button: sits to the right of the slider panel, vertically centred
        self.next_btn_rect: pygame.Rect = pygame.Rect(
            self.slider_panel_rect.right + _NEXT_BTN_GAP,
            self.slider_panel_rect.centery - _NEXT_BTN_SIZE // 2,
            _NEXT_BTN_SIZE,
            _NEXT_BTN_SIZE,
        )

        self.MUSIC_END_EVENT: int = pygame.USEREVENT + 1
        pygame.mixer.music.set_endevent(self.MUSIC_END_EVENT)
        pygame.mixer.music.set_volume(self.volume)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _handle_y(self) -> int:
        """Y pixel of the top of the slider handle based on current volume."""
        track_top = self.slider_track_rect.top
        track_bottom = self.slider_track_rect.bottom - _HANDLE_HEIGHT
        return int(track_top + (1.0 - self.volume) * (track_bottom - track_top))

    def _handle_rect(self) -> pygame.Rect:
        return pygame.Rect(
            self.slider_track_rect.x - (_SLIDER_WIDTH // 2 - 2),
            self._handle_y(),
            _SLIDER_WIDTH,
            _HANDLE_HEIGHT,
        )

    def _volume_from_mouse_y(self, mouse_y: int) -> float:
        track_top = self.slider_track_rect.top
        track_bottom = self.slider_track_rect.bottom - _HANDLE_HEIGHT
        ratio = 1.0 - (mouse_y - track_top) / max(track_bottom - track_top, 1)
        return max(0.0, min(1.0, ratio))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def draw(self, screen: pygame.Surface) -> None:
        mouse_pos = pygame.mouse.get_pos()

        # Button panel
        pygame.draw.rect(screen, TAN, self.control_rect)
        pygame.draw.rect(screen, DARK_BROWN, self.control_rect, 2)
        screen.blit(self.button_image, self.button_rect)

        if self.button_rect.collidepoint(mouse_pos):
            overlay = pygame.Surface((self.button_rect.width, self.button_rect.height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 20))
            screen.blit(overlay, self.button_rect)
            pygame.draw.rect(screen, DARK_BROWN, self.button_rect, 1)

        if self.playing:
            overlay = pygame.Surface((self.button_rect.width, self.button_rect.height), pygame.SRCALPHA)
            overlay.fill((0, 255, 0, 40))
            screen.blit(overlay, self.button_rect)

        # Volume slider
        if self.show_slider:
            pygame.draw.rect(screen, TAN, self.slider_panel_rect)
            pygame.draw.rect(screen, DARK_BROWN, self.slider_panel_rect, 2)

            # Track: draw as light/empty rail
            pygame.draw.rect(screen, WHITE, self.slider_track_rect)
            pygame.draw.rect(screen, DARK_BROWN, self.slider_track_rect, 1)

            # Fill from track bottom up to handle centre — volume level indicator
            handle_center_y = self._handle_y() + _HANDLE_HEIGHT // 2
            fill_rect = pygame.Rect(
                self.slider_track_rect.x,
                handle_center_y,
                self.slider_track_rect.width,
                self.slider_track_rect.bottom - handle_center_y,
            )
            pygame.draw.rect(screen, DARK_BROWN, fill_rect)

            # Handle
            handle = self._handle_rect()
            pygame.draw.rect(screen, DARK_BROWN, handle, border_radius=3)

            # Next-song button
            pygame.draw.rect(screen, TAN, self.next_btn_rect)
            pygame.draw.rect(screen, DARK_BROWN, self.next_btn_rect, 2)
            # Skip-forward icon: filled triangle + vertical bar
            tri = 8
            cx = self.next_btn_rect.centerx - 2
            cy = self.next_btn_rect.centery
            pygame.draw.polygon(screen, DARK_BROWN, [
                (cx - tri // 2, cy - tri // 2),
                (cx + tri // 2, cy),
                (cx - tri // 2, cy + tri // 2),
            ])
            bar_x = cx + tri // 2 + 2
            pygame.draw.rect(screen, DARK_BROWN, pygame.Rect(bar_x, cy - tri // 2, 3, tri))
            if self.next_btn_rect.collidepoint(mouse_pos):
                overlay = pygame.Surface((self.next_btn_rect.width, self.next_btn_rect.height), pygame.SRCALPHA)
                overlay.fill((0, 0, 0, 20))
                screen.blit(overlay, self.next_btn_rect)

            # Tooltip — % when hovering slider/button, "Next song" when hovering skip button
            if self.next_btn_rect.collidepoint(mouse_pos):
                tip_text = "Next song"
                tip_color = DARK_BROWN
            elif self.slider_panel_rect.collidepoint(mouse_pos) or self.control_rect.collidepoint(mouse_pos):
                tip_text = f"{int(self.volume * 100)}%"
                tip_color = DARK_BROWN
            else:
                tip_text = None
                tip_color = DARK_BROWN
            if tip_text:
                label_surf = self.font.render(tip_text, True, tip_color)
                tip_x = mouse_pos[0] + 35
                tip_y = mouse_pos[1] - 10
                tip_rect = label_surf.get_rect(topleft=(tip_x, tip_y))
                if tip_rect.right > screen.get_width() - 10:
                    tip_rect.topright = (mouse_pos[0] - 15, tip_y)
                if tip_rect.bottom > screen.get_height():
                    tip_rect.bottom = screen.get_height()
                bg_rect = tip_rect.inflate(10, 8)
                pygame.draw.rect(screen, WHITE, bg_rect)
                pygame.draw.rect(screen, DARK_BROWN, bg_rect, 1)
                screen.blit(label_surf, tip_rect)

    def handle_click(self, pos: Tuple[int, int], game: 'Game') -> bool:
        """Handle left-click: toggle music playback."""
        if self.button_rect.collidepoint(pos):
            if not self.playing:
                self.play_random_song(game)
                self.playing = True
                game.play_sound("button_click")
            else:
                pygame.mixer.music.fadeout(1500)
                self.playing = False
                self.current_song = None
                game.play_sound("button_click")
            return True
        # Next-song button: fade out current song; MUSIC_END_EVENT will advance the queue
        if self.show_slider and self.next_btn_rect.collidepoint(pos):
            if self.playing:
                pygame.mixer.music.fadeout(1500)
            return True
        # Left-clicking outside the slider/next-button area closes the panel
        if self.show_slider and not self.slider_panel_rect.collidepoint(pos) and not self.next_btn_rect.collidepoint(pos):
            self.show_slider = False
        return False

    def handle_right_click(self, pos: Tuple[int, int]) -> bool:
        """Handle right-click on the button: toggle the volume slider."""
        if self.button_rect.collidepoint(pos) or self.control_rect.collidepoint(pos):
            self.show_slider = not self.show_slider
            return True
        return False

    def handle_mouse_down(self, pos: Tuple[int, int]) -> bool:
        """Start dragging the slider handle if clicked."""
        if self.show_slider and self._handle_rect().collidepoint(pos):
            self.dragging_slider = True
            return True
        return False

    def handle_mouse_motion(self, pos: Tuple[int, int]) -> None:
        """Update volume while dragging."""
        if self.dragging_slider:
            self.volume = self._volume_from_mouse_y(pos[1])
            pygame.mixer.music.set_volume(self.volume)

    def handle_mouse_up(self) -> None:
        """Stop dragging."""
        self.dragging_slider = False

    def handle_music_end_event(self, game: 'Game') -> None:
        if self.playing:
            self.play_random_song(game)

    def play_random_song(self, game: 'Game') -> None:
        available_songs = list(game.music_paths.keys())

        if not self.play_queue:
            self.play_queue = available_songs.copy()
            if self.last_played_song and self.last_played_song in self.play_queue:
                self.play_queue.remove(self.last_played_song)

        self.current_song = random.choice(self.play_queue)
        self.play_queue.remove(self.current_song)
        self.last_played_song = self.current_song

        pygame.mixer.music.set_endevent()  # suppress end event from the forced stop
        pygame.mixer.music.stop()
        pygame.mixer.music.set_endevent(self.MUSIC_END_EVENT)
        pygame.mixer.music.load(game.music_paths[self.current_song])
        pygame.mixer.music.set_volume(self.volume)
        pygame.mixer.music.play()
