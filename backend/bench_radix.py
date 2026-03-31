#!/usr/bin/env python3
"""Benchmark script for trie-based LPM (single-threaded and multi-threaded reads).

Usage:
    python backend/bench_radix.py [prefix_count] [lookup_count]

Defaults: 20000 prefixes, 100000 lookups.
"""
import sys
import time
import random
from backend.simple_radix import build_index

PREFIX_COUNT = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
LOOKUP_COUNT = int(sys.argv[2]) if len(sys.argv) > 2 else 100000

# generate many /24 prefixes in 198.51.x.0/24 and some /25
pairs = []
for i in range(PREFIX_COUNT):
    a = 198
    b = 51
    c = i % 256
    plen = 24 if (i % 5) else 25
    prefix = f"{a}.{b}.{c}.0/{plen}"
    asn = 64500 + (i % 1000)
    pairs.append((prefix, asn, 'bench'))

print('Building index with', len(pairs), 'prefixes...')
start = time.perf_counter()
idx = build_index(pairs)
build_time = time.perf_counter() - start
print('Build time: %.3fs' % build_time)

# prepare lookup IPs
ips = []
for i in range(LOOKUP_COUNT):
    c = random.randint(0, 255)
    d = random.randint(1, 254)
    ips.append(f"198.51.{c}.{d}")

# single-threaded lookup
start = time.perf_counter()
found = 0
for ip in ips:
    node = idx.search_best(ip)
    if node:
        found += 1
st = time.perf_counter() - start
print('Single-threaded: lookups=%d time=%.3fs qps=%.0f found=%d' % (LOOKUP_COUNT, st, LOOKUP_COUNT / st if st>0 else 0, found))

# multi-threaded readers
import threading

THREADS = 8
per = LOOKUP_COUNT // THREADS

def worker(sub):
    c = 0
    for ip in sub:
        if idx.search_best(ip):
            c += 1
    return c

subs = [ips[i*per:(i+1)*per] for i in range(THREADS)]
threads = []
start = time.perf_counter()
results = [0] * THREADS
for i in range(THREADS):
    def run(i=i):
        results[i] = worker(subs[i])
    t = threading.Thread(target=run)
    threads.append(t)
    t.start()
for t in threads:
    t.join()
mt = time.perf_counter() - start
print('Multi-threaded (%d threads): time=%.3fs qps=%.0f total_found=%d' % (THREADS, mt, LOOKUP_COUNT / mt if mt>0 else 0, sum(results)))
