import socket

class Network:
    def __init__(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.host = ""
        self.port = 0
        self.addr = ()

    def connect(self, host, port):
        self.host = host
        self.port = port
        self.addr = (self.host, self.port)
        try:
            self.client.connect(self.addr)
            # Receive the welcome message from the server
            return self.client.recv(2048).decode('utf-8')
        except Exception as e:
            print(f"Connection Error: {e}")
            return None

    def send(self, data):
        try:
            self.client.send(str.encode(data))
            return self.client.recv(2048).decode('utf-8')
        except socket.error as e:
            print(f"Socket Error: {e}")
            return None

    def disconnect(self):
        try:
            self.client.close()
        except:
            pass
