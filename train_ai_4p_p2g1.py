from splendor_env_4p_p2g1 import SplendorEnv4PP2G1
from sb3_contrib import MaskablePPO
from stable_baselines3.common.monitor import Monitor
import os

# 0. Get names from user
model_name = input("Enter a name for the trained model (P2G1) (default: ai_4p_p2g1): ").strip()
if not model_name:
    model_name = "ai_4p_p2g1"

start_model = input("Enter a name for the STARTING model (leave empty to start from scratch): ").strip()

# Create log directory
log_dir = f"logs_{model_name}/"
os.makedirs(log_dir, exist_ok=True)

# 1. Initialize Environment
env = SplendorEnv4PP2G1(num_players=4)
env = Monitor(env, log_dir)

# 2. Initialize Agent
if start_model:
    print(f"Loading starting weights from models/{start_model}...")
    model = MaskablePPO.load(
        f"models/{start_model}",
        env=env,
        learning_rate=3e-4,
        batch_size=64,
        gamma=0.99,
        verbose=1,
        tensorboard_log=log_dir
    )
else:
    print("Initializing agent from scratch...")
    model = MaskablePPO(
        "MlpPolicy",
        env,
        learning_rate=3e-4,
        batch_size=64,
        gamma=0.99,
        verbose=1,
        tensorboard_log=log_dir
    )

# 3. Train
print(f"Starting training for {model_name}...")
TIMESTEPS = 200000
model.learn(total_timesteps=TIMESTEPS)

# 4. Save Model
model.save(f"models/{model_name}")
print(f"\nTraining finished. Model saved as models/{model_name}.zip")
