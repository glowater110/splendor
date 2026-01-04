from classdef import Card,Tile,Player
from splendor_data import CARD1_SET, CARD2_SET, CARD3_SET, TILE_SET
import random
from copy import deepcopy
from itertools import combinations

class Game:
    def __init__(self, p_count:int):
        self.turn_count = 0
        self.curr_player_idx = 0
        self.game_over = False
        
        base_cnt = {2:4, 3:5, 4:7}[p_count]
        self.bank = [base_cnt] * 5 + [5]
        
        self.players = [Player(f'Player {i+1}') for i in range(p_count)]
        
        self.decks:dict[int,list[Card]] = {1: [], 2: [], 3: []}
        self.board:dict[int,list[Card]] = {1: [], 2: [], 3: []}
        self.tiles:list[Tile] = []
        self.init_game()
        
    def init_game(self):
        """카드 90장과 귀족 타일을 로드하고 셔플하는 로직"""
        card1 = deepcopy(CARD1_SET)
        card2 = deepcopy(CARD2_SET)
        card3 = deepcopy(CARD3_SET)
        tiles = deepcopy(TILE_SET)
        
        random.shuffle(card1)
        random.shuffle(card2)
        random.shuffle(card3)
        random.shuffle(tiles)
        
        self.board[1] = deepcopy(card1[:4])
        del card1[:4]
        self.decks[1] = deepcopy(card1)
        
        self.board[2] = deepcopy(card2[:4])
        del card2[:4]
        self.decks[2] = deepcopy(card2)
        
        self.board[3] = deepcopy(card3[:4])
        del card3[:4]
        self.decks[3] = deepcopy(card3)
        
        self.tiles = deepcopy(tiles[:5])

    def get_curr_player(self):
        return self.players[self.curr_player_idx]

    def get_valid_actions(self):
        """현재 가능한 행동을 반환"""
        if self.game_over: return []

        player = self.get_curr_player()
        actions = []
        
        # 1. 토큰 버리기
        if player.token_count() > 10:
            for i in range(6):
                if player.tokens[i] > 0: actions.append({'type': 'discard_token', 'gem_idx': i})
            return actions

        # 2. 토큰 가져오기
        avail = [i for i in range(5) if self.bank[i] > 0]
        if len(avail) >= 3:
            for c in combinations(avail, 3):
                t = [0]*6
                for color in c: t[color] = 1
                actions.append({'type': 'get_token', 'tokens': t})
        elif len(avail) == 2:
             t = [0]*6
             for c in avail: t[c] = 1
             actions.append({'type': 'get_token', 'tokens': t})
        elif len(avail) == 1:
             t = [0]*6
             t[avail[0]] = 1
             actions.append({'type': 'get_token', 'tokens': t})

        for i in range(5):
            if self.bank[i] >= 4:
                t = [0]*6; t[i] = 2
                actions.append({'type': 'get_token', 'tokens': t})

        # 3. 카드 구매/예약
        # 오픈카드
        for tier in [1,2,3]:
            for card in self.board[tier]:
                # 구매
                if player.can_buy(card):
                    actions.append({'type': 'buy_card', 'card': card, 'tier': tier})
                # 예약 (3장 미만)
                if len(player.keeped) < 3:
                    actions.append({'type': 'reserve_card', 'card': card, 'tier': tier})
        
        # 예약카드 구매
        for card in player.keeped:
            if player.can_buy(card):
                actions.append({'type': 'buy_reserved', 'card': card})
        
        # 덱카드 예약
        if player.can_reserve_card():
            for tier in [1,2,3]:
                if len(self.decks[tier]) > 0:
                    actions.append({'type': 'reserve_deck', 'tier': tier})
        
        # 4. 아무것도 하지 않음
        actions.append({'type':'do_nothing'})

        return actions

    def pay_card(self, player:Player, card:Card):
        """카드 구매 로직 (구매 능력이 있다고 가정)"""
        discounts = player.card_gem()
        total_gold_needed = 0
        
        for i in range(5):
            cost = card.cost[i]
            if cost == 0: continue

            # 토큰으로 지불해야 하는 비용
            pay_cost = max(0, cost - discounts[i])
            
            if pay_cost > 0:
                # 플레이어가 가진 해당 색상 토큰으로 낼 수 있는 만큼 냄
                # 이론상 황금토큰을 먼저 써도 되긴 하지만 스스로 불리해지는 행동이므로 고려하지 않음
                paid_tokens = min(player.tokens[i], pay_cost)
                
                player.tokens[i] -= paid_tokens
                self.bank[i] += paid_tokens
                
                # 토큰으로 부족한 부분은 골드로 메꿔야 함
                shortage = pay_cost - paid_tokens
                total_gold_needed += shortage
        
        # 부족했던 만큼 황금 토큰 지불
        if total_gold_needed > 0:
            player.tokens[5] -= total_gold_needed
            self.bank[5] += total_gold_needed

    def refill_board(self, tier:int):
        """빈 자리가 났을 때 덱에서 카드를 뽑아 채움"""
        # 덱에 카드가 남아있을 때만 pop 실행
        if len(self.decks[tier]) > 0:
            new_card = self.decks[tier].pop(0)
            self.board[tier].append(new_card)

    def check_nobles(self, player: Player):
        """조건을 만족하는 귀족이 있으면 획득 (여러 명이면 다른 플레이어가 노리는 귀족을 우선적으로 뺏음)"""
        # 내가 가져갈 수 있는 귀족 후보 찾기
        candidates = []
        discounts = player.card_gem()
        
        for tile in self.tiles:
            condition_met = True
            for color_idx, required in enumerate(tile.cost):
                if discounts[color_idx] < required:
                    condition_met = False
                    break
            if condition_met:
                candidates.append(tile)
        
        # 획득 가능한 귀족타일 없음
        if not candidates:
            return
        
        # 기본값: 첫 번째 타일 (후보 1개인 경우 포함)
        target_noble = candidates[0]

        # 후보가 여러 개면 어느 타일을 고를지 선택
        # 다른 플레이어와 가장 근접한 타일을 먼저 고르기
        if len(candidates) > 1:
            # 다른 플레이어 리스트
            opponents = [p for p in self.players if p is not player]
            
            # 모든 귀족타일 중 가장 근접한 타일의 거리
            min_global_missing = 999
            
            for noble in candidates:
                # 해당 귀족과 가장 가까운 플레이어와의 거리
                noble_min_missing = 999
                
                for op in opponents:
                    op_discounts = op.card_gem()
                    missing = 0
                    for c_idx, req in enumerate(noble.cost):
                        missing += max(0, req - op_discounts[c_idx])
                    
                    # 누군가 이 귀족에 더 가깝다면 업데이트
                    if missing < noble_min_missing:
                        noble_min_missing = missing
                
                # 더 가까운 타일인 경우 타겟 변경
                if noble_min_missing < min_global_missing:
                    min_global_missing = noble_min_missing
                    target_noble = noble

        # 선택된 귀족 획득
        player.tiles.append(target_noble)
        self.tiles.remove(target_noble)

    def step(self, action):
        """선택한 행동(action)을 실행하고 게임 상태를 업데이트함"""
        action_type = action['type']
        player = self.get_curr_player()
        
        # 토큰 버리기
        # discard_token : gem_idx(int)
        if action_type == 'discard_token':
            gem_idx = action['gem_idx']
            
            player.tokens[gem_idx] -= 1
            self.bank[gem_idx] += 1
            
            if player.token_count() <= 10:
                self.next_turn()
            return self.check_winner()

        # 토큰 가져오기
        # get_token : tokens(list[int])
        elif action_type == 'get_token':
            token_list = action['tokens']
            for i, count in enumerate(token_list):
                if count > 0:
                    player.tokens[i] += count
                    self.bank[i] -= count
        
        # 카드 구매 (오픈카드)
        # buy_card : card(Card), tier(int)
        elif action_type == 'buy_card':
            card = action['card']
            tier = action['tier']
            
            # 비용 지불
            self.pay_card(player,card)
            
            # 플레이어에게 카드 추가
            player.cards.append(card)
            
            # 보드에서 카드 제거하고 리필
            self.board[tier].remove(card)
            self.refill_board(tier)
                    
            # 귀족 체크
            self.check_nobles(player)
            
        # 카드 구매 (예약카드)
        # buy_reserved : card(Card)
        elif action_type == 'buy_reserved':
            card = action['card']
            
            # 비용 지불
            self.pay_card(player,card)
            
            # 플레이어에게 카드 추가
            player.cards.append(card)
            
            # 플레이어 예약 리스트에서 제거
            player.keeped.remove(card)
            
            # 귀족 체크
            self.check_nobles(player)
        
        # 카드 예약 (오픈카드)
        # reserve_card : card(Card), tier(int)
        # reserve_deck : tier(int)
        elif action_type in ['reserve_card', 'reserve_deck']:
            # 황금토큰이 남아있으면 추가
            if self.bank[5] > 0:
                player.tokens[5] += 1
                self.bank[5] -= 1
            
            if action_type == 'reserve_card':
                card = action['card']
                tier = action['tier']
                self.board[tier].remove(card)
                player.keeped.append(card)
                self.refill_board(tier)
                
            elif action_type == 'reserve_deck':
                tier = action['tier']
                card = self.decks[tier].pop(0)
                player.keeped.append(card)

        # do_nothing : 없음
        elif action_type == 'do_nothing':
            pass
        
        # 턴 종료 조건 확인
        if player.token_count() <= 10:
            self.next_turn()
        
        return self.check_winner()

    def next_turn(self):
        """턴 넘기기"""
        self.curr_player_idx = (self.curr_player_idx + 1) % len(self.players)
        self.turn_count += 1

    def check_winner(self):
        """승리 조건 체크 (15점 이상 & 라운드 종료)"""
        # 라운드가 다 돌았을 때(인덱스가 0)만 체크
        if self.curr_player_idx == 0:
            candidates = [p for p in self.players if p.points() >= 15]      # 15점 이상 플레이어
            if len(candidates) == 0:
                return None
            
            candidates.sort(key=lambda p: (
                -p.points(), 
                p.card_count(), 
                -p.token_count(), 
                -self.players.index(p)
            ))
            
            return candidates[0] # 1등 반환
        return None
    
    def clone(self):
        """시뮬레이션을 위해 현재 게임 상태를 통째로 복사"""
        return deepcopy(self)