"""
Demo File to test map rendering, player movement, and collision detection.
"""

import os
import pygame

from src.config.constants import MAX_RECULCULATIONS_PER_SEC

class Tile:
    """Represents a single map tile"""
    def __init__(self, tile_type, walkable=True, sprite_path=None):
        self.tile_type = tile_type
        self.walkable = walkable
        self.sprite = None
        if sprite_path:
            self.sprite = pygame.image.load(sprite_path)

class Camera:
    """Handles camera/viewport that follows the player"""
    def __init__(self, screen_width, screen_height):
        self.x = 0
        self.y = 0
        self.screen_width = screen_width
        self.screen_height = screen_height
    
    def update(self, target_x, target_y, tile_size):
        """Center camera on target (usually player)"""
        self.x = target_x - self.screen_width // 2
        self.y = target_y - self.screen_height // 2
    
    def apply(self, x, y):
        """Convert world coordinates to screen coordinates"""
        return x - self.x, y - self.y

class GameMap:
    """Main map class that handles rendering and collision"""
    def __init__(self, width, height, tile_size=32):
        self.width = width  # in tiles
        self.height = height  # in tiles
        self.tile_size = tile_size
        self.tiles = [[None for _ in range(width)] for _ in range(height)]
        
        # Load tile sprites
        self.tile_sprites = {
            'grass': pygame.Surface((tile_size, tile_size)),
            'water': pygame.Surface((tile_size, tile_size)),
            'tree': pygame.Surface((tile_size, tile_size)),
            'path': pygame.Surface((tile_size, tile_size))
        }
        
        # Set default colors (replace with actual sprites later)
        self.tile_sprites['grass'].fill((34, 139, 34))
        self.tile_sprites['water'].fill((30, 144, 255))
        self.tile_sprites['tree'].fill((0, 100, 0))
        self.tile_sprites['path'].fill((139, 69, 19))
    
    def set_tile(self, x, y, tile_type, walkable=True):
        """Set a tile at grid position"""
        if 0 <= x < self.width and 0 <= y < self.height:
            self.tiles[y][x] = {
                'type': tile_type,
                'walkable': walkable
            }
    
    def get_tile(self, x, y):
        """Get tile at grid position"""
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.tiles[y][x]
        return None
    
    def is_walkable(self, x, y):
        """Check if tile is walkable"""
        tile = self.get_tile(x, y)
        return tile is not None and tile.get('walkable', True)
    
    def world_to_grid(self, world_x, world_y):
        """Convert world pixel coordinates to grid coordinates"""
        return int(world_x) // self.tile_size, int(world_y) // self.tile_size
    
    def grid_to_world(self, grid_x, grid_y):
        """Convert grid coordinates to world pixel coordinates"""
        return grid_x * self.tile_size, grid_y * self.tile_size
    
    def render(self, screen, camera):
        """Render visible portion of map"""
        # Calculate which tiles are visible
        start_x = max(0, int(camera.x) // self.tile_size)
        start_y = max(0, int(camera.y) // self.tile_size)
        end_x = min(self.width, (int(camera.x) + camera.screen_width) // self.tile_size + 2)
        end_y = min(self.height, (int(camera.y) + camera.screen_height) // self.tile_size + 2)
        
        # Render only visible tiles
        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                tile = self.tiles[y][x]
                if tile:
                    world_x, world_y = self.grid_to_world(x, y)
                    screen_x, screen_y = camera.apply(world_x, world_y)
                    
                    sprite = self.tile_sprites.get(tile['type'])
                    if sprite:
                        screen.blit(sprite, (screen_x, screen_y))


class DirectionalAnimator:
    """Handles directional animations with sprite fallbacks."""

    DIRECTIONS = ("front", "back", "left", "right")

    def __init__(self, base_path, sprite_definitions, target_width, fallback_static):
        self.base_path = base_path
        self.sprite_definitions = sprite_definitions
        self.target_width = target_width

        self.fallback_surface = self._load_and_scale(fallback_static)
        if self.fallback_surface is None:
            self.fallback_surface = pygame.Surface((self.target_width, self.target_width), pygame.SRCALPHA)
            self.fallback_surface.fill((255, 0, 255))

        self.frames = {}
        for direction in self.DIRECTIONS:
            config = self.sprite_definitions.get(direction, {})
            static_surface = self._load_and_scale(config.get("static"))
            if static_surface is None:
                static_surface = self.fallback_surface

            move_frames = []
            for filename in config.get("move", []):
                frame = self._load_and_scale(filename)
                if frame:
                    move_frames.append(frame)

            if not move_frames:
                move_frames = [static_surface]

            self.frames[direction] = {
                "static": [static_surface],
                "move": move_frames,
            }

        self.current_direction = "front"
        self.is_moving = False
        self.current_frame_index = 0
        self.time_since_last_frame = 0.0

        # Use the recalc constant as baseline and slow animation slightly for readability.
        base_interval = 1.0 / max(1, MAX_RECULCULATIONS_PER_SEC)
        # increase interval to make animation slower, for example base_interval * 2 is twice as base_interval * 1
        self.frame_interval = max(base_interval * 8, 0.05)

    @property
    def current_frame_size(self):
        frame = self.get_current_frame()
        return frame.get_width(), frame.get_height()

    def _load_and_scale(self, filename):
        if not filename:
            return None

        path = os.path.join(self.base_path, filename)
        if not os.path.exists(path):
            return None

        try:
            image = pygame.image.load(path).convert_alpha()
        except pygame.error:
            return None

        original_width, original_height = image.get_size()
        if original_width <= 0 or original_height <= 0:
            return None

        scale_ratio = self.target_width / float(original_width)
        scaled_height = max(1, int(round(original_height * scale_ratio)))
        return pygame.transform.smoothscale(image, (self.target_width, scaled_height))

    def update(self, dt, direction, is_moving):
        if direction not in self.frames:
            direction = "front"

        if direction != self.current_direction or is_moving != self.is_moving:
            self.current_direction = direction
            self.is_moving = is_moving
            self.current_frame_index = 0
            self.time_since_last_frame = 0.0

        self.time_since_last_frame += dt

        active_key = "move" if self.is_moving else "static"
        frames = self.frames[self.current_direction][active_key]

        if len(frames) <= 1:
            self.current_frame_index = 0
            return

        if self.time_since_last_frame >= self.frame_interval:
            self.time_since_last_frame %= self.frame_interval
            self.current_frame_index = (self.current_frame_index + 1) % len(frames)

    def get_current_frame(self):
        active_key = "move" if self.is_moving else "static"
        frames = self.frames[self.current_direction][active_key]
        if not frames:
            return self.fallback_surface
        return frames[self.current_frame_index % len(frames)]

class Player:
    """Player character that moves around the map"""
    def __init__(self, x, y, tile_size=32):
        self.x = x  # world coordinates (float for smooth movement)
        self.y = y
        self.tile_size = tile_size
        self.speed = 140  # pixels per second

        sprite_dir = os.path.join('assets', 'map_sprites')
        sprite_definitions = {
            "front": {
                "static": "player_front_static.png",
                "move": ["player_front_move1.png", "player_front_move2.png"],
            },
            "back": {
                "static": "player_back_static.png",
                "move": ["player_back_move1.png", "player_back_move2.png"],
            },
            "left": {
                "static": "player_left_static.png",
                "move": ["player_left_move1.png", "player_left_move2.png"],
            },
            "right": {
                "static": "player_right_static.png",
                "move": ["player_right_move1.png", "player_right_move2.png"],
            },
        }

        self.animator = DirectionalAnimator(
            base_path=sprite_dir,
            sprite_definitions=sprite_definitions,
            target_width=tile_size,
            fallback_static="player_front_static.png",
        )

        self.sprite = self.animator.get_current_frame()
        self.width = tile_size
        self.height = self.sprite.get_height()
        
        # Movement state
        self.vel_x = 0
        self.vel_y = 0
    
    def set_movement(self, dx, dy):
        """Set movement direction (-1, 0, 1 for each axis)"""
        self.vel_x = dx
        self.vel_y = dy
    
    def update(self, dt, game_map):
        """Update player position with collision detection and animation."""
        is_moving = self.vel_x != 0 or self.vel_y != 0

        if is_moving:
            move_x = self.vel_x * self.speed * dt
            move_y = self.vel_y * self.speed * dt

            if move_x != 0:
                new_x = self.x + move_x
                if self.can_move_to(new_x, self.y, game_map):
                    self.x = new_x

            if move_y != 0:
                new_y = self.y + move_y
                if self.can_move_to(self.x, new_y, game_map):
                    self.y = new_y

        direction = self._determine_direction(is_moving)
        self.animator.update(dt, direction, is_moving)
        self.sprite = self.animator.get_current_frame()
        self.width = self.sprite.get_width()
        self.height = self.sprite.get_height()

    def _determine_direction(self, is_moving):
        if is_moving:
            if self.vel_y > 0:
                return "front"
            if self.vel_y < 0:
                return "back"
            if self.vel_x < 0:
                return "left"
            if self.vel_x > 0:
                return "right"
        return self.animator.current_direction
    
    def can_move_to(self, x, y, game_map):
        """Check if player can move to the given position"""
        # Ensure coordinates are within map bounds
        if x < 0 or y < 0:
            return False
        if x + self.width > game_map.width * game_map.tile_size:
            return False
        if y + self.height > game_map.height * game_map.tile_size:
            return False
        
        # Get the four corners of the player sprite
        corners = [
            (x, y),  # top-left
            (x + self.width - 1, y),  # top-right
            (x, y + self.height - 1),  # bottom-left
            (x + self.width - 1, y + self.height - 1)  # bottom-right
        ]
        
        # Check if all corners are in walkable tiles
        for corner_x, corner_y in corners:
            # Make sure corner coordinates are positive
            if corner_x < 0 or corner_y < 0:
                return False
                
            grid_x, grid_y = game_map.world_to_grid(corner_x, corner_y)
            if not game_map.is_walkable(grid_x, grid_y):
                return False
        
        return True
    
    def render(self, screen, camera):
        """Render player"""
        screen_x, screen_y = camera.apply(self.x, self.y)
        screen.blit(self.sprite, (int(screen_x), int(screen_y)))

class Game:
    """Main game class"""
    def __init__(self):
        pygame.init()
        self.screen_width = 1400
        self.screen_height = 1000
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Map Demo")
        
        self.clock = pygame.time.Clock()
        self.running = True
        
        # Initialize game objects
        self.camera = Camera(self.screen_width, self.screen_height)
        self.game_map = GameMap(50, 50, 32)  # 50x50 tile map
        self.player = Player(5 * 32, 5 * 32, 32)  # Start at grid position (5,5)
        
        # Input handling
        self.keys_pressed = set()
        
        # Create a simple test map
        self.create_test_map()
    
    def create_test_map(self):
        """Create a simple test map"""
        # Fill with grass
        for y in range(self.game_map.height):
            for x in range(self.game_map.width):
                self.game_map.set_tile(x, y, 'grass')
        
        # Add some water
        for x in range(10, 15):
            for y in range(10, 15):
                self.game_map.set_tile(x, y, 'water', walkable=False)
        
        # Add some trees
        for i in range(20):
            import random
            x, y = random.randint(0, 49), random.randint(0, 49)
            if self.game_map.get_tile(x, y)['type'] == 'grass':
                self.game_map.set_tile(x, y, 'tree', walkable=False)
        
        # Add a path
        for x in range(0, 20):
            self.game_map.set_tile(x, 25, 'path')
    
    def handle_events(self):
        """Handle input events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self.keys_pressed.add(event.key)
            elif event.type == pygame.KEYUP:
                self.keys_pressed.discard(event.key)
        
        # Handle continuous movement based on currently pressed keys
        dx, dy = 0, 0
        
        if pygame.K_UP in self.keys_pressed or pygame.K_w in self.keys_pressed:
            dy -= 1
        if pygame.K_DOWN in self.keys_pressed or pygame.K_s in self.keys_pressed:
            dy += 1
        if pygame.K_LEFT in self.keys_pressed or pygame.K_a in self.keys_pressed:
            dx -= 1
        if pygame.K_RIGHT in self.keys_pressed or pygame.K_d in self.keys_pressed:
            dx += 1
        
        # Normalize diagonal movement
        if dx != 0 and dy != 0:
            dx *= 0.707  # 1/sqrt(2)
            dy *= 0.707
        
        self.player.set_movement(dx, dy)
    
    def update(self):
        """Update game state"""
        # Get delta time in seconds
        dt = self.clock.get_time() / 1000.0
        
        self.player.update(dt, self.game_map)
        self.camera.update(
            self.player.x + self.player.width / 2,
            self.player.y + self.player.height / 2,
            self.player.width
        )  # Center on player
    
    def render(self):
        """Render everything"""
        self.screen.fill((0, 0, 0))
        
        # Render map
        self.game_map.render(self.screen, self.camera)
        
        # Render player
        self.player.render(self.screen, self.camera)
        
        pygame.display.flip()
    
    def run(self):
        """Main game loop"""
        while self.running:
            self.handle_events()
            self.update()
            self.render()
            self.clock.tick(60)
        
        pygame.quit()

# Example usage
if __name__ == "__main__":
    game = Game()
    game.run()