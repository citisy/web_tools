import requests
import socket
import json


def get_public_ip1():
    r = requests.get('http://ip.42.pl/raw')
    return r.text


def get_public_ip2():
    r = requests.get('http://jsonip.com')
    # r = requests.get('https://api.ipify.org/?format=json')
    return json.loads(r.text)['ip']


def get_public_ip3():
    r = requests.get('http://httpbin.org/ip')
    return json.loads(r.text)['origin']


def get_intranet_ip1():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))      # dns server address
        ip = s.getsockname()[0]
        return ip
    finally:
        s.close()

def get_intranet_ip2():
    addrs = socket.getaddrinfo(socket.gethostname(), None)
    for item in addrs:
        if ':' not in item[4][0]:
            return item[4][0]


if __name__ == '__main__':
    # print(get_public_ip1())
    # print(get_public_ip2())
    # print(get_public_ip3())
    # print(get_intranet_ip1())
    print(get_intranet_ip2())
