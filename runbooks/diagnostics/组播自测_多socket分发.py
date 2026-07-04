#!/usr/bin/env python3
"""多socket组播分发自测:3个REUSEADDR接收者共享10317,发1包,看几个收到(gz场景复刻)"""
import socket, struct, threading, time

GRP, PORT = "239.255.0.7", 10317
results = {}

def rx(name):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except OSError:
        pass
    s.bind(("", PORT))
    mreq = struct.pack("4s4s", socket.inet_aton(GRP), socket.inet_aton("0.0.0.0"))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    s.settimeout(6)
    try:
        data, addr = s.recvfrom(1024)
        results[name] = addr
    except socket.timeout:
        results[name] = None

ths = [threading.Thread(target=rx, args=(f"rx{i}",)) for i in range(3)]
[t.start() for t in ths]
time.sleep(1)
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
tx.sendto(b"probe", (GRP, PORT))
[t.join() for t in ths]
ok = sum(1 for v in results.values() if v)
print(f"收到的接收者: {ok}/3  detail={results}")
print("VERDICT:", "ALL_OK" if ok == 3 else ("PARTIAL(分发bug)" if ok else "NONE(全聋)"))
