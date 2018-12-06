import threading
import hashlib
import socket
import base64
import json
import struct

clients = {}
serves = {}


def parse_recv_data(msg):
    v = msg[1] & 0x7f
    if v == 0x7e:
        p = 4
    elif v == 0x7f:
        p = 10
    else:
        p = 2
    mask = msg[p:p + 4]
    data = msg[p + 4:]
    bytes_list = bytearray()
    for i in range(len(data)):
        chunk = data[i] ^ mask[i % 4]
        bytes_list.append(chunk)
    return str(bytes_list, encoding="utf8", errors='ignore')


def parse_send_data(message):
    msgLen = len(message)
    backMsgList = []
    backMsgList.append(struct.pack('B', 129))

    if msgLen <= 125:
        backMsgList.append(struct.pack('b', msgLen))
    elif msgLen <= 65535:
        backMsgList.append(struct.pack('b', 126))
        backMsgList.append(struct.pack('>h', msgLen))
    elif msgLen <= (2 ^ 64 - 1):
        backMsgList.append(struct.pack('b', 127))
        backMsgList.append(struct.pack('>h', msgLen))
    else:
        print("the message is too long to send in a time")
        return
    message_byte = bytes()
    for c in backMsgList:
        message_byte += c
    message_byte += bytes(message, encoding="utf8")
    return message_byte


class clients_thread(threading.Thread):
    def __init__(self, connection, username, alive=1):
        super(clients_thread, self).__init__()
        self.connection = connection
        self.username = username
        self.alive = alive

    def run(self):
        while self.alive:
            try:
                data = self.connection.recv(2048)
            except socket.error as e:
                print("unexpected error: ", e)
                clients.pop(self.username)
                break
            if not data:
                continue
            data = parse_recv_data(data)
            message = 'server: %s : %s' % (self.username, data)
            print(message)
        print('user: %s has been quited!' % self.username)

    def notify(self, message, user_id):
        message = json.dumps(message)
        message_byte = parse_send_data(message)
        serves[user_id]['connection'].send(message_byte)


class server_thread(threading.Thread):
    def __init__(self, connection, username, alive=1):
        super(server_thread, self).__init__()
        self.connection = connection
        self.username = username
        self.alive = alive

    def run(self):
        while self.alive:
            try:
                data = self.connection.recv(2048)
            except socket.error as e:
                print("unexpected error: ", e)
                serves.pop(self.username)
                break
            if not data:
                continue
            data = parse_recv_data(data)
            message = 'server: %s : %s' % (self.username, data)
            print(message)
            re = 'this is server %s, hello world!' % self.username
            for k in clients:
                self.notify(re, k)
        print('user: %s has been quited!' % self.username)

    def notify(self, message, user_id):
        message = json.dumps(message)
        message_byte = parse_send_data(message)
        clients[user_id]['connection'].send(message_byte)


class websocket_server(threading.Thread):
    def __init__(self, port):
        super(websocket_server, self).__init__()
        self.port = port

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', self.port))
        sock.listen(5)
        print('websocket server started!')

        while True:
            connection, address = sock.accept()
            try:
                print('new websocket client joined!')
                data = connection.recv(2048)
                headers = self.parse_headers(str(data))
                print(headers)
                username = address[1]
                if headers['User-Agent'] == 'client':
                    if username in clients:
                        clients[username]['thread'].alive = 0
                        print('user: %s restart new thread!' % username)
                    token = self.generate_token(headers['Sec-WebSocket-Key'])
                    self.hand_shake(connection, token)
                    clients[username] = {}
                    clients[username]['connection'] = connection
                    clients[username]['thread'] = clients_thread(connection, username)
                    clients[username]['thread'].start()
                elif headers['User-Agent'] == 'server':
                    if username in serves:
                        serves[username]['thread'].alive = 0
                        print('user: %s restart new thread!' % username)
                    token = self.generate_token(headers['Sec-WebSocket-Key'])
                    self.hand_shake(connection, token)
                    serves[username] = {}
                    serves[username]['connection'] = connection
                    serves[username]['thread'] = server_thread(connection, username)
                    serves[username]['thread'].start()
            except socket.timeout:
                print('websocket connection timeout!')

    def hand_shake(self, connection, token):
        response_key_str = str(token)
        response_key_str = response_key_str[2:30]
        response_key_entity = "Sec-WebSocket-Accept: " + response_key_str + "\r\n"
        connection.send(bytes("HTTP/1.1 101 Web Socket Protocol Handshake\r\n", encoding="utf8"))
        connection.send(bytes("Upgrade: websocket\r\n", encoding="utf8"))
        connection.send(bytes(response_key_entity, encoding="utf8"))
        connection.send(bytes("Connection: Upgrade\r\n\r\n", encoding="utf8"))
        print("send the hand shake data")

    def parse_headers(self, msg):
        headers = {}
        data, header = msg.split('\\r\\n', 1)
        for line in header.split('\\r\\n'):
            try:
                key, value = line.split(': ', 1)
                headers[key] = value
            except:
                pass
        headers['data'] = data
        return headers

    def generate_token(self, msg):
        key = msg + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
        ser_key = hashlib.sha1(key.encode('utf8')).digest()
        return base64.b64encode(ser_key)


if __name__ == '__main__':
    server = websocket_server(10090)
    server.start()
