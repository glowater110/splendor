import gymnasium as gym
from gymnasium import spaces
import numpy as np
from game import Game
from classdef import Gem, Card, Player
import random
from itertools import combinations
from sb3_contrib import MaskablePPO

class SplendorEnv4PP2(gym.Env):
    """
    Unified Splendor Environment for Policy 2 (Point-Focus).
    Rewards:
    - Win: +100
    - Lose: -100
    - Points: +5.0 per prestige point gained
    - Step Penalty: -0.1
    Supports training against Random Bots or a loaded Model.
    """
    metadata = {'render.modes': ['console']}

    def __init__(self, num_players=4, opponent_model_path=None):
        super(SplendorEnv4PP2, self).__init__()
        
        self.num_players = num_players
        self.combos_3 = list(combinations(range(5), 3))
        
        # Load opponent model if provided
        self.opponent_model = None
        if opponent_model_path and opponent_model_path.lower() != "random":
            if not opponent_model_path.startswith("models/"):
                 opponent_model_path = f"models/{opponent_model_path}"

            print(f"Loading opponent model from {opponent_model_path}...")
            try:
                self.opponent_model = MaskablePPO.load(opponent_model_path)
                print("Opponent model loaded.")
            except Exception as e:
                print(f"Failed to load opponent model: {e}. Falling back to Random.")

        self.action_space = spaces.Discrete(52)
        self.observation_space = spaces.Box(low=-1, high=100, shape=(250,), dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.game = Game(p_count=self.num_players)
        self.agent_idx = 0 
        return self._get_obs_for_player(self.agent_idx), {}

    def step(self, action_idx):
        action = self._map_action(action_idx, self.agent_idx)
        agent = self.game.players[self.agent_idx]
        
        # Track state for point differential
        prev_points = agent.points()
        
        # 1. Execute Agent Action
        try:
            winner = self.game.step(action)
        except:
            winner = None

        # 2. Opponents' Turns
        if self.game.curr_player_idx != self.agent_idx:
            while self.game.curr_player_idx != self.agent_idx and not self.game.game_over:
                current_p_idx = self.game.curr_player_idx
                
                if self.opponent_model:
                    obs = self._get_obs_for_player(current_p_idx)
                    mask = self._get_action_mask_for_player(current_p_idx)
                    act_idx, _ = self.opponent_model.predict(obs, action_masks=mask, deterministic=False)
                    opp_action = self._map_action(int(act_idx), current_p_idx)
                else:
                    opts = self.game.get_valid_actions()
                    opp_action = random.choice(opts)
                
                self.game.step(opp_action)
                winner = self.game.check_winner()

        # 3. Calculate Reward
        terminated = bool(winner)
        reward = 0
        
        if winner:
            if winner == agent:
                reward += 100
            else:
                reward -= 100 # Penalty for losing
        
        # Intermediate Rewards
        if not terminated:
            new_points = agent.points()
            points_diff = new_points - prev_points
            if points_diff > 0:
                reward += points_diff * 5.0
            reward -= 0.1 # Step Penalty
        
        return self._get_obs_for_player(self.agent_idx), reward, terminated, False, {}

    def action_masks(self):
        return self._get_action_mask_for_player(self.agent_idx)

    def _get_action_mask_for_player(self, p_idx):
        mask = [False] * 52
        p = self.game.players[p_idx]
        bank = self.game.bank
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
            if slot < len(self.game.board[tier]) and p.can_buy(self.game.board[tier][slot]):
                mask[15 + i] = True
        for i in range(min(3, len(p.keeped))):
            if p.can_buy(p.keeped[i]): mask[27 + i] = True
        if p.can_reserve_card():
            for i in range(12):
                tier, slot = (i // 4) + 1, i % 4
                if slot < len(self.game.board[tier]): mask[30 + i] = True
        if p.can_reserve_card():
            for i in range(3):
                if len(self.game.decks[i+1]) > 0: mask[42 + i] = True
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
        obs = []
        obs.extend(self.game.bank) 
        for t in [1, 2, 3]: 
            for s in range(4):
                if s < len(self.game.board[t]):
                    c = self.game.board[t][s]
                    obs.extend(c.cost); obs.append(c.points); obs.append(c.gem.value)
                else: obs.extend([0]*7)
        p = self.game.players[p_idx]
        obs.extend(p.tokens); obs.extend(p.card_gem()); obs.append(p.points())
        for i in range(3):
            if i < len(p.keeped):
                c = p.keeped[i]; obs.extend(c.cost); obs.append(c.points); obs.append(c.gem.value)
            else: obs.extend([0]*7)
        num_p = len(self.game.players)
        for i in range(1, num_p):
            op_idx = (p_idx + i) % num_p
            op = self.game.players[op_idx]
            obs.extend(op.tokens); obs.extend(op.card_gem()); obs.append(op.points()); obs.append(len(op.keeped))
        for i in range(5):
            if i < len(self.game.tiles): obs.extend(self.game.tiles[i].cost)
            else: obs.extend([0]*5)
        obs.extend([0] * (250 - len(obs)))
        return np.array(obs, dtype=np.float32)
