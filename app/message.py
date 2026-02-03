from __future__ import annotations
from . import *
from .utils import sanitize
from re import sub

@dataclass(slots=True, frozen=True)
class MessageCategory:
    '''Keywords to categorize messages (simplified for OwO).'''
    hunt: str = 'hunt'
    battle: str = 'battle'

@dataclass
class Message:
    '''Message class to convert raw events into usable messages.'''
    id: str = None
    title: str = field(default=None, repr=False)
    description: str = field(default=None, repr=False)
    content: str = None
    items: list[str] = field(default_factory=list, repr=False)
      
    @property
    def name(self) -> str:
        return f'{self.__class__.__name__}'
    
    def make(self, event: dict) -> None:
        '''Makes message schematics, assigning ids and attributes.'''
        self.reset()
        if event:
            self.content = event.get('content', '')
            self.id = event.get('id')
            
            embeds = event.get('embeds', [])
            if embeds:
                for embed in embeds:
                    self.title = embed.get('title')
                    self.description = embed.get('description')
                    if self.title: break
        return None
    
    def reset(self) -> None:
        self.id = None
        self.title = None
        self.description = None
        self.content = None
        self.items = []
        return None
