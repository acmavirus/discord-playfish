#------------------------ IMPORTS --------------------------#
from dataclasses import dataclass, field
from time import time
import json
import os

@dataclass
class StatsManager:
    history: list[dict] = field(default_factory=list)
    max_history: int = 100
    file_path: str = './dashboard/stats.json'

    def __post_init__(self):
        # Ensure dashboard folder exists
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        self.load()

    def load(self):
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, 'r') as f:
                    data = json.load(f)
                    history = data.get("history", [])
                    # Validate format: if first item lacks 'amount', it's old format
                    if history and "amount" not in history[0]:
                        self.history = []
                    else:
                        self.history = history
        except Exception as e:
            # debugger.log(e, "StatsManager - load")
            self.history = []

    def add_record(self, amount: float):
        record = {
            "timestamp": int(time()),
            "amount": amount
        }
        self.history.append(record)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        self.save()

    def save(self):
        data = {
            "last_update": int(time()),
            "history": self.history,
            "total_session_earned": sum(h["amount"] for h in self.history)
        }
        with open(self.file_path, 'w') as f:
            json.dump(data, f)

stats_manager = StatsManager()
