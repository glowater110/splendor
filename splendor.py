import pygame
import sys
import random
import traceback
import glob
import os
import json
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
    def __init__(self, text, x, y, w, h, callback, color=GRAY, hover_color=HOVER_COLOR, font_size=30, style="rect"):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.callback = callback
        self.font = pygame.font.SysFont('Verdana', font_size)
        self.color = color
        self.hover_color = hover_color
        self.is_active = True
        self.style = style # "rect" or "text"

    def draw(self, screen):
        if not self.is_active:
            current_color = DARK_GRAY
        else:
            mouse_pos = pygame.mouse.get_pos()
            current_color = self.hover_color if self.rect.collidepoint(mouse_pos) else self.color
        
        if self.style == "rect":
            pygame.draw.rect(screen, current_color, self.rect, border_radius=10)
            pygame.draw.rect(screen, BLACK, self.rect, 2, border_radius=10)
            text_color = BLACK
        else:
            # Text only style
            text_color = current_color
        
        text_surf = self.font.render(self.text, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)
        screen.blit(text_surf, text_rect)

    def check_click(self, event):
        if self.is_active and event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                if self.rect.collidepoint(event.pos):
                    self.callback()

class InputField:
    def __init__(self, x, y, w, h, label="", initial_text="", password_mode=False):
        self.rect = pygame.Rect(x, y, w, h)
        self.label = label
        self.text = initial_text
        self.active = False
        self.font = pygame.font.SysFont('Verdana', 24)
        self.label_font = pygame.font.SysFont('Verdana', 18, bold=True)
        self.password_mode = password_mode

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
        display_text = "*" * len(self.text) if self.password_mode else self.text
        text_surf = self.font.render(display_text, True, BLACK)
        screen.blit(text_surf, (self.rect.x + 10, self.rect.y + 5))

def deserialize_card(d):
    if not d: return None
    # Reconstruct Card object. Points, Gem(Enum), Cost
    return Card(d["points"], Gem(d["gem"]), d["cost"])

def update_game_from_state(game, state):
    game.turn_count = state["turn"]
    game.curr_player_idx = state["curr_player_idx"]
    game.bank = state["bank"]
    
    # Board
    game.board = {int(t): [deserialize_card(c) for c in cards] for t, cards in state["board"].items()}
    
    # Decks (Dummy fill)
    if "decks_counts" in state:
        for t, count in state["decks_counts"].items():
            game.decks[int(t)] = [None] * count 
    
    # Nobles
    from classdef import Tile
    game.tiles = [Tile(t_cost) for t_cost in state["nobles"]]
    
    # Players
    for i, p_data in enumerate(state["players"]):
        if i >= len(game.players): break 
        p = game.players[i]
        p.name = p_data["name"]
        p.tokens = p_data["tokens"]
        p.cards = [deserialize_card(c) for c in p_data["cards"]]
        p.keeped = [deserialize_card(c) for c in p_data["reserved"]]

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
        self.my_player_id = None
        # self.online_name_input = InputField(center_x, 250, 300, 50, label="Your Name (ID):", initial_text="Player1")
        self.online_ip_input = InputField(center_x, 250, 300, 50, label="Server IP:", initial_text="0.tcp.jp.ngrok.io")
        self.online_port_input = InputField(center_x, 350, 300, 50, label="Port:")
        
        self.online_connect_button = Button("CONNECT TO SERVER", center_x, 450, 300, 80, self.try_connect, color=GREEN, font_size=20)
        
        # Login/Register UI
        self.login_id_input = InputField(center_x, 250, 300, 50, label="ID:")
        self.login_pw_input = InputField(center_x, 350, 300, 50, label="Password:", password_mode=True)
        self.btn_do_login = Button("LOGIN", center_x, 450, 140, 60, self.req_login, color=GREEN, font_size=20)
        self.btn_do_register = Button("REGISTER", center_x + 160, 450, 140, 60, self.req_register, color=GRAY, font_size=20)
        
        # Lobby Variables
        self.room_name_input = InputField(SCREEN_WIDTH - 350, 200, 300, 50, label="New Room Name:", initial_text="My Room")
        
        # Max Player Select Buttons
        self.create_max_players = 4
        self.btn_mp_2 = Button("2P", SCREEN_WIDTH - 350, 280, 90, 50, lambda: self.set_create_mp(2), color=GRAY)
        self.btn_mp_3 = Button("3P", SCREEN_WIDTH - 245, 280, 90, 50, lambda: self.set_create_mp(3), color=GRAY)
        self.btn_mp_4 = Button("4P", SCREEN_WIDTH - 140, 280, 90, 50, lambda: self.set_create_mp(4), color=GREEN) # Default
        
        self.btn_create_room = Button("CREATE ROOM", SCREEN_WIDTH - 350, 350, 300, 60, self.req_create_room, color=BLUE_RESERVE)
        self.btn_refresh_rooms = Button("REFRESH", 50, 650, 200, 50, self.req_room_list, color=GRAY)
        
        self.lobby_rooms = [] # List of room dicts
        self.room_join_buttons = []
        self.last_room_fetch = 0
        
        self.is_host = False
        self.am_i_ready = False
        self.current_room_info = None
        self.btn_leave_room = Button("LEAVE ROOM", 50, 650, 200, 50, self.req_leave_room, color=RED_ERROR)
        self.btn_toggle_ready = Button("READY", 270, 650, 200, 50, self.req_toggle_ready, color=GRAY)
        self.btn_close_room = Button("DESTROY ROOM", 490, 650, 200, 50, lambda: self.set_state("CONFIRM_DESTROY"), color=(139, 0, 0))
        self.btn_start_online_game = Button("START GAME", SCREEN_WIDTH - 250, 650, 200, 50, self.check_start_game_condition, color=GRAY) # Disabled by default
        
        self.connection_msg = "" # Message from server or error status
        self.server_time_str = "--:--:--" # For connection test
        self.available_ai_models = ["Random Bot"] # Default list
        self.network_buffer = ""
        
        # Global Back Button (Text Style)
        self.btn_global_back = Button("< Back", 10, 10, 100, 40, self.go_back, color=BLACK, hover_color=GRAY, font_size=24, style="text")

    def set_create_mp(self, num):
        self.create_max_players = num
        self.btn_mp_2.color = GREEN if num == 2 else GRAY
        self.btn_mp_3.color = GREEN if num == 3 else GRAY
        self.btn_mp_4.color = GREEN if num == 4 else GRAY

    def set_state(self, new_state):
        self.state = new_state
        if new_state == "ONLINE_LOBBY":
            self.req_room_list()

    def go_back(self):
        if self.state in ["ONLINE_CONNECT", "PLAYER_SELECT", "AI_VS_USER", "AI_VS_AI"]:
            self.state = "MENU"
            self.game = None
        elif self.state == "ONLINE_LOGIN":
            self.disconnect_network() # Goes back to MENU (via disconnect)
            self.state = "ONLINE_CONNECT" # Override to CONNECT screen
        elif self.state == "AI_SELECT":
            self.state = "PLAYER_SELECT"
        elif self.state == "ONLINE_LOBBY":
            self.disconnect_network() # Goes to MENU
        elif self.state in ["ONLINE_ROOM", "ONLINE_GAME"]:
            self.req_leave_room() # Goes to ONLINE_LOBBY

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
        # print("Switching to Online Connection screen...")
        self.state = "ONLINE_CONNECT"

    def try_connect(self):
        ip = self.online_ip_input.text.strip()
        self.connection_msg = "" 
        try:
            port = int(self.online_port_input.text.strip())
        except:
            self.connection_msg = "Error: Invalid Port!"
            return

        self.network = Network()
        # Initial connection (no handshake name needed now)
        welcome_str = self.network.connect(ip, port)
        
        if welcome_str:
            # We don't care about welcome message content yet, server expects LOGIN
            print("Connected to server. Moving to Login.")
            self.state = "ONLINE_LOGIN"
        else:
            self.connection_msg = "Error: Connection Refused."
            self.network = None

    def req_login(self):
        uid = self.login_id_input.text.strip()
        upw = self.login_pw_input.text.strip()
        if not uid or not upw: return
        msg = {"type": "LOGIN", "username": uid, "password": upw}
        self.network.send(json.dumps(msg) + "\n")

    def req_register(self):
        uid = self.login_id_input.text.strip()
        upw = self.login_pw_input.text.strip()
        if not uid or not upw: return
        msg = {"type": "REGISTER", "username": uid, "password": upw}
        self.network.send(json.dumps(msg) + "\n")

    def clear_selected_tokens(self):
        self.pending_tokens = [0] * 6
        self.validate_token_selection() # Force update button to SKIP state
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
        
        # --- SKIP Logic ---
        if total_selected_count == 0:
            self.player_action_state = "IDLE"
            self.confirm_button.text = "Skip"
            self.confirm_button.color = (255, 140, 0) # Orange/Yellow warning
            self.confirm_button.is_active = True
            self.cancel_button.is_active = False
            return

        # --- Normal Selection Logic ---
        self.player_action_state = "SELECTING_TOKENS"
        self.confirm_button.text = "Confirm"
        self.confirm_button.color = GREEN
        self.cancel_button.is_active = True
        self.confirm_button.is_active = False # Default to false until proven valid

        # Rule 1: 2 Same Color
        if 2 in self.pending_tokens:
            if self.pending_tokens.count(2) == 1 and total_selected_count == 2:
                gem_idx_of_two = self.pending_tokens.index(2)
                if self.game.bank[gem_idx_of_two] >= 4:
                    self.confirm_button.is_active = True
            return # If you have a 2, you can't have anything else

        # Rule 2: 3 Different Colors (Standard)
        # Rule 3: < 3 Different Colors (If bank is depleted)
        if total_selected_count <= 3:
            # Check if all selected are 1 (distinct)
            if all(x <= 1 for x in self.pending_tokens):
                # Count how many distinct colors are available in the BANK
                available_colors_in_bank = sum(1 for x in self.game.bank[:5] if x > 0)
                
                # If we selected 3 distinct, it's valid.
                if total_selected_count == 3:
                    self.confirm_button.is_active = True
                
                # If we selected < 3, it's ONLY valid if we couldn't take more
                elif total_selected_count < 3:
                    # Logic: We took X tokens. Valid if X == available_colors_in_bank
                    # OR if we simply decided to take fewer? 
                    # Standard rule: "Player can take 3 distinct gems". It implies you *can* take fewer if you want?
                    # Actually, usually you must take 3 if available. But if only 2 types left, take 2.
                    # Let's allow taking N tokens if N == min(3, available_colors_in_bank)
                    
                    max_possible = min(3, available_colors_in_bank)
                    if total_selected_count == max_possible:
                        self.confirm_button.is_active = True
                    # Also allow if user just wants fewer? Some house rules allow it. 
                    # Let's stick to: Valid if total == max_possible.
                    
                    # BUT: What if user selects Blue+Green (2), but Red is also available?
                    # Strict rules say you must take Red too.
                    # Relaxed rules say okay.
                    # Let's Implement: Valid if total_selected == min(3, distinct_types_selected + available_unselected_types)
                    # Actually simpler: If total_selected == 3, good.
                    # If total_selected < 3, check if we *could* have taken more distinct ones.
                    
                    # Implementation for "Strict but Fair":
                    # You can take N distinct tokens only if you literally cannot take N+1 distinct tokens (because bank is empty or you hit 3).
                    
                    # Actually, to make it user friendly as requested: "user cannot take only less than 3 tokens ... even if there are only one or two kinds of token left."
                    # This implies the user SHOULD be allowed to take what is available.
                    
                    if total_selected_count == available_colors_in_bank:
                         self.confirm_button.is_active = True
                    elif total_selected_count < available_colors_in_bank and total_selected_count < 3:
                        # User took 2, but 3 were available. Strict rule says NO.
                        # User request says: "I want to make this possible to choose... even if there are only one or two kinds left"
                        # Wait, the prompt said: "now user CANNOT take... I want to make this POSSIBLE"
                        # So I should allow it.
                        self.confirm_button.is_active = True

    def req_game_action(self, action):
        # print(f"DEBUG: Sending GAME_ACTION: {action}")
        msg = {"type": "GAME_ACTION", "action": action}
        payload = json.dumps(msg) + "\n"
        self.network.send(payload)
        # We don't update local game immediately; wait for server update
        self.player_action_state = "IDLE"
        self.clear_selected_tokens()

    def execute_token_action(self):
        if not self.confirm_button.is_active: return

        # Handle Skip
        if self.confirm_button.text == "Skip":
            self.state = "CONFIRM_SKIP" # Transition to warning state
            return

        action = {'type': 'get_token', 'tokens': self.pending_tokens[:]}
        
        if self.state == "ONLINE_GAME":
            self.req_game_action(action)
            return

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

    def req_create_room(self):
        name = self.room_name_input.text.strip()
        if not name: return
        msg = {"type": "CREATE_ROOM", "name": name, "max_players": self.create_max_players}
        self.network.send(json.dumps(msg) + "\n")

    def req_join_room(self, rid):
        msg = {"type": "JOIN_ROOM", "room_id": rid}
        self.network.send(json.dumps(msg) + "\n")

    def req_toggle_ready(self):
        msg = {"type": "TOGGLE_READY"}
        self.network.send(json.dumps(msg) + "\n")

    def req_update_bot(self, seat_idx, current_model):
        # print(f"DEBUG: req_update_bot called for seat {seat_idx}, curr={current_model}")
        # print(f"DEBUG: Available models: {self.available_ai_models}")
        
        # Cycle to next model
        if not self.available_ai_models: return
        
        try:
            curr_idx = self.available_ai_models.index(current_model)
            next_idx = (curr_idx + 1) % len(self.available_ai_models)
        except ValueError:
            next_idx = 0
            
        new_model = self.available_ai_models[next_idx]
        # print(f"DEBUG: Requesting change to {new_model}")
        
        msg = {
            "type": "UPDATE_BOT_SETTINGS",
            "seat_idx": seat_idx,
            "model": new_model
        }
        self.network.send(json.dumps(msg) + "\n")

    def req_leave_room(self):
        msg = {"type": "LEAVE_ROOM"}
        self.network.send(json.dumps(msg) + "\n")
        self.set_state("ONLINE_LOBBY")
        self.current_room_info = None

    def req_close_room(self):
        # print("DEBUG: req_close_room called")
        msg = {"type": "CLOSE_ROOM"}
        self.network.send(json.dumps(msg) + "\n")
        # Wait for server ROOM_CLOSED message to transition

    def req_room_list(self):
        msg = {"type": "GET_ROOMS"}
        self.network.send(json.dumps(msg) + "\n")

    def check_start_game_condition(self):
        # print("DEBUG: check_start_game_condition called")
        # Check if room is full
        r = self.current_room_info
        connected_count = len(r.get("players", [])) # Assuming players list has connected IDs
        # print(f"DEBUG: connected={connected_count}, max={r['max_players']}")
        
        if connected_count < r['max_players']:
            # print("DEBUG: Opening Bot Popup")
            # Need to configure bots
            self.init_bot_selection_popup(connected_count, r['max_players'])
        else:
            # print("DEBUG: Starting immediately")
            # Full room, start immediately
            self.req_start_game()

    def init_bot_selection_popup(self, current_count, max_players):
        # print("DEBUG: Init Bot Popup")
        self.bot_select_buttons = []
        self.bot_settings_local = {} # seat_idx -> model_name
        
        start_y = SCREEN_WIDTH // 2 - 100 # Using X center for Y? Typo in thought, let's fix coords
        center_x = SCREEN_WIDTH // 2 - 200
        start_y = 200
        
        # Identify empty seats
        # Seat indices 0..current_count-1 are humans.
        # Bots are current_count..max_players-1.
        
        for i in range(current_count, max_players):
            # Default model
            self.bot_settings_local[i] = "Random Bot"
            
            btn = Button(f"Seat {i+1}: Random Bot", center_x, start_y, 400, 60, lambda idx=i: self.cycle_local_bot_model(idx))
            self.bot_select_buttons.append(btn)
            start_y += 80
            
        self.btn_confirm_bots = Button("CONFIRM & START", center_x, start_y + 20, 400, 60, self.confirm_bot_selection_and_start, color=GREEN)
        self.btn_cancel_bots = Button("CANCEL", center_x, start_y + 100, 400, 60, lambda: self.set_state("ONLINE_ROOM"), color=RED_ERROR)
        
        self.state = "BOT_SELECT_POPUP"

    def cycle_local_bot_model(self, seat_idx):
        # print(f"DEBUG: Cycling bot for seat {seat_idx}")
        # print(f"DEBUG: Available models: {self.available_ai_models}")
        
        if not self.available_ai_models: return
        
        current = self.bot_settings_local.get(seat_idx, "Random Bot")
        try:
            curr_idx = self.available_ai_models.index(current)
            next_idx = (curr_idx + 1) % len(self.available_ai_models)
        except:
            next_idx = 0
            
        new_model = self.available_ai_models[next_idx]
        self.bot_settings_local[seat_idx] = new_model
        # print(f"DEBUG: New model: {new_model}")
        
        # Update button text
        target_prefix = f"Seat {seat_idx+1}:"
        for btn in self.bot_select_buttons:
            if btn.text.startswith(target_prefix):
                btn.text = f"Seat {seat_idx+1}: {new_model}"
                break

    def confirm_bot_selection_and_start(self):
        # Send updates for all bots
        for seat_idx, model in self.bot_settings_local.items():
            msg = {
                "type": "UPDATE_BOT_SETTINGS",
                "seat_idx": seat_idx,
                "model": model
            }
            self.network.send(json.dumps(msg) + "\n")
            # We don't wait for response, assuming reliable TCP order
            
        # Then start
        self.req_start_game()

    def draw_bot_select_popup(self):
        self.draw_online_room() # Background
        s = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA); s.fill((0,0,0,200)); self.screen.blit(s, (0,0))
        
        title = self.font_xl.render("Configure Bots", True, WHITE)
        self.screen.blit(title, (SCREEN_WIDTH//2 - 150, 100))
        
        for btn in self.bot_select_buttons:
            btn.draw(self.screen)
            
        self.btn_confirm_bots.draw(self.screen)
        self.btn_cancel_bots.draw(self.screen)

    def req_start_game(self):
        msg = {"type": "START_GAME"}
        self.network.send(json.dumps(msg) + "\n")

    def handle_network_messages(self):
        if not self.network: return
        
        try:
            raw_data = self.network.receive()
            if not raw_data: return
            
            self.network_buffer += raw_data
            
            while "\n" in self.network_buffer:
                msg_str, self.network_buffer = self.network_buffer.split("\n", 1)
                if not msg_str.strip(): continue
                
                try:
                    data = json.loads(msg_str)
                    # print(f"DEBUG: Full Packet: {data}") 
                    msg_type = data.get("type")
                    # print(f"DEBUG: Client received {msg_type}")
                    
                    if msg_type == "ROOM_LIST":
                        self.lobby_rooms = data.get("rooms", [])
                        self.update_room_buttons()
                        
                    elif msg_type == "LOGIN_SUCCESS":
                        self.my_player_id = data.get("player_id")
                        self.connection_msg = data.get("message", "Logged in!")
                        if "ai_models" in data:
                            self.available_ai_models = data["ai_models"]
                        print(f"Logged in! ID: {self.my_player_id}")
                        self.set_state("ONLINE_LOBBY")
                        
                    elif msg_type == "REGISTER_SUCCESS":
                        self.connection_msg = "Success: " + data.get("message", "Registered!")
                        
                    elif msg_type == "ROOM_CREATED":
                        # I created a room, so I join it automatically
                        self.current_room_info = data.get("room")
                        self.is_host = (self.current_room_info["host"] == self.my_player_id)
                        self.am_i_ready = False
                        self.set_state("ONLINE_ROOM")
                        
                    elif msg_type == "JOINED_ROOM":
                        # I joined a room
                        self.current_room_info = data.get("room")
                        self.is_host = (self.current_room_info["host"] == self.my_player_id)
                        self.am_i_ready = False
                        self.set_state("ONLINE_ROOM")
                        
                    elif msg_type in ["PLAYER_JOINED", "PLAYER_LEFT", "ROOM_UPDATE"]:
                        if self.state == "ONLINE_ROOM":
                            self.current_room_info = data.get("room")
                            # Check local ready state consistency just in case
                            for p in self.current_room_info["player_details"]:
                                if p["id"] == self.my_player_id:
                                    self.am_i_ready = p["ready"]
                                    break
                            
                    elif msg_type == "READY_TOGGLED":
                        self.am_i_ready = data.get("state")

                    elif msg_type == "HOST_CHANGED":
                        new_host = data.get("new_host")
                        if self.state == "ONLINE_ROOM":
                            self.current_room_info["host"] = new_host
                            self.is_host = (new_host == self.my_player_id)
                            self.log_action(f"Host changed to {new_host}")

                    elif msg_type == "ROOM_CLOSED":
                        self.log_action(data.get("message", "Room closed."))
                        self.current_room_info = None
                        self.is_host = False
                        self.set_state("ONLINE_LOBBY")

                    elif msg_type == "GAME_STARTED":
                        self.log_action("Game is starting!")
                        self.game_log = [] # Clear previous log
                        self.set_state("ONLINE_GAME")
                        # Init local dummy game to hold state
                        if self.current_room_info:
                            self.game = Game(p_count=self.current_room_info["max_players"])
                        
                        self.init_token_buttons() # Initialize UI buttons for tokens

                    elif msg_type == "GAME_LOG":
                        self.log_action(data.get("message", ""))

                    elif msg_type == "GAME_OVER":
                        # print(f"DEBUG: GAME_OVER packet: {data}")
                        self.online_winner_name = data.get("winner", "Unknown")
                        self.log_action(f"Game Over! Winner: {self.online_winner_name}")
                        self.state = "GAME_OVER"

                    elif msg_type == "GAME_STATE_UPDATE":
                        if not self.game:
                            # Should have been created in GAME_STARTED, but safe fallback
                            # We guess max players from player list len if not avail?
                            p_len = len(data.get("state")["players"])
                            self.game = Game(p_count=p_len)
                        
                        update_game_from_state(self.game, data.get("state"))
                        
                        # Mapping logic if sent
                        if "your_seat_mapping" in data:
                            mapping = data["your_seat_mapping"]
                            # Key is string in JSON, convert to my_player_id
                            # But wait, my_player_id IS string.
                            if self.my_player_id in mapping:
                                self.user_player_idx = mapping[self.my_player_id]
                                # print(f"My Seat: {self.user_player_idx}")

                    elif msg_type == "ERROR":
                        self.log_action(f"Server Error: {data.get('message')}")
                        
                    elif msg_type == "TIME_UPDATE":
                        self.server_time_str = data.get("time")
                        
                except json.JSONDecodeError:
                    print(f"JSON Error in packet: {msg_str}")

        except Exception as e:
            print(f"Net Handle Error: {e}")
            import traceback
            traceback.print_exc()

    def update_room_buttons(self):
        self.room_join_buttons = []
        start_y = 150
        for room in self.lobby_rooms:
            label = f"{room['name']} ({len(room['players'])}/{room['max_players']})"
            # Status
            if room['started']: label += " [PLAYING]"
            
            btn = Button("JOIN " + label, 50, start_y, 400, 50, lambda rid=room['id']: self.req_join_room(rid))
            if room['started'] or len(room['players']) >= room['max_players']:
                btn.color = GRAY
                btn.is_active = False # Can't join full/started
            else:
                btn.color = GREEN
            
            self.room_join_buttons.append(btn)
            start_y += 60

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
            
            # Tier Colors
            if self.selected_card_tier == 1:
                color = (0, 150, 0) # Green
            elif self.selected_card_tier == 2:
                color = (200, 200, 0) # Yellow
            else:
                color = (0, 70, 200) # Blue
            
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
            
            if i < 5 and self.state in ["AI_VS_USER", "ONLINE_GAME"] and self.game.curr_player_idx == self.user_player_idx and self.player_action_state != "DISCARDING_TOKENS":
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
        
        # Bottom box shows USER info in AI_VS_USER/ONLINE_GAME, or CURRENT player in AI_VS_AI
        display_p = user_p if self.state in ["AI_VS_USER", "ONLINE_GAME"] else curr_p
        
        player_box_x = 200 # Centered player info box
        # Increase height to fit discounts
        pygame.draw.rect(self.screen, (200, 200, 200), (player_box_x, 550, 600, 160), border_radius=10) 
        
        # User stats in bottom box
        if self.state in ["AI_VS_USER", "ONLINE_GAME"]:
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
        
        winner_name = "Unknown"
        if self.online_winner_name:
            winner_name = self.online_winner_name
        else:
            winner = self.game.check_winner()
            winner_name = winner.name if winner else "Unknown"
        
        title_surf = self.font_xl.render("GAME OVER", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 - 50))
        self.screen.blit(title_surf, title_rect)
        
        winner_surf = self.font_l.render(f"Winner: {winner_name}", True, GREEN)
        winner_rect = winner_surf.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 20))
        self.screen.blit(winner_surf, winner_rect)
        
        # Button
        btn = Button("Return to Menu", SCREEN_WIDTH//2 - 150, SCREEN_HEIGHT//2 + 80, 300, 60, self.return_to_menu, color=GRAY)
        btn.draw(self.screen)
        self.game_over_button = btn

    def return_to_menu(self):
        if self.network and self.current_room_info:
            # Online Mode: Return to Lobby (Leave Room)
            self.req_leave_room()
        else:
            # Local Mode
            self.state = "MENU"
            self.game = None
        self.clear_selected_tokens()

    def draw_confirm_skip(self):
        # Draw game board in background (dimmed)
        if self.state == "ONLINE_GAME":
            self.draw_online_game()
        else:
            self.draw_game_board()
        
        # Dimming
        s = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        s.fill((0,0,0,150))
        self.screen.blit(s, (0,0))
        
        # Popup Box - Centered in GAME BOARD (Screen - Log Width)
        log_width = 280
        effective_center_x = (SCREEN_WIDTH - log_width) // 2
        
        rect = pygame.Rect(effective_center_x - 200, SCREEN_HEIGHT//2 - 100, 400, 200)
        pygame.draw.rect(self.screen, WHITE, rect, border_radius=10)
        pygame.draw.rect(self.screen, BLACK, rect, 3, border_radius=10)
        
        # Text
        msg = self.font_l.render("Skip Turn?", True, BLACK)
        msg_rect = msg.get_rect(center=(rect.centerx, rect.top + 50))
        self.screen.blit(msg, msg_rect)
        
        sub_msg = self.font_s.render("You will gain nothing this turn.", True, DARK_GRAY)
        sub_rect = sub_msg.get_rect(center=(rect.centerx, rect.top + 80))
        self.screen.blit(sub_msg, sub_rect)
        
        # Buttons
        btn_yes = Button("YES (Skip)", rect.x + 30, rect.bottom - 70, 150, 50, self.do_skip_turn, color=RED_ERROR, font_size=20)
        btn_no = Button("NO (Cancel)", rect.right - 180, rect.bottom - 70, 150, 50, self.cancel_skip_turn, color=GRAY, font_size=20)
        
        btn_yes.draw(self.screen)
        btn_no.draw(self.screen)
        
        self.skip_yes_btn = btn_yes
        self.skip_no_btn = btn_no

    def do_skip_turn(self):
        action = {'type': 'do_nothing'}
        
        if self.network and self.current_room_info:
            # Online Mode
            self.state = "ONLINE_GAME"
            self.req_game_action(action)
            return

        self.log_action(f"Player {self.game.get_curr_player().name} skipped turn.")
        self.game.step(action)
        self.player_action_state = "IDLE"
        self.state = "AI_VS_USER" 
        self.clear_selected_tokens()
        self.end_turn()

    def cancel_skip_turn(self):
        if self.network and self.current_room_info:
            self.state = "ONLINE_GAME"
        else:
            self.state = "AI_VS_USER"

    def draw_confirm_destroy(self):
        # Background
        self.draw_online_room()
        s = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA); s.fill((0,0,0,150)); self.screen.blit(s, (0,0))
        
        # Center on WHOLE SCREEN
        rect = pygame.Rect(SCREEN_WIDTH//2 - 200, SCREEN_HEIGHT//2 - 100, 400, 200)
        pygame.draw.rect(self.screen, WHITE, rect, border_radius=10)
        pygame.draw.rect(self.screen, BLACK, rect, 3, border_radius=10)
        
        self.screen.blit(self.font_l.render("Destroy Room?", True, BLACK), (rect.centerx-100, rect.top+30))
        self.screen.blit(self.font_s.render("All players will be kicked.", True, RED_ERROR), (rect.centerx-100, rect.top+80))
        
        self.destroy_yes_btn = Button("YES", rect.x+30, rect.bottom-70, 150, 50, self.req_close_room, color=RED_ERROR)
        self.destroy_no_btn = Button("NO", rect.right-180, rect.bottom-70, 150, 50, lambda: self.set_state("ONLINE_ROOM"), color=GRAY)
        
        self.destroy_yes_btn.draw(self.screen)
        self.destroy_no_btn.draw(self.screen)

    def draw_menu(self):
        self.screen.fill(WHITE)
        title_surf = self.font_xl.render("SPLENDOR", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 150))
        self.screen.blit(title_surf, title_rect)
        for btn in self.menu_buttons:
            btn.draw(self.screen)

    def draw_online_connect(self):
        self.screen.fill(WHITE)
        self.btn_global_back.draw(self.screen) # Back Button
        
        title_surf = self.font_l.render("Online Connection", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 100))
        self.screen.blit(title_surf, title_rect)
        
        # self.online_name_input.draw(self.screen)
        self.online_ip_input.draw(self.screen)
        self.online_port_input.draw(self.screen)
        self.online_connect_button.draw(self.screen)
        # self.online_back_button.draw(self.screen)
        
        # Show Error message prominently
        if self.connection_msg:
            color = RED_ERROR if self.connection_msg.startswith("Error") else GREEN
            log_surf = self.font_m.render(self.connection_msg, True, color)
            log_rect = log_surf.get_rect(center=(SCREEN_WIDTH//2, 550))
            self.screen.blit(log_surf, log_rect)

    def draw_online_login(self):
        self.screen.fill(WHITE)
        self.btn_global_back.draw(self.screen)
        
        title_surf = self.font_l.render("Authentication", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 100))
        self.screen.blit(title_surf, title_rect)
        
        self.login_id_input.draw(self.screen)
        self.login_pw_input.draw(self.screen)
        self.btn_do_login.draw(self.screen)
        self.btn_do_register.draw(self.screen)
        
        if self.connection_msg:
            color = RED_ERROR if self.connection_msg.startswith("Error") else GREEN
            log_surf = self.font_m.render(self.connection_msg, True, color)
            log_rect = log_surf.get_rect(center=(SCREEN_WIDTH//2, 550))
            self.screen.blit(log_surf, log_rect)

    def draw_online_lobby(self):
        self.screen.fill(WHITE)
        self.btn_global_back.draw(self.screen)
        
        title_surf = self.font_l.render(f"Lobby - ID: {self.my_player_id}", True, BLACK)
        self.screen.blit(title_surf, (150, 30)) # Shifted right
        
        # Connection Test (Time)
        time_surf = self.font_m.render(f"Server Time: {self.server_time_str}", True, BLUE_RESERVE)
        self.screen.blit(time_surf, (SCREEN_WIDTH - 250, 30))
        
        # Show Success Message from Server
        if self.connection_msg and not self.connection_msg.startswith("Error"):
            msg_surf = self.font_m.render(self.connection_msg, True, GREEN)
            self.screen.blit(msg_surf, (50, 70))
        
        # Room List Area
        pygame.draw.rect(self.screen, (240, 240, 240), (40, 100, 420, 530))
        pygame.draw.rect(self.screen, BLACK, (40, 100, 420, 530), 2)
        
        if not self.room_join_buttons:
            info = self.font_m.render("No rooms found...", True, DARK_GRAY)
            self.screen.blit(info, (100, 150))
            
        for btn in self.room_join_buttons:
            btn.draw(self.screen)
            
        # Create Room Area (Right Side)
        pygame.draw.rect(self.screen, (230, 230, 250), (SCREEN_WIDTH - 400, 100, 350, 300))
        pygame.draw.rect(self.screen, BLACK, (SCREEN_WIDTH - 400, 100, 350, 300), 2)
        
        lbl = self.font_m.render("Create New Room", True, BLACK)
        self.screen.blit(lbl, (SCREEN_WIDTH - 350, 120))
        
        self.room_name_input.draw(self.screen)
        
        # Max Player Buttons
        self.btn_mp_2.draw(self.screen)
        self.btn_mp_3.draw(self.screen)
        self.btn_mp_4.draw(self.screen)
        
        self.btn_create_room.draw(self.screen)
        self.btn_refresh_rooms.draw(self.screen)
        
        back_btn = Button("Disconnect", SCREEN_WIDTH - 250, 650, 200, 50, self.disconnect_network, color=RED_ERROR)
        back_btn.draw(self.screen)
        self.temp_back_btn = back_btn 

    def draw_online_room(self):
        self.screen.fill(WHITE)
        self.btn_global_back.draw(self.screen)
        
        if not self.current_room_info: return
        
        r = self.current_room_info
        title = f"Room: {r['name']} ({len(r['players'])}/{r['max_players']})"
        t_surf = self.font_xl.render(title, True, BLACK)
        t_rect = t_surf.get_rect(center=(SCREEN_WIDTH//2, 80))
        self.screen.blit(t_surf, t_rect)
        
        # Player List
        y = 200
        all_ready = True
        self.bot_config_buttons = [] # Reset per frame for immediate mode check
        
        # Use player_details list for status
        p_details = r.get("player_details", [])
        
        # Draw connected players and bots
        for i, p_data in enumerate(p_details):
            pid = p_data["id"]
            name = p_data["name"]
            is_ready = p_data["ready"]
            is_bot = p_data.get("is_bot", False)
            
            if not is_ready: all_ready = False
            
            role = "HOST" if pid == r['host'] else "PLAYER"
            color = GREEN if pid == self.my_player_id else BLACK
            
            status_text = "[READY]" if is_ready else "[WAITING]"
            status_color = GREEN if is_ready else RED_ERROR
            
            # If it's a Bot and I am Host, allow configuration
            if is_bot and self.is_host:
                model_name = p_data.get("model", "Random Bot")
                btn_txt = f"{name}: {model_name} (Click to Change)"
                # Seat index is 'i' (0-based index in the player list... wait, player_details might be sparse? 
                # No, to_dict fills it in order: humans then bots)
                # Correct seat index is 'i'.
                
                # Draw button instead of text
                btn = Button(btn_txt, SCREEN_WIDTH//2 - 200, y, 400, 40, lambda idx=i, m=model_name: self.req_update_bot(idx, m), color=GRAY, font_size=18)
                btn.draw(self.screen)
                self.bot_config_buttons.append(btn)
            else:
                # Normal Text Display
                p_text = f"{i+1}. {name} [{role}]"
                if is_bot: p_text += f" ({p_data.get('model', 'Random')})"
                
                p_surf = self.font_l.render(p_text, True, color)
                self.screen.blit(p_surf, (SCREEN_WIDTH//2 - 200, y))
                
                s_surf = self.font_l.render(status_text, True, status_color)
                self.screen.blit(s_surf, (SCREEN_WIDTH//2 + 100, y))
            
            y += 50
            
        self.btn_leave_room.draw(self.screen)
        
        # Update Ready Button
        self.btn_toggle_ready.text = "NOT READY" if self.am_i_ready else "READY?"
        self.btn_toggle_ready.color = GREEN if self.am_i_ready else GRAY
        self.btn_toggle_ready.draw(self.screen)
        
        if self.is_host:
            self.btn_close_room.draw(self.screen)
            # Update Start Button
            if all_ready:
                self.btn_start_online_game.color = GREEN
                self.btn_start_online_game.is_active = True
            else:
                self.btn_start_online_game.color = GRAY
                self.btn_start_online_game.is_active = False
            self.btn_start_online_game.draw(self.screen)

    def draw_online_game(self):
        # Reuse local game board drawing
        # But we need to ensure self.game is populated
        if self.game:
            self.draw_game_board()
        else:
            self.screen.fill(WHITE)
            self.btn_global_back.draw(self.screen)
            info = self.font_m.render("Waiting for game state...", True, DARK_GRAY)
            self.screen.blit(info, (SCREEN_WIDTH//2 - 100, SCREEN_HEIGHT//2))

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
        self.btn_global_back.draw(self.screen)
        
        title_surf = self.font_xl.render("Configure AI Players", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 80))
        self.screen.blit(title_surf, title_rect)
        
        for btn in self.ai_config_buttons:
            btn.draw(self.screen)
        
        self.start_game_button.draw(self.screen)

    def draw_player_select(self):
        self.screen.fill(WHITE)
        self.btn_global_back.draw(self.screen)
        
        title_surf = self.font_xl.render("Select Players", True, BLACK)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 150))
        self.screen.blit(title_surf, title_rect)
        for btn in self.player_select_buttons:
            btn.draw(self.screen)

    def handle_click(self, pos):
        if not self.game: return
        
        current_player_idx = self.game.curr_player_idx
        
        # In AI vs AI, we allow clicks only for viewing cards
        # In Online Game, allow input if it's my turn
        if self.state == "AI_VS_USER" and current_player_idx != self.user_player_idx:
            return
        
        if self.state == "ONLINE_GAME":
            # Only allow if it's my turn
            # print(f"DEBUG: Click. Curr: {current_player_idx}, Me: {self.user_player_idx}")
            if current_player_idx != self.user_player_idx:
                return
            # else:
            #     print("DEBUG: Click processed (My Turn)")

        if self.player_action_state == "SELECTING_CARD_ACTION":
            for btn in self.popup_buttons:
                btn.check_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'button':1, 'pos':pos}))
            return 

        # Non-gameplay clicks (Confirm/Reset) only for User Turn
        if self.state in ["AI_VS_USER", "ONLINE_GAME"]:
            self.confirm_button.check_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'button':1, 'pos':pos}))
            self.cancel_button.check_click(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {'button':1, 'pos':pos}))

        if self.player_action_state in ["IDLE", "SELECTING_TOKENS"]:
            if self.state in ["AI_VS_USER", "ONLINE_GAME"]:
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
                        if self.state == "ONLINE_GAME":
                            self.req_game_action(action)
                            self.player_action_state = "IDLE"
                            return

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
                if self.state in ["AI_VS_USER", "ONLINE_GAME"]:
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
                        if self.state in ["AI_VS_USER", "ONLINE_GAME"]:
                            self.open_card_popup(card, tier, idx_in_board)
                        else: # AI_VS_AI
                            self.open_view_only_popup(card)
                        return
                    current_card_x += 90
                start_y += 120
            
            # Reserved card click (Bottom box)
            for r_card_rect, card_obj, idx in self.reserved_card_rects:
                if r_card_rect.collidepoint(pos):
                    if self.state in ["AI_VS_USER", "ONLINE_GAME"]:
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
        
        res_btn = Button(f"Reserve Lv{tier}", self.popup_rect.centerx - 80, self.popup_rect.bottom - 80, 160, 50, 
                         self.confirm_reserve_deck, color=BLUE_RESERVE if can_reserve else GRAY, font_size=20)
        res_btn.is_active = can_reserve
        
        cancel_btn = Button("Cancel", self.popup_rect.right - 130, self.popup_rect.bottom - 80, 100, 50, 
                            self.close_card_popup, color=RED_ERROR, font_size=20)
        
        self.popup_buttons = [res_btn, cancel_btn]

    def confirm_reserve_deck(self):
        tier = self.selected_card_tier
        player = self.game.get_curr_player()
        
        if player.can_reserve_card():
            action = {'type': 'reserve_deck', 'tier': tier}
            
            if self.state == "ONLINE_GAME":
                self.req_game_action(action)
                self.close_card_popup()
                return

            try:
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
            if self.state == "ONLINE_GAME":
                tier = self.selected_card_tier
                try:
                    slot = self.game.board[tier].index(self.selected_card_obj)
                    action = {
                        'type': 'buy_card_index',
                        'tier': tier,
                        'slot': slot
                    }
                    self.req_game_action(action)
                    self.close_card_popup()
                    return
                except ValueError:
                    print("Card not found in board list")
                    return

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
            if self.state == "ONLINE_GAME":
                tier = self.selected_card_tier
                try:
                    slot = self.game.board[tier].index(self.selected_card_obj)
                    action = {
                        'type': 'reserve_card_index',
                        'tier': tier,
                        'slot': slot
                    }
                    self.req_game_action(action)
                    self.close_card_popup()
                    return
                except ValueError: return

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
            if self.state == "ONLINE_GAME":
                action = {
                    'type': 'buy_reserved_index',
                    'reserved_idx': self.selected_reserved_card_idx
                }
                self.req_game_action(action)
                self.close_card_popup()
                return

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
        # self.confirm_button.is_active = False # REMOVED: this was overriding validate_token_selection!
        self.clear_selected_tokens() 
        
        if self.network and self.current_room_info:
            return

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
                # Network Tick
                if self.state in ["ONLINE_LOGIN", "ONLINE_LOBBY", "ONLINE_ROOM", "ONLINE_GAME", "CONFIRM_DESTROY", "CONFIRM_SKIP", "BOT_SELECT_POPUP"]:
                    self.handle_network_messages()
                    # Auto refresh lobby
                    if self.state == "ONLINE_LOBBY":
                        if pygame.time.get_ticks() - self.last_room_fetch > 2000:
                            self.req_room_list()
                            self.last_room_fetch = pygame.time.get_ticks()

                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    
                    if self.state == "MENU":
                        for btn in self.menu_buttons:
                            btn.check_click(event)
                    
                    elif self.state == "ONLINE_CONNECT":
                        self.btn_global_back.check_click(event)
                        # self.online_name_input.handle_event(event)
                        self.online_ip_input.handle_event(event)
                        self.online_port_input.handle_event(event)
                        self.online_connect_button.check_click(event)
                    
                    elif self.state == "ONLINE_LOGIN":
                        self.btn_global_back.check_click(event)
                        self.login_id_input.handle_event(event)
                        self.login_pw_input.handle_event(event)
                        self.btn_do_login.check_click(event)
                        self.btn_do_register.check_click(event)
                    
                    elif self.state == "ONLINE_LOBBY":
                        self.btn_global_back.check_click(event)
                        self.room_name_input.handle_event(event)
                        self.btn_mp_2.check_click(event)
                        self.btn_mp_3.check_click(event)
                        self.btn_mp_4.check_click(event)
                        self.btn_create_room.check_click(event)
                        self.btn_refresh_rooms.check_click(event)
                        if hasattr(self, 'temp_back_btn'):
                            self.temp_back_btn.check_click(event)
                        for btn in self.room_join_buttons:
                            btn.check_click(event)

                    elif self.state == "ONLINE_ROOM":
                        self.btn_global_back.check_click(event)
                        self.btn_leave_room.check_click(event)
                        self.btn_toggle_ready.check_click(event) # Add Ready click
                        
                        # Bot Config Buttons (Dynamic)
                        if hasattr(self, 'bot_config_buttons'):
                            for btn in self.bot_config_buttons:
                                btn.check_click(event)

                        if self.is_host:
                            self.btn_close_room.check_click(event) # Add Close click
                            self.btn_start_online_game.check_click(event)

                    elif self.state == "ONLINE_GAME":
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            if event.button == 1:
                                self.btn_global_back.check_click(event)
                                self.handle_click(event.pos)

                    elif self.state == "AI_VS_USER":
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            if event.button == 1: 
                                self.handle_click(event.pos)
                        elif event.type == pygame.KEYDOWN:
                            if event.key == pygame.K_ESCAPE:
                                self.state = "MENU"
                                self.game = None
                                self.clear_selected_tokens() 
                    
                    elif self.state == "CONFIRM_SKIP":
                        if hasattr(self, 'skip_yes_btn'):
                            self.skip_yes_btn.check_click(event)
                            self.skip_no_btn.check_click(event)

                    elif self.state == "CONFIRM_DESTROY":
                        if hasattr(self, 'destroy_yes_btn'):
                            self.destroy_yes_btn.check_click(event)
                            self.destroy_no_btn.check_click(event)

                    elif self.state == "BOT_SELECT_POPUP":
                        if hasattr(self, 'bot_select_buttons'):
                            for btn in self.bot_select_buttons:
                                btn.check_click(event)
                            self.btn_confirm_bots.check_click(event)
                            self.btn_cancel_bots.check_click(event)

                    elif self.state == "GAME_OVER":
                        if event.type == pygame.MOUSEBUTTONDOWN:
                            if hasattr(self, 'game_over_button'):
                                self.game_over_button.check_click(event)

                    elif self.state == "PLAYER_SELECT":
                        self.btn_global_back.check_click(event)
                        for btn in self.player_select_buttons:
                            btn.check_click(event)

                    elif self.state == "AI_SELECT":
                        self.btn_global_back.check_click(event)
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
                elif self.state == "ONLINE_LOGIN":
                    self.draw_online_login()
                elif self.state == "ONLINE_LOBBY":
                    self.draw_online_lobby()
                elif self.state == "ONLINE_ROOM":
                    self.draw_online_room()
                elif self.state == "ONLINE_GAME":
                    self.draw_online_game()
                elif self.state == "AI_VS_USER":
                    self.draw_game_board()
                elif self.state == "CONFIRM_SKIP":
                    self.draw_confirm_skip()
                elif self.state == "CONFIRM_DESTROY":
                    self.draw_confirm_destroy()
                elif self.state == "BOT_SELECT_POPUP":
                    self.draw_bot_select_popup()
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
