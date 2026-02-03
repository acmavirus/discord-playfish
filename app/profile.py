from __future__ import annotations
from . import *
from .utils import debugger
from time import time
from re import sub

@dataclass(slots=True)
class Profile:
    '''Simplified Profile for OwO.'''
    level: str = None
    balance: str = None
    last_update: float = None

    @property
    def name(self) -> str:
        return f'{self.__class__.__name__}'
    
    def update(self, raw_data: str) -> bool:
        self.last_update = time()
        return True
