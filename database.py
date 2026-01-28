import sqlite3
import hashlib
import os

DB_NAME = "users.db"

def hash_password(password):
    """
    Hashes a password using SHA-256 with a simple salt.
    In production, use 'bcrypt' or 'scrypt' and unique salts per user.
    """
    salt = "splendor_secure_salt_" # Static salt for simplicity in this demo
    return hashlib.sha256((salt + password).encode()).hexdigest()

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Create users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized.")

def register_user(username, password):
    """
    Registers a new user. Returns True if successful, False if username exists.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    pwd_hash = hash_password(password)
    
    try:
        # SECURE: Using '?' placeholder prevents SQL Injection
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, pwd_hash))
        conn.commit()
        return True, "Registration successful"
    except sqlite3.IntegrityError:
        return False, "Username already exists"
    except Exception as e:
        return False, f"Error: {e}"
    finally:
        conn.close()

def verify_user(username, password):
    """
    Verifies credentials. Returns True if valid.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    pwd_hash = hash_password(password)
    
    # SECURE: Using '?' placeholder
    c.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    
    if row:
        stored_hash = row[0]
        if stored_hash == pwd_hash:
            return True, "Login successful"
        else:
            return False, "Invalid password"
    else:
        return False, "User not found"
