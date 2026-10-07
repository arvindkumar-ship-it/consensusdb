class KV:
    """Simple state machine. Commands: 'SET key value', 'DEL key'."""
    def __init__(self):
        self.data = {}

    def apply(self, cmd):
        p = cmd.split(" ", 2)
        if p[0] == "SET":
            self.data[p[1]] = p[2]
        elif p[0] == "DEL":
            self.data.pop(p[1], None)