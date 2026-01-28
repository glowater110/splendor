import socket
import threading
import json
import time
import uuid
import glob
import os
import random
import numpy as np
from itertools import combinations
from sb3_contrib import MaskablePPO
from game import Game
from classdef import Gem, Card, Player
import database

class Room:
    def __init__(self, room_id, name, host_id, max_players=4):
        self.id = room_id
        self.name = name
        self.host_id = host_id
        self.max_players = max_players
        self.players = [host_id]  # List of player_ids
        self.game_started = False
        self.bot_settings = {} # {seat_index: "model_name"}
        self.game = None
        self.ai_map = {} # seat_idx -> model
        self.seat_map = {}

    def add_player(self, player_id):
        if len(self.players) < self.max_players and not self.game_started:
            self.players.append(player_id)
            return True
        return False

    def remove_player(self, player_id):
        if player_id in self.players:
            self.players.remove(player_id)
            return True
        return False

    def is_full(self):
        return len(self.players) >= self.max_players

    def to_dict(self, server_clients):
        player_data = []
        for pid in self.players:
            p_info = server_clients.get(pid, {})
            player_data.append({
                "id": pid,
                "name": p_info.get("name", "Unknown"),
                "ready": p_info.get("ready", False),
                "is_bot": False
            })
        
        for i in range(len(self.players), self.max_players):
            bot_model = self.bot_settings.get(i, "Random Bot")
            player_data.append({
                "id": f"Bot_{i+1}",
                "name": f"Bot {i+1}",
                "ready": True,
                "is_bot": True,
                "model": bot_model
            })
            
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host_id,
            "players": self.players, 
            "player_details": player_data, 
            "max_players": self.max_players,
            "started": self.game_started
        }

def serialize_card(card):
    if not card: return None
    return {
        "points": card.points,
        "gem": card.gem.value,
        "cost": card.cost
    }

def serialize_game(game):
    return {
        "turn": game.turn_count,
        "curr_player_idx": game.curr_player_idx,
        "bank": game.bank,
        "board": {
            tier: [serialize_card(c) for c in cards] 
            for tier, cards in game.board.items()
        },
        "decks_counts": {t: len(d) for t, d in game.decks.items()},
        "nobles": [t.cost for t in game.tiles],
        "players": [
            {
                "name": p.name,
                "points": p.points(),
                "tokens": p.tokens,
                "cards": [serialize_card(c) for c in p.cards],
                "reserved": [serialize_card(c) for c in p.keeped]
            }
            for p in game.players
        ]
    }

class SplendorServer:
    def __init__(self, host="0.0.0.0", port=5555):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rooms = {}  # {room_id: Room}
        self.clients = {}  # {player_id: {"conn": conn, ...}}
        self.lock = threading.Lock()
        
        # Init DB
        database.init_db()
        self.active_sessions = set() 
        
        self.ai_models = {}
        self.load_ai_models()
        self.ai_model_names = ["Random Bot"] + list(self.ai_models.keys())
        if "Random" in self.ai_model_names: self.ai_model_names.remove("Random")

        threading.Thread(target=self.broadcast_time_loop, daemon=True).start()

    def load_ai_models(self):
        # print("Loading AI Models...")
        if os.path.exists("models"):
            for file in glob.glob("models/*.zip"):
                name = os.path.splitext(os.path.basename(file))[0]
                try:
                    self.ai_models[name] = MaskablePPO.load(file)
                    # print(f"Loaded {name}")
                except:
                    pass

    def broadcast_time_loop(self):
        while True:
            time.sleep(1)
            current_time = time.strftime("%H:%M:%S")
            msg = (json.dumps({"type": "TIME_UPDATE", "time": current_time}) + "\n").encode('utf-8')
            with self.lock:
                for client in self.clients.values():
                    try: client["conn"].send(msg)
                    except: pass

    def start(self):
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen()
            self.server_socket.settimeout(1.0)
            print(f"Server started on {self.host}:{self.port}. Press Ctrl+C to stop.")
            running = True
            while running:
                try:
                    conn, addr = self.server_socket.accept()
                    thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                    thread.daemon = True
                    thread.start()
                except socket.timeout: continue
                except KeyboardInterrupt: running = False
        except Exception as e: print(f"Server Error: {e}")
        finally: self.server_socket.close()

    def handle_client(self, conn, addr):
        player_id = None
        buffer = ""
        while True:
            try:
                data = conn.recv(4096).decode('utf-8')
                if not data: break
                buffer += data
                while "\n" in buffer:
                    msg_str, buffer = buffer.split("\n", 1)
                    if not msg_str.strip(): continue
                    try:
                        request = json.loads(msg_str)
                        cmd = request.get("type")
                        
                        if not player_id:
                            if cmd == "LOGIN":
                                username = request.get("username")
                                password = request.get("password")
                                success, msg = database.verify_user(username, password)
                                if success:
                                    with self.lock:
                                        if username in self.active_sessions:
                                            resp = {"type": "ERROR", "message": "User already logged in"}
                                        else:
                                            player_id = username
                                            self.active_sessions.add(player_id)
                                            self.clients[player_id] = {"conn": conn, "addr": addr, "room_id": None, "name": username, "ready": False}
                                            resp = {
                                                "type": "LOGIN_SUCCESS", 
                                                "player_id": player_id,
                                                "message": "Logged in",
                                                "ai_models": self.ai_model_names
                                            }
                                else:
                                    resp = {"type": "ERROR", "message": msg}
                                conn.send((json.dumps(resp) + "\n").encode('utf-8'))
                                
                            elif cmd == "REGISTER":
                                username = request.get("username")
                                password = request.get("password")
                                success, msg = database.register_user(username, password)
                                resp = {"type": "REGISTER_SUCCESS" if success else "ERROR", "message": msg}
                                conn.send((json.dumps(resp) + "\n").encode('utf-8'))
                            else:
                                conn.send((json.dumps({"type": "ERROR", "message": "Please Login first"}) + "\n").encode('utf-8'))
                        else:
                            self.process_request(player_id, request)
                    except: pass
            except: break
            
        if player_id:
            self.handle_disconnect(player_id)
            with self.lock:
                if player_id in self.active_sessions:
                    self.active_sessions.remove(player_id)
        conn.close()

    def process_request(self, player_id, request):
        cmd = request.get("type")
        if player_id not in self.clients: return
        conn = self.clients[player_id]["conn"]
        response = {"type": "ERROR", "message": "Unknown Command"}

        with self.lock:
            if cmd == "GET_ROOMS":
                room_list = [r.to_dict(self.clients) for r in self.rooms.values()]
                response = {"type": "ROOM_LIST", "rooms": room_list}

            elif cmd == "CREATE_ROOM":
                name = request.get("name", "New Room")
                max_p = request.get("max_players", 4)
                if len(self.rooms) >= 5: response = {"type": "ERROR", "message": "Server full"}
                elif self.clients[player_id]["room_id"]: response = {"type": "ERROR", "message": "In room"}
                else:
                    self.clients[player_id]["ready"] = False
                    rid = str(uuid.uuid4())[:8]
                    room = Room(rid, name, player_id, max_p)
                    self.rooms[rid] = room
                    self.clients[player_id]["room_id"] = rid
                    response = {"type": "ROOM_CREATED", "room": room.to_dict(self.clients)}

            elif cmd == "JOIN_ROOM":
                rid = request.get("room_id")
                room = self.rooms.get(rid)
                if not room: response = {"type": "ERROR", "message": "Not found"}
                elif self.clients[player_id]["room_id"]: response = {"type": "ERROR", "message": "In room"}
                elif room.is_full(): response = {"type": "ERROR", "message": "Full"}
                else:
                    room.add_player(player_id)
                    self.clients[player_id]["room_id"] = rid
                    self.clients[player_id]["ready"] = False
                    response = {"type": "JOINED_ROOM", "room": room.to_dict(self.clients)}
                    self.broadcast_to_room(rid, {"type": "PLAYER_JOINED", "player_id": player_id, "room": room.to_dict(self.clients)})

            elif cmd == "LEAVE_ROOM":
                self.handle_leave_room(player_id)
                response = {"type": "LEFT_ROOM"}

            elif cmd == "TOGGLE_READY":
                rid = self.clients[player_id]["room_id"]
                if rid:
                    self.clients[player_id]["ready"] = not self.clients[player_id]["ready"]
                    room = self.rooms.get(rid)
                    if room: self.broadcast_to_room(rid, {"type": "ROOM_UPDATE", "room": room.to_dict(self.clients)})
                    response = {"type": "READY_TOGGLED", "state": self.clients[player_id]["ready"]}

            elif cmd == "UPDATE_BOT_SETTINGS":
                rid = self.clients[player_id]["room_id"]
                room = self.rooms.get(rid)
                if room and room.host_id == player_id:
                    room.bot_settings[request.get("seat_idx")] = request.get("model")
                    self.broadcast_to_room(rid, {"type": "ROOM_UPDATE", "room": room.to_dict(self.clients)})
                    response = {"type": "OK"}

            elif cmd == "CLOSE_ROOM":
                rid = self.clients[player_id]["room_id"]
                room = self.rooms.get(rid)
                if room and room.host_id == player_id:
                    for pid in list(room.players):
                        c = self.clients.get(pid)
                        if c:
                            c["room_id"] = None
                            try: c["conn"].send((json.dumps({"type": "ROOM_CLOSED"})+"\n").encode('utf-8'))
                            except: pass
                    del self.rooms[rid]
                    return

            elif cmd == "START_GAME":
                rid = self.clients[player_id]["room_id"]
                room = self.rooms.get(rid)
                if room and room.host_id == player_id:
                    if all(self.clients[p]["ready"] for p in room.players):
                        parts = []
                        for p in room.players: parts.append({"id": p, "bot": False, "name": self.clients[p]["name"]})
                        for i in range(len(room.players), room.max_players): parts.append({"bot": True, "model": room.bot_settings.get(i, "Random Bot")})
                        random.shuffle(parts)
                        
                        room.game = Game(p_count=room.max_players)
                        room.ai_map = {}
                        room.seat_map = {}
                        for i, pinfo in enumerate(parts):
                            if pinfo["bot"]:
                                m = pinfo["model"]
                                room.game.players[i].name = f"Bot {i+1} ({m})"
                                room.ai_map[i] = self.ai_models.get(m)
                            else:
                                room.game.players[i].name = pinfo["name"]
                                room.seat_map[pinfo["id"]] = i
                        room.game_started = True
                        state = serialize_game(room.game)
                        self.broadcast_to_room(rid, {"type": "GAME_STATE_UPDATE", "state": state, "your_seat_mapping": room.seat_map})
                        self.broadcast_to_room(rid, {"type": "GAME_STARTED"})
                        if 0 in room.ai_map: self._process_ai_turns(rid, room)
                        return

            elif cmd == "GAME_ACTION":
                rid = self.clients[player_id]["room_id"]
                room = self.rooms.get(rid)
                action = request.get("action")
                if room and room.game_started:
                    game = room.game
                    s_idx = room.seat_map.get(player_id, -1)
                    
                    if s_idx == game.curr_player_idx:
                        try:
                            if action['type'] == 'buy_card_index':
                                t, s = action['tier'], action['slot']
                                action = {'type': 'buy_card', 'tier': t, 'card': game.board[t][s]}
                            elif action['type'] == 'reserve_card_index':
                                t, s = action['tier'], action['slot']
                                action = {'type': 'reserve_card', 'tier': t, 'card': game.board[t][s]}
                            elif action['type'] == 'buy_reserved_index':
                                action = {'type': 'buy_reserved', 'card': game.players[s_idx].keeped[action['reserved_idx']]}

                            game.step(action)
                            msg = self.format_action_log(self.clients[player_id]['name'], action)
                            self.broadcast_to_room(rid, {"type": "GAME_LOG", "message": msg})
                            self.broadcast_to_room(rid, {"type": "GAME_STATE_UPDATE", "state": serialize_game(game)})
                            
                            win = game.check_winner()
                            if win:
                                self.broadcast_to_room(rid, {"type": "GAME_OVER", "winner": win.name})
                                return
                            
                            if game.curr_player_idx in room.ai_map:
                                self._process_ai_turns(rid, room)
                            return
                        except: pass
                    else: response = {"type": "ERROR", "message": "Not your turn"}

        try: conn.send((json.dumps(response)+"\n").encode('utf-8'))
        except: pass

    def handle_leave_room(self, player_id):
        c = self.clients.get(player_id)
        if not c: return
        rid = c["room_id"]
        if rid in self.rooms:
            r = self.rooms[rid]
            r.remove_player(player_id)
            c["room_id"] = None
            if not r.players: del self.rooms[rid]
            else:
                if r.host_id == player_id: r.host_id = r.players[0]
                self.broadcast_to_room(rid, {"type": "ROOM_UPDATE", "room": r.to_dict(self.clients)})

    def handle_disconnect(self, player_id):
        with self.lock:
            if player_id in self.clients:
                self.handle_leave_room(player_id)
                del self.clients[player_id]

    def broadcast_to_room(self, rid, msg_dict):
        r = self.rooms.get(rid)
        if not r: return
        data = (json.dumps(msg_dict) + "\n").encode('utf-8')
        for pid in r.players:
            c = self.clients.get(pid)
            if c:
                try: c["conn"].send(data)
                except: pass

    def _process_ai_turns(self, rid, room):
        g = room.game
        count = 0
        while count < 100:
            count += 1
            idx = g.curr_player_idx
            if idx in room.ai_map:
                self.lock.release(); time.sleep(1.0); self.lock.acquire()
                if not room.game_started: break
                model = room.ai_map[idx]
                try:
                    obs = self._get_obs_for_player(g, idx)
                    if model:
                        mask = self._get_action_mask_for_player(g, idx)
                        act_idx, _ = model.predict(obs, action_masks=mask, deterministic=False)
                        act = self._map_action(int(act_idx), g, idx)
                    else:
                        acts = g.get_valid_actions()
                        act = random.choice(acts) if acts else {'type':'do_nothing'}
                    g.step(act)
                    self.ai_discard_excess_tokens(g, idx)
                    log = self.format_action_log(f"Bot {idx+1}", act)
                    self.broadcast_to_room(rid, {"type": "GAME_LOG", "message": log})
                    self.broadcast_to_room(rid, {"type": "GAME_STATE_UPDATE", "state": serialize_game(g)})
                    win = g.check_winner()
                    if win:
                        self.broadcast_to_room(rid, {"type": "GAME_OVER", "winner": win.name})
                        return
                except: g.next_turn(); break
            else: break

    def ai_discard_excess_tokens(self, game, p_idx):
        p = game.players[p_idx]
        while p.token_count() > 10:
            gems = [i for i, c in enumerate(p.tokens[:5]) if c > 0]
            if not gems: gems = [i for i, c in enumerate(p.tokens) if c > 0]
            if gems: game.step({'type': 'discard_token', 'gem_idx': random.choice(gems)})
            else: break

    def format_action_log(self, name, action):
        t = action['type']
        colors = ["White", "Blue", "Green", "Red", "Black", "Gold"]
        if t == 'get_token':
            taken = [colors[i] for i, c in enumerate(action['tokens']) if c > 0]
            return f"{name} took {', '.join(taken)}"
        if t == 'buy_card' or t == 'buy_card_index': return f"{name} bought card"
        if t == 'reserve_card' or t == 'reserve_card_index': return f"{name} reserved card"
        if t == 'reserve_deck': return f"{name} reserved from deck"
        if t == 'discard_token': return f"{name} discarded {colors[action['gem_idx']]}"
        return f"{name} performed {t}"

    def _get_obs_for_player(self, game, p_idx):
        obs = []
        obs.extend(game.bank)
        for t in [1, 2, 3]:
            for s in range(4):
                if s < len(game.board[t]):
                    c = game.board[t][s]
                    obs.extend(c.cost); obs.append(c.points); obs.append(c.gem.value)
                else: obs.extend([0]*7)
        p = game.players[p_idx]
        obs.extend(p.tokens); obs.extend(p.card_gem()); obs.append(p.points())
        for i in range(3):
            if i < len(p.keeped):
                c = p.keeped[i]; obs.extend(c.cost); obs.append(c.points); obs.append(c.gem.value)
            else: obs.extend([0]*7)
        for i in range(1, len(game.players)):
            op = game.players[(p_idx + i) % len(game.players)]
            obs.extend(op.tokens); obs.extend(op.card_gem()); obs.append(op.points()); obs.append(len(op.keeped))
        for i in range(5):
            if i < len(game.tiles): obs.extend(game.tiles[i].cost)
            else: obs.extend([0]*5)
        obs.extend([0] * (250 - len(obs)))
        return np.array(obs, dtype=np.float32)

    def _get_action_mask_for_player(self, game, p_idx):
        mask = [False] * 52
        p = game.players[p_idx]; bank = game.bank
        combos = list(combinations(range(5), 3))
        if p.token_count() > 10:
            for i in range(6):
                if p.tokens[i] > 0: mask[46 + i] = True
            return mask
        for i in range(5):
            if bank[i] >= 4: mask[i] = True
        for i, combo in enumerate(combos):
            if all(bank[c] > 0 for c in combo): mask[5 + i] = True
        for i in range(12):
            t, s = (i // 4) + 1, i % 4
            if s < len(game.board[t]) and p.can_buy(game.board[t][s]): mask[15 + i] = True
        for i in range(min(3, len(p.keeped))):
            if p.can_buy(p.keeped[i]): mask[27 + i] = True
        if p.can_reserve_card():
            for i in range(12):
                t, s = (i // 4) + 1, i % 4
                if s < len(game.board[t]): mask[30 + i] = True
            for i in range(3):
                if len(game.decks[i+1]) > 0: mask[42 + i] = True
        mask[45] = True
        return mask

    def _map_action(self, idx, game, p_idx):
        combos = list(combinations(range(5), 3))
        if 0 <= idx <= 4:
            t = [0]*6; t[idx] = 2
            return {'type': 'get_token', 'tokens': t}
        if 5 <= idx <= 14:
            t = [0]*6
            for c in combos[idx - 5]: t[c] = 1
            return {'type': 'get_token', 'tokens': t}
        if 15 <= idx <= 26:
            t, s = ((idx - 15) // 4) + 1, (idx - 15) % 4
            return {'type': 'buy_card', 'card': game.board[t][s], 'tier': t}
        if 27 <= idx <= 29: return {'type': 'buy_reserved', 'card': game.players[p_idx].keeped[idx - 27]}
        if 30 <= idx <= 41:
            t, s = ((idx - 30) // 4) + 1, (idx - 30) % 4
            return {'type': 'reserve_card', 'card': game.board[t][s], 'tier': t}
        if 42 <= idx <= 44: return {'type': 'reserve_deck', 'tier': idx - 41}
        if 46 <= idx <= 51: return {'type': 'discard_token', 'gem_idx': idx - 46}
        return {'type': 'do_nothing'}

if __name__ == "__main__":
    SplendorServer().start()