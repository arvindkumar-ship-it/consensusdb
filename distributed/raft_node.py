import random
import re
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from .states import Nodestate

MAX_BATCH = 500        # ek AppendEntries me max entries
SEEN_MAX = 50000       # dedup ke liye yaad rakhe gaye request ids
_RID = re.compile(r"^#(\S+) ")


@dataclass
class LogEntry:
    term: int
    command: str


def split_cmd(cmd: str):
    """'#<rid> <cmd>' -> (rid, cmd). rid na ho to (None, cmd)."""
    m = _RID.match(cmd)
    return (m.group(1), cmd[m.end():]) if m else (None, cmd)


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
        self.seen = OrderedDict()      # rid -> error/None: retry hua write dobara apply nahi hota
        self.sm = None                 # state machine, koi bhi object jisme apply(cmd) ho
        self.next_index = {}
        self.match_index = {}

        # mu: node ki saari state isi se guard hoti hai. Network call ke time ye chhoda jaata hai.
        self.mu = threading.RLock()
        self.cv = threading.Condition(self.mu)
        self._inflight: set[str] = set()   # jin peers ka push abhi chal raha hai
        self._round = 0                    # ReadIndex: heartbeat round counter
        self._ack_round = {}               # peer -> sabse naya round jiska jawab aaya
        self.wait_all = True               # True: replicate() saare peers ka wait kare (in-memory, deterministic)
                                           # False: sirf majority ka (real cluster, rpc.serve set karta hai)
        self.persist_hook = None           # vote maangne se pehle term/voted_for disk pe

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
        self.cv.notify_all()

    def handle_request_vote(self, term, candidate_id, last_log_index=0, last_log_term=0):
        with self.mu:
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
        with self.mu:
            self.current_term += 1
            self.state = Nodestate.CANDIDATE
            self.voted_for = self.node_id
            self.votes = {self.node_id}
            if self.persist_hook:
                self.persist_hook()        # apna vote durable, phir hi doosron se maango
            for pid in self.peer_ids:
                if not self.peers[pid].alive:
                    continue
                try:
                    term, granted = self.peers[pid].handle_request_vote(
                        self.current_term, self.node_id, len(self.log) - 1, self.log[-1].term)[:2]
                except OSError:
                    continue
                if term > self.current_term:
                    self._step_down(term)
                    return
                if granted:
                    self.votes.add(pid)
            if self.state == Nodestate.CANDIDATE and len(self.votes) >= self.majority():
                self.state = Nodestate.LEADER
                self.next_index = {p: len(self.log) for p in self.peer_ids}
                self.match_index = {p: 0 for p in self.peer_ids}
                self._ack_round = {p: 0 for p in self.peer_ids}
                self.log.append(LogEntry(self.current_term, "NOOP"))

    def handle_append_entries(self, term, leader_id, prev_idx, prev_term, entries, leader_commit):
        """Return (term, ok, hint). Reject par hint = leader agla next_index kahan rakhe (fast backup)."""
        with self.mu:
            if term < self.current_term:
                return self.current_term, False, 0
            if term > self.current_term:
                self._step_down(term)
            if self.state != Nodestate.FOLLOWER:
                self.state = Nodestate.FOLLOWER
                self.cv.notify_all()
            self.elapsed = 0
            if prev_idx >= len(self.log):
                return self.current_term, False, len(self.log)
            if self.log[prev_idx].term != prev_term:
                t, i = self.log[prev_idx].term, prev_idx
                while i > 1 and self.log[i - 1].term == t:
                    i -= 1                 # is conflicting term ki pehli entry
                return self.current_term, False, i
            for i, e in enumerate(entries):
                idx = prev_idx + 1 + i
                if idx < len(self.log) and self.log[idx].term != e.term:
                    del self.log[idx:]
                if idx >= len(self.log):
                    self.log.append(e)
            if leader_commit > self.commit_index:
                self.commit_index = min(leader_commit, prev_idx + len(entries))
            return self.current_term, True, prev_idx + len(entries)

    def client_append(self, cmd):
        """Log me append, replicate NAHI. Entry ka index return, leader nahi to None.
        Group commit ke liye: kai appends ke baad ek replicate()."""
        with self.mu:
            if self.state != Nodestate.LEADER:
                return None
            self.log.append(LogEntry(self.current_term, cmd))
            return len(self.log) - 1

    def client_request(self, cmd):
        if self.client_append(cmd) is None:
            return False
        self.replicate()
        return True

    def _advance_commit(self):
        for n in range(len(self.log) - 1, self.commit_index, -1):
            acks = 1 + sum(m >= n for m in self.match_index.values())
            if self.log[n].term == self.current_term and acks >= self.majority():
                self.commit_index = n
                break

    def _push(self, pid):
        """Ek peer ka replication loop. mu sirf state padhne/likhne ke liye, network call ke bahar."""
        peer = self.peers[pid]
        try:
            while True:
                with self.mu:
                    if self.state != Nodestate.LEADER or not peer.alive:
                        return
                    term, rnd = self.current_term, self._round
                    prev = self.next_index[pid] - 1
                    entries = self.log[prev + 1:prev + 1 + MAX_BATCH]
                    prev_term, commit = self.log[prev].term, self.commit_index
                try:
                    res = peer.handle_append_entries(term, self.node_id, prev, prev_term, entries, commit)
                except Exception:
                    return             # ye peer skip, agla tick dobara try karega
                with self.mu:
                    if self.state != Nodestate.LEADER or self.current_term != term:
                        return
                    if res[0] > self.current_term:
                        self._step_down(res[0])
                        return
                    self._ack_round[pid] = max(self._ack_round.get(pid, 0), rnd)   # isne hume leader maana
                    if res[1]:
                        self.match_index[pid] = max(self.match_index[pid], prev + len(entries))
                        self.next_index[pid] = self.match_index[pid] + 1
                        self._advance_commit()
                    else:
                        hint = res[2] if len(res) > 2 else self.next_index[pid] - 1
                        self.next_index[pid] = max(1, min(hint, self.next_index[pid] - 1))
                    self.cv.notify_all()
                    if res[1] and self.next_index[pid] > len(self.log) - 1 and rnd == self._round:
                        return         # peer barabar aa gaya aur koi naya round nahi maanga gaya
        finally:
            with self.mu:
                self._inflight.discard(pid)
                self.cv.notify_all()

    def _kick(self):
        """Jin peers ka push nahi chal raha unka shuru karo. mu pakde hue bulao."""
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=max(1, len(self.peer_ids)))
        for pid in self.peer_ids:
            if pid not in self._inflight:
                self._inflight.add(pid)
                self._pool.submit(self._push, pid)

    def replicate(self, timeout=5.0):
        """Peers ko log bhejo. wait_all: sab ka jawab aane tak ruko; warna majority commit tak."""
        with self.mu:
            if self.state != Nodestate.LEADER:
                return
            target = len(self.log) - 1
            self._kick()
            if self.wait_all:
                self.cv.wait_for(lambda: not self._inflight, timeout)
            else:
                self.cv.wait_for(lambda: self.state != Nodestate.LEADER or self.commit_index >= target
                                 or not self._inflight, timeout)

    def wait_commit(self, idx, timeout=2.0):
        """idx commit hone tak (ya leadership jaane tak) ruko. Slow follower ka wait nahi hota."""
        with self.mu:
            if self.state == Nodestate.LEADER:
                self._kick()
            self.cv.wait_for(lambda: self.state != Nodestate.LEADER or self.commit_index >= idx, timeout)
            return self.commit_index >= idx

    def read_barrier(self, timeout=1.0):
        """ReadIndex: True tabhi jab local read linearizable ho.
        1) apne term ki entry commit ho chuki ho, 2) is read ke BAAD ke heartbeat ko majority ne maana ho,
        3) state machine us commit index tak apply ho chuka ho."""
        with self.mu:
            if self.state != Nodestate.LEADER:
                return False
            term = self.current_term

            def lost():
                return self.state != Nodestate.LEADER or self.current_term != term

            self._kick()
            self.cv.wait_for(lambda: lost() or self.log[self.commit_index].term == term, timeout)
            if lost() or self.log[self.commit_index].term != term:
                return False
            ridx = self.commit_index
            self._round += 1
            rnd = self._round
            self._kick()

            def confirmed():
                return 1 + sum(r >= rnd for r in self._ack_round.values()) >= self.majority()

            self.cv.wait_for(lambda: lost() or confirmed(), timeout)
            if lost() or not confirmed():
                return False
            self.apply_committed()
            return self.last_applied >= ridx

    def apply_committed(self):
        """Commit ho chuki entries ko order mein state machine pe chalao. Same rid dobara apply nahi hota."""
        with self.mu:
            while self.last_applied < self.commit_index:
                i = self.last_applied + 1
                rid, cmd = split_cmd(self.log[i].command)
                if cmd != "NOOP":
                    if rid is not None and rid in self.seen:
                        err = self.seen[rid]                 # retry: pehle wala result lautao
                    else:
                        err = None
                        if self.sm:
                            self.sm.apply(cmd)  # exception aaye to entry skip nahi hogi, agle tick pe retry
                            err = getattr(self.sm, "last_error", None)
                        if rid is not None:
                            self.seen[rid] = err
                            if len(self.seen) > SEEN_MAX:
                                self.seen.popitem(last=False)
                    if err:
                        self.apply_errors[i] = err
                        if len(self.apply_errors) > 1000:
                            self.apply_errors.pop(next(iter(self.apply_errors)))
                self.last_applied += 1

    def tick(self):
        with self.mu:
            if not self.alive:
                return
            if self.state == Nodestate.LEADER:
                if self.wait_all:
                    self.replicate()
                else:
                    self._kick()           # heartbeat: ticker ko kisi peer ka wait nahi
                return
            self.elapsed += 1
            if self.elapsed >= self.timeout:
                self.elapsed = 0
                self.timeout = _new_timeout()
                self.start_election()
