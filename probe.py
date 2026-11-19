# 排障探针：先看教师机 fps，再自己收流统计帧数，然后再看一次 fps
import http.client
import sys
import time
from urllib.parse import quote

ip, port, key = sys.argv[1], int(sys.argv[2]), sys.argv[3]


def policy():
    c = http.client.HTTPConnection(ip, port, timeout=5)
    c.request("GET", f"/policy?key={quote(key)}")
    r = c.getresponse()
    body = r.read().decode()
    c.close()
    return body


def stream(seconds):
    c = http.client.HTTPConnection(ip, port, timeout=8)
    c.request("GET", f"/stream?key={quote(key)}")
    r = c.getresponse()
    print("status", r.status, r.getheader("Content-Type"))
    buf = bytearray()
    n = 0
    end = time.time() + seconds

    def fill():
        d = r.read1(1 << 16)
        if not d:
            raise ConnectionError("eof")
        buf.extend(d)

    while time.time() < end:
        while True:
            j = buf.find(b"Content-Length: ")
            if j < 0:
                fill()
                continue
            k = j + len(b"Content-Length: ")
            ln = int(buf[k:k + 8].split(b"\r\n")[0])
            while len(buf) < k + ln:
                fill()
            n += 1
            del buf[:k + ln]
            break
    c.close()
    return n


for i in range(4):
    print("policy", policy())
    time.sleep(1)
print("stream frames:", stream(6))
print("policy after:", policy())
