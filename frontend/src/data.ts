// README me likhe measured numbers (ek Windows laptop, sab localhost). Live data nahi, ye fixed measurements hain.
export const IMPACT = [
  { label: "Leader failover outage", before: 7600, after: 650, unit: "ms", lowerIsBetter: true, note: "Router connect timeout 0.3 s" },
  { label: "Write with a dead follower", before: 1000, after: 2, unit: "ms", lowerIsBetter: true, note: "Cached liveness + background ping" },
  { label: "SET throughput (8 threads)", before: 1172, after: 2233, unit: "ops/s", lowerIsBetter: false, note: "Group commit" },
  { label: "Full-scan throughput", before: 661.6, after: 1272.7, unit: "ops/s", lowerIsBetter: false, note: "Index suggested by the optimizer" },
];

export const DIAGRAMS = [
  { file: "01-architecture.svg", title: "Architecture", text: "A router sends each key or table to the group that owns it. Every group is three Raft replicas." },
  { file: "02-write-path.svg", title: "Write path", text: "A write is acknowledged only after a majority of replicas have it." },
  { file: "03-raft-states.svg", title: "Raft states", text: "Follower, candidate, leader. One vote per term prevents split brain." },
  { file: "04-failover.svg", title: "Failover", text: "When a leader dies, a new one is elected in about 0.5 to 1.0 s." },
  { file: "05-group-commit.svg", title: "Group commit", text: "Concurrent writes share one replication round and one fsync." },
  { file: "06-sharding-ring.svg", title: "Sharding ring", text: "Consistent hashing with 100 virtual nodes per group." },
  { file: "07-optimizer.svg", title: "Optimizer", text: "Query log, features, suggestion, validation, cost, apply, measured impact." },
  { file: "08-rebalance.svg", title: "Rebalance", text: "Copy first, then leave a MOVED tombstone at the source." },
];

export const LIMITS = [
  "Reads are served from the leader's local state, so a partition can return stale reads.",
  "No snapshots or log compaction. A restart replays the full log.",
  "Membership is static. Nodes cannot join an existing group.",
  "No cross-shard transactions or joins. A hot table is a hot shard.",
  "Writes are paused while a rebalance runs.",
  "All numbers were measured on localhost.",
];
