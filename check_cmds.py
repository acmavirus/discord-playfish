from app.config import ConfigManager
from app.api_wrapper import DiscordWrapper
from dataclasses import dataclass, field

@dataclass
class DummyMenu:
    rcv_bypasses: int = 0
    rcv_streak: int = 0
    is_alive: bool = True
    
    def notify(self, msg, priority=None):
        print(f"[NOTIFY] {msg}")
    def kill(self):
        pass

if __name__ == "__main__":
    try:
        print("Loading config...")
        config = ConfigManager()
        menu = DummyMenu()
        print("Initializing Wrapper...")
        # auto_connect=False to avoid websocket connection, just HTTP
        wrapper = DiscordWrapper(config=config, menu=menu, auto_connect=False)
        
        print("\n--- COMMANDS ---")
        found = False
        for cmd in wrapper.commands:
            if cmd['name'] == 'verify':
                found = True
                print(f"Name: {cmd['name']}")
                print(f"ID: {cmd['id']}")
                print(f"Full Dump: {cmd}")
                if 'options' in cmd:
                    for opt in cmd['options']:
                        print(f"  Option: name='{opt['name']}', type={opt['type']}, required={opt.get('required')}")
        
        if not found:
            print("Command 'verify' NOT FOUND in fetched commands.")
            
    except Exception as e:
        print(f"Error: {e}")
