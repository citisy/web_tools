import threading
import hashlib
import socket
import base64
import json
import struct

clients = {}
serves = {}


def parse_recv_data(msg):
    """
    https://www.cnblogs.com/JetpropelledSnake/p/9033064.html
    报文格式：
    1.FIN: 占 1bit
        0：不是消息的最后一个分片
        1：是消息的最后一个分片

    2.RSV1, RSV2, RSV3：各占 1bit，共3bit
        一般情况下全为 0。当客户端、服务端协商采用 WebSocket 扩展时，这三个标志位可以非 0，且值的含义由扩展进行定义。如果出现非零的值，且并没有采用 WebSocket 扩展，连接出错。
    3.Opcode: 4bit
        \x0：表示一个延续帧。当 Opcode 为 0 时，表示本次数据传输采用了数据分片，当前收到的数据帧为其中一个数据分片；
        \x1：表示这是一个文本帧（text frame）；
        \x2：表示这是一个二进制帧（binary frame）；
        \x3-7：保留的操作代码，用于后续定义的非控制帧；
        \x8：表示连接断开；
        \x9：表示这是一个心跳请求（ping）；
        \xA：表示这是一个心跳响应（pong）；
        \xB-F：保留的操作代码，用于后续定义的控制帧。

    4.Mask: 1bit
        表示是否要对数据载荷进行掩码异或操作。
        0：否
        1：是

    5.Payload length: 7bit or (7 + 16)bit or (7 + 64)bit
        表示数据载荷的长度。
        0~126：数据的长度等于该值；
        126：后续 2 个字节代表一个 16 位的无符号整数，该无符号整数的值为数据的长度；
        127：后续 8 个字节代表一个 64 位的无符号整数（最高位为 0），该无符号整数的值为数据的长度。

    6.Masking-key: 0 or 4bytes
        当 Mask 为 1，则携带了 4 字节的 Masking-key；
        当 Mask 为 0，则没有 Masking-key。
        掩码算法：按位做循环异或运算，先对该位的索引取模来获得 Masking-key 中对应的值 x，然后对该位与 x 做异或，从而得到真实的 byte 数据。
        注意：掩码的作用并不是为了防止数据泄密，而是为了防止早期版本的协议中存在的代理缓存污染攻击（proxy cache poisoning attacks）等问题。

    7.Payload Data: 载荷数据

    eg:
        现有一个待解析报文，（8bit=1Byte）
        * 一开始的8bit为报文类型标志位，常用的有
            1000 0001 即129代表字符串数据
            1000 0002 即130代表字节流数据
        * 接着的报文消息长度标志位是变长的，第一位通常为1，可以舍弃
          故先和\x7f进行与操作取后7位，由前7位决定该标志位的长度，
          譬如：
            消息长度是127，则与运算后值为126，
            根据126确定再取2个字节即16位，可以得到\x00\x7f，即127
        * 接着是掩码部分，为4个字节，一般字符编码成字节都会带上
          根据解码规则用掩码即可对数据进行解码
        """
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
    """
    Format	C Type	            Python type	        Standard size
        x	pad byte	        no value
        c	char	            string of length 1	1
        b	signed char	        integer	            1
        B	unsigned char	    integer	            1
        ?	_Bool	            bool	            1
        h	short	            integer	            2
        H	unsigned short	    integer	            2
        i	int	                integer	            4
        I	unsigned int	    integer	            4
        l	long	            integer	            4
        L	unsigned long	    integer	            4
        q	long long	        integer	            8
        Q	unsigned long long	integer         	8
        f	float	            float	            4
        d	double	            float	            8
        s	char[]	            string
        p	char[]	            string
        P	void *	            integer
    """
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
        # send separately or together? seems it's same.
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
