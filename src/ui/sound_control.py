import pygame
import random
from ..config.colors import *

class SoundControl:
    def __init__(self, screen_width, screen_height, font, button_image):
        self.font = font
        self.button_image = button_image
        self.playing = False
        self.current_song = None
        
        # Set up button position and size
        self.button_size = 45  # Target size for button
        
        # Resize button image if needed
        if button_image.get_height() > self.button_size or button_image.get_width() > self.button_size:
            aspect_ratio = button_image.get_width() / button_image.get_height()
            new_height = self.button_size
            new_width = int(new_height * aspect_ratio)
            self.button_image = pygame.transform.scale(button_image, (new_width, new_height))
        
        # Position the button to the left of time control
        button_x = screen_width - 400  # Position left of time control
        button_y = screen_height - self.button_image.get_height() -8
        
        # Create button rectangle
        self.button_rect = pygame.Rect(
            button_x, button_y, self.button_image.get_width(), self.button_image.get_height()
        )
    
    def draw(self, screen):
        # Get mouse position for hover effects
        mouse_pos = pygame.mouse.get_pos()
        
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
                # Play a random song
                available_songs = ["song_1", "song_2", "song_3", "song_4", "song_5"]
                self.current_song = random.choice(available_songs)
                pygame.mixer.music.load(game.music_paths[self.current_song])
                pygame.mixer.music.play(-1)  # Loop indefinitely
                self.playing = True
                game.play_sound("button_click")
            else:
                # Fade out current song
                pygame.mixer.music.fadeout(1500)  # 1 second fadeout
                self.playing = False
                game.play_sound("button_click")
            return True
        return False
