from __future__ import annotations
from . import *
from .utils import convert_time, debugger
from .scheduler import SchStatus
import curses
from time import sleep
from math import ceil
from threading import Thread
from os import path
from re import sub
import json

#------------------------ CONSTANTS --------------------------#
MENUART = [
    '   ____               ____        _   ',
    '  / __ \_      _____ | __ )  ___ | |_ ',
    ' / / _` \ \ /\ / / _ \|  _ \ / _ \| __|',
    '| | (_| |\ V  V / (_) | |_) | (_) | |_ ',
    ' \ \__,_| \_/\_/ \___/|____/ \___/ \__|',
    '  \____/                               '
]

DEFAULT_KEYBINDS = {
    'pause': 'p',
    'quit': 'Q',
    'claim_daily': 'D',
}

class NotificationPriority:
    VERY_LOW = 1
    LOW = 3
    NORMAL = 5
    HIGH = 10
    VERY_HIGH = 30

@dataclass(slots=True)
class Keybinder:
    file: str = './app/keybinds.json'
    keybinds: dict = field(init=False, repr=False)
    _list: list[tuple] = field(default_factory=list)
    
    def loader(self) -> bool:
        if not path.exists(self.file):
            with open(self.file, 'w') as f:
                f.write(json.dumps(DEFAULT_KEYBINDS))
            self.keybinds = DEFAULT_KEYBINDS
            return True
        else:
            try:
                with open(self.file, 'r') as f:
                    self.keybinds = json.loads(f.read())
                return True
            except:
                self.keybinds = DEFAULT_KEYBINDS
                return False
    
    def __post_init__(self) -> None:
        self.loader()

    @property
    def list(self) -> list[tuple]:
        if not self._list:
            for key, value in self.keybinds.items():
                self._list.append((value, sub('_', ' ', key).title()))
        return self._list

@dataclass(slots=True)
class BaseMenu:
    config: ConfigManager = field(init=False, repr=False)
    profile: Profile = field(init=False, repr=False)
    dispatcher: object = field(init=False, repr=False)
    sch: Scheduler = field(init=False, repr=False)
    items: list[str] = field(default_factory=list)
    current_notification: str = ''
    notification_queue: list[tuple] = field(default_factory=list)
    keybinds: Keybinder = field(default_factory=Keybinder)
    x: int = 0
    y: int = 0
    is_alive: bool = False
    rcv_streak: int = 0
    rcv_bypasses: int = 0
    
    def get_max_size(self, stdscr: curses.window) -> tuple:
        self.y, self.x = stdscr.getmaxyx()
        return (self.y, self.x)

    def notify(self, message: str, display_time: float = NotificationPriority.NORMAL) -> None:
        self.notification_queue.append((message, display_time))
    
    def notifications_thread(self) -> None:
        while True:
            if self.notification_queue:
                message, display_time = self.notification_queue.pop(0)
                self.current_notification = message
                sleep(display_time)
                self.current_notification = ''
            else:
                sleep(0.5)

    def run(self, config: ConfigManager, dispatcher: object, profile: Profile, scheduler: Scheduler, threads: list[Thread]) -> None:
        self.config = config
        self.dispatcher = dispatcher
        self.profile = profile
        self.sch = scheduler
        Thread(target=self.notifications_thread, daemon=True).start()
        curses.wrapper(self.__run__, threads)

    def kill(self) -> None:
        self.is_alive = False

    def __run__(self, stdscr: curses.window, threads: list[Thread]) -> None:
        curses.curs_set(0)
        stdscr.nodelay(True)
        self.is_alive = True
        while self.is_alive:
            self.get_max_size(stdscr)
            stdscr.erase()
            stdscr.addstr(0, 0, f"Notification: {self.current_notification}")
            stdscr.addstr(2, 2, "OwO Bot Helper v2.0")
            for i, line in enumerate(MENUART):
                stdscr.addstr(4 + i, 2, line)
            
            stdscr.addstr(12, 2, f"Streak: {self.rcv_streak}")
            stdscr.addstr(13, 2, f"Bypasses: {self.rcv_bypasses}")
            stdscr.addstr(14, 2, f"Scheduler: {self.sch.status.name}")
            
            key = stdscr.getch()
            if key == ord('q') or key == ord('Q'): self.kill()
            if key == ord('p'): self.dispatcher.pause
            
            stdscr.refresh()
            sleep(0.1)

@dataclass(slots=True)
class MainMenu(BaseMenu):
    pass

@dataclass(slots=True)
class CompactMenu(BaseMenu):
    pass

@dataclass(slots=True)
class LogMenu(BaseMenu):
    def run(self, config, dispatcher, profile, scheduler, threads):
        self.is_alive = True
        print("[*] Log Mode: Bot is running... (Press Ctrl+C to exit)")
        while self.is_alive:
            for thread in threads:
                if not thread.is_alive():
                    self.is_alive = False
                    print(f"[E] Thread {thread.name} has stopped unexpectedly.")
                    return
            sleep(1)
    def notify(self, message, display_time=5):
        print(f"[*] {message}")
    def kill(self): self.is_alive = False