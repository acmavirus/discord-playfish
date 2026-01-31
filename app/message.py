#------------------------ IMPORTS --------------------------#
from __future__ import annotations

from . import *
from .utils import sanitize
from re import sub


#------------------------- CLASSES ---------------------------#

@dataclass(slots=True, frozen=True)
class MessageCategory:
    '''Essential keyworks to categorize each message title.'''
    farm: str = 'You farmed:'
    profile: str = 'Inventory of'
    charms: str = 'Charms are found in'
    buffs: str = 'current multipliers'
    quests: str = 'Quest List'
    leaderboard: str = '\'s leaderboard positions'


@dataclass
class Message:
    '''Message class to convert raw events into usable messages.'''
    id: str = None
    play_id: str = None
    sell_id: str = None
    title: str = field(default=None, repr=False)
    description: str = field(default=None, repr=False)
    content: str = None
    items: list[str] = field(default_factory=list, repr=False)
    untitled: str = None
      
    @property
    def name(self) -> str:
        '''Returns the class name in the correct format.'''
        return f'{self.__class__.__name__}'
    
    def make(self, event: dict) -> None:
        '''Makes message schematics, assigning ids and attributes.'''
        self.reset()
        if event != []:
            self.content = event['content']
            
            #Assign ids
            components = event['components']
            custom_id = None
            sell_id = None
            if components != []:
                for component in components[0]['components']:
                    try:
                        label = component.get('label', '')
                        if label in ['Farm Again', 'Farm', 'Harvest', 'Plant Again', 'Plant']:
                            custom_id = component['custom_id']
                        elif label in ['Sell']:
                            sell_id = component['custom_id']
                    except KeyError:
                        pass
                if custom_id or sell_id:
                    self.id = event['id']
                    self.play_id = custom_id
                    self.sell_id = sell_id
            else:
                pass
                #self.reset_ids()
            
            #Assign attributes
            #Todo: revisit this logic (make it cleaner)
            embeds = event['embeds']
            if len(embeds) > 0:
                for embed in embeds:
                    try:
                        self.title = embed['title']
                        try: 
                            self.description = embed['description']
                        except KeyError:
                            pass
                        if self.title == 'You farmed':
                            break
                    except KeyError:
                        #Untitled
                        try:
                            self.untitled = sanitize(embed['description'])
                        except KeyError:
                            self.untitled = sanitize(self.content)
                            #pass
                return None
            else:
                return None
        else:
            return None
    
    def build(self, extra_list: list = []) -> list:
        '''Builds message list ready to be displayed.'''
        #Todo: refactor this function
        for line in self.description.split('\n'):
            final = ''
            if line.find('LEVEL UP!') > -1:
                #Level up information
                level = sub('[^\d+]', '', sub(r'<.+?> ', '', line))
                final = f'<< LEVEL UP: {int(level) - 1} -> {level} >>'
            elif line.find('<:') > -1:
                #Emotes 
                final = sub(r'  ', ' ', sub(r'<.+?>', '', line))
            elif line.find(':') > -1:
                #Duplicator Emote (and commom emotes)
                final = sub(r'  ', ' ', sub(r':.+?: ', '', line))
            elif line.find('#') > -1: 
                #Global boost information
                pass
            elif line == '' or line == None or line == '\n':
                pass
            else:
                final = line
            self.items.append(sub('[\*+]', '', final))
        if extra_list != []:
            self.items = extra_list + self.items
        return self.items
    
    def reset(self) -> None:
        '''Reset values to default.'''
        self.id: str = None
        self.play_id: str = None
        self.sell_id: str = None
        self.title: str = None
        self.description: str = None
        self.content: str = None
        self.items: list[str] = []
        self.untitled: str = None
        return None

    def reset_ids(self) -> None:
        self.id = None
        self.play_id = None
        self.sell_id = None

