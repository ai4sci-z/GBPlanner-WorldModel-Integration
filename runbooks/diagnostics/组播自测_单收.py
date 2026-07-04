#!/usr/bin/env python3
"""WSL host netns 组播自测:能否在 239.255.0.7:10317(gz-transport 同款)收到自己发的组播"""
import socket, struct, threading, time, sys

GRP, PORT = "239.255.0.7", 10317
got = []

def rx():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", PORT))
    mreq = struct.pack("4s4s", socket.inet_aton(GRP), socket.inet_aton("0.0.0.0"))
    s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    s.settimeout(6)
    try:
        data, addr = s.recvfrom(1024)
        got.append((data, addr))
    except socket.timeout:
        pass

t = threading.Thread(target=rx); t.start()
time.sleep(1)
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
tx.sendto(b"gz-mcast-probe", (GRP, PORT))
t.join()
print("MULTICAST_OK" if got else "MULTICAST_BROKEN", got[:1])
