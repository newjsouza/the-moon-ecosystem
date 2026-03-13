"""
learning/reinforcement.py
Reinforcement learning logic for agent decision making.
"""
import numpy as np
from typing import Dict, Any, Tuple
import time

class ReinforcementLearner:
    def __init__(self, learning_rate: float = 0.1, discount_factor: float = 0.95, exploration_decay: float = 0.995):
        self.lr = learning_rate
        self.gamma = discount_factor
        self.epsilon_decay = exploration_decay
        self.epsilon = 1.0
        self.q_table: Dict[str, Dict[str, float]] = {}
        self.history = []

    def get_action(self, state: str, available_actions: list[str]) -> str:
        if np.random.rand() < self.epsilon:
            return np.random.choice(available_actions)
            
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in available_actions}
            return np.random.choice(available_actions)
            
        action_values = self.q_table[state]
        return max(available_actions, key=lambda a: action_values.get(a, 0.0))

    def update_q_value(self, state: str, action: str, reward: float, next_state: str, next_actions: list[str]):
        if state not in self.q_table:
            self.q_table[state] = {}
        if action not in self.q_table[state]:
            self.q_table[state][action] = 0.0
            
        current_q = self.q_table[state][action]
        
        if next_state not in self.q_table:
            max_next_q = 0.0
        else:
            max_next_q = max([self.q_table[next_state].get(a, 0.0) for a in next_actions], default=0.0)
            
        new_q = current_q + self.lr * (reward + self.gamma * max_next_q - current_q)
        self.q_table[state][action] = new_q
        
        self.epsilon = max(0.01, self.epsilon * self.epsilon_decay)
        self.history.append({"state": state, "action": action, "reward": reward, "time": time.time()})
