import bisect
import hashlib


class Ring:
    """Consistent hash ring. Har group ke 100 virtual points ring pe."""
    def __init__(self, groups, vnodes=100):
        self.ring = sorted((self._h(f"{g}#{i}"), g) for g in groups for i in range(vnodes))
        self.keys = [h for h, _ in self.ring]

    @staticmethod
    def _h(s):
        return int(hashlib.sha256(s.encode()).hexdigest(), 16)

    def get(self, key):
        i = bisect.bisect(self.keys, self._h(key)) % len(self.ring)  # clockwise pehla point
        return self.ring[i][1]