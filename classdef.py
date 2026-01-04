# 게임에 필요한 요소를 정의한 파일
from enum import Enum

# 보석
class Gem(Enum):
    DIAMOND = 0
    SAPPHIRE = 1
    EMERALD = 2
    RUBY = 3
    ONYX = 4
    GOLD = 5

# 카드
class Card:
    def __init__(self, points:int, gem:Gem, cost:list[int]):
        self.points = points
        self.gem = gem
        self.cost = cost

# 귀족타일
class Tile:
    def __init__(self, cost:list[int]):
        self.points = 3
        self.cost = cost

# 플레이어
class Player:
    def __init__(self, name:str=''):
        self.name = name                # 플레이어 이름
        self.cards:list[Card] = []      # 플레이어가 구매한 카드
        self.keeped:list[Card] = []     # 플레이어가 예약한 카드
        self.tiles:list[Tile] = []      # 플레이어가 소유한 타일
        self.tokens = [0,0,0,0,0,0]     # 플레이어가 소유한 토큰 (황금 제외)
    
    def __repr__(self):
        return f'{self.name} [{self.points()} pts]'
    
    def points(self):
        pts = 0
        for c in self.cards:
            pts += c.points
        for t in self.tiles:
            pts += t.points
        return pts
    
    def set_name(self, name):
        self.name = name
    
    def card_gem(self):
        res = [0,0,0,0,0]
        for c in self.cards:
            res[c.gem.value] += 1
        return res
    
    def token_count(self):
        return sum(self.tokens)
    
    def card_count(self):
        return len(self.cards)
    
    def can_reserve_card(self):
        return True if len(self.keeped) < 3 else False
    
    def can_buy(self, card:Card):
        shortage = 0
        for i in range(5):
            cost = card.cost[i]
            have = self.tokens[i] + self.card_gem()[i]
            if cost > have: shortage += (cost - have)
        return self.tokens[5] >= shortage
    