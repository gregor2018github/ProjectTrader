import pygame
import os
from typing import Optional, List, Tuple, TYPE_CHECKING
from ...config.colors import *
from ...config.constants import FONTS_PATH, PICTURES_PATH, MAIN_PATH, SCREEN_WIDTH, SCREEN_HEIGHT
from .warning_message import WarningMessage

if TYPE_CHECKING:
    from ...game import Game

class ContractView:
    def __init__(self, screen: pygame.Surface, game: 'Game', contract_file: str, image_file: str) -> None:
        self.screen = screen
        self.game = game
        self.active = True
        
        # Load Fonts
        try:
            self.title_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 42)
            self.body_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 22)
        except:
            # Fallback if fonts are missing (though user said they exist)
            self.title_font = pygame.font.SysFont("arial", 32)
            self.body_font = pygame.font.SysFont("arial", 18)

        # Load Text
        try:
            # Construct path to assets/texts/contracts
            text_path = os.path.join(MAIN_PATH, "assets", "texts", "contracts", contract_file)
            with open(text_path, 'r', encoding='utf-8') as f:
                self.raw_text = f.readlines()
        except FileNotFoundError:
            self.raw_text = ["Contract text not found."]

        # Load Images
        try:
            self.stone_image = pygame.image.load(os.path.join(PICTURES_PATH, "contracts", image_file))
            # Scale stone image if needed. Let's aim for a reasonable width, maybe 100px
            if self.stone_image:
                 # original scale factor logic
                 target_width = 100
                 orig_w, orig_h = self.stone_image.get_size()
                 scale_factor = target_width / orig_w
                 new_size = (int(orig_w * scale_factor), int(orig_h * scale_factor))
                 self.stone_image = pygame.transform.smoothscale(self.stone_image, new_size)

            self.cursor_quill = pygame.image.load(os.path.join(PICTURES_PATH, "contracts", "cursor_quill.png"))
            self.cursor_quill = self.cursor_quill.convert_alpha()
            # Scale cursor. It's huge. Let's make it more reasonable, maybe 60px high?
            orig_cw, orig_ch = self.cursor_quill.get_size()
            cursor_height = 80
            c_scale = cursor_height / orig_ch
            self.cursor_quill = pygame.transform.smoothscale(self.cursor_quill, (int(orig_cw * c_scale), int(orig_ch * c_scale)))

        except Exception as e:
            print(f"Error loading contract images: {e}")
            self.stone_image = None
            self.cursor_quill = None

        # Dimensions
        self.overlay_rect = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        
        # Paper dimensions
        paper_w = int(SCREEN_WIDTH * 0.5)
        paper_h = int(SCREEN_HEIGHT * 0.9)
        self.paper_rect = pygame.Rect((SCREEN_WIDTH - paper_w) // 2, (SCREEN_HEIGHT - paper_h) // 2, paper_w, paper_h)
        self.paper_color = (245, 235, 210) # Parchment color ish

        # Signature Area
        sig_w = int(paper_w * 0.8)
        sig_h = 100
        self.signature_rect = pygame.Rect(
            self.paper_rect.x + (paper_w - sig_w) // 2,
            self.paper_rect.bottom - 160, # Above buttons
            sig_w,
            sig_h
        )
        
        # Surface for signature (now covers the whole paper)
        self.signature_surface = pygame.Surface((self.paper_rect.width, self.paper_rect.height), pygame.SRCALPHA)
        self.is_signing = False
        self.last_pos = None
        self.hit_signature_box = False

        # Buttons
        btn_w = 120
        btn_h = 40
        spacing = 20
        start_x = self.paper_rect.centerx - btn_w - (spacing // 2)
        btn_y = self.paper_rect.bottom - 50
        
        self.btn_confirm = pygame.Rect(start_x, btn_y, btn_w, btn_h)
        self.btn_deny = pygame.Rect(start_x + btn_w + spacing, btn_y, btn_w, btn_h)

    def split_text_to_lines(self, text: str, font: pygame.font.Font, paper_w: int, x_margin: int, start_y: int, line_height: int, img_rect: Optional[pygame.Rect] = None) -> List[str]:
        # First handle explicit newlines
        raw_paragraphs = text.splitlines()
        final_lines = []
        current_y_offset = start_y
        
        for paragraph in raw_paragraphs:
            if not paragraph.strip():
                final_lines.append("") # Preserve empty lines
                current_y_offset += line_height
                continue
                
            words = paragraph.split(' ')
            current_line = []
            
            for word in words:
                # Calculate available width for this line based on image overlap
                available_width = paper_w - (x_margin * 2)
                # If image is on the right and we are within its vertical range
                if img_rect and (self.paper_rect.y + current_y_offset) < img_rect.bottom + 10:
                    available_width -= (img_rect.width + 20)

                current_line.append(word)
                # Check width
                w, h = font.size(' '.join(current_line))
                if w > available_width:
                    # Pop last word, add line, start new line with popped word
                    current_line.pop()
                    final_lines.append(' '.join(current_line))
                    current_line = [word]
                    current_y_offset += line_height
            
            if current_line:
                final_lines.append(' '.join(current_line))
                current_y_offset += line_height
        
        return final_lines

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # Check buttons
                if self.btn_confirm.collidepoint(event.pos):
                    if not self.hit_signature_box:
                        self.game.state.warning = WarningMessage(self.screen, "You have to sign in the field!", self.game.font, self.game)
                        return None
                    self.active = False
                    return "Confirm"
                elif self.btn_deny.collidepoint(event.pos):
                    self.active = False
                    return "Deny"
                
                # Start signing anywhere on paper
                if self.paper_rect.collidepoint(event.pos):
                    self.is_signing = True
                    # Translate to local surface coordinates
                    self.last_pos = (event.pos[0] - self.paper_rect.x, event.pos[1] - self.paper_rect.y)
                    # Check if starting stroke inside box
                    if self.signature_rect.collidepoint(event.pos):
                        self.hit_signature_box = True

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:
                self.is_signing = False
                self.last_pos = None

        elif event.type == pygame.MOUSEMOTION:
            if self.is_signing:
                if self.paper_rect.collidepoint(event.pos):
                    current_pos = (event.pos[0] - self.paper_rect.x, event.pos[1] - self.paper_rect.y)
                    if self.last_pos:
                        # Draw line on signature surface
                        pygame.draw.line(self.signature_surface, (0, 0, 0), self.last_pos, current_pos, 2)
                    self.last_pos = current_pos
                    
                    # Check if stroke passes through signature box
                    if self.signature_rect.collidepoint(event.pos):
                        self.hit_signature_box = True
                else:
                    # Mouse went out of paper bounds while signing
                    self.is_signing = False
                    self.last_pos = None
        
        return None

    def draw(self) -> None:
        # Darken background
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        overlay.set_alpha(150)
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        # Paper
        pygame.draw.rect(self.screen, self.paper_color, self.paper_rect)
        # Outer Border
        pygame.draw.rect(self.screen, (100, 80, 60), self.paper_rect, 3) 
        # Inner decorative border
        inner_rect = self.paper_rect.inflate(-20, -20)
        pygame.draw.rect(self.screen, (100, 80, 60), inner_rect, 1)

        # Title
        if self.raw_text:
            # Clean title text - remove BOM or other weird chars if present
            title_text = self.raw_text[0].strip().replace('\ufeff', '')
            title_surf = self.title_font.render(title_text, True, (60, 40, 20))
            title_rect = title_surf.get_rect(centerx=self.paper_rect.centerx, top=self.paper_rect.top + 30)
            self.screen.blit(title_surf, title_rect)
            
            # Line under title
            pygame.draw.line(self.screen, (60, 40, 20), (self.paper_rect.left + 60, title_rect.bottom + 5), (self.paper_rect.right - 60, title_rect.bottom + 5), 2)

        # Image (Stone) - Moved down slightly to avoid overlap
        if self.stone_image:
            img_rect = self.stone_image.get_rect()
            img_rect.topright = (self.paper_rect.right - 40, self.paper_rect.top + 90)
            self.screen.blit(self.stone_image, img_rect)

        # Body Text
        y_offset_start = 120
        x_margin = 40
        line_height = 28
        
        if len(self.raw_text) > 1:
            full_body = "".join(self.raw_text[1:]) # Join rest of lines
            
            # Clean up the text - replace placeholder boxes/unknown chars
            full_body = full_body.replace('—', '-').replace('"', '"').replace('“', '"').replace('”', '"').replace('’', "'")
            
            # Pass image rect to respect wrapping
            img_rect = None
            if self.stone_image:
                img_rect = self.stone_image.get_rect()
                img_rect.topright = (self.paper_rect.right - 40, self.paper_rect.top + 90)

            lines = self.split_text_to_lines(full_body, self.body_font, self.paper_rect.width, x_margin, y_offset_start, line_height, img_rect)
            
            y_offset = y_offset_start
            for line in lines:
                # Basic cleaner
                line = line.strip()
                if not line:
                     y_offset += 15 # smaller gap for empty lines
                     continue
                     
                line_surf = self.body_font.render(line, True, BLACK)
                current_y = self.paper_rect.y + y_offset
                
                # Render
                self.screen.blit(line_surf, (self.paper_rect.x + x_margin, current_y))
                y_offset += line_height

        # Signature Area
        # Draw dotted line or box
        pygame.draw.rect(self.screen, (230, 220, 200), self.signature_rect)
        pygame.draw.rect(self.screen, (150, 150, 150), self.signature_rect, 1) # Thin border
        
        # 'X' mark
        x_mark = self.body_font.render("X", True, BLACK)
        self.screen.blit(x_mark, (self.signature_rect.x - 20, self.signature_rect.bottom - 30))

        # Signature content
        self.screen.blit(self.signature_surface, self.paper_rect)

        # Buttons
        mouse_pos = pygame.mouse.get_pos()
        
        # Confirm (Buy style)
        confirm_hover = self.btn_confirm.collidepoint(mouse_pos)
        confirm_color = BUY_BUTTON_HOVER if confirm_hover else BUY_BUTTON
        pygame.draw.rect(self.screen, confirm_color, self.btn_confirm)
        pygame.draw.rect(self.screen, BUY_BUTTON_BORDER, self.btn_confirm, 2)
        confirm_text = self.body_font.render("Confirm", True, BUTTON_TEXT)
        self.screen.blit(confirm_text, confirm_text.get_rect(center=self.btn_confirm.center))
        
        # Deny (Sell style)
        deny_hover = self.btn_deny.collidepoint(mouse_pos)
        deny_color = SELL_BUTTON_HOVER if deny_hover else SELL_BUTTON
        pygame.draw.rect(self.screen, deny_color, self.btn_deny)
        pygame.draw.rect(self.screen, SELL_BUTTON_BORDER, self.btn_deny, 2)
        deny_text = self.body_font.render("Deny", True, BUTTON_TEXT)
        self.screen.blit(deny_text, deny_text.get_rect(center=self.btn_deny.center))

    def draw_cursor(self) -> None:
        if self.cursor_quill:
            mouse_pos = pygame.mouse.get_pos()
            # Offset so the tip is at the mouse position
            # Assuming the tip is at the bottom-left of the image
            # The quill usually leans right, so tip is bottom-left
            # We draw the image so its bottom-left is at mouse_pos
            rect = self.cursor_quill.get_rect()
            rect.bottomleft = mouse_pos
            self.screen.blit(self.cursor_quill, rect)
