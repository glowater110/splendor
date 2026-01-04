import socket
import threading
import json
import time
import uuid

class Room:
    def __init__(self, room_id, name, host_id, max_players=4):
        self.id = room_id
        self.name = name
        self.host_id = host_id
        self.max_players = max_players
        self.players = [host_id]  # List of player_ids
        self.game_started = False
        # self.game_state = None  # Will hold the Game object later

    def add_player(self, player_id):
        if len(self.players) < self.max_players and not self.game_started:
            self.players.append(player_id)
            return True
        return False

    def remove_player(self, player_id):
        if player_id in self.players:
            self.players.remove(player_id)
            return True
        return False

    def is_full(self):
        return len(self.players) >= self.max_players

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host_id,
            "players": self.players,
            "max_players": self.max_players,
            "started": self.game_started
        }

class SplendorServer:
    def __init__(self, host="0.0.0.0", port=5555):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.rooms = {}  # {room_id: Room}
        self.clients = {}  # {player_id: {"conn": conn, "addr": addr, "room_id": None}}
        self.lock = threading.Lock()

    def start(self):
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen()
            print(f"Server started on {self.host}:{self.port}")
            while True:
                conn, addr = self.server_socket.accept()
                thread = threading.Thread(target=self.handle_client, args=(conn, addr))
                thread.start()
                print(f"Active Connections: {threading.active_count() - 1}")
        except Exception as e:
            print(f"Server Error: {e}")
        finally:
            self.server_socket.close()

    def handle_client(self, conn, addr):
        print(f"New connection from {addr}")
        player_id = None
        
        # 1. Handshake (Receive Name)
        try:
            name_data = conn.recv(1024).decode('utf-8')
            if not name_data:
                return
            
            # Simple unique ID generation: Name + timestamp suffix to avoid collisions
            # In a real app, we'd use a better ID system.
            raw_name = name_data.strip()
            player_id = f"{raw_name}_{uuid.uuid4().hex[:4]}"
            
            with self.lock:
                self.clients[player_id] = {"conn": conn, "addr": addr, "room_id": None, "name": raw_name}
            
            # Send back the assigned ID confirmation
            conn.send(json.dumps({"type": "WELCOME", "player_id": player_id, "message": "Connected to Lobby"}).encode('utf-8'))
            
        except Exception as e:
            print(f"Handshake Error: {e}")
            conn.close()
            return

        # 2. Main Loop
        while True:
            try:
                data = conn.recv(4096).decode('utf-8')
                if not data:
                    break
                
                request = json.loads(data)
                self.process_request(player_id, request)

            except json.JSONDecodeError:
                print(f"Invalid JSON from {player_id}")
            except ConnectionResetError:
                break
            except Exception as e:
                print(f"Error handling client {player_id}: {e}")
                break

        # 3. Disconnect Cleanup
        print(f"Client {player_id} disconnected.")
        self.handle_disconnect(player_id)
        conn.close()

    def process_request(self, player_id, request):
        cmd = request.get("type")
        conn = self.clients[player_id]["conn"]
        
        response = {"type": "ERROR", "message": "Unknown Command"}

        with self.lock:
            if cmd == "GET_ROOMS":
                room_list = [r.to_dict() for r in self.rooms.values()]
                response = {"type": "ROOM_LIST", "rooms": room_list}

            elif cmd == "CREATE_ROOM":
                room_name = request.get("name", "New Room")
                max_p = request.get("max_players", 4)
                
                # Check if player is already in a room
                if self.clients[player_id]["room_id"]:
                    response = {"type": "ERROR", "message": "Already in a room"}
                else:
                    room_id = str(uuid.uuid4())[:8]
                    new_room = Room(room_id, room_name, player_id, max_p)
                    self.rooms[room_id] = new_room
                    self.clients[player_id]["room_id"] = room_id
                    
                    response = {"type": "ROOM_CREATED", "room": new_room.to_dict()}
                    print(f"Room created: {room_name} ({room_id}) by {player_id}")

            elif cmd == "JOIN_ROOM":
                room_id = request.get("room_id")
                room = self.rooms.get(room_id)
                
                if not room:
                    response = {"type": "ERROR", "message": "Room not found"}
                elif self.clients[player_id]["room_id"]:
                    response = {"type": "ERROR", "message": "Already in a room"}
                elif room.is_full():
                    response = {"type": "ERROR", "message": "Room is full"}
                elif room.game_started:
                    response = {"type": "ERROR", "message": "Game already started"}
                else:
                    room.add_player(player_id)
                    self.clients[player_id]["room_id"] = room_id
                    response = {"type": "JOINED_ROOM", "room": room.to_dict()}
                    
                    # Notify other players in the room (Broadcast)
                    self.broadcast_to_room(room_id, {"type": "PLAYER_JOINED", "player_id": player_id, "room": room.to_dict()})

            elif cmd == "LEAVE_ROOM":
                self.handle_leave_room(player_id)
                response = {"type": "LEFT_ROOM"}

        # Send strictly to the requester (Broadcasts handled separately)
        try:
            conn.send(json.dumps(response).encode('utf-8'))
        except:
            pass

    def handle_leave_room(self, player_id):
        # Assumes lock is acquired OR called from thread-safe context
        client_data = self.clients.get(player_id)
        if not client_data: return

        room_id = client_data["room_id"]
        if room_id and room_id in self.rooms:
            room = self.rooms[room_id]
            room.remove_player(player_id)
            client_data["room_id"] = None
            
            print(f"{player_id} left room {room_id}")
            
            # If room empty, delete it
            if len(room.players) == 0:
                del self.rooms[room_id]
                print(f"Room {room_id} deleted (empty)")
            else:
                # If host left, assign new host
                if room.host_id == player_id:
                    room.host_id = room.players[0]
                    self.broadcast_to_room(room_id, {"type": "HOST_CHANGED", "new_host": room.host_id})
                
                # Notify others
                self.broadcast_to_room(room_id, {"type": "PLAYER_LEFT", "player_id": player_id, "room": room.to_dict()})

    def handle_disconnect(self, player_id):
        with self.lock:
            if player_id in self.clients:
                self.handle_leave_room(player_id)
                del self.clients[player_id]

    def broadcast_to_room(self, room_id, message_dict):
        # Assumes lock is acquired
        room = self.rooms.get(room_id)
        if not room: return
        
        msg_bytes = json.dumps(message_dict).encode('utf-8')
        
        for pid in room.players:
            client = self.clients.get(pid)
            if client and client["conn"]:
                try:
                    client["conn"].send(msg_bytes)
                except:
                    pass

if __name__ == "__main__":
    server = SplendorServer()
    server.start()