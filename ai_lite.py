import numpy as np

class LiteModel:
    def __init__(self, npz_path):
        data = np.load(npz_path)
        self.fc0_w = data['fc0_w']
        self.fc0_b = data['fc0_b']
        self.fc1_w = data['fc1_w']
        self.fc1_b = data['fc1_b']
        self.act_w = data['act_w']
        self.act_b = data['act_b']
        
    def predict(self, obs, action_masks=None, deterministic=True):
        # Neural Network Forward Pass (MLP)
        # Layer 0
        x = np.tanh(obs @ self.fc0_w + self.fc0_b)
        
        # Layer 1
        x = np.tanh(x @ self.fc1_w + self.fc1_b)
        
        # Output Layer (Logits)
        logits = x @ self.act_w + self.act_b
        
        # Apply Action Mask
        if action_masks is not None:
            # Set invalid actions to a very small number (effectively -inf)
            HUGE_NEG = -1e8
            # Assuming action_masks is boolean or 0/1 where 1 is valid
            # In SB3, mask=True means Valid.
            # We want to keep valid logits, and squash invalid ones.
            
            # Mask: [T, T, F, ...] -> [0, 0, -inf, ...]
            # We construct a mask_penalty array
            mask_penalty = np.where(action_masks, 0.0, HUGE_NEG)
            logits += mask_penalty
            
        # Select Action (Argmax for deterministic)
        action_idx = np.argmax(logits)
        
        return action_idx, None # Return format matching SB3 (action, state)
