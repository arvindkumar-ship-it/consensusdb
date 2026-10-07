import random
from dataclasses import dataclass
from .states import Nodestate


@dataclass
class LogEntry:
    term: int
    command: str


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
        self.next_index = {}
        self.match_index = {}

        self.alive = True              # False = node crashed
        self.elapsed = 0               # last heartbeat se kitne tick guzre
        self.timeout = random.randint(5, 10)

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
            term, granted = self.peers[pid].handle_request_vote(
                self.current_term, self.node_id, len(self.log) - 1, self.log[-1].term)
            if term > self.current_term:
                self._step_down(term)
                return
            if granted:
                self.votes.add(pid)
        if len(self.votes) >= self.majority():
            self.state = Nodestate.LEADER
            self.next_index = {p: len(self.log) for p in self.peer_ids}
            self.match_index = {p: 0 for p in self.peer_ids}

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

    def client_request(self, cmd):
        if self.state != Nodestate.LEADER:
            return False
        self.log.append(LogEntry(self.current_term, cmd))
        self.replicate()
        return True

    def replicate(self):
        for pid in self.peer_ids:
            if not self.peers[pid].alive:
                continue
            while self.state == Nodestate.LEADER:
                prev = self.next_index[pid] - 1
                entries = self.log[prev + 1:]
                term, ok = self.peers[pid].handle_append_entries(
                    self.current_term, self.node_id, prev, self.log[prev].term,
                    entries, self.commit_index)
                if term > self.current_term:
                    self._step_down(term)
                    return
                if ok:
                    self.match_index[pid] = prev + len(entries)
                    self.next_index[pid] = prev + len(entries) + 1
                    break
                self.next_index[pid] -= 1
        for n in range(len(self.log) - 1, self.commit_index, -1):
            acks = 1 + sum(m >= n for m in self.match_index.values())
            if self.log[n].term == self.current_term and acks >= self.majority():
                self.commit_index = n
                break

    def tick(self):
        if not self.alive:
            return
        if self.state == Nodestate.LEADER:
            self.replicate()           # heartbeat
            return
        self.elapsed += 1
        if self.elapsed >= self.timeout:
            self.elapsed = 0
            self.timeout = random.randint(5, 10)
            self.start_election()