#!/usr/bin/env python3
"""监听 239.255.0.7:10317 组播 15 秒,统计 gz discovery 流量(谁在发/发了啥开头)"""
import socket, struct, time, collections

GRP, PORT = "239.255.0.7", 10317
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
except OSError:
    pass
s.bind(("", PORT))
mreq = struct.pack("4s4s", socket.inet_aton(GRP), socket.inet_aton("0.0.0.0"))
s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
s.settimeout(0.5)

count = collections.Counter()
samples = {}
end = time.time() + 15
while time.time() < end:
    try:
        data, addr = s.recvfrom(2048)
        count[addr] += 1
        if addr not in samples:
            samples[addr] = data[:60]
    except socket.timeout:
        pass

print(f"15秒内收到 {sum(count.values())} 个包,来源 {len(count)} 个:")
for addr, n in count.most_common(8):
    print(f"  {addr}  x{n}  head={samples[addr][:40]!r}")
if not count:
    print("!!! 零流量:gz 进程根本没在这个组播组上发 discovery !!!")
