import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from .states import Nodestate


@dataclass
class LogEntry:
    term: int
    command: str


def _new_timeout() -> int:
    # ticks mein (1 tick = 0.1s in rpc.py ticker) -> 0.5s .. 1.0s
    return random.randint(5, 10)


class RaftNode:
    def __init__(self, node_id: str, peer_ids: list[str]):
        self.node_id = node_id
        self.peer_ids = peer_ids
        self.peers: dict[str, "RaftNode"] = {}

        self.state = Nodestate.FOLLOWER
        self.current_term = 0
        self.voted_for: str | None = None
        self.votes: set[str] = set()
        self.log = [LogEntry(0, "")]   # index 0 sentinel
        self.commit_index = 0
        self.last_applied = 0          # state machine pe kahan tak apply hua
        self._pool = None
        self.apply_errors = {}         # log index -> SQL error (sirf jahan sm ne reject kiya)
        self.sm = None                 # state machine, koi bhi object jisme apply(cmd) ho
        self.next_index = {}
        self.match_index = {}

        self.alive = True
        self.elapsed = 0
        self.timeout = _new_timeout()

    def connect_peers(self, peers: dict[str, "RaftNode"]):
        self.peers = peers

    def majority(self) -> int:
        return (len(self.peer_ids) + 1) // 2 + 1

    def _step_down(self, term: int):
        self.state = Nodestate.FOLLOWER
        self.current_term = term
        self.voted_for = None
        self.votes = set()

    def handle_request_vote(self, term, candidate_id, last_log_index=0, last_log_term=0):
        if term < self.current_term:
            return self.current_term, False
        if term > self.current_term:
            self._step_down(term)
        ok = (last_log_term, last_log_index) >= (self.log[-1].term, len(self.log) - 1)
        if ok and (self.voted_for is None or self.voted_for == candidate_id):
            self.voted_for = candidate_id
            self.elapsed = 0
            return self.current_term, True
        return self.current_term, False

    def start_election(self):
        self.current_term += 1
        self.state = Nodestate.CANDIDATE
        self.voted_for = self.node_id
        self.votes = {self.node_id}
        for pid in self.peer_ids:
            if not self.peers[pid].alive:
                continue
            try:
                term, granted = self.peers[pid].handle_request_vote(
                    self.current_term, self.node_id, len(self.log) - 1, self.log[-1].term)
            except OSError:
                continue
            if term > self.current_term:
                self._step_down(term)
                return
            if granted:
                self.votes.add(pid)
        if len(self.votes) >= self.majority():
            self.state = Nodestate.LEADER
            self.next_index = {p: len(self.log) for p in self.peer_ids}
            self.match_index = {p: 0 for p in self.peer_ids}
            self.log.append(LogEntry(self.current_term, "NOOP"))

    def handle_append_entries(self, term, leader_id, prev_idx, prev_term, entries, leader_commit):
        if term < self.current_term:
            return self.current_term, False
        if term > self.current_term:
            self._step_down(term)
        self.state = Nodestate.FOLLOWER
        self.elapsed = 0
        if prev_idx >= len(self.log) or self.log[prev_idx].term != prev_term:
            return self.current_term, False
        for i, e in enumerate(entries):
            idx = prev_idx + 1 + i
            if idx < len(self.log) and self.log[idx].term != e.term:
                del self.log[idx:]
            if idx >= len(self.log):
                self.log.append(e)
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, prev_idx + len(entries))
        return self.current_term, True

    def client_append(self, cmd):
        """Log me append, replicate NAHI. Entry ka index return, leader nahi to None.
        Group commit ke liye: kai appends ke baad ek replicate()."""
        if self.state != Nodestate.LEADER:
            return None
        self.log.append(LogEntry(self.current_term, cmd))
        return len(self.log) - 1

    def client_request(self, cmd):
        if self.client_append(cmd) is None:
            return False
        self.replicate()
        return True

    def _push(self, pid):
        """Ek peer ko log bhejo. Higher term mila to wo term return karo, warna None."""
        if not self.peers[pid].alive:
            return None
        while self.state == Nodestate.LEADER:
            prev = self.next_index[pid] - 1
            entries = self.log[prev + 1:]
            try:
                term, ok = self.peers[pid].handle_append_entries(
                    self.current_term, self.node_id, prev, self.log[prev].term,
                    entries, self.commit_index)
            except OSError:
                return None        # ye peer skip, baaki peers ko heartbeat jaane do
            if term > self.current_term:
                return term
            if ok:
                self.match_index[pid] = prev + len(entries)
                self.next_index[pid] = prev + len(entries) + 1
                return None
            self.next_index[pid] -= 1
        return None

    def replicate(self):
        # peers parallel: total latency = sabse slow peer, sum nahi
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=max(1, len(self.peer_ids)))
        results = dict(zip(self.peer_ids, self._pool.map(self._push, self.peer_ids)))
        higher = [t for t in results.values() if t]
        if higher:
            self._step_down(max(higher))
            return
        for n in range(len(self.log) - 1, self.commit_index, -1):
            acks = 1 + sum(m >= n for m in self.match_index.values())
            if self.log[n].term == self.current_term and acks >= self.majority():
                self.commit_index = n
                break

    def apply_committed(self):
        """Commit ho chuki entries ko order mein state machine pe chalao."""
        while self.last_applied < self.commit_index:
            cmd = self.log[self.last_applied + 1].command
            if self.sm and cmd != "NOOP":
                self.sm.apply(cmd)      # exception aaye to entry skip nahi hogi, agle tick pe retry
                err = getattr(self.sm, "last_error", None)
                if err:
                    self.apply_errors[self.last_applied + 1] = err
                    if len(self.apply_errors) > 1000:
                        self.apply_errors.pop(next(iter(self.apply_errors)))
            self.last_applied += 1

    def tick(self):
        if not self.alive:
            return
        if self.state == Nodestate.LEADER:
            self.replicate()
            return
        self.elapsed += 1
        if self.elapsed >= self.timeout:
            self.elapsed = 0
            self.timeout = _new_timeout()
            self.start_election()