import numpy as np
from game import Game
from classdef import Gem
import random
import sys
import os
from itertools import combinations, permutations
from sb3_contrib import MaskablePPO
import time

class ModelWrapper:
    def __init__(self, name, model_path=None):
        self.name = name
        self.is_random = (name.lower() == "random")
        self.model = None
        self.combos_3 = list(combinations(range(5), 3))
        
        if not self.is_random:
            try:
                print(f"Loading {name} from {model_path}...")
                self.model = MaskablePPO.load(model_path)
            except Exception as e:
                print(f"Error loading {name}: {e}. Defaulting to Random.")
                self.is_random = True

    def predict(self, game, player_idx):
        if self.is_random:
            actions = game.get_valid_actions()
            if not actions: return None
            return random.choice(actions)
        
        # RL Prediction
        obs = self._get_obs(game, player_idx)
        mask = self._get_action_mask(game, player_idx)
        action_idx, _ = self.model.predict(obs, action_masks=mask, deterministic=False) # Use stochastic for eval variety? Or deterministic?
        # Usually deterministic=True for evaluation.
        # But Splendor has hidden info (decks), so deterministic might be fine.
        # Let's stick to True for "best play".
        action_idx, _ = self.model.predict(obs, action_masks=mask, deterministic=True)
        return self._map_action(int(action_idx), game, player_idx)

    def _get_action_mask(self, game, p_idx):
        mask = [False] * 52
        p = game.players[p_idx]
        bank = game.bank
        
        if p.token_count() > 10:
            for i in range(6):
                if p.tokens[i] > 0: mask[46 + i] = True
            return mask

        for i in range(5):
            if bank[i] >= 4: mask[i] = True
        for i, combo in enumerate(self.combos_3):
            if all(bank[c] > 0 for c in combo): mask[5 + i] = True
        for i in range(12):
            tier, slot = (i // 4) + 1, i % 4
            if slot < len(game.board[tier]) and p.can_buy(game.board[tier][slot]):
                mask[15 + i] = True
        for i in range(min(3, len(p.keeped))):
            if p.can_buy(p.keeped[i]): mask[27 + i] = True
        if p.can_reserve_card():
            for i in range(12):
                tier, slot = (i // 4) + 1, i % 4
                if slot < len(game.board[tier]): mask[30 + i] = True
        if p.can_reserve_card():
            for i in range(3):
                if len(game.decks[i+1]) > 0: mask[42 + i] = True
        mask[45] = True
        return mask

    def _map_action(self, idx, game, p_idx):
        p = game.players[p_idx]
        if 0 <= idx <= 4:
            t = [0]*6; t[idx] = 2
            return {'type': 'get_token', 'tokens': t}
        if 5 <= idx <= 14:
            t = [0]*6
            for c in self.combos_3[idx - 5]: t[c] = 1
            return {'type': 'get_token', 'tokens': t}
        if 15 <= idx <= 26:
            tier, slot = ((idx - 15) // 4) + 1, (idx - 15) % 4
            if slot < len(game.board[tier]):
                return {'type': 'buy_card', 'card': game.board[tier][slot], 'tier': tier}
        if 27 <= idx <= 29:
            slot = idx - 27
            if slot < len(p.keeped):
                return {'type': 'buy_reserved', 'card': p.keeped[slot]}
        if 30 <= idx <= 41:
            tier, slot = ((idx - 30) // 4) + 1, (idx - 30) % 4
            if slot < len(game.board[tier]):
                return {'type': 'reserve_card', 'card': game.board[tier][slot], 'tier': tier}
        if 42 <= idx <= 44:
            return {'type': 'reserve_deck', 'tier': idx - 41}
        if 46 <= idx <= 51:
            return {'type': 'discard_token', 'gem_idx': idx - 46}
        return {'type': 'do_nothing'}

    def _get_obs(self, game, p_idx):
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
        num_p = len(game.players)
        for i in range(1, num_p):
            op_idx = (p_idx + i) % num_p
            op = game.players[op_idx]
            obs.extend(op.tokens); obs.extend(op.card_gem()); obs.append(op.points()); obs.append(len(op.keeped))
        for i in range(5):
            if i < len(game.tiles): obs.extend(game.tiles[i].cost)
            else: obs.extend([0]*5)
        obs.extend([0] * (250 - len(obs)))
        return np.array(obs, dtype=np.float32)

def run_tournament(model_paths):
    # Prepare Models
    models = []
    for path in model_paths:
        name = "Random" if path.lower() == "random" else os.path.splitext(path)[0]
        models.append(ModelWrapper(name, path))

    # Stats: { "ModelName": { "total_wins": 0, "seat_wins": [0,0,0,0], "games_played": 0 } }
    stats = {}
    for m in models:
        if m.name not in stats:
            stats[m.name] = {"total_wins": 0, "seat_wins": [0,0,0,0], "games_played": 0}

    # Generate Permutations (Indices 0, 1, 2, 3)
    perms = list(permutations(range(4)))
    total_perms = len(perms) # 24
    games_per_perm = 100
    total_games = total_perms * games_per_perm

    print(f"\nStarting Tournament!")
    print(f"Models: {[m.name for m in models]}")
    print(f"Total Games: {total_games} ({total_perms} orders * {games_per_perm} games)")
    
    start_time = time.time()
    
    # Use tqdm for progress bar tracking every game
    try:
        from tqdm import tqdm
        pbar = tqdm(total=total_games, desc="Tournament Progress", unit="game")
    except ImportError:
        print("tqdm not found, running without progress bar.")
        pbar = None

    for order in perms:
        # order is tuple of indices
        current_seat_map = {seat: models[model_idx] for seat, model_idx in enumerate(order)}
        
        for _ in range(games_per_perm):
            game = Game(p_count=4)
            turn_limit = 200 # prevent infinite games
            
            while not game.game_over and game.turn_count < turn_limit:
                curr_p_idx = game.curr_player_idx
                agent = current_seat_map[curr_p_idx]
                
                action = agent.predict(game, curr_p_idx)
                
                if action is None:
                    game.next_turn() 
                else:
                    try:
                        winner = game.step(action)
                        if winner:
                            winner_seat = game.players.index(winner)
                            winning_model = current_seat_map[winner_seat]
                            
                            stats[winning_model.name]["total_wins"] += 1
                            stats[winning_model.name]["seat_wins"][winner_seat] += 1
                            break
                    except Exception:
                        game.next_turn()
            
            if pbar:
                pbar.update(1)

    if pbar:
        pbar.close()

    duration = time.time() - start_time
    print(f"\nTournament Finished in {duration:.2f} seconds.")
    print("-" * 80)
    print(f"{'Model Name':<20} | {'Win Rate':<10} | {'Seat 1':<8} | {'Seat 2':<8} | {'Seat 3':<8} | {'Seat 4':<8}")
    print("-" * 80)
    
    for name, data in stats.items():
        # Total games this model played = total_games (since every model plays every game in a full permutation set)
        win_rate = (data["total_wins"] / total_games) * 100
        seats = data["seat_wins"]
        seat_1_wr = (seats[0] / (total_games/4)) * 100
        seat_2_wr = (seats[1] / (total_games/4)) * 100
        seat_3_wr = (seats[2] / (total_games/4)) * 100
        seat_4_wr = (seats[3] / (total_games/4)) * 100
        
        print(f"{name:<20} | {win_rate:6.2f}%   | {seat_1_wr:6.1f}%  | {seat_2_wr:6.1f}%  | {seat_3_wr:6.1f}%  | {seat_4_wr:6.1f}%")
    print("-" * 80)

if __name__ == "__main__":
    # Input 4 models
    print("Enter 4 model paths or 'random' (duplicates allowed).")
    defaults = ["random", "random", "random", "random"]
    paths = []
    for i in range(4):
        val = input(f"Model {i+1} (default: {defaults[i]}): ").strip()
        if not val: val = defaults[i]
        paths.append(val)
        
    run_tournament(paths)
