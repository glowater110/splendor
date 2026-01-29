import socket

class Network:
    def __init__(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.host = ""
        self.port = 0
        self.addr = ()

    def connect(self, ip, port):
        try:
            self.client.settimeout(2.0) 
            self.client.connect((ip, port))
            
            # Handshake Verification
            data = self.client.recv(1024).decode('utf-8')
            if "Splendor" in data: # Simple check
                self.client.settimeout(None)
                return "Connected"
            else:
                print("Invalid Server Handshake")
                self.client.close()
                return None
                
        except socket.error as e:
            print(f"Connection Failed: {e}")
            return None

    def send(self, data):
        try:
            self.client.send(str.encode(data))
            # return self.client.recv(2048).decode('utf-8') 
            # Send does not wait for reply immediately anymore to allow async processing
            return True
        except socket.error as e:
            print(f"Socket Error: {e}")
            return None

    def receive(self):
        try:
            # Set to non-blocking mode temporarily
            self.client.setblocking(0)
            data = self.client.recv(4096).decode('utf-8')
            if not data: 
                return "DISCONNECT" # Empty string means server closed connection
            return data
        except BlockingIOError:
            return None # No data available
        except Exception as e:
            # print(f"Receive Error: {e}")
            return "DISCONNECT" # Error means connection lost

    def disconnect(self):
        try:
            self.client.close()
        except:
            pass
