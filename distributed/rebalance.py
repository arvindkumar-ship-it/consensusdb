import re
from workload import sqlinfo


def owner(cmd):
    """Command kis key ya table ki hai. KV: 'SET k v' / 'DEL k'. SQL: table ka naam."""
    p = cmd.split()
    if p[0] in ("SET", "DEL"):
        return p[1]
    t = sqlinfo.parse(cmd)["table"]
    if t is None:                                   # CREATE INDEX ... ON table (...)
        m = re.search(r"\bon\s+(\w+)", cmd, re.I)
        t = m and m.group(1).lower()
    return t


def cmds_for(cmds, name):
    """name ki commands, order me. 'MOVED name' ke pehle ki purani commands chhod do."""
    out = []
    for c in cmds:
        if c == f"MOVED {name}":
            out = []
        elif owner(c) == name:
            out.append(c)
    return out


def moves(logs, ring):
    """{name: (src, dst)} un names ka jinka naye ring me owner badal gaya."""
    out = {}
    for g, cmds in logs.items():
        for name in {owner(c) for c in cmds if not c.startswith("MOVED ")} - {None}:
            if cmds_for(cmds, name) and ring.get(name) != g:
                out[name] = (g, ring.get(name))
    return out


def rebalance(logs, ring, send):
    """logs {group: [cmds]}, send(group, cmd) -> bool. Pehle sab copy, phir src pe MOVED tombstone."""
    plan = moves(logs, ring)
    for name, (src, dst) in plan.items():
        for c in cmds_for(logs[src], name):
            if not send(dst, c):
                return {"error": f"{name}: copy fail", "moved": {}}
    for name, (src, _) in plan.items():
        send(src, f"MOVED {name}")
    return {"moved": {n: list(v) for n, v in plan.items()}}
