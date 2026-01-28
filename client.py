import socket

class Network:
    def __init__(self):
        self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.host = ""
        self.port = 0
        self.addr = ()

    def connect(self, ip, port):
        try:
            self.client.connect((ip, port))
            return "Connected" # Dummy success message
        except socket.error as e:
            print(e)
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
            return data
        except BlockingIOError:
            return None # No data available
        except Exception as e:
            # print(f"Receive Error: {e}")
            return None

    def disconnect(self):
        try:
            self.client.close()
        except:
            pass
