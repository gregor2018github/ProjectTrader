"""Module for displaying and handling trade license contracts.

This module provides the ContractView class which displays a parchment-style 
contract that the player can sign, stamp, or tear up.
"""

import pygame
import os
import random
import math
from typing import Optional, List, Tuple, TYPE_CHECKING
from ...config.colors import *
from ...config.constants import FONTS_PATH, PICTURES_PATH, MAIN_PATH, SCREEN_WIDTH, SCREEN_HEIGHT, SIDEBAR_WIDTH
from .warning_message import WarningMessage

if TYPE_CHECKING:
    from ...game import Game

class ContractView:
    """A UI component that displays a license contract for trading specific goods.
    
    The contract allows the player to read terms, sign the document with a quill,
    and then either confirm (stamp) or deny (rip up) the agreement.
    """

    def __init__(self, screen: pygame.Surface, game: 'Game', contract_type: str, contract_months: int, contract_cost: int) -> None:
        """Initialize the contract view with specific terms.
        
        Args:
            screen: The main Pygame display surface.
            game: Reference to the main Game object.
            contract_type: The type of contract (e.g., 'Stone', 'Iron') which determines image and text files.
            contract_months: Duration of the contract in game months.
            contract_cost: Cost to acquire the license.
        """
        self.screen = screen
        self.game = game
        self.active = True
        self.finalized = False  # To prevent double-charging/logging
        self.contract_type = contract_type
        self.contract_months = contract_months
        self.contract_cost = contract_cost
        
        # Determine file names based on contract type
        # "Hide" is stored internally as "Hide" but its text assets use "Hides"
        file_type = "Hides" if contract_type == "Hide" else contract_type
        contract_file = f"License_{file_type}.txt"
        image_file = f"{file_type.lower()}.png"
        extra_file = f"License_{file_type}_Bottom.txt"

        # Load Fonts
        try:
            self.title_font = pygame.font.Font(os.path.join(FONTS_PATH, "Medici Text.ttf"), 42)
            self.body_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 22)
            # Create a larger font for the drop caps (first letter of paragraphs)
            self.drop_cap_font = pygame.font.Font(os.path.join(FONTS_PATH, "Augusta.ttf"), 38)
        except:
            # Fallback if fonts are missing
            self.title_font = pygame.font.SysFont("arial", 32)
            self.body_font = pygame.font.SysFont("arial", 18)
            self.drop_cap_font = pygame.font.SysFont("arial", 32)

        # Load Text
        try:
            # Construct path to assets/texts/contracts
            text_path = os.path.join(MAIN_PATH, "assets", "texts", "contracts", contract_file)
            with open(text_path, 'r', encoding='utf-8') as f:
                self.raw_text = f.readlines()
            
            # Replace placeholders in the loaded text
            placeholders = {
                "contract_months": contract_months,
                "contract_cost": contract_cost
            }
            for i, line in enumerate(self.raw_text):
                for key, value in placeholders.items():
                    placeholder_str = f"[$${key}$$]"
                    line = line.replace(placeholder_str, str(value))
                self.raw_text[i] = line
                
        except FileNotFoundError:
            self.raw_text = ["Contract text not found."]

        # Load extra signature acknowledgement text
        try:
            extra_text_path = os.path.join(MAIN_PATH, "assets", "texts", "contracts", extra_file)
            with open(extra_text_path, 'r', encoding='utf-8') as f:
                self.extra_text = f.read().strip()
        except FileNotFoundError:
            self.extra_text = ""

        # Load Images
        # 1. Essential UI Images
        try:
            self.cursor_quill = pygame.image.load(os.path.join(PICTURES_PATH, "contracts", "cursor_quill.png")).convert_alpha()
            orig_cw, orig_ch = self.cursor_quill.get_size()
            cursor_height = 80
            c_scale = cursor_height / orig_ch
            self.cursor_quill = pygame.transform.smoothscale(self.cursor_quill, (int(orig_cw * c_scale), int(orig_ch * c_scale)))
        except Exception as e:
            print(f"Error loading quill image: {e}")
            self.cursor_quill = None

        try:
            self.stamp_image = pygame.image.load(os.path.join(PICTURES_PATH, "contracts", "stamp.png")).convert_alpha()
            s_w, s_h = self.stamp_image.get_size()
            s_scale = 150 / s_w # target width 150
            self.stamp_image = pygame.transform.smoothscale(self.stamp_image, (int(s_w * s_scale), int(s_h * s_scale)))
        except Exception as e:
            print(f"Error loading stamp image: {e}")
            self.stamp_image = None

        # 2. Specific Contract Image
        try:
            self.contract_image = pygame.image.load(os.path.join(PICTURES_PATH, "contracts", image_file))
            # Scale contract image if needed. Let's aim for a reasonable width, maybe 100px
            if self.contract_image:
                 target_width = 100
                 orig_w, orig_h = self.contract_image.get_size()
                 scale_factor = target_width / orig_w
                 new_size = (int(orig_w * scale_factor), int(orig_h * scale_factor))
                 self.contract_image = pygame.transform.smoothscale(self.contract_image, new_size)
        except Exception as e:
            print(f"Contract specific image not found: {e}")
            self.contract_image = None

        # Dimensions
        self.total_width = SCREEN_WIDTH + SIDEBAR_WIDTH
        self.overlay_rect = pygame.Rect(0, 0, self.total_width, SCREEN_HEIGHT)
        
        # Paper dimensions
        paper_w = int(SCREEN_WIDTH * 0.5)
        paper_h = int(SCREEN_HEIGHT * 0.9)
        self.paper_rect = pygame.Rect((self.total_width - paper_w) // 2, (SCREEN_HEIGHT - paper_h) // 2, paper_w, paper_h)
        self.paper_color = (245, 235, 210) # Parchment color ish
        self.paper_texture = self._generate_paper_texture(paper_w, paper_h)

        # Signature Area
        sig_w = int(paper_w * 0.8)
        sig_h = 100
        self.signature_rect = pygame.Rect(
            self.paper_rect.x + (paper_w - sig_w) // 2,
            self.paper_rect.bottom - 230, # Above buttons
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
        self.is_denied = False
        self.stamp_timer = 0.0 # 3.0 (1s wait + 2s fade)
        self.global_alpha = 255
        self.shake_offset = [0, 0]

        self.scribble_channel = None
        self.last_motion_ticks = 0

        # Ripping animation state
        self.rip_pieces = [] # Stores (surface, pos, angle, velocity_x, velocity_y, rot_vel)
        self.rip_progress = 0.0

        # Adjust volume for scribble sounds - Pygame limits volume to 1.0, 
        # so for "louder" we'll ensure they are at max and potentially double-play.
        for i in range(1, 5):
            s_name = f"scribble_{i}"
            if s_name in self.game.sounds:
                self.game.sounds[s_name].set_volume(1.0)

        # Buttons
        btn_w = 120
        btn_h = 40
        spacing = 20
        start_x = self.paper_rect.centerx - btn_w - (spacing // 2)
        btn_y = self.paper_rect.bottom - 80
        
        self.btn_confirm = pygame.Rect(start_x, btn_y, btn_w, btn_h)
        self.btn_deny = pygame.Rect(start_x + btn_w + spacing, btn_y, btn_w, btn_h)

    def split_text_to_lines(self, text: str, font: pygame.font.Font, paper_w: int, x_margin: int, start_y: int, line_height: int, img_rect: Optional[pygame.Rect] = None, use_drop_caps: bool = True) -> List[Tuple[str, bool]]:
        """Split a long text string into lines that fit within the contract's width.
        
        Args:
            text: The full string to wrap.
            font: Pygame font for standard text.
            paper_w: Total width of the parchment surface.
            x_margin: Horizontal margin from the edge.
            start_y: Starting vertical position (used to check image overlap).
            line_height: Vertical spacing between lines.
            img_rect: Optional rectangle of an image that text should wrap around.
            use_drop_caps: If True, treats the first letter of paragraphs as large drop caps.
            
        Returns:
            A list of tuples (line_text, is_paragraph_start).
        """
        # First handle explicit newlines
        raw_paragraphs = text.splitlines()
        final_lines = [] # Now stores (text, is_paragraph_start)
        current_y_offset = start_y
        
        for paragraph in raw_paragraphs:
            if not paragraph.strip():
                final_lines.append(("", False)) # Preserve empty lines
                current_y_offset += 15 # Match the spacing used in draw()
                continue
                
            words = paragraph.split(' ')
            current_line = []
            is_start = True
            
            for word in words:
                # Calculate available width
                available_width = paper_w - (x_margin * 2)
                if img_rect and current_y_offset < img_rect.bottom + 10:
                    available_width -= (img_rect.width + 20)

                # Special handling for calculating width of the first line of a paragraph
                # because the drop cap is wider
                test_line = ' '.join(current_line + [word])
                if is_start and use_drop_caps:
                    if test_line.startswith("• "):
                        # Skip "• " and make the next character bigger
                        prefix = test_line[:2]
                        if len(test_line) > 2:
                            first_char = test_line[2]
                            rest = test_line[3:]
                            w = font.size(prefix)[0] + self.drop_cap_font.size(first_char)[0] + font.size(rest)[0]
                        else:
                            w = font.size(prefix)[0]
                    else:
                        # Width of the big first letter + the rest of the line
                        first_char = test_line[0]
                        rest = test_line[1:]
                        w = self.drop_cap_font.size(first_char)[0] + font.size(rest)[0]
                else:
                    w = font.size(test_line)[0]

                if w > available_width:
                    final_lines.append((' '.join(current_line), is_start))
                    current_line = [word]
                    current_y_offset += line_height
                    is_start = False # rest of lines in this paragraph are NOT starts
                else:
                    current_line.append(word)
            
            if current_line:
                final_lines.append((' '.join(current_line), is_start))
                current_y_offset += line_height
        
        return final_lines

    def _stop_scribble_sounds(self) -> None:
        """Stop all currently playing scribble sound variations."""
        for i in range(1, 5):
            s_name = f"scribble_{i}"
            if s_name in self.game.sounds:
                self.game.sounds[s_name].stop()
        self.scribble_channel = None

    def _finalize_contract(self) -> None:
        if self.finalized:
            return

        depot = self.game.depot
        state = self.game.state

        # Deduct the contract cost
        if depot.money >= self.contract_cost:
            depot.money -= self.contract_cost
            depot.expenditures += self.contract_cost
            depot.license_expenditures += self.contract_cost
        else:
            # Shouldn't happen — affordability is checked before opening
            state.show_warning("Not enough money!")
            return

        # Grant the trading license
        depot.stats.licenses_acquired += 1
        depot.add_license(self.contract_type, self.contract_months, state.date)
        state.log_event(
            "LICENSE",
            f"License acquired: {self.contract_type} ({self.contract_months} months)"
        )

        # Save a screenshot of the signed contract
        self._save_contract_image()
        self.finalized = True

    def _save_contract_image(self) -> None:
        """Render the paper content and save it as a JPEG in the contract_views folder."""
        paper_surf = pygame.Surface(
            (self.paper_rect.width, self.paper_rect.height), pygame.SRCALPHA
        )
        # Render without buttons for the screenshot
        self._render_paper_content(paper_surf, include_buttons=False)

        # Convert SRCALPHA surface to RGB for JPEG saving
        rgb_surf = pygame.Surface((self.paper_rect.width, self.paper_rect.height))
        rgb_surf.fill((255, 255, 255))  # white background
        rgb_surf.blit(paper_surf, (0, 0))

        # Ensure the output directory exists
        views_dir = os.path.join(PICTURES_PATH, "contracts", "contract_views")
        os.makedirs(views_dir, exist_ok=True)

        filename = f"contract_{self.contract_type.lower()}.jpg"
        filepath = os.path.join(views_dir, filename)
        pygame.image.save(rgb_surf, filepath)

    def update(self, delta_time: float) -> None:
        """Update animations, timers, and fading effects.
        
        Args:
            delta_time: Time elapsed since the last frame in seconds.
        """
        if self.is_stamped or self.is_denied:
            self.stamp_timer -= delta_time
            if self.stamp_timer <= 0:
                if self.is_stamped:
                    self._finalize_contract()
                self.active = False
            elif self.stamp_timer < 2.0:
                # Fade out over 2 seconds
                self.global_alpha = int(255 * (self.stamp_timer / 2.0))
            
            # Shake effect when stamped (only for first 0.1s after impact)
            if self.is_stamped and self.stamp_timer > 3.9:
                shake_intensity = 2
                self.shake_offset = [random.randint(-shake_intensity, shake_intensity), 
                                    random.randint(-shake_intensity, shake_intensity)]
            else:
                self.shake_offset = [0, 0]
        
        if self.is_denied and self.rip_pieces:
            # Update piece positions
            for i in range(len(self.rip_pieces)):
                surf, pos, angle, vx, vy, rv = self.rip_pieces[i]
                new_pos = (pos[0] + vx * delta_time, pos[1] + vy * delta_time)
                new_angle = angle + rv * delta_time
                # Add gravity-like effect
                new_vy = vy + 500 * delta_time
                self.rip_pieces[i] = (surf, new_pos, new_angle, vx, new_vy, rv)

        # Handle scribble sound stopping during idle motion while still signing
        if self.is_signing and self.scribble_channel and self.scribble_channel.get_busy():
            current_ticks = pygame.time.get_ticks()
            if current_ticks - self.last_motion_ticks > 150:
                self._stop_scribble_sounds()

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle mouse interactions for signing and clicking buttons.
        
        Args:
            event: The Pygame event to process.
            
        Returns:
            'Deny' if the player rips the contract, else None.
        """
        if self.is_stamped or self.is_denied:
             return None # Block input during animation

        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                # Check buttons
                if self.btn_confirm.collidepoint(event.pos):
                    if not self.hit_signature_box:
                        self.game.state.warning = WarningMessage(self.screen, "You have to sign in the field!", self.game.font, self.game)
                        return None
                    # Play stamp sound
                    self.game.play_sound("stamp")
                    # Start stamp and fade process
                    self.is_stamped = True
                    self.stamp_timer = 4.0
                    return None
                elif self.btn_deny.collidepoint(event.pos):
                    # Start fade out process immediately
                    self.is_denied = True
                    self.stamp_timer = 2.0
                    self.game.play_sound("rip_paper")
                    self._create_rip_pieces()
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
                self._stop_scribble_sounds()
                self.last_pos = None

        elif event.type == pygame.MOUSEMOTION:
            if self.is_signing:
                if self.paper_rect.collidepoint(event.pos):
                    self.last_motion_ticks = pygame.time.get_ticks()
                    
                    # Play scribble sound if not already playing
                    if not self.scribble_channel or not self.scribble_channel.get_busy():
                        sound_name = f"scribble_{random.randint(1, 4)}"
                        if sound_name in self.game.sounds:
                            # We play the sound on two channels simultaneously to 
                            # reach a volume level above the standard 1.0 limit.
                            self.scribble_channel = self.game.sounds[sound_name].play()
                            self.game.sounds[sound_name].play() 

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
                    self._stop_scribble_sounds()
                    self.last_pos = None
        
        return None

    def _create_rip_pieces(self) -> None:
        """Create the animation fragments when the contract is denied/ripped."""
        # Create a surface with the current full content of the paper
        full_paper = pygame.Surface((self.paper_rect.width, self.paper_rect.height), pygame.SRCALPHA)
        self._render_paper_content(full_paper)

        w, h = full_paper.get_size()
        center_x = w // 2
        
        # Generate jagged rip points
        points = [(center_x + random.randint(-15, 15), y) for y in range(0, h + 10, 15)]
        points[0] = (center_x + random.randint(-5, 5), 0)
        points[-1] = (center_x + random.randint(-5, 5), h)

        # Left piece
        left_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        poly_left = [(0, 0)] + points + [(0, h)]
        
        # We'll use a temp surface as a mask
        mask_left = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.polygon(mask_left, (255, 255, 255, 255), poly_left)
        left_surf.blit(full_paper, (0, 0))
        left_surf.blit(mask_left, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        # Right piece
        right_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        poly_right = [(w, 0)] + points + [(w, h)]
        mask_right = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.polygon(mask_right, (255, 255, 255, 255), poly_right)
        right_surf.blit(full_paper, (0, 0))
        right_surf.blit(mask_right, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        # Define physics for pieces
        # [surface, (x, y), angle, vx, vy, rot_vel]
        start_x, start_y = self.paper_rect.x, self.paper_rect.y
        self.rip_pieces = [
            [left_surf, [start_x, start_y], 0.0, -200.0, -100.0, -30.0], # Left piece moves left and rotates CCW
            [right_surf, [start_x, start_y], 0.0, 200.0, -150.0, 45.0]   # Right piece moves right and rotates CW
        ]

    def _generate_paper_texture(self, width: int, height: int) -> pygame.Surface:
        """Generates a parchment-like texture surface using procedural noise."""
        surface = pygame.Surface((width, height))
        # Slightly darker base for better contrast
        base_color = (240, 230, 205)
        surface.fill(base_color)
        
        # 1. Heavy Grain / Noise
        for _ in range(8000):
            x = random.randint(0, width)
            y = random.randint(0, height)
            radius = random.randint(1, 2)
            
            # Use a brownish/grey noise color
            # Much more contrast than before
            noise_color = (180, 170, 150)
            
            # Higher alpha for visibility
            alpha = random.randint(30, 80)
            
            temp_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(temp_surf, (*noise_color, alpha), (radius, radius), radius)
            surface.blit(temp_surf, (x - radius, y - radius))
            
        # 2. Larger "dirty" stains/blots
        for _ in range(25):
            x = random.randint(0, width)
            y = random.randint(0, height)
            w_blob = random.randint(40, 150)
            h_blob = random.randint(40, 150)
            
            # Irregular ellipses
            temp_surf = pygame.Surface((w_blob, h_blob), pygame.SRCALPHA)
            # Coffee-stain like brown
            pygame.draw.ellipse(temp_surf, (160, 140, 110, 15), (0, 0, w_blob, h_blob))
            surface.blit(temp_surf, (x - w_blob//2, y - h_blob//2))

        # 3. Simulate some random creases/fibers
        for _ in range(50):
            x1 = random.randint(0, width)
            y1 = random.randint(0, height)
            length = random.randint(10, 50)
            angle = random.uniform(0, 3.14159 * 2)
            x2 = x1 + int(length * math.cos(angle))
            y2 = y1 + int(length * math.sin(angle))
            
            # Dark thin lines for fibers
            color_fiber = (150, 140, 120, 100)
            
            # Draw line on temp surface for alpha
            min_x = min(x1, x2)
            min_y = min(y1, y2)
            w_line = abs(x2 - x1) + 4
            h_line = abs(y2 - y1) + 4
            
            if w_line > 0 and h_line > 0:
                temp_line = pygame.Surface((w_line, h_line), pygame.SRCALPHA)
                pygame.draw.aaline(
                    temp_line, 
                    color_fiber, 
                    (x1 - min_x + 2, y1 - min_y + 2), 
                    (x2 - min_x + 2, y2 - min_y + 2)
                )
                surface.blit(temp_line, (min_x - 2, min_y - 2))

        return surface

    def _render_paper_content(self, paper_surf: pygame.Surface, include_buttons: bool = True) -> None:
        """Drives the actual drawing of text and graphics onto the parchment surface.
        
        Args:
            paper_surf: The surface to draw the contract content upon.
            include_buttons: Whether to draw the Confirm/Deny buttons (False for screenshots).
        """
        local_paper_rect = pygame.Rect(0, 0, self.paper_rect.width, self.paper_rect.height)

        # Paper Background
        paper_surf.blit(self.paper_texture, (0, 0))
        
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

        # Image
        if self.contract_image:
            img_rect = self.contract_image.get_rect()
            img_rect.topright = (local_paper_rect.right - 60, local_paper_rect.top + 110)
            frame_rect = img_rect.inflate(10, 10)
            pygame.draw.rect(paper_surf, (100, 80, 60), frame_rect, 2)
            paper_surf.blit(self.contract_image, img_rect)

        # Body Text
        y_offset_start = 120
        x_margin = 40
        line_height = 28
        
        if len(self.raw_text) > 1:
            full_body = "".join(self.raw_text[1:])
            full_body = full_body.replace('—', '-').replace('"', '"').replace('“', '"').replace('”', '"').replace('’', "'")
            
            wrapping_img_rect = None
            if self.contract_image:
                wrapping_img_rect = self.contract_image.get_rect()
                wrapping_img_rect.topright = (local_paper_rect.right - 60, local_paper_rect.top + 110)
                wrapping_img_rect.width += 10 

            lines = self.split_text_to_lines(full_body, self.body_font, self.paper_rect.width, x_margin, y_offset_start, line_height, wrapping_img_rect)

            y_offset = y_offset_start
            for line_text, is_start in lines:
                line_text = line_text.strip()
                if not line_text:
                     y_offset += 15
                     continue
                
                if is_start and line_text:
                    if line_text.startswith("• "):
                        prefix = line_text[:2]
                        if len(line_text) > 2:
                            first_char = line_text[2]
                            rest = line_text[3:]
                            prefix_surf = self.body_font.render(prefix, True, BLACK)
                            char_surf = self.drop_cap_font.render(first_char, True, BLACK)
                            rest_surf = self.body_font.render(rest, True, BLACK)
                            paper_surf.blit(prefix_surf, (x_margin, y_offset))
                            p_width = prefix_surf.get_width()
                            paper_surf.blit(char_surf, (x_margin + p_width, y_offset - 8))
                            c_width = char_surf.get_width()
                            paper_surf.blit(rest_surf, (x_margin + p_width + c_width, y_offset))
                        else:
                            line_surf = self.body_font.render(line_text, True, BLACK)
                            paper_surf.blit(line_surf, (x_margin, y_offset))
                    else:
                        first_char = line_text[0]
                        rest = line_text[1:]
                        char_surf = self.drop_cap_font.render(first_char, True, BLACK)
                        rest_surf = self.body_font.render(rest, True, BLACK)
                        paper_surf.blit(char_surf, (x_margin, y_offset - 8))
                        char_width = char_surf.get_width()
                        paper_surf.blit(rest_surf, (x_margin + char_width, y_offset))
                else:
                    line_surf = self.body_font.render(line_text, True, BLACK)
                    paper_surf.blit(line_surf, (x_margin, y_offset))
                y_offset += line_height

        # Signature Area
        local_sig_rect = pygame.Rect(
            (local_paper_rect.width - self.signature_rect.width) // 2,
            local_paper_rect.height - 230, # Moved down as requested
            self.signature_rect.width,
            self.signature_rect.height
        )
        pygame.draw.rect(paper_surf, (230, 220, 200), local_sig_rect)
        pygame.draw.rect(paper_surf, (150, 150, 150), local_sig_rect, 1)
        x_mark = self.body_font.render("X", True, BLACK)
        paper_surf.blit(x_mark, (local_sig_rect.x - 20, local_sig_rect.bottom - 30))
        paper_surf.blit(self.signature_surface, (0, 0))

        # Extra clause about the signature Field
        if self.extra_text:
            extra_lines = self.split_text_to_lines(self.extra_text, self.body_font, local_paper_rect.width, 60, local_sig_rect.bottom + 10, 22, use_drop_caps=False)
            curr_y = local_sig_rect.bottom + 5
            for line_text, _ in extra_lines:
                text_surf = self.body_font.render(line_text, True, (60, 40, 20))
                text_rect = text_surf.get_rect(centerx=local_paper_rect.centerx, top=curr_y)
                paper_surf.blit(text_surf, text_rect)
                curr_y += 22

        if include_buttons:
            mouse_pos = pygame.mouse.get_pos()
            local_mouse_pos = (mouse_pos[0] - self.paper_rect.x, mouse_pos[1] - self.paper_rect.y)
            local_btn_confirm = pygame.Rect(self.btn_confirm.x - self.paper_rect.x, self.btn_confirm.y - self.paper_rect.y, self.btn_confirm.width, self.btn_confirm.height)
            local_btn_deny = pygame.Rect(self.btn_deny.x - self.paper_rect.x, self.btn_deny.y - self.paper_rect.y, self.btn_deny.width, self.btn_deny.height)

            confirm_hover = local_btn_confirm.collidepoint(local_mouse_pos) and not self.is_stamped and not self.is_denied
            confirm_color = BUY_BUTTON_HOVER if confirm_hover else BUY_BUTTON
            pygame.draw.rect(paper_surf, confirm_color, local_btn_confirm)
            pygame.draw.rect(paper_surf, BUY_BUTTON_BORDER, local_btn_confirm, 2)
            confirm_text = self.body_font.render("Confirm", True, BUTTON_TEXT)
            paper_surf.blit(confirm_text, confirm_text.get_rect(center=local_btn_confirm.center))
            
            # Deny
            deny_hover = local_btn_deny.collidepoint(local_mouse_pos) and not self.is_stamped and not self.is_denied
            deny_color = SELL_BUTTON_HOVER if deny_hover else SELL_BUTTON
            pygame.draw.rect(paper_surf, deny_color, local_btn_deny)
            pygame.draw.rect(paper_surf, SELL_BUTTON_BORDER, local_btn_deny, 2)
            deny_text = self.body_font.render("Deny", True, BUTTON_TEXT)
            paper_surf.blit(deny_text, deny_text.get_rect(center=local_btn_deny.center))

        if self.is_stamped and self.stamp_image:
            stamp_rect = self.stamp_image.get_rect()
            stamp_rect.bottomright = (local_paper_rect.right - 60, local_paper_rect.bottom - 100)
            paper_surf.blit(self.stamp_image, stamp_rect)

    def draw(self) -> None:
        """Draw the entire contract view, including background overlay and animations.
        
        This method handles the global transparency for fading effects and applies 
        the shake offset for impact animations.
        """
        # Darken background
        overlay = pygame.Surface((self.total_width, SCREEN_HEIGHT))
        overlay.set_alpha(int(150 * (self.global_alpha / 255)))
        overlay.fill((0, 0, 0))
        self.screen.blit(overlay, (0, 0))

        if self.is_denied and self.rip_pieces:
            # Draw ripping pieces
            for surf, pos, angle, vx, vy, rv in self.rip_pieces:
                # Apply alpha to piece
                temp_surf = surf.copy()
                alpha_surf = pygame.Surface(temp_surf.get_size(), pygame.SRCALPHA)
                alpha_surf.fill((255, 255, 255, self.global_alpha))
                temp_surf.blit(alpha_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                
                # Rotate
                rotated_surf = pygame.transform.rotate(temp_surf, angle)
                rotated_rect = rotated_surf.get_rect(topleft=pos)
                self.screen.blit(rotated_surf, rotated_rect)
            return

        # Create a temporary surface for the paper and its content to allow global fading
        paper_surf = pygame.Surface((self.paper_rect.width, self.paper_rect.height), pygame.SRCALPHA)
        self._render_paper_content(paper_surf)

        # Finally blit the paper surface with global alpha
        # Easiest way to fade a surface with transparency:
        # Create a surface with the alpha we want
        alpha_surf = pygame.Surface(paper_surf.get_size(), pygame.SRCALPHA)
        alpha_surf.fill((255, 255, 255, self.global_alpha))
        paper_surf.blit(alpha_surf, (0,0), special_flags=pygame.BLEND_RGBA_MULT)

        self.screen.blit(paper_surf, (self.paper_rect.x + self.shake_offset[0], self.paper_rect.y + self.shake_offset[1]))

    def draw_cursor(self) -> None:
        """Draw the custom quill cursor if the contract is active and not yet decided."""
        if self.cursor_quill and not self.is_stamped and not self.is_denied:
            mouse_pos = pygame.mouse.get_pos()
            # Offset so the tip is at the mouse position
            # Assuming the tip is at the bottom-left of the image
            # The quill usually leans right, so tip is bottom-left
            # We draw the image so its bottom-left is at mouse_pos
            rect = self.cursor_quill.get_rect()
            rect.bottomleft = mouse_pos
            self.screen.blit(self.cursor_quill, rect)
