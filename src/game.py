import pygame
import os
from .game_state import GameState
from .handlers.event_handler import EventHandler
from .ui.layout import draw_layout
from .ui.chart import draw_chart
from .models.good import Good
from .models.depot import Depot
from .config.colors import *
from .config.constants import PICTURES_PATH, FONTS_PATH, MAX_RECULCULATIONS_PER_SEC
from .ui.depot_view import draw_depot_view  # Add this import at the top
from .ui.menu import Menu  # Add to imports

class Game:
    def __init__(self):
        pygame.init()
        
        # Initialize screen first
        self.screen = pygame.display.set_mode((1536, 864))
        
        # Initialize basic components
        self.state = GameState()
        self.state.screen = self.screen  # Set screen reference in GameState
        self.state.game = self  # Add reference to self (Game instance)
        self.event_handler = EventHandler()
        self.clock = pygame.time.Clock()
        
        # Set up window properties
        pygame.display.set_caption("Merchant's Rise")
        icon = pygame.image.load(os.path.join(PICTURES_PATH, 'Icon.png'))
        pygame.display.set_icon(icon)
        
        # Initialize font
        self.font = pygame.font.Font(os.path.join(FONTS_PATH, "RomanAntique.ttf"), 24)
        self.state.font = self.font  # Set font reference in GameState
        self.chart_border = (50, self.screen.get_size()[1]-150)
        
        # Initialize goods
        self.goods = self._initialize_goods()
        
        # Initialize depot
        self.depot = Depot(money=100.0)
        
        # Load images
        self.images = self._load_images()
        
        self.update_delay = 1000 // MAX_RECULCULATIONS_PER_SEC  # milliseconds between updates
        self.last_update = 0
        
        self.menu = Menu(self.screen.get_width(), self.font)  # Add menu initialization

    def _initialize_goods(self):
        goods = []
        goods_data = [
            ("Wood", 1, 5000, PALE_BROWN, 0, True),
            ("Stone", 2, 2000, GRAY, 1, True),
            ("Iron", 5, 900, STEELE_BLUE, 2, True),
            ("Wool", 3, 2500, WHITE, 3, False),
            ("Hide", 4, 1000, DARK_GRAY, 4, False),
            ("Fish", 2, 5000, LIGHT_BLUE, 5, False),
            ("Wheat", 1, 5000, YELLOW, 6, False),
            ("Wine", 10, 500, RED, 7, False),
            ("Beer", 5, 500, PALE_BROWN, 8, False),
            ("Meat", 5, 800, ROSE, 9, False),
            ("Pottery", 3, 3500, DARK_ORANGE, 10, False),
            ("Linen", 3, 2000, WHITE, 11, False)
        ]
        
        for name, price, quantity, color, index, show in goods_data:
            goods.append(Good(name=name, price=price, market_quantity=quantity,
                            color=color, index=index, show_in_charts=show))
        return goods

    def _load_images(self):
        images = {'goods_30': {}}
        
        # Load money icon
        images['money_50'] = pygame.image.load(os.path.join(PICTURES_PATH, "money_50.png"))
        
        # Load all good icons
        for good in self.goods:
            img_path = os.path.join(PICTURES_PATH, f"{good.name.lower()}_30.png")
            images['goods_30'][good.name] = pygame.image.load(img_path)
            
        return images

    def run(self):
        running = True
        buttons = {}
        while running:
            self.clock.tick(60)
            current_time = pygame.time.get_ticks()
            
            if current_time - self.last_update >= self.update_delay:
                self.last_update = current_time
                day_changed = self.state.update()
                for good in self.goods:
                    good.update_price()
                # Only update wealth when the day changes
                if day_changed:
                    self.depot.update_wealth(self.goods)
                    self.depot.update_total_stock()
            
            if self.state.tick_counter % 4 == 0:
                # Draw base UI first
                buttons = draw_layout(self.screen, self.goods, self.depot, self.font, 
                                   self.state.date, self.state.input_fields, 
                                   self.state.mouse_clicked_on, self.images['money_50'], 
                                   self.images['goods_30'], self.state)
                   
                # Draw chart
                self.state.image_boxes = draw_chart(self.screen, self.font, self.chart_border, 
                                                  self.goods, self.images['goods_30'])
                
                # Draw depot view if state is active (for testing, always draw it)
                draw_depot_view(self.screen, self.font, self.depot, self.state)
                
                # Draw menu
                self.menu.draw(self.screen)
                
                # Draw dropdowns after everything else
                for dropdown in self.state.dropdowns.values():
                    if dropdown.is_open:  # Changed from checking active_dropdown
                        dropdown.draw(self.screen)
                                                
                # Draw message last if exists
                if self.state.message:
                    self._draw_message(self.state.message)
                    
                # Draw info window if active
                if self.state.info_window:
                    self.state.info_window.draw()
                    
                pygame.display.update()

            for event in pygame.event.get():
                running = self.event_handler.handle_events(event, self.state, 
                                                        self.goods, self.depot, buttons)

    def _draw_message(self, message):
        # Draw message in center of screen
        message_font = pygame.font.Font(None, 36)
        text = message_font.render(message, True, (255, 0, 0))
        text_rect = text.get_rect(center=(self.screen.get_width()/2, self.screen.get_height()/2))
        pygame.draw.rect(self.screen, (255, 255, 255), text_rect.inflate(20, 20))
        pygame.draw.rect(self.screen, (0, 0, 0), text_rect.inflate(20, 20), 2)
        self.screen.blit(text, text_rect)
