from enum import Enum
class Nodestate(Enum):
    """Enum for node states."""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"