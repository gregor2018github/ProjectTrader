import pygame
import json

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

class Player:
    """Player character that moves around the map"""
    def __init__(self, x, y, tile_size=32):
        self.x = x  # world coordinates (float for smooth movement)
        self.y = y
        self.tile_size = tile_size
        self.speed = 140  # pixels per second
        
        # Load the player sprite from assets/map_sprites/player.png
        self.sprite = pygame.image.load('assets/map_sprites/player.png').convert_alpha()
        original_width, original_height = self.sprite.get_size()
        if original_width == 0:
            scale_height = tile_size
        else:
            scale_ratio = tile_size / original_width
            scale_height = max(1, int(round(original_height * scale_ratio)))

        self.width = tile_size
        self.height = scale_height
        self.sprite = pygame.transform.smoothscale(self.sprite, (self.width, self.height))
        
        # Movement state
        self.vel_x = 0
        self.vel_y = 0
    
    def set_movement(self, dx, dy):
        """Set movement direction (-1, 0, 1 for each axis)"""
        self.vel_x = dx
        self.vel_y = dy
    
    def update(self, dt, game_map):
        """Update player position with collision detection"""
        if self.vel_x == 0 and self.vel_y == 0:
            return
        
        # Calculate movement delta
        move_x = self.vel_x * self.speed * dt
        move_y = self.vel_y * self.speed * dt
        
        # Store original position
        original_x = self.x
        original_y = self.y
        
        # Try moving horizontally first
        if move_x != 0:
            new_x = self.x + move_x
            if self.can_move_to(new_x, self.y, game_map):
                self.x = new_x
        
        # Try moving vertically
        if move_y != 0:
            new_y = self.y + move_y
            if self.can_move_to(self.x, new_y, game_map):
                self.y = new_y
    
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
        self.screen_width = 1000
        self.screen_height = 800
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Pokemon-Style Map")
        
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