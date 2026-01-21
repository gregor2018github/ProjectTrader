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

            self.stamp_image = pygame.image.load(os.path.join(PICTURES_PATH, "contracts", "stamp.png"))
            if self.stamp_image:
                s_w, s_h = self.stamp_image.get_size()
                s_scale = 150 / s_w # target width 150
                self.stamp_image = pygame.transform.smoothscale(self.stamp_image, (int(s_w * s_scale), int(s_h * s_scale)))

        except Exception as e:
            print(f"Error loading contract images: {e}")
            self.stone_image = None
            self.cursor_quill = None
            self.stamp_image = None

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
        
        # Stamping and Fading state
        self.is_stamped = False
        self.stamp_timer = 0.0 # 3.0 (1s wait + 2s fade)
        self.global_alpha = 255

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

    def update(self, delta_time: float) -> None:
        if self.is_stamped:
            self.stamp_timer -= delta_time
            if self.stamp_timer <= 0:
                self.active = False
            elif self.stamp_timer < 2.0:
                # Fade out over 2 seconds
                self.global_alpha = int(255 * (self.stamp_timer / 2.0))

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        if self.is_stamped:
             return None # Block input during animation

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # Check buttons
                if self.btn_confirm.collidepoint(event.pos):
                    if not self.hit_signature_box:
                        self.game.state.warning = WarningMessage(self.screen, "You have to sign in the field!", self.game.font, self.game)
                        return None
                    # Start stamp and fade process
                    self.is_stamped = True
                    self.stamp_timer = 4.0
                    return None
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
        overlay.set_alpha(int(150 * (self.global_alpha / 255)))
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        # Create a temporary surface for the paper and its content to allow global fading
        paper_surf = pygame.Surface((self.paper_rect.width, self.paper_rect.height), pygame.SRCALPHA)
        
        # Local rect for drawing inside paper_surf
        local_paper_rect = pygame.Rect(0, 0, self.paper_rect.width, self.paper_rect.height)

        # Paper Background
        pygame.draw.rect(paper_surf, self.paper_color, local_paper_rect)
        # Outer Border
        pygame.draw.rect(paper_surf, (100, 80, 60), local_paper_rect, 3) 
        # Inner decorative border
        inner_rect = local_paper_rect.inflate(-20, -20)
        pygame.draw.rect(paper_surf, (100, 80, 60), inner_rect, 1)

        # Title
        if self.raw_text:
            title_text = self.raw_text[0].strip().replace('\ufeff', '')
            title_surf = self.title_font.render(title_text, True, (60, 40, 20))
            title_rect = title_surf.get_rect(centerx=local_paper_rect.centerx, top=local_paper_rect.top + 30)
            paper_surf.blit(title_surf, title_rect)
            
            # Line under title
            pygame.draw.line(paper_surf, (60, 40, 20), (local_paper_rect.left + 60, title_rect.bottom + 5), (local_paper_rect.right - 60, title_rect.bottom + 5), 2)

        # Image (Stone)
        if self.stone_image:
            img_rect = self.stone_image.get_rect()
            img_rect.topright = (local_paper_rect.right - 40, local_paper_rect.top + 90)
            paper_surf.blit(self.stone_image, img_rect)

        # Body Text
        y_offset_start = 120
        x_margin = 40
        line_height = 28
        
        if len(self.raw_text) > 1:
            full_body = "".join(self.raw_text[1:])
            full_body = full_body.replace('—', '-').replace('"', '"').replace('“', '"').replace('”', '"').replace('’', "'")
            
            # We already have lines split, but we used self.paper_rect.width which is fine
            # We'll just re-render them onto paper_surf
            # Note: handle_event split them using paper_rect.width, so they fit.
            # But the logic for split_text_to_lines in draw was a bit messy. 
            # I'll just re-use the local coordinates.
            
            # Simple re-rendering logic
            # For simplicity I'll re-calculate lines to ensure they fit the local surf
            # (Though they are usually the same)
            lines = self.split_text_to_lines(full_body, self.body_font, self.paper_rect.width, x_margin, y_offset_start, line_height, img_rect)
            
            y_offset = y_offset_start
            for line in lines:
                line = line.strip()
                if not line:
                     y_offset += 15
                     continue
                line_surf = self.body_font.render(line, True, BLACK)
                paper_surf.blit(line_surf, (x_margin, y_offset))
                y_offset += line_height

        # Signature Area
        local_sig_rect = pygame.Rect(
            (local_paper_rect.width - self.signature_rect.width) // 2,
            local_paper_rect.height - 160,
            self.signature_rect.width,
            self.signature_rect.height
        )
        pygame.draw.rect(paper_surf, (230, 220, 200), local_sig_rect)
        pygame.draw.rect(paper_surf, (150, 150, 150), local_sig_rect, 1)
        
        x_mark = self.body_font.render("X", True, BLACK)
        paper_surf.blit(x_mark, (local_sig_rect.x - 20, local_sig_rect.bottom - 30))

        # Signature content (already in local coords for paper_rect)
        paper_surf.blit(self.signature_surface, (0, 0))

        # Buttons
        mouse_pos = pygame.mouse.get_pos()
        # Translate mouse pos to local paper surf coords for hover check
        local_mouse_pos = (mouse_pos[0] - self.paper_rect.x, mouse_pos[1] - self.paper_rect.y)
        
        # Local button rects
        local_btn_confirm = pygame.Rect(self.btn_confirm.x - self.paper_rect.x, self.btn_confirm.y - self.paper_rect.y, self.btn_confirm.width, self.btn_confirm.height)
        local_btn_deny = pygame.Rect(self.btn_deny.x - self.paper_rect.x, self.btn_deny.y - self.paper_rect.y, self.btn_deny.width, self.btn_deny.height)

        # Confirm 
        confirm_hover = local_btn_confirm.collidepoint(local_mouse_pos) and not self.is_stamped
        confirm_color = BUY_BUTTON_HOVER if confirm_hover else BUY_BUTTON
        pygame.draw.rect(paper_surf, confirm_color, local_btn_confirm)
        pygame.draw.rect(paper_surf, BUY_BUTTON_BORDER, local_btn_confirm, 2)
        confirm_text = self.body_font.render("Confirm", True, BUTTON_TEXT)
        paper_surf.blit(confirm_text, confirm_text.get_rect(center=local_btn_confirm.center))
        
        # Deny
        deny_hover = local_btn_deny.collidepoint(local_mouse_pos) and not self.is_stamped
        deny_color = SELL_BUTTON_HOVER if deny_hover else SELL_BUTTON
        pygame.draw.rect(paper_surf, deny_color, local_btn_deny)
        pygame.draw.rect(paper_surf, SELL_BUTTON_BORDER, local_btn_deny, 2)
        deny_text = self.body_font.render("Deny", True, BUTTON_TEXT)
        paper_surf.blit(deny_text, deny_text.get_rect(center=local_btn_deny.center))

        # Stamp
        if self.is_stamped and self.stamp_image:
            stamp_rect = self.stamp_image.get_rect()
            # Position relatively but not completely at the right bottom
            stamp_rect.bottomright = (local_paper_rect.right - 60, local_paper_rect.bottom - 80)
            paper_surf.blit(self.stamp_image, stamp_rect)

        # Finally blit the paper surface with global alpha
        # Easiest way to fade a surface with transparency:
        # Create a surface with the alpha we want
        alpha_surf = pygame.Surface(paper_surf.get_size(), pygame.SRCALPHA)
        alpha_surf.fill((255, 255, 255, self.global_alpha))
        paper_surf.blit(alpha_surf, (0,0), special_flags=pygame.BLEND_RGBA_MULT)

        self.screen.blit(paper_surf, self.paper_rect)

    def draw_cursor(self) -> None:
        if self.cursor_quill and not self.is_stamped:
            mouse_pos = pygame.mouse.get_pos()
            # Offset so the tip is at the mouse position
            # Assuming the tip is at the bottom-left of the image
            # The quill usually leans right, so tip is bottom-left
            # We draw the image so its bottom-left is at mouse_pos
            rect = self.cursor_quill.get_rect()
            rect.bottomleft = mouse_pos
            self.screen.blit(self.cursor_quill, rect)
