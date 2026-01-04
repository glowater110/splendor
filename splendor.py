import pygame
import sys
import random
import traceback
import glob
import os
from itertools import combinations
from sb3_contrib import MaskablePPO
from game import Game
from classdef import Gem, Card, Player # Import Card for type hinting in UI
from client import Network

# --- Constants ---
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 60

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
DARK_GRAY = (100, 100, 100)
HOVER_COLOR = (220, 220, 220)
GREEN = (0, 200, 0)
RED_ERROR = (255, 0, 0)
BLUE_RESERVE = (0, 100, 255)

# Gem Colors
GEM_COLORS = {
    Gem.DIAMOND.value: (220, 220, 220), # White/Silver
    Gem.SAPPHIRE.value: (30, 144, 255), # Blue
    Gem.EMERALD.value: (46, 139, 87),   # Green
    Gem.RUBY.value: (220, 20, 60),      # Red
    Gem.ONYX.value: (50, 50, 50),       # Black
    Gem.GOLD.value: (255, 215, 0)       # Gold
}

class Button:
    def __init__(self, text, x, y, w, h, callback, color=GRAY, hover_color=HOVER_COLOR, font_size=30):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self.font = pygame.font.SysFont('Verdana', font_size)
        self.color = color
        self.hover_color = hover_color
        self.is_active = True

    def draw(self, screen):
        if not self.is_active:
            current_color = DARK_GRAY
        else:
            mouse_pos = pygame.mouse.get_pos()
            current_color = self.hover_color if self.rect.collidepoint(mouse_pos) else self.color
        
        pygame.draw.rect(screen, current_color, self.rect, border_radius=10)
        pygame.draw.rect(screen, BLACK, self.rect, 2, border_radius=10)
        
        text_surf = self.font.render(self.text, True, BLACK)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def check_click(self, event):
        if self.is_active and event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self.rect.collidepoint(event.pos):
                    self.callback()

class InputField:
    def __init__(self, x, y, w, h, label="", initial_text=""):
        self.rect = pygame.Rect(x, y, w, h)
        self.label = label
        self.text = initial_text
        self.active = False
        self.font = pygame.font.SysFont('Verdana', 24)
        self.label_font = pygame.font.SysFont('Verdana', 18, bold=True)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.active = True
            else:
                self.active = False
        if self.active and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                if len(self.text) < 20: # Limit length
                    self.text += event.unicode

    def draw(self, screen):
        # Draw Label
        label_surf = self.label_font.render(self.label, True, BLACK)
        screen.blit(label_surf, (self.rect.x, self.rect.y - 25))
        
        # Draw Box
        color = GREEN if self.active else BLACK
        pygame.draw.rect(screen, WHITE, self.rect)
        pygame.draw.rect(screen, color, self.rect, 2)
        
        # Draw Text
        text_surf = self.font.render(self.text, True, BLACK)
        screen.blit(text_surf, (self.rect.x + 10, self.rect.y + 5))

class SplendorApp:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Splendor Online")
        self.clock = pygame.time.Clock()
        self.state = "MENU"
        
        # Font Settings
        self.font_s = pygame.font.SysFont('Verdana', 14)
        self.font_m = pygame.font.SysFont('Verdana', 20)
        self.font_l = pygame.font.SysFont('Verdana', 30, bold=True)
        self.font_xl = pygame.font.SysFont('Verdana', 60, bold=True)
        self.font_card_pts = pygame.font.SysFont('Verdana', 20, bold=True)
        self.font_card_pts_large = pygame.font.SysFont('Verdana', 40, bold=True)
        self.font_card_gem = pygame.font.SysFont('Verdana', 10)
        self.font_card_gem_large = pygame.font.SysFont('Verdana', 20)
        self.font_player_turn = pygame.font.SysFont('Verdana', 18, bold=True)
        self.font_opponent_name = pygame.font.SysFont('Verdana', 18)

        center_x = SCREEN_WIDTH // 2 - 150
        start_y = 250
        gap = 100
        
        self.menu_buttons = [
            Button("AI vs AI (Watch)", center_x, start_y, 300, 80, self.goto_player_select_ai, font_size=25),
            Button("AI vs User (Play)", center_x, start_y + gap, 300, 80, self.goto_player_select_user, font_size=25),
            Button("Online (Multiplayer)", center_x, start_y + gap*2, 300, 80, self.start_online, font_size=25)
        ]
        
        self.selected_mode = None
        self.player_select_buttons = [
            Button("2 Players", center_x, start_y, 300, 80, lambda: self.finalize_player_count(2), font_size=25),
            Button("3 Players", center_x, start_y + gap, 300, 80, lambda: self.finalize_player_count(3), font_size=25),
            Button("4 Players", center_x, start_y + gap*2, 300, 80, lambda: self.finalize_player_count(4), font_size=25)
        ]
        
        self.ai_models = []
        self.selected_ai_model = None 
        self.ai_select_buttons = []
        self.temp_player_count = 4 
        
        self.game = None
        self.game_log = []
        
        self.pending_tokens = [0] * 6
        self.token_buttons = []
        
        self.confirm_button = Button("Confirm", SCREEN_WIDTH // 2 - 50, SCREEN_HEIGHT - 70, 100, 40, self.execute_token_action, color=GREEN, font_size=20)
        self.confirm_button.is_active = False
        self.cancel_button = Button("Reset", SCREEN_WIDTH // 2 + 70, SCREEN_HEIGHT - 70, 100, 40, self.clear_selected_tokens, color=RED_ERROR, font_size=20)
        self.cancel_button.is_active = False

        self.player_action_state = "IDLE"
        self.user_player_idx = 0
        
        self.ai_vs_ai_auto_play = True
        self.last_ai_move_time = 0
        
        self.selected_card_obj = None
        self.selected_card_tier = 0
        self.selected_card_idx_on_board = 0
        self.selected_reserved_card_idx = -1
        # Center of 1000px wide board area: 500. Rect width 480 -> x=260.
        self.popup_rect = pygame.Rect(260, 150, 480, 400)
        self.popup_buttons = []
        self.reserved_card_rects = []
        self.combos_3 = list(combinations(range(5), 3))
        self.loaded_model = None
        self.ai_agents = {}
        
        # Network Settings
        self.network = None
        self.online_name_input = InputField(center_x, 250, 300, 50, label="Your Name (ID):", initial_text="Player1")
        self.online_ip_input = InputField(center_x, 350, 300, 50, label="Server IP:", initial_text="0.tcp.jp.ngrok.io")
        self.online_port_input = InputField(center_x, 450, 300, 50, label="Port:", initial_text="12047")
        
        self.online_connect_button = Button("Connect", center_x, 550, 300, 80, self.try_connect, color=GREEN, font_size=20)
        self.online_back_button = Button("Back", center_x, 650, 300, 50, lambda: self.set_state("MENU"), color=GRAY, font_size=20)

    def set_state(self, new_state):
        self.state = new_state

    def scan_ai_models(self):
        self.ai_models = ["Random Bot"]
        for file in glob.glob("models/*.zip"):
            self.ai_models.append(os.path.basename(file))
            
    def log_action(self, text):
        self.game_log.append(text)
        if len(self.game_log) > 20:
            self.game_log.pop(0)

    def init_token_buttons(self):
        self.token_buttons = []
        bank_y_start = 50 
        btn_x = 90  
        
        for i in range(6):
            current_y = bank_y_start + i * 60
            if i == Gem.GOLD.value:
                self.token_buttons.append((None, None))
                continue
            
            p_btn = Button("+", btn_x, current_y - 12.5, 25, 25, lambda idx=i: self.adjust_token_count(idx, 1))
            p_btn.font = pygame.font.SysFont('Verdana', 18, bold=True)
            
            m_btn = Button("-", btn_x + 50, current_y - 12.5, 25, 25, lambda idx=i: self.adjust_token_count(idx, -1))
            m_btn.font = pygame.font.SysFont('Verdana', 18, bold=True)
            
            self.token_buttons.append((p_btn, m_btn))

    def load_model_by_name(self, name):
        if name == "Random Bot": return None
        try:
            print(f"Loading {name}...")
            return MaskablePPO.load(f"models/{name}")
        except Exception as e:
            print(f"Error loading {name}: {e}")
            return None

    def start_ai_vs_ai(self, p_count, models_list):
        print(f"Starting AI vs AI mode with {p_count} players...")
        self.state = "AI_VS_AI"
        self.game = Game(p_count=p_count)
        self.ai_agents = {}
        
        for i, p in enumerate(self.game.players):
            model_name = models_list[i]
            display_name = "Random" if model_name == "Random Bot" else os.path.splitext(model_name)[0]
            p.name = f"Bot {i+1} ({display_name})"
            self.ai_agents[i] = self.load_model_by_name(model_name)
            
        self.game_log = ["Game Started (AI vs AI)"]
        self.clear_selected_tokens()
        self.ai_vs_ai_auto_play = True
        self.last_ai_move_time = pygame.time.get_ticks()
        self.init_token_buttons()
        
    def start_ai_vs_user(self, p_count, models_list):
        print(f"Starting AI vs User mode with {p_count} players...")
        self.state = "AI_VS_USER"
        self.game = Game(p_count=p_count)
        self.ai_agents = {}
        
        # Randomize user seat
        self.user_player_idx = random.randint(0, p_count - 1)
        self.game.players[self.user_player_idx].name = "You"
        
        # Randomize AI seats
        ai_seats = [i for i in range(p_count) if i != self.user_player_idx]
        random.shuffle(models_list) # Shuffle models to randomize their positions
        
        for i, seat_idx in enumerate(ai_seats):
            model_name = models_list[i]
            display_name = "Random" if model_name == "Random Bot" else os.path.splitext(model_name)[0]
            p = self.game.players[seat_idx]
            p.name = f"Bot {seat_idx+1} ({display_name})"
            self.ai_agents[seat_idx] = self.load_model_by_name(model_name)
        
        self.game_log = [f"Game Started. You are Player {self.user_player_idx + 1}"]
        self.clear_selected_tokens()
        self.init_token_buttons()
        self.player_action_state = "IDLE"
        
        if self.game.curr_player_idx != self.user_player_idx:
            self.run_ai_turns_until_user()

    def start_online(self):
        print("Switching to Online Connection screen...")
        self.state = "ONLINE_CONNECT"

    def try_connect(self):
        name = self.online_name_input.text.strip()
        ip = self.online_ip_input.text.strip()
        try:
            port = int(self.online_port_input.text.strip())
        except:
            self.log_action("Invalid Port!")
            return

        if not name:
            self.log_action("Name cannot be empty!")
            return

        self.network = Network()
        welcome = self.network.connect(ip, port, name)
        
        if welcome:
            print(f"Connected! Server says: {welcome}")
            self.log_action(f"Connected to {ip}")
            # For now, just a placeholder transition
            self.state = "ONLINE_LOBBY"
        else:
            self.log_action("Connection Failed!")
            self.network = None

    def clear_selected_tokens(self):
        self.pending_tokens = [0] * 6
        self.confirm_button.is_active = False
        self.cancel_button.is_active = False
        if self.player_action_state == "SELECTING_TOKENS":
            self.player_action_state = "IDLE"

    def adjust_token_count(self, gem_idx, delta):
        if self.game.curr_player_idx != self.user_player_idx: return
        
        new_val = self.pending_tokens[gem_idx] + delta
        if new_val < 0: return
        if new_val > 2: return
        
        if delta > 0 and self.game.bank[gem_idx] < new_val:
            self.log_action(f"Not enough {Gem(gem_idx).name} tokens in bank!")
            return

        self.pending_tokens[gem_idx] = new_val
        self.validate_token_selection()

    def validate_token_selection(self):
        total_selected_count = sum(self.pending_tokens)
        
        if total_selected_count > 0:
            self.player_action_state = "SELECTING_TOKENS"
            self.cancel_button.is_active = True
        else:
            self.player_action_state = "IDLE"
            self.cancel_button.is_active = False
            self.confirm_button.is_active = False
            return

        is_valid = False
        if 2 in self.pending_tokens:
            if self.pending_tokens.count(2) == 1 and total_selected_count == 2:
                gem_idx_of_two = self.pending_tokens.index(2)
                if self.game.bank[gem_idx_of_two] >= 4:
                    is_valid = True
        elif total_selected_count == 3:
            if self.pending_tokens.count(1) == 3:
                is_valid = True
        
        self.confirm_button.is_active = is_valid

    def execute_token_action(self):
        if not self.confirm_button.is_active: return

        action = {'type': 'get_token', 'tokens': self.pending_tokens[:]}
        self.log_action(f"Player {self.game.get_curr_player().name} took tokens: {self.pending_tokens}")
        
        try:
            self.game.step(action)
            self.clear_selected_tokens()
            self.end_turn()
        except Exception as e:
            self.log_action(f"Error taking tokens: {e}")
            print(f"Error taking tokens: {e}")
            traceback.print_exc()
            self.clear_selected_tokens()

    def draw_text_with_outline(self, text, font, x, y, text_color, outline_color, outline_width=1):
        # Render outline (Iterate through a square grid to fill gaps)
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx == 0 and dy == 0: continue # Skip the center
                
                outline_surf = font.render(text, True, outline_color)
                outline_rect = outline_surf.get_rect(center=(x + dx, y + dy))
                self.screen.blit(outline_surf, outline_rect)
        
        # Render main text
        text_surf = font.render(text, True, text_color)
        text_rect = text_surf.get_rect(center=(x, y))
        self.screen.blit(text_surf, text_rect)
    # --- Drawing Functions ---

    def draw_token(self, x, y, gem_value, radius=15):
        color = GEM_COLORS.get(gem_value, BLACK)
        pygame.draw.circle(self.screen, color, (x, y), radius)
        pygame.draw.circle(self.screen, BLACK, (x, y), radius, 1)

    def draw_card(self, x, y, card: Card, highlight=False, scale=1.0):
        width = int(80 * scale)
        height = int(110 * scale)
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, WHITE, rect, border_radius=int(5*scale))
        
        if highlight:
            pygame.draw.rect(self.screen, BLUE_RESERVE, rect, int(4*scale), border_radius=int(5*scale))
        else:
            pygame.draw.rect(self.screen, BLACK, rect, int(2*scale), border_radius=int(5*scale))
        
        pts_font = self.font_card_pts if scale == 1.0 else self.font_card_pts_large
        gem_font = self.font_card_gem if scale == 1.0 else self.font_card_gem_large
        
        pts_surf = pts_font.render(str(card.points), True, BLACK)
        self.screen.blit(pts_surf, (x + 5*scale, y + 2*scale)) 

        gem_color = GEM_COLORS.get(card.gem.value, BLACK)
        bonus_center = (x + 65*scale, y + 15*scale)
        pygame.draw.circle(self.screen, gem_color, bonus_center, int(10*scale))
        pygame.draw.circle(self.screen, BLACK, bonus_center, int(10*scale), max(1, int(1*scale)))
        
        # Align costs to bottom
        type_of_gems = 0
        for c in card.cost:
            if c > 0:
                type_of_gems += 1
        
        start_cost_y = y + height - (type_of_gems * 18 * scale) + 5*scale
        for i, cost_val in enumerate(card.cost):
            if cost_val > 0:
                cost_color = GEM_COLORS.get(i, BLACK)
                cost_center = (x + 15*scale, start_cost_y)
                pygame.draw.circle(self.screen, cost_color, cost_center, int(8*scale))
                pygame.draw.circle(self.screen, BLACK, cost_center, int(8*scale), max(1, int(1*scale)))
                
                self.draw_text_with_outline(str(cost_val), gem_font, cost_center[0], cost_center[1]-1*scale, WHITE, BLACK, outline_width=max(1, int(1*scale)))
                
                start_cost_y += 18 * scale

    def draw_noble(self, x, y, tile):
        rect = pygame.Rect(x, y, 70, 70)
        pygame.draw.rect(self.screen, (240, 230, 140), rect, border_radius=5)
        pygame.draw.rect(self.screen, BLACK, rect, 2, border_radius=5)
        
        pts_surf = self.font_card_pts.render("3", True, BLACK)
        pts_rect = pts_surf.get_rect(midtop=(x + 12, y + 2))
        self.screen.blit(pts_surf, pts_rect)
        
        start_cost_x = x + 5
        for i, cost_val in enumerate(tile.cost):
            if cost_val > 0:
                cost_color = GEM_COLORS.get(i, BLACK)
                pygame.draw.rect(self.screen, cost_color, (start_cost_x, y+45, 15, 20))
                pygame.draw.rect(self.screen, BLACK, (start_cost_x, y+45, 15, 20), 1)
                
                self.draw_text_with_outline(str(cost_val), self.font_s, start_cost_x+7.5, y+55, WHITE, BLACK, outline_width=1)
                # cost_text = self.font_s.render(str(cost_val), True, BLACK)
                # text_rect = cost_text.get_rect(center=(start_cost_x + 7.5, y + 55))
                # self.screen.blit(cost_text, text_rect)
                start_cost_x += 17

    def draw_game_log(self):
        log_width = 280
        log_rect = pygame.Rect(SCREEN_WIDTH - log_width, 0, log_width, SCREEN_HEIGHT)
        pygame.draw.rect(self.screen, (30, 30, 30), log_rect)
        pygame.draw.line(self.screen, WHITE, (SCREEN_WIDTH - log_width, 0), (SCREEN_WIDTH - log_width, SCREEN_HEIGHT))
        
        title = self.font_m.render("Game Log", True, WHITE)
        self.screen.blit(title, (SCREEN_WIDTH - log_width + 20, 10))
        
        y = 50
        x_offset = SCREEN_WIDTH - log_width + 20
        max_width = log_width - 40
        
        for line in self.game_log:
            words = line.split(' ')
            current_line = []
            
            for word in words:
                test_line = ' '.join(current_line + [word])
                fw, fh = self.font_s.size(test_line)
                if fw < max_width:
                    current_line.append(word)
                else:
                    text_surf = self.font_s.render(' '.join(current_line), True, (200, 200, 200))
                    self.screen.blit(text_surf, (x_offset, y))
                    y += 20
                    current_line = [word]
            
            if current_line:
                text_surf = self.font_s.render(' '.join(current_line), True, (200, 200, 200))
                self.screen.blit(text_surf, (x_offset, y))
                y += 20
            
            y += 5 # Little extra spacing between separate log entries

    def draw_card_popup(self):
        if not (self.selected_card_obj or self.selected_card_tier): return 
        
        s = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        s.fill((0,0,0,128))
        self.screen.blit(s, (0,0))
        
        pygame.draw.rect(self.screen, WHITE, self.popup_rect, border_radius=10)
        pygame.draw.rect(self.screen, BLACK, self.popup_rect, 3, border_radius=10)
        
        if self.selected_card_obj:
            scale = 2.0
            card_w = 80 * scale
            card_x = self.popup_rect.centerx - card_w // 2
            card_y = self.popup_rect.top + 30
            self.draw_card(card_x, card_y, self.selected_card_obj, highlight=True, scale=scale) 
        else:
            deck_x = self.popup_rect.centerx - 40
            deck_y = self.popup_rect.top + 30
            deck_rect = pygame.Rect(deck_x, deck_y, 80, 110)
            color = (100, 50 + self.selected_card_tier*30, 50)
            pygame.draw.rect(self.screen, color, deck_rect, border_radius=5)
            pygame.draw.rect(self.screen, BLACK, deck_rect, 2, border_radius=5)
            text = self.font_m.render("?", True, WHITE)
            text_rect = text.get_rect(center=deck_rect.center)
            self.screen.blit(text, text_rect)
            
            info = self.font_s.render("Hidden Card", True, BLACK)
            info_rect = info.get_rect(midtop=(deck_rect.centerx, deck_rect.bottom + 10))
            self.screen.blit(info, info_rect)


        for btn in self.popup_buttons:
            btn.draw(self.screen)

    def draw_player_discounts(self, player:Player, x, y):
        # Draw 5 gem stacks showing discount counts
        discounts = player.card_gem() # Returns list [diamond_cnt, sapphire_cnt, ...]
        
        current_x = x
        for i in range(5): # 5 gem types (excluding gold)
            count = discounts[i]
            gem_color = GEM_COLORS.get(i, BLACK)
            
            # Card-like background
            rect = pygame.Rect(current_x, y, 40, 55)
            pygame.draw.rect(self.screen, WHITE, rect, border_radius=5)
            pygame.draw.rect(self.screen, BLACK, rect, 1, border_radius=5)
            
            # Gem Icon
            pygame.draw.circle(self.screen, gem_color, (current_x + 20, y + 20), 10)
            pygame.draw.circle(self.screen, BLACK, (current_x + 20, y + 20), 10, 1)
            
            # Count (Discount)
            self.draw_text_with_outline(str(count), self.font_m, current_x + 20, y + 40, BLACK, WHITE, 1)
            
            current_x += 45

    def draw_game_board(self):
        self.screen.fill((50, 150, 50)) 
        if not self.game: return

        # ... (Nobles, Cards, Bank drawing logic remains same) ...
        noble_x = 305 
        noble_y = 20
        for tile in self.game.tiles:
            self.draw_noble(noble_x, noble_y, tile)
            noble_x += 80

        start_x_cards_block = 375 
        start_y = 120
        for tier in [3, 2, 1]:
            # Deck Placeholder
            deck_x = start_x_cards_block - 100
            deck_rect = pygame.Rect(deck_x, start_y, 80, 110)
            
            # Set specific colors for each tier (darker shades)
            deck_color = GRAY # Default for unknown tier
            if tier == 1:
                deck_color = (0, 150, 0) # Darker Green
            elif tier == 2:
                deck_color = (200, 200, 0) # Darker Yellow
            elif tier == 3:
                deck_color = (0, 70, 200) # Darker Blue

            pygame.draw.rect(self.screen, deck_color, deck_rect, border_radius=5)
            pygame.draw.rect(self.screen, BLACK, deck_rect, 2, border_radius=5) 
            self.draw_text_with_outline(f'Lv{tier}', self.font_m, deck_rect.centerx, deck_rect.centery, WHITE, BLACK, 1)
            
            # Cards
            current_card_x = start_x_cards_block
            for card in self.game.board[tier]:
                self.draw_card(current_card_x, start_y, card)
                current_card_x += 90
            start_y += 120

        bank_x = 50
        bank_y_start = 50 
        btn_x = 90 
        for i in range(6): 
            current_y = bank_y_start + i * 60 
            gem_val = self.game.bank[i]
            self.draw_token(bank_x, current_y, i, radius=25)
            
            self.draw_text_with_outline(str(gem_val), self.font_l, bank_x, current_y, WHITE, BLACK, 2)
            
            if i < 5 and self.state == "AI_VS_USER" and self.game.curr_player_idx == self.user_player_idx and self.player_action_state != "DISCARDING_TOKENS":
                plus, minus = self.token_buttons[i]
                if plus and minus:
                    plus.draw(self.screen)
                    minus.draw(self.screen)
                    p_val = self.pending_tokens[i]
                    p_surf = self.font_m.render(str(p_val), True, BLACK)
                    p_rect = p_surf.get_rect(center=(btn_x + 37.5, current_y))
                    self.screen.blit(p_surf, p_rect)

        # 4. Draw Players (Right Side & Bottom)
        curr_p = self.game.get_curr_player()
        user_p = self.game.players[self.user_player_idx]
        
        # Bottom box shows USER info in AI_VS_USER, or CURRENT player in AI_VS_AI
        display_p = user_p if self.state == "AI_VS_USER" else curr_p
        
        player_box_x = 200 # Centered player info box
        # Increase height to fit discounts
        pygame.draw.rect(self.screen, (200, 200, 200), (player_box_x, 550, 600, 160), border_radius=10) 
        
        # User stats in bottom box
        if self.state == "AI_VS_USER":
            name_text = f"{user_p.name} ({user_p.points()} pts)"
        else:
            name_text = f"{curr_p.name} ({curr_p.points()} pts)"
            
        name_surf = self.font_player_turn.render(name_text, True, BLACK)
        self.screen.blit(name_surf, (player_box_x + 20, 560))
        
        # ... (Discounts, Tokens logic remains same) ...
        # [I will keep the existing logic here but I need to make sure I match the context]
        # Draw Discounts (Purchased Cards)
        self.draw_player_discounts(display_p, player_box_x + 20, 600)
        
        # Player Tokens (Moved down)
        p_tok_x = player_box_x + 35
        p_tok_y = 680 # Moved down
        for i in range(6):
            if display_p.tokens[i] > 0:
                highlight_discard = False
                if self.player_action_state == "DISCARDING_TOKENS" and display_p == curr_p:
                    highlight_discard = True

                self.draw_token(p_tok_x, p_tok_y, i, radius=15) 
                if highlight_discard:
                    pygame.draw.circle(self.screen, RED_ERROR, (p_tok_x, p_tok_y), 15, 2)

                tok_cnt = self.font_m.render(str(display_p.tokens[i]), True, BLACK)
                count_rect = tok_cnt.get_rect(midleft=(p_tok_x + 20, p_tok_y))
                self.screen.blit(tok_cnt, count_rect)
                p_tok_x += 50
        
        # Reserved Cards
        self.reserved_card_rects = [] 
        res_x = player_box_x + 350 
        res_y = 560
        res_label = self.font_m.render("Reserved:", True, BLACK)
        self.screen.blit(res_label, (res_x, res_y))
        for idx, card in enumerate(display_p.keeped):
            r_rect = pygame.Rect(res_x + 110, res_y, 40, 55)
            pygame.draw.rect(self.screen, WHITE, r_rect)
            pygame.draw.rect(self.screen, BLACK, r_rect, 1)
            g_c = GEM_COLORS.get(card.gem.value, BLACK)
            pygame.draw.circle(self.screen, g_c, (res_x+140, res_y+10), 5)
            self.reserved_card_rects.append((r_rect, card, idx)) 
            res_x += 45
        
        # Draw Turn indicator in top-right
        opp_right_align = SCREEN_WIDTH - 300 
        turn_text = f"Turn: {curr_p.name}"
        turn_surf = self.font_player_turn.render(turn_text, True, WHITE)
        turn_rect = turn_surf.get_rect(topright=(opp_right_align, 15))
        self.screen.blit(turn_surf, turn_rect)

        # Other Players...
        opp_y = 50
        
        # Decide who to show in the side list
        if self.state == "AI_VS_AI":
            # Show everyone
            players_to_show = self.game.players
        else:
            # AI_VS_USER: Show only the bots (not the user)
            players_to_show = [p for p in self.game.players if p != user_p]

        for p in players_to_show:
            # Highlight current turn player
            is_turn = (p == curr_p)
            name_color = GREEN if is_turn else WHITE
            
            # Opponent Name
            info_text = f"{p.name}: {p.points()}pts"
            info_surf = self.font_opponent_name.render(info_text, True, name_color)
            info_rect = info_surf.get_rect(topright=(opp_right_align, opp_y))
            self.screen.blit(info_surf, info_rect)
            
            # Opponent Reserved Cards Count
            res_text = f"Reserved: {len(p.keeped)}"
            res_surf = self.font_s.render(res_text, True, (200, 200, 200))
            res_rect = res_surf.get_rect(topright=(opp_right_align, opp_y + 25))
            self.screen.blit(res_surf, res_rect)

            # Opponent Tokens (Right Aligned)
            token_radius = 10
            # Calculate total width to determine start x
            active_tokens = [i for i in range(6) if p.tokens[i] > 0]
            total_tok_width = len(active_tokens) * 35
            
            opp_tok_x = opp_right_align - total_tok_width + 15 # Balanced offset
            opp_tok_y = opp_y + 50 + token_radius
            
            for i in range(6):
                if p.tokens[i] > 0:
                    self.draw_token(opp_tok_x, opp_tok_y, i, radius=token_radius)
                    tok_cnt = self.font_s.render(str(p.tokens[i]), True, WHITE)
                    tok_rect = tok_cnt.get_rect(midleft=(opp_tok_x + 12, opp_tok_y))
                    self.screen.blit(tok_cnt, tok_rect)
                    opp_tok_x += 35
            
            # Opponent Cards (Discounts) (Right Aligned)
            opp_card_y = opp_y + 75
            # 5 card types always shown, total width = 4 * 30 + 24 = 144
            opp_card_x = opp_right_align - 144 
            
            discounts = p.card_gem()
            for i in range(5):
                count = discounts[i]
                gem_color = GEM_COLORS.get(i, BLACK)
                
                # Mini Card Background
                rect = pygame.Rect(opp_card_x, opp_card_y, 24, 35)
                pygame.draw.rect(self.screen, WHITE, rect, border_radius=3)
                pygame.draw.rect(self.screen, BLACK, rect, 1, border_radius=3)
                
                # Gem Icon (Small)
                pygame.draw.circle(self.screen, gem_color, (opp_card_x + 12, opp_card_y + 12), 6)
                pygame.draw.circle(self.screen, BLACK, (opp_card_x + 12, opp_card_y + 12), 6, 1)
                
                # Count
                self.draw_text_with_outline(str(count), self.font_s, opp_card_x + 12, opp_card_y + 26, BLACK, WHITE, 1)
                
                opp_card_x += 30

            opp_y += 130
        
        # Buttons...
        confirm_btn_center_x = player_box_x + 370
        cancel_btn_center_x = player_box_x + 490
        self.confirm_button.rect.x = confirm_btn_center_x
        self.confirm_button.rect.y = 660 # Adjusted Y
        self.cancel_button.rect.x = cancel_btn_center_x
        self.cancel_button.rect.y = 660 # Adjusted Y
        self.confirm_button.draw(self.screen)
        self.cancel_button.draw(self.screen)

        if self.state == "AI_VS_AI":
            status_text = "PLAYING" if self.ai_vs_ai_auto_play else "PAUSED (SPACE)"
            status_surf = self.font_l.render(status_text, True, RED_ERROR)
            status_rect = status_surf.get_rect(midbottom=(500, 545))
            self.screen.blit(status_surf, status_rect)

        self.draw_game_log()
        
        if self.player_action_state == "DISCARDING_TOKENS":
            # ... logic ...
            pass
            
        if self.player_action_state == "SELECTING_CARD_ACTION":
            self.draw_card_popup()


    def draw_game_over(self):
        self.screen.fill(WHITE)
        
        winner = self.game.check_winner()
        winner_name = winner.name if winner else "Unknown"
        
        title_surf = self.font_xl.render("GAME OVER", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 50))
        self.screen.blit(title_surf, title_rect)
        
        winner_surf = self.font_l.render(f"Winner: {winner_name}", True, GREEN)
        winner_rect = winner_surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 20))
        self.screen.blit(winner_surf, winner_rect)
        
        msg_surf = self.font_m.render("Press any key to return to Menu", True, DARK_GRAY)
        msg_rect = msg_surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 80))
        self.screen.blit(msg_surf, msg_rect)

    def draw_menu(self):
        self.screen.fill(WHITE)
        title_surf = self.font_xl.render("SPLENDOR", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 150))
        self.screen.blit(title_surf, title_rect)
        for btn in self.menu_buttons:
            btn.draw(self.screen)

    def draw_online_connect(self):
        self.screen.fill(WHITE)
        title_surf = self.font_l.render("Online Connection", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 100))
        self.screen.blit(title_surf, title_rect)
        
        self.online_name_input.draw(self.screen)
        self.online_ip_input.draw(self.screen)
        self.online_port_input.draw(self.screen)
        self.online_connect_button.draw(self.screen)
        self.online_back_button.draw(self.screen)
        
        # Show recent log at bottom
        if self.game_log:
            log_text = self.game_log[-1]
            log_surf = self.font_m.render(log_text, True, RED_ERROR)
            log_rect = log_surf.get_rect(center=(SCREEN_WIDTH//2, 520))
            self.screen.blit(log_surf, log_rect)

    def draw_online_lobby(self):
        self.screen.fill(WHITE)
        title_surf = self.font_l.render(f"Lobby - Welcome, {self.online_name_input.text}", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 100))
        self.screen.blit(title_surf, title_rect)
        
        info = self.font_m.render("Server connection established. Lobby UI coming soon...", True, DARK_GRAY)
        self.screen.blit(info, (SCREEN_WIDTH//2 - 250, 300))
        
        back_btn = Button("DISCONNECT", SCREEN_WIDTH//2 - 150, 600, 300, 60, self.disconnect_network, color=RED_ERROR)
        back_btn.draw(self.screen)
        self.temp_back_btn = back_btn # Quick hack for click detection

    def disconnect_network(self):
        if self.network:
            self.network.disconnect()
            self.network = None
        self.state = "MENU"

    def draw_game_placeholder(self, mode_name):
        self.screen.fill(WHITE)
        font = pygame.font.SysFont('Verdana', 40)
        text = font.render(f"Mode: {mode_name} - (Coming Soon)", True, BLACK)
        self.screen.blit(text, (50, 50))
        small_font = pygame.font.SysFont('Verdana', 20)
        back_text = small_font.render("Press ESC to return to Menu", True, (100, 100, 100))
        self.screen.blit(back_text, (50, 100))

    def goto_player_select_ai(self):
        self.state = "PLAYER_SELECT"
        self.selected_mode = "AI_VS_AI"

    def goto_player_select_user(self):
        self.state = "PLAYER_SELECT"
        self.selected_mode = "AI_VS_USER"

    def finalize_player_count(self, p_count):
        self.temp_player_count = p_count
        self.scan_ai_models()
        
        btn_w_ai = 400
        btn_w_start = 300
        center_x_ai = SCREEN_WIDTH // 2 - btn_w_ai // 2
        center_x_start = SCREEN_WIDTH // 2 - btn_w_start // 2
        
        start_y = 150
        gap = 100
        
        self.ai_config_buttons = []
        
        # Determine number of AI slots
        num_ai = p_count if self.selected_mode == "AI_VS_AI" else p_count - 1
        
        for i in range(num_ai):
            label = f"Seat {i+1}" if self.selected_mode == "AI_VS_AI" else f"Opponent {i+1}"
            btn = Button(f"{label}: Random Bot", center_x_ai, start_y + i*gap, btn_w_ai, 80, lambda idx=i: self.cycle_ai_model(idx), font_size=20)
            btn.model_idx = 0 
            self.ai_config_buttons.append(btn)
            
        # Start Button
        start_btn_y = start_y + num_ai * gap + 20
        self.start_game_button = Button("START GAME", center_x_start, start_btn_y, btn_w_start, 80, self.confirm_ai_selection, color=GREEN, font_size=25)
            
        self.state = "AI_SELECT"

    def cycle_ai_model(self, btn_idx):
        btn = self.ai_config_buttons[btn_idx]
        # Increment index
        btn.model_idx = (btn.model_idx + 1) % len(self.ai_models)
        # Update text
        model_name = self.ai_models[btn.model_idx]
        prefix = f"Seat {btn_idx+1}" if self.selected_mode == "AI_VS_AI" else f"Opponent {btn_idx+1}"
        btn.text = f"{prefix}: {model_name}"

    def confirm_ai_selection(self):
        # Collect models
        selected_models_list = []
        for btn in self.ai_config_buttons:
            model_name = self.ai_models[btn.model_idx]
            selected_models_list.append(model_name)
            
        # Pre-load models (Cache them?)
        # We need to map Player Index -> Model.
        # But we don't know Player Indices for AI_VS_USER yet (user is random).
        # So we pass the list of models to the start function.
        
        if self.selected_mode == "AI_VS_AI":
            self.start_ai_vs_ai(self.temp_player_count, selected_models_list)
        elif self.selected_mode == "AI_VS_USER":
            self.start_ai_vs_user(self.temp_player_count, selected_models_list)

    def draw_ai_select(self):
        self.screen.fill(WHITE)
        title_surf = self.font_xl.render("Configure AI Players", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 80))
        self.screen.blit(title_surf, title_rect)
        
        for btn in self.ai_config_buttons:
            btn.draw(self.screen)
        
        self.start_game_button.draw(self.screen)

    def draw_player_select(self):
        self.screen.fill(WHITE)
        title_surf = self.font_xl.render("Select Players", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 150))
        self.screen.blit(title_surf, title_rect)
        for btn in self.player_select_buttons:
            btn.draw(self.screen)

    def handle_click(self, pos):
        if not self.game: return
        
        current_player_idx = self.game.curr_player_idx
        
        # In AI vs AI, we allow clicks only for viewing cards
        if self.state == "AI_VS_USER" and current_player_idx != self.user_player_idx:
            return

        if self.player_action_state == "SELECTING_CARD_ACTION":
            for btn in self.popup_buttons:
                btn.check_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'button':1, 'pos':pos}))
            return 

        # Non-gameplay clicks (Confirm/Reset) only for User Turn
        if self.state == "AI_VS_USER":
            self.confirm_button.check_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'button':1, 'pos':pos}))
            self.cancel_button.check_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'button':1, 'pos':pos}))

        if self.player_action_state in ["IDLE", "SELECTING_TOKENS"]:
            if self.state == "AI_VS_USER":
                for i in range(5): 
                    plus, minus = self.token_buttons[i]
                    if plus: plus.check_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'button':1, 'pos':pos}))
                    if minus: minus.check_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'button':1, 'pos':pos}))

        if self.player_action_state == "DISCARDING_TOKENS":
            # ... (Existing discard logic) ...
            p_tok_x = 235 
            p_tok_y = 680 
            for i in range(6):
                if self.game.get_curr_player().tokens[i] > 0:
                    dist = ((pos[0] - p_tok_x)**2 + (pos[1] - p_tok_y)**2)**0.5
                    if dist < 15: 
                        action = {'type': 'discard_token', 'gem_idx': i}
                        self.log_action(f"Player {self.game.get_curr_player().name} discards {Gem(i).name}")
                        self.game.step(action)
                        if self.game.get_curr_player().token_count() <= 10:
                            self.player_action_state = "IDLE" 
                            self.end_turn() 
                        return
                    p_tok_x += 50 
            return 

        if self.player_action_state == "IDLE":
            start_x_cards_block = 375
            start_y = 120
            for tier in [3, 2, 1]:
                # Deck click (Only for User)
                if self.state == "AI_VS_USER":
                    deck_x = start_x_cards_block - 100
                    deck_rect = pygame.Rect(deck_x, start_y, 80, 110)
                    if deck_rect.collidepoint(pos):
                        self.open_deck_reserve_popup(tier)
                        return

                # Card click
                current_card_x = start_x_cards_block
                for idx_in_board, card in enumerate(self.game.board[tier]):
                    card_rect = pygame.Rect(current_card_x, start_y, 80, 110)
                    if card_rect.collidepoint(pos):
                        if self.state == "AI_VS_USER":
                            self.open_card_popup(card, tier, idx_in_board)
                        else: # AI_VS_AI
                            self.open_view_only_popup(card)
                        return
                    current_card_x += 90
                start_y += 120
            
            # Reserved card click (Bottom box)
            for r_card_rect, card_obj, idx in self.reserved_card_rects:
                if r_card_rect.collidepoint(pos):
                    if self.state == "AI_VS_USER":
                        self.open_reserved_card_popup(card_obj, idx)
                    else: # AI_VS_AI
                        self.open_view_only_popup(card_obj)
                    return


    def open_view_only_popup(self, card: Card):
        self.selected_card_obj = card
        self.selected_card_tier = 0 
        self.player_action_state = "SELECTING_CARD_ACTION"
        
        close_btn = Button("Close", self.popup_rect.centerx - 50, self.popup_rect.bottom - 80, 100, 50, 
                            self.close_card_popup, color=GRAY, font_size=20)
        self.popup_buttons = [close_btn]

    def open_deck_reserve_popup(self, tier):
        if len(self.game.decks[tier]) == 0:
            self.log_action(f"Level {tier} Deck is empty!")
            return

        self.selected_card_tier = tier
        self.selected_card_obj = None 
        self.selected_reserved_card_idx = -1 
        self.player_action_state = "SELECTING_CARD_ACTION"
        
        player = self.game.get_curr_player()
        can_reserve = player.can_reserve_card()
        
        res_btn = Button(f"RESERVE Lv{tier}", self.popup_rect.centerx - 80, self.popup_rect.bottom - 80, 160, 50, 
                         self.confirm_reserve_deck, color=BLUE_RESERVE if can_reserve else GRAY)
        res_btn.is_active = can_reserve
        
        cancel_btn = Button("CANCEL", self.popup_rect.right - 130, self.popup_rect.bottom - 80, 100, 50, 
                            self.close_card_popup, color=RED_ERROR)
        
        self.popup_buttons = [res_btn, cancel_btn]

    def confirm_reserve_deck(self):
        tier = self.selected_card_tier
        player = self.game.get_curr_player()
        
        if player.can_reserve_card():
            try:
                action = {'type': 'reserve_deck', 'tier': tier}
                self.log_action(f"You reserved a hidden Level {tier} card.")
                self.game.step(action)
                self.close_card_popup()
                self.end_turn()
            except Exception as e:
                self.log_action(f"Error reserving from deck: {e}")
                print(f"Error reserving from deck: {e}")
                traceback.print_exc()
                self.close_card_popup()
        else:
            self.log_action("Cannot reserve more cards!")
            self.close_card_popup()

    def open_card_popup(self, card: Card, tier: int, idx_on_board: int):
        self.selected_card_obj = card
        self.selected_card_tier = tier
        self.selected_card_idx_on_board = idx_on_board
        self.selected_reserved_card_idx = -1 
        self.player_action_state = "SELECTING_CARD_ACTION"
        
        player = self.game.get_curr_player()
        
        can_buy = player.can_buy(card)
        buy_btn = Button("Buy", self.popup_rect.x + 50, self.popup_rect.bottom - 80, 100, 50, 
                         self.confirm_buy_card, color=GREEN if can_buy else GRAY, font_size=20)
        buy_btn.is_active = can_buy
        
        can_reserve = player.can_reserve_card() and (len(self.game.board[tier]) > idx_on_board) 
        res_btn = Button("Reserve", self.popup_rect.x + 190, self.popup_rect.bottom - 80, 120, 50, 
                         self.confirm_reserve_card_from_board, color=BLUE_RESERVE if can_reserve else GRAY, font_size=20) 
        res_btn.is_active = can_reserve
        
        cancel_btn = Button("Cancel", self.popup_rect.right - 130, self.popup_rect.bottom - 80, 100, 50, 
                            self.close_card_popup, color=RED_ERROR, font_size=20)
        cancel_btn.is_active = True 
        
        self.popup_buttons = [buy_btn, res_btn, cancel_btn]

    def open_reserved_card_popup(self, card: Card, reserved_idx: int):
        self.selected_card_obj = card
        self.selected_card_tier = 0 
        self.selected_card_idx_on_board = -1 
        self.selected_reserved_card_idx = reserved_idx 
        self.player_action_state = "SELECTING_CARD_ACTION"
        
        player = self.game.get_curr_player()
        
        can_buy = player.can_buy(card)
        buy_btn = Button("Buy", self.popup_rect.centerx - 100, self.popup_rect.bottom - 80, 100, 50, 
                         self.confirm_buy_reserved_card, color=GREEN if can_buy else GRAY, font_size=20)
        buy_btn.is_active = can_buy
        
        cancel_btn = Button("Cancel", self.popup_rect.centerx + 10, self.popup_rect.bottom - 80, 100, 50, 
                            self.close_card_popup, color=RED_ERROR, font_size=20)
        cancel_btn.is_active = True 
        
        self.popup_buttons = [buy_btn, cancel_btn]

    def close_card_popup(self):
        self.player_action_state = "IDLE"
        self.selected_card_obj = None
        self.selected_card_tier = 0
        self.selected_card_idx_on_board = 0
        self.selected_reserved_card_idx = -1
        self.popup_buttons = [] 
    
    def confirm_buy_card(self):
        if not self.selected_card_obj or not self.game: return
        player = self.game.get_curr_player()
        
        if player.can_buy(self.selected_card_obj):
            try:
                action = {
                    'type': 'buy_card',
                    'card': self.selected_card_obj,
                    'tier': self.selected_card_tier,
                }
                self.log_action(f"Player {player.name} bought a Level {self.selected_card_tier} card.")
                self.game.step(action)
                self.close_card_popup()
                self.end_turn()
            except ValueError:
                self.log_action("Error: Card not found on board!")
                self.close_card_popup() 
            except Exception as e:
                self.log_action(f"Error buying card: {e}")
                print(f"Error buying card: {e}")
                traceback.print_exc()
                self.close_card_popup()
        else:
            self.log_action("Cannot afford this card!") 
            self.close_card_popup() 


    def confirm_reserve_card_from_board(self): 
        if not self.selected_card_obj or not self.game: return
        player = self.game.get_curr_player()

        if player.can_reserve_card():
            try:
                action = {
                    'type': 'reserve_card',
                    'card': self.selected_card_obj,
                    'tier': self.selected_card_tier,
                }
                self.log_action(f"Player {player.name} reserved a Level {self.selected_card_tier} card.")
                self.game.step(action)
                self.close_card_popup()
                self.end_turn()
            except ValueError:
                self.log_action("Error: Card not found on board!")
                self.close_card_popup()
            except Exception as e:
                self.log_action(f"Error reserving card: {e}")
                print(f"Error reserving card: {e}")
                traceback.print_exc()
                self.close_card_popup()
        else:
            self.log_action("Cannot reserve more cards (max 3)!") 
            self.close_card_popup()

    def confirm_buy_reserved_card(self):
        if self.selected_reserved_card_idx == -1 or not self.game: return
        player = self.game.get_curr_player()
        
        reserved_card = player.keeped[self.selected_reserved_card_idx]

        if player.can_buy(reserved_card):
            try:
                action = {
                    'type': 'buy_reserved',
                    'card': reserved_card,
                    'reserved_idx': self.selected_reserved_card_idx 
                }
                self.log_action(f"Player {player.name} bought a reserved card.")
                self.game.step(action)
                self.close_card_popup()
                self.end_turn()
            except ValueError:
                self.log_action("Error: Reserved card not found!")
                self.close_card_popup()
            except Exception as e:
                self.log_action(f"Error buying reserved card: {e}")
                print(f"Error buying reserved card: {e}")
                traceback.print_exc()
                self.close_card_popup()
        else:
            self.log_action("Cannot afford this reserved card!") 
            self.close_card_popup()


    def run_ai_turns_until_user(self):
        while self.game.curr_player_idx != self.user_player_idx and not self.game.game_over:
            # Refresh screen to show current turn info
            self.draw_game_board()
            pygame.display.flip()
            pygame.event.pump()
            pygame.time.delay(1000)
            
            self.ai_execute_turn()
            
            # Check winner at end of round (when index wraps to 0)
            if self.game.curr_player_idx == 0:
                winner = self.game.check_winner()
                if winner:
                    self.log_action(f"Game Over! Winner is {winner.name}!")
                    self.state = "GAME_OVER"
                    break

    def end_turn(self):
        self.player_action_state = "IDLE"
        self.clear_selected_tokens() 
        self.confirm_button.is_active = False 

        player = self.game.get_curr_player()
        if player.token_count() > 10:
            self.log_action(f"Player {player.name} has too many tokens ({player.token_count()}). Must discard!")
            if self.game.curr_player_idx == self.user_player_idx: 
                self.player_action_state = "DISCARDING_TOKENS"
                return 
            else: 
                self.ai_discard_tokens()
                self.game.next_turn() 
                return

        winner = self.game.check_winner()
        if winner:
            self.log_action(f"Game Over! Winner is {winner.name}!")
            self.state = "MENU" 
            return

        # self.game.next_turn() # Removed redundant call
        self.log_action(f"It's {self.game.get_curr_player().name}'s turn.")

        if self.game.curr_player_idx != self.user_player_idx and not self.game.game_over:
            self.run_ai_turns_until_user() 

    def ai_execute_turn(self):
        p_idx = self.game.curr_player_idx
        player = self.game.players[p_idx]
        # self.log_action(f"{player.name} is thinking...") 

        action = None
        model = self.ai_agents.get(p_idx)
        
        if model:
            try:
                obs = self._get_obs_for_player(p_idx)
                mask = self._get_action_mask_for_player(p_idx)
                action_idx, _ = model.predict(obs, action_masks=mask, deterministic=False)
                action = self._map_action(int(action_idx), p_idx)
            except Exception as e:
                print(f"AI Prediction Error: {e}")
                action = None # Fallback to random

        if action is None:
            actions = self.game.get_valid_actions()
            if not actions:
                self.log_action(f"{player.name} has no valid moves. Skipping.")
                self.game.next_turn()
                return
            action = random.choice(actions)
        
        # Log based on action type
        at = action['type']
        if at == 'discard_token':
            self.log_action(f"{player.name} discards {Gem(action['gem_idx']).name}.")
        elif at == 'buy_card':
            self.log_action(f"{player.name} bought a card.")
        elif at == 'buy_reserved':
            self.log_action(f"{player.name} bought a reserved card.")
        elif at == 'get_token':
            self.log_action(f"{player.name} took tokens: {action['tokens']}.")
        elif at == 'reserve_card':
            self.log_action(f"{player.name} reserved a card.")
        elif at == 'reserve_deck':
            self.log_action(f"{player.name} reserved from deck.")
        else:
            self.log_action(f"{player.name} chose action: {at}")
        
        try:
            self.game.step(action)
        except Exception as e:
            self.log_action(f"AI Error: {e}")
            print(f"AI Error: {e}")
            traceback.print_exc()
            self.game.next_turn()
        
        if player.token_count() > 10:
            self.ai_discard_tokens()
    
    def ai_discard_tokens(self):
        player = self.game.get_curr_player()
        while player.token_count() > 10:
            discardable_gems = [i for i, count in enumerate(player.tokens[:5]) if count > 0] 
            if not discardable_gems: 
                discardable_gems = [i for i, count in enumerate(player.tokens) if count > 0]
            
            if discardable_gems:
                gem_to_discard = random.choice(discardable_gems)
                action = {'type': 'discard_token', 'gem_idx': gem_to_discard}
                self.log_action(f"AI {player.name} discards {Gem(gem_to_discard).name}")
                self.game.step(action)
            else:
                break
            
    def ai_move_step(self):
        if self.state != "AI_VS_AI": return
        
        winner = self.game.check_winner()
        if winner:
            self.log_action(f"Game Over! Winner is {winner.name}!")
            self.state = "GAME_OVER"
            return

        self.ai_execute_turn()

        winner = self.game.check_winner()
        if winner:
            self.log_action(f"Game Over! Winner is {winner.name}!")
            self.state = "GAME_OVER"

    def run(self):
        try:
            running = True
            while running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    
                    if self.state == "MENU":
                        for btn in self.menu_buttons:
                            btn.check_click(event)
                    
                    elif self.state == "ONLINE_CONNECT":
                        self.online_name_input.handle_event(event)
                        self.online_ip_input.handle_event(event)
                        self.online_port_input.handle_event(event)
                        self.online_connect_button.check_click(event)
                        self.online_back_button.check_click(event)
                    
                    elif self.state == "ONLINE_LOBBY":
                        if hasattr(self, 'temp_back_btn'):
                            self.temp_back_btn.check_click(event)

                    elif self.state == "AI_VS_USER":
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            if event.button == 1: 
                                self.handle_click(event.pos)
                        elif event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_ESCAPE:
                                self.state = "MENU"
                                self.game = None
                                self.clear_selected_tokens() 
                    
                    elif self.state == "GAME_OVER":
                        if event.type == pygame.KEYDOWN or event.type == pygame.MOUSEBUTTONDOWN:
                            self.state = "MENU"
                            self.game = None
                            self.clear_selected_tokens()

                    elif self.state == "PLAYER_SELECT":
                        for btn in self.player_select_buttons:
                            btn.check_click(event)

                    elif self.state == "AI_SELECT":
                        for btn in self.ai_config_buttons:
                            btn.check_click(event)
                        self.start_game_button.check_click(event)

                    elif self.state == "AI_VS_AI":
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            if event.button == 1:
                                self.handle_click(event.pos)
                        elif event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_ESCAPE:
                                self.state = "MENU"
                                self.game = None
                            elif event.key == pygame.K_SPACE:
                                self.ai_vs_ai_auto_play = not self.ai_vs_ai_auto_play
                                log_msg = "Auto-Play ON" if self.ai_vs_ai_auto_play else "Auto-Play PAUSED"
                                self.log_action(log_msg)
                            elif event.key == pygame.K_RIGHT:
                                if not self.ai_vs_ai_auto_play:
                                    self.ai_move_step()
                
                if self.state == "MENU":
                    self.draw_menu()
                elif self.state == "ONLINE_CONNECT":
                    self.draw_online_connect()
                elif self.state == "ONLINE_LOBBY":
                    self.draw_online_lobby()
                elif self.state == "AI_VS_USER":
                    self.draw_game_board()
                elif self.state == "GAME_OVER":
                    self.draw_game_over()
                elif self.state == "PLAYER_SELECT":
                    self.draw_player_select()
                elif self.state == "AI_SELECT":
                    self.draw_ai_select()
                elif self.state == "AI_VS_AI":
                    self.draw_game_board()
                    # Auto-play logic
                    if self.ai_vs_ai_auto_play:
                        now = pygame.time.get_ticks()
                        if now - self.last_ai_move_time > 1000: # 1 second delay
                            self.ai_move_step()
                            self.last_ai_move_time = now

                elif self.state == "ONLINE":
                    self.draw_game_placeholder("Online Multiplayer")
                    
                pygame.display.flip()
                self.clock.tick(FPS)
        except Exception as e:
            print(f"CRASH: {e}")
            traceback.print_exc()
        finally:
            pygame.quit()
            sys.exit()

    def _get_action_mask_for_player(self, p_idx):
        mask = [False] * 52
        p = self.game.players[p_idx]
        bank = self.game.bank
        
        # --- CASE A: MUST DISCARD (> 10 tokens) ---
        if p.token_count() > 10:
            for i in range(6):
                if p.tokens[i] > 0: mask[46 + i] = True
            return mask

        # --- CASE B: NORMAL TURN ---
        # 0-4: Take 2
        for i in range(5):
            if bank[i] >= 4: mask[i] = True
        # 5-14: Take 3
        for i, combo in enumerate(self.combos_3):
            if all(bank[c] > 0 for c in combo): mask[5 + i] = True
        # 15-26: Buy Board
        for i in range(12):
            tier, slot = (i // 4) + 1, i % 4
            if slot < len(self.game.board[tier]) and p.can_buy(self.game.board[tier][slot]):
                mask[15 + i] = True
        # 27-29: Buy Reserved
        for i in range(min(3, len(p.keeped))):
            if p.can_buy(p.keeped[i]): mask[27 + i] = True
        # 30-41: Reserve Board
        if p.can_reserve_card():
            for i in range(12):
                tier, slot = (i // 4) + 1, i % 4
                if slot < len(self.game.board[tier]): mask[30 + i] = True
        # 42-44: Reserve Deck
        if p.can_reserve_card():
            for i in range(3):
                if len(self.game.decks[i+1]) > 0: mask[42 + i] = True
        # 45: Pass
        mask[45] = True
        return mask

    def _map_action(self, idx, p_idx):
        p = self.game.players[p_idx]
        if 0 <= idx <= 4:
            t = [0]*6; t[idx] = 2
            return {'type': 'get_token', 'tokens': t}
        if 5 <= idx <= 14:
            t = [0]*6
            for c in self.combos_3[idx - 5]: t[c] = 1
            return {'type': 'get_token', 'tokens': t}
        if 15 <= idx <= 26:
            tier, slot = ((idx - 15) // 4) + 1, (idx - 15) % 4
            if slot < len(self.game.board[tier]):
                return {'type': 'buy_card', 'card': self.game.board[tier][slot], 'tier': tier}
        if 27 <= idx <= 29:
            slot = idx - 27
            if slot < len(p.keeped):
                return {'type': 'buy_reserved', 'card': p.keeped[slot]}
        if 30 <= idx <= 41:
            tier, slot = ((idx - 30) // 4) + 1, (idx - 30) % 4
            if slot < len(self.game.board[tier]):
                return {'type': 'reserve_card', 'card': self.game.board[tier][slot], 'tier': tier}
        if 42 <= idx <= 44:
            return {'type': 'reserve_deck', 'tier': idx - 41}
        if 46 <= idx <= 51:
            return {'type': 'discard_token', 'gem_idx': idx - 46}
        return {'type': 'do_nothing'}

    def _get_obs_for_player(self, p_idx):
        import numpy as np # Local import if needed
        obs = []
        obs.extend(self.game.bank) # 6
        
        # Board (84)
        for t in [1, 2, 3]: 
            for s in range(4):
                if s < len(self.game.board[t]):
                    c = self.game.board[t][s]
                    obs.extend(c.cost); obs.append(c.points); obs.append(c.gem.value)
                else: obs.extend([0]*7)
        
        # Subject Player (33)
        p = self.game.players[p_idx]
        obs.extend(p.tokens); obs.extend(p.card_gem()); obs.append(p.points())
        for i in range(3):
            if i < len(p.keeped):
                c = p.keeped[i]; obs.extend(c.cost); obs.append(c.points); obs.append(c.gem.value)
            else: obs.extend([0]*7)
            
        # Opponents (39) - We must rotate the view so "Opponent 1" is relative
        # E.g. if p_idx is 1, opponents are 2, 3, 0.
        num_p = len(self.game.players)
        for i in range(1, num_p):
            op_idx = (p_idx + i) % num_p
            op = self.game.players[op_idx]
            obs.extend(op.tokens); obs.extend(op.card_gem()); obs.append(op.points()); obs.append(len(op.keeped))
            
        # Nobles (25)
        for i in range(5):
            if i < len(self.game.tiles): obs.extend(self.game.tiles[i].cost)
            else: obs.extend([0]*5)
            
        obs.extend([0] * (250 - len(obs))) # Pad
        return np.array(obs, dtype=np.float32)

if __name__ == "__main__":
    app = SplendorApp()
    app.run()
