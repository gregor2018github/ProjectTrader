import pygame
import random
from ..config.colors import *

class SoundControl:
    def __init__(self, screen_width, screen_height, font, button_image):
        self.font = font
        self.button_image = button_image
        self.playing = False
        self.current_song = None
        self.last_played_song = None
        self.play_queue = []
        
        # Set up button position and size
        self.button_size = 45  # Target size for button
        
        # Resize button image if needed
        if button_image.get_height() > self.button_size or button_image.get_width() > self.button_size:
            aspect_ratio = button_image.get_width() / button_image.get_height()
            new_height = self.button_size
            new_width = int(new_height * aspect_ratio)
            self.button_image = pygame.transform.scale(button_image, (new_width, new_height))
        
        # Create a background panel rect similar to time control
        padding = 3  # Padding around the button
        panel_width = self.button_image.get_width() + padding * 2
        panel_height = 50  # Same height as time control panel
        
        # Position the button to the left of time control
        button_x = screen_width - 400  # Position left of time control
        
        self.control_rect = pygame.Rect(
            button_x - padding,  # Account for "Music:" text
            screen_height - 55,  # Same positioning as time control
            panel_width,
            panel_height
        )
        
        # Create button rectangle centered in the panel
        self.button_rect = pygame.Rect(
            self.control_rect.x + (self.control_rect.width - self.button_image.get_width()) // 2,
            self.control_rect.y + (self.control_rect.height - self.button_image.get_height()) // 2,
            self.button_image.get_width(),
            self.button_image.get_height()
        )
        
        # Register for the music end event
        self.MUSIC_END_EVENT = pygame.USEREVENT + 1
        pygame.mixer.music.set_endevent(self.MUSIC_END_EVENT)
    
    def draw(self, screen):
        # Get mouse position for hover effects
        mouse_pos = pygame.mouse.get_pos()
        
        # Draw the background panel first
        pygame.draw.rect(screen, TAN, self.control_rect)
        pygame.draw.rect(screen, DARK_BROWN, self.control_rect, 2)
        
        # Draw the button
        screen.blit(self.button_image, self.button_rect)
        
        # If hovered, draw hover effect
        if self.button_rect.collidepoint(mouse_pos):
            overlay = pygame.Surface((self.button_rect.width, self.button_rect.height), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 20))  # Semi-transparent black
            screen.blit(overlay, self.button_rect)
            
            # Add a highlight border
            pygame.draw.rect(screen, DARK_BROWN, self.button_rect, 1)
        
        # Visual indicator when music is playing
        if self.playing:
            overlay = pygame.Surface((self.button_rect.width, self.button_rect.height), pygame.SRCALPHA)
            overlay.fill((0, 255, 0, 40))  # Green tint
            screen.blit(overlay, self.button_rect)
    
    def handle_click(self, pos, game):
        if self.button_rect.collidepoint(pos):
            if not self.playing:
                # Start playing music
                self.play_random_song(game)
                self.playing = True
                game.play_sound("button_click")
            else:
                # Fade out current song
                pygame.mixer.music.fadeout(1500)  # 1.5 second fadeout
                self.playing = False
                self.current_song = None
                game.play_sound("button_click")
            return True
        return False
    
    def handle_music_end_event(self, game):
        """Handle when a song ends and play the next song"""
        if self.playing:
            self.play_random_song(game)
    
    def play_random_song(self, game):
        """Play a random song that's different from the last played song"""
        available_songs = ["song_1", "song_2", "song_3", "song_4", "song_5"]
        
        # If we've played all songs, refill the queue but exclude the last played song
        if not self.play_queue:
            self.play_queue = available_songs.copy()
            if self.last_played_song and self.last_played_song in self.play_queue:
                self.play_queue.remove(self.last_played_song)
        
        # Pick a song from the queue
        self.current_song = random.choice(self.play_queue)
        self.play_queue.remove(self.current_song)
        
        # Remember this as the last played song
        self.last_played_song = self.current_song
        
        # Play the song (no looping)
        pygame.mixer.music.load(game.music_paths[self.current_song])
        pygame.mixer.music.play()
