import gymnasium as gym
from gymnasium import spaces
import numpy as np
from game import Game
from classdef import Gem, Card, Player
import random
from itertools import combinations
from sb3_contrib import MaskablePPO

class SplendorEnv4PP1G3(gym.Env):
    """
    Splendor Environment 4P P1G3: Policy 1 (Win=100), Generation 3.
    The Agent trains against the P1G2 model (ai_4p_p1g2.zip).
    """
    metadata = {'render.modes': ['console']}

    def __init__(self, num_players=4, opponent_model_path="ai_4p_p1g2.zip"):
        super(SplendorEnv4PP1G3, self).__init__()
        
        self.num_players = num_players
        self.combos_3 = list(combinations(range(5), 3))
        
        # Load the opponent model
        if not opponent_model_path.startswith("models/"):
             opponent_model_path = f"models/{opponent_model_path}"

        print(f"Loading opponent model from {opponent_model_path}...")
        try:
            self.opponent_model = MaskablePPO.load(opponent_model_path)
            print("Opponent model loaded.")
        except Exception as e:
            print(f"Failed to load opponent model: {e}. Defaulting opponents to Random.")
            self.opponent_model = None

        # Action Space: 52 actions
        self.action_space = spaces.Discrete(52)
        
        # Observation Space
        self.observation_space = spaces.Box(low=-1, high=100, shape=(250,), dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.game = Game(p_count=self.num_players)
        self.agent_idx = 0 # Agent is Player 1
        return self._get_obs_for_player(self.agent_idx), {}

    def step(self, action_idx):
        action = self._map_action(action_idx, self.agent_idx)
        agent = self.game.players[self.agent_idx]
        
        # 1. Execute Agent Action
        try:
            winner = self.game.step(action)
        except:
            winner = None

        # 2. Opponents' Turns (Controlled by Opponent Model)
        if self.game.curr_player_idx != self.agent_idx:
            while self.game.curr_player_idx != self.agent_idx and not self.game.game_over:
                current_p_idx = self.game.curr_player_idx
                
                # Predict action
                if self.opponent_model:
                    obs = self._get_obs_for_player(current_p_idx)
                    mask = self._get_action_mask_for_player(current_p_idx)
                    action_idx, _ = self.opponent_model.predict(obs, action_masks=mask, deterministic=False)
                    opp_action = self._map_action(int(action_idx), current_p_idx)
                else:
                    opts = self.game.get_valid_actions()
                    opp_action = random.choice(opts)
                
                self.game.step(opp_action)
                
                # Auto-discard logic handled naturally if model plays optimally, 
                # but we need a fallback for infinite loops or invalid states just in case.
                # Actually, game.step handles discard phase logic implicitly by NOT advancing turn.
                # So if opponent has > 10 tokens, curr_player_idx stays same.
                # Next loop, model sees discard mask, plays discard.
                # We trust the model/mask logic.
                
                winner = self.game.check_winner()

        # 3. Calculate Reward (Policy 1: Win=100, Else=0)
        terminated = bool(winner)
        reward = 0
        if winner == agent:
            reward = 100
        
        return self._get_obs_for_player(self.agent_idx), reward, terminated, False, {}

    def action_masks(self):
        """Mask for the AGENT (Player 0)"""
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
