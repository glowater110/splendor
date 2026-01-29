import os
import glob
import numpy as np
import torch
from sb3_contrib import MaskablePPO

def extract_weights(model_path, output_path):
    print(f"Processing {model_path}...")
    model = MaskablePPO.load(model_path)
    
    # Access the internal neural network (Policy)
    # Structure: features_extractor -> mlp_extractor -> action_net
    # We assume a standard MlpPolicy structure
    
    params = {}
    
    # 1. Feature Extractor (usually identity, but let's check)
    # SB3 Default: Flatten -> Linear layers
    
    # We need to extract weights from the shared net or separate actor/critic
    # MaskablePPO uses ActorCriticPolicy.
    # We only care about the ACTOR (Action Net) for inference.
    
    # Iterate named parameters to find actor weights
    # Typical names: mlp_extractor.policy_net.0.weight, mlp_extractor.policy_net.0.bias, ... action_net.weight
    
    policy = model.policy
    
    # Helper to convert torch tensor to numpy
    def to_np(tensor):
        return tensor.detach().cpu().numpy()

    # Extract Policy Network (Actor)
    # Layer 0
    params['fc0_w'] = to_np(policy.mlp_extractor.policy_net[0].weight).T # Transpose for x @ W
    params['fc0_b'] = to_np(policy.mlp_extractor.policy_net[0].bias)
    
    # Layer 2 (Layer 1 is Tanh usually)
    params['fc1_w'] = to_np(policy.mlp_extractor.policy_net[2].weight).T
    params['fc1_b'] = to_np(policy.mlp_extractor.policy_net[2].bias)
    
    # Action Net (Output)
    params['act_w'] = to_np(policy.action_net.weight).T
    params['act_b'] = to_np(policy.action_net.bias)
    
    print(f"Extracted weights shapes:")
    print(f"  FC0: {params['fc0_w'].shape}")
    print(f"  FC1: {params['fc1_w'].shape}")
    print(f"  ACT: {params['act_w'].shape}")
    
    np.savez_compressed(output_path, **params)
    print(f"Saved to {output_path}")

def main():
    if not os.path.exists("models"):
        print("Error: 'models' folder not found.")
        return

    files = glob.glob("models/*.zip")
    if not files:
        print("No .zip models found.")
        return

    for zip_file in files:
        npz_file = os.path.splitext(zip_file)[0] + ".npz"
        try:
            extract_weights(zip_file, npz_file)
        except Exception as e:
            print(f"Failed to convert {zip_file}: {e}")

if __name__ == "__main__":
    main()
