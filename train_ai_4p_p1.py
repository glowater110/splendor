from splendor_env_4p_p1 import SplendorEnv4PP1
from sb3_contrib import MaskablePPO
from stable_baselines3.common.monitor import Monitor
import os

# 0. Configuration
print("--- Splendor Policy 1 Training Master ---")
opp_name = input("Enter OPPONENT model name (leave empty for 'random'): ").strip()
if not opp_name:
    opp_name = "random"
    opp_path = "random"
else:
    opp_path = f"models/{opp_name}.zip"

model_name = input("Enter name for the NEW trained model: ").strip()
if not model_name:
    model_name = "ai_4p_p1_new"

start_model = input("Enter name of model to load WEIGHTS from (optional): ").strip()

# Create log directory
log_dir = f"logs_{model_name}/"
os.makedirs(log_dir, exist_ok=True)

# 1. Initialize Environment
env = SplendorEnv4PP1(num_players=4, opponent_model_path=opp_path)
env = Monitor(env, log_dir)

# 2. Initialize Agent
if start_model:
    start_path = f"models/{start_model}.zip" if not start_model.endswith(".zip") else f"models/{start_model}"
    print(f"Loading starting weights from {start_path}...")
    try:
        model = MaskablePPO.load(
            start_path,
            env=env,
            learning_rate=3e-4,
            batch_size=64,
            gamma=0.99,
            verbose=1,
            tensorboard_log=log_dir
        )
    except Exception as e:
        print(f"Failed to load weights: {e}. Starting from scratch.")
        model = MaskablePPO("MlpPolicy", env, verbose=1, tensorboard_log=log_dir)
else:
    print("Initializing agent from scratch...")
    model = MaskablePPO(
        "MlpPolicy",
        env,
        learning_rate=3e-4,
        batch_size=64,
        n_steps=2048,
        ent_coef=0.01,
        gamma=0.99,
        verbose=1,
        tensorboard_log=log_dir
    )
# 3. Train
print(f"Starting training: {model_name} (against {opp_name})")
TIMESTEPS = 200000
model.learn(total_timesteps=TIMESTEPS)

# 4. Save Model
model.save(f"models/{model_name}")
print(f"\nTraining finished. Model saved as models/{model_name}.zip")
