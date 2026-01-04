import gymnasium as gym
from gymnasium import spaces
import numpy as np
from game import Game
from classdef import Gem, Card, Player
import random
from itertools import combinations

class SplendorEnv4PP1G1(gym.Env):
    """
    Custom Environment that follows gym interface.
    Wraps the Splendor Game logic for a single RL agent playing against random bots.
    """
    metadata = {'render.modes': ['console']}

    def __init__(self, num_players=4):
        super(SplendorEnv4PP1G1, self).__init__()
        
        self.num_players = num_players
        self.combos_3 = list(combinations(range(5), 3))
        
        # Action Space: 52 actions
        # 0-4: Take 2 tokens
        # 5-14: Take 3 tokens
        # 15-26: Buy board card (12 slots)
        # 27-29: Buy reserved card (3 slots)
        # 30-41: Reserve board card (12 slots)
        # 42-44: Reserve deck (3 tiers)
        # 45: Pass
        # 46-51: Discard token (Diamond to Gold)
        self.action_space = spaces.Discrete(52)
        
        # Observation Space: Flat vector of game features (Bank, Board, Players, Nobles)
        self.observation_space = spaces.Box(low=-1, high=100, shape=(250,), dtype=np.float32)

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.game = Game(p_count=self.num_players)
        self.agent_idx = 0 # Agent is always Player 1
        return self._get_obs(), {}

    def step(self, action_idx):
        action = self._map_action(action_idx)
        agent = self.game.players[self.agent_idx]
        
        # 1. Execute Agent Action
        try:
            winner = self.game.step(action)
        except:
            winner = None

        # 2. Handle turn advancement and opponent moves
        # If agent still has > 10 tokens, game.step didn't advance turn.
        # Agent will stay in step loop until they discard down to 10.
        
        if self.game.curr_player_idx != self.agent_idx:
            # Agent turn finished (including any discards). Play opponents.
            while self.game.curr_player_idx != self.agent_idx and not self.game.game_over:
                opts = self.game.get_valid_actions()
                opp_action = random.choice(opts)
                self.game.step(opp_action)
                
                # Heuristic: Opponent auto-discards most abundant gem
                curr_p = self.game.get_curr_player()
                while curr_p.token_count() > 10:
                    toks = curr_p.tokens[:5]
                    d_idx = toks.index(max(toks)) if sum(toks) > 0 else 5
                    self.game.step({'type': 'discard_token', 'gem_idx': d_idx})
                
                winner = self.game.check_winner()

        # 3. Calculate Reward
        terminated = bool(winner)
        reward = 0
        if winner == agent:
            reward = 100
        
        return self._get_obs(), reward, terminated, False, {}

    def action_masks(self):
        """
        Returns a boolean mask of valid actions.
        Enforces: Discard actions ONLY when tokens > 10.
        """
        mask = [False] * 52
        p = self.game.players[self.agent_idx]
        bank = self.game.bank
        
        # --- CASE A: MUST DISCARD (> 10 tokens) ---
        if p.token_count() > 10:
            # Only Discard actions (46-51) allowed
            for i in range(6):
                if p.tokens[i] > 0:
                    mask[46 + i] = True
            return mask # Normal actions 0-45 remain False

        # --- CASE B: NORMAL TURN (<= 10 tokens) ---
        # 0-4: Take 2 same tokens
        for i in range(5):
            if bank[i] >= 4:
                mask[i] = True
        
        # 5-14: Take 3 different tokens
        for i, combo in enumerate(self.combos_3):
            if all(bank[c] > 0 for c in combo):
                mask[5 + i] = True
                
        # 15-26: Buy Board Card
        for i in range(12):
            tier, slot = (i // 4) + 1, i % 4
            if slot < len(self.game.board[tier]):
                if p.can_buy(self.game.board[tier][slot]):
                    mask[15 + i] = True
                    
        # 27-29: Buy Reserved
        for i in range(min(3, len(p.keeped))):
            if p.can_buy(p.keeped[i]):
                mask[27 + i] = True
                    
        # 30-41: Reserve Board
        if p.can_reserve_card():
            for i in range(12):
                tier, slot = (i // 4) + 1, i % 4
                if slot < len(self.game.board[tier]):
                    mask[30 + i] = True
                    
        # 42-44: Reserve Deck
        if p.can_reserve_card():
            for i in range(3):
                if len(self.game.decks[i+1]) > 0:
                    mask[42 + i] = True
                    
        # 45: Pass (Always valid fallback)
        mask[45] = True
        
        return mask

    def _map_action(self, idx):
        p = self.game.players[self.agent_idx]
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

    def _get_obs(self):
        obs = []
        obs.extend(self.game.bank) # 6
        for t in [1, 2, 3]: # Board Cards (12 * 7 = 84)
            for s in range(4):
                if s < len(self.game.board[t]):
                    c = self.game.board[t][s]
                    obs.extend(c.cost); obs.append(c.points); obs.append(c.gem.value)
                else: obs.extend([0]*7)
        p = self.game.players[self.agent_idx] # Agent (33)
        obs.extend(p.tokens); obs.extend(p.card_gem()); obs.append(p.points())
        for i in range(3):
            if i < len(p.keeped):
                c = p.keeped[i]; obs.extend(c.cost); obs.append(c.points); obs.append(c.gem.value)
            else: obs.extend([0]*7)
        for i in range(1, self.num_players): # Opponents (3 * 13 = 39)
            op = self.game.players[i]
            obs.extend(op.tokens); obs.extend(op.card_gem()); obs.append(op.points()); obs.append(len(op.keeped))
        for i in range(5): # Noble Tiles (5 * 5 = 25)
            if i < len(self.game.tiles): obs.extend(self.game.tiles[i].cost)
            else: obs.extend([0]*5)
        obs.extend([0] * (250 - len(obs))) # Pad to 250
        return np.array(obs, dtype=np.float32)
