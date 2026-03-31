"""Pure-Python prefix trie implementation for LPM (binary trie).

This builds two separate binary tries (IPv4 / IPv6). Each trie node
may store a `data` dict when a prefix terminates on that node. The
search traverses bits from most-significant to least, remembering the
last node that contained data to implement LPM efficiently.
"""
from ipaddress import ip_network, ip_address
from typing import Dict, Any, Optional, Tuple
import threading


class ReadWriteLock:
    """A simple readers-writer lock.

    Multiple concurrent readers allowed; writers are exclusive.
    """
    def __init__(self):
        self._read_ready = threading.Condition(threading.Lock())
        self._readers = 0

    def acquire_read(self):
        with self._read_ready:
            self._readers += 1

    def release_read(self):
        with self._read_ready:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notify_all()

    def acquire_write(self):
        self._read_ready.acquire()
        while self._readers > 0:
            self._read_ready.wait()

    def release_write(self):
        try:
            self._read_ready.release()
        except RuntimeError:
            pass


class _TrieNode:
    __slots__ = ("child0", "child1", "data", "prefix")

    def __init__(self):
        self.child0 = None
        self.child1 = None
        self.data: Dict[str, Any] = {}
        self.prefix: Optional[str] = None


class Radix:
    def __init__(self):
        # separate roots for v4 and v6
        self._root4 = _TrieNode()
        self._root6 = _TrieNode()
        # read-write lock for concurrency (read-heavy workloads)
        self._rw = ReadWriteLock()

    def _get_root_and_bits(self, net) -> Tuple[_TrieNode, int, int]:
        if net.version == 4:
            return self._root4, 32, net.prefixlen
        return self._root6, 128, net.prefixlen

    def add(self, prefix: str):
        net = ip_network(prefix, strict=False)
        root, total_bits, plen = self._get_root_and_bits(net)
        addr = int(net.network_address)
        # writers should acquire exclusive access
        self._rw.acquire_write()
        try:
            node = root
            # traverse bits from MSB to prefixlen
            for i in range(plen):
                shift = total_bits - 1 - i
                bit = (addr >> shift) & 1
                if bit == 0:
                    if node.child0 is None:
                        node.child0 = _TrieNode()
                    node = node.child0
                else:
                    if node.child1 is None:
                        node.child1 = _TrieNode()
                    node = node.child1
            node.prefix = str(net)
            return node
        finally:
            self._rw.release_write()

    def search_best(self, ip_str: str) -> Optional[_TrieNode]:
        try:
            ip = ip_address(ip_str)
        except Exception:
            return None
        addr = int(ip)
        if ip.version == 4:
            root = self._root4
            total_bits = 32
        else:
            root = self._root6
            total_bits = 128
        # readers acquire shared access
        self._rw.acquire_read()
        try:
            node = root
            best: Optional[_TrieNode] = None
            for i in range(total_bits):
                if node is None:
                    break
                if node.prefix is not None:
                    best = node
                shift = total_bits - 1 - i
                bit = (addr >> shift) & 1
                node = node.child1 if bit else node.child0
            # final check
            if node and node.prefix is not None:
                best = node
            return best
        finally:
            self._rw.release_read()


def build_index(pairs):
    r = Radix()
    for prefix, asn, source in pairs:
        try:
            node = r.add(prefix)
            node.data['asn'] = asn
            if source is not None:
                node.data['source'] = source
        except Exception:
            continue
    return r
