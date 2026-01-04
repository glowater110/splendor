from splendor_env_4p_p1g1 import SplendorEnv4PP1G1
from sb3_contrib import MaskablePPO
from sb3_contrib.common.maskable.utils import get_action_masks
from stable_baselines3.common.monitor import Monitor
import os

# 0. Get model name from user
model_name = input("Enter a name for the trained model (default: ai_4p_p1g1): ").strip()
if not model_name:
    model_name = "ai_4p_p1g1"

# Create log directory
log_dir = f"logs_{model_name}/"
os.makedirs(log_dir, exist_ok=True)

# 1. Initialize Environment
env = SplendorEnv4PP1G1(num_players=4)
env = Monitor(env, log_dir)

# 2. Initialize Agent
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