#! /usr/bin/env python3
#------------------------ IMPORTS --------------------------#
from __future__ import annotations
from app import *
from websocket import WebSocketConnectionClosedException
from threading import Thread
from time import sleep, time
from random import random, uniform


@dataclass(slots=True)
class Receiver:
    #Pointers
    session: DiscordWrapper
    config: ConfigManager 
    menu: MainMenu
    scheduler: Scheduler = None
    
    #Objects
    captcha: Captcha = field(init=False)
    profile: Profile = field(default_factory=Profile)
    message: Message = field(default_factory=Message)
    category: MessageCategory = field(default_factory=MessageCategory)
    event: dict = None

    #Flags
    is_ready: bool = False
    
    def __post_init__(self) -> None:
        '''Setups captcha.'''
        self.captcha = Captcha(
            api_key=self.config.ocr_api_key, 
            gemini_api_key=self.config.gemini_api_key,
            gemini_model=self.config.gemini_model,
            menu=self.menu
        )
    
    @property
    def name(self) -> str:
        '''Returns the class name in the correct format.'''
        return f'{self.__class__.__name__}'
    
    def check_event(self, response: dict) -> bool:
        '''Checks if event is targeted to the user.'''
        if not response:
            return False
        
        try:
            e = response['d']
            e_name = response['t']
            
            if not isinstance(e, dict):
                return False
            
            e_channel = e.get('channel_id')
            if e_channel and e_channel != self.config.channel_id:
                return False
                
            e_author_id = e.get('author', {}).get('id')
            if e_author_id and e_author_id != APPLICATION_ID:
                return False
        except (KeyError, TypeError, AttributeError):
            return False
        
        if e_name in TARGET_EVENT_NAMES:
            self.event = e
            return True
        return False

    def run(self) -> None:
        '''Main loop, checks gateway events.'''
        self.is_ready = True
        while True:
            try:
                response = self.session.receive_event()
            except WebSocketConnectionClosedException as e:
                debugger.log(e, f'{self.name} - run - reconnection')
                self.is_ready = False
                self.menu.notify('[!] Connection lost, attempting to reconnect...', NotificationPriority.HIGH)
                if self.session.reconnect():
                    self.is_ready = True
                    self.menu.notify('[*] Reconnection succeeded.')
                    continue
                else:
                    self.menu.kill()
                    print(f'[E] Reconnection failed. Exception: {e}')
                    break
            except Exception as e:
                debugger.log(e, f'{self.name} - run - reconnection')
                break
            
            if not self.check_event(response):
                continue
            
            self.message.make(self.event)
            
            if self.captcha.detected and not self.captcha.regenerating:
                if 'You may now continue' in self.message.content or \
                   'You currently do not have an active captcha' in self.message.content:
                    self.menu.rcv_bypasses += 1
                    self.captcha.reset()
                    self.menu.notify('[*] Captcha bypassed !')
                    send_webhook(self.config.webhook_url, "Captcha Bypassed", "The captcha has been successfully bypassed.", 65280)
                    continue
                elif self.message.content.find('Incorrect code') > -1:
                    self.menu.notify('[*] Incorrect code.', NotificationPriority.LOW)
                    continue
                else:
                    if self.captcha.detect(self.event):
                        self.captcha.solve(self.event)
                    continue
            elif self.captcha.regenerating:
                if 'You may now continue' in self.message.content or \
                   'You currently do not have an active captcha' in self.message.content:
                     self.menu.rcv_bypasses += 1
                     self.captcha.reset()
                     self.menu.notify('[*] Captcha bypassed !')
                     continue

                if self.captcha.detect(self.event):
                    self.captcha.solve(self.event)
                    continue
            else:
                if self.captcha.detect(self.event):
                    self.menu.notify('[!] Captcha detected !', NotificationPriority.NORMAL)
                    send_webhook(self.config.webhook_url, "Captcha Detected", "Autofishbot has detected a captcha. Attempting to solve...", 16711680)
                    self.captcha.solve(self.event)
                    continue
                else:
                    if self.message.content:
                        if 'You must wait' in self.message.content:
                            self.menu.notify('[*] Rate limit detected, waiting...', NotificationPriority.LOW)
                        elif self.menu.is_alive:
                            # self.menu.notify(f'[*] {self.message.content}')
                            pass
        self.is_ready = False
        exit()

@dataclass(slots=True)
class Dispatcher:
    session: DiscordWrapper
    config: ConfigManager
    menu: BaseMenu
    sch: Scheduler
    rcv: Receiver
    captcha: Captcha = field(init=False)
    message: Message = field(init=False)
    cooldown: CooldownManager = field(init=False)
    paused: bool = False

    def __post_init__(self) -> None:
        self.captcha = self.rcv.captcha
        self.message = self.rcv.message
        self.cooldown = CooldownManager(user_cooldown=self.config.user_cooldown)
        
    def make_command(self, cmd: str, name: str, value: str, type: int = 3) -> tuple:
        parameters = {"type": type, "name": name, "value": value}
        return (cmd, parameters)

    @property
    def name(self) -> str:
        return f'{self.__class__.__name__}'

    @property
    def pause(self) -> None:
        if self.sch.status == SchStatus.BREAK:
            self.sch.interrupt_break()
        if self.paused:
            self.paused = False
            self.menu.notify('[*] Bot resumed.')
        else:
            self.paused = True
            self.menu.notify('[*] Bot paused.')
    
    @property
    def timeout(self) -> float:
        return self.cooldown.custom(mu=uniform(3, 5), sigma=random())
    
    def run(self) -> None:
        _delay = 0.2
        while True:
            if not self.rcv.is_ready:
                sleep(_delay)
                continue
            
            if self.captcha.detected and not self.captcha.regenerating:
                if self.captcha.solving or len(self.captcha.answers) > 0:
                    try:
                        answer = self.captcha.answers.pop()
                        self.menu.notify(f'[!] Attempting code: "{answer}".')
                        cmd, param = self.make_command('verify', 'answer', answer)
                        self.session.request(command=cmd, parameters=param, category=COMMAND)
                        sleep(self.timeout)
                    except IndexError: continue
                else:
                    if self.captcha.regens < MAX_CAPTCHA_REGENS:
                        self.captcha.regens += 1
                        self.menu.notify(f'[!] Regenerating captcha...')
                        self.captcha.regenerating = True
                        cmd, param = self.make_command('verify', 'answer', 'regen')
                        self.session.request(command=cmd, parameters=param, category=COMMAND)
                    else:
                        self.menu.notify(f'[!] CAPTCHA BYPASS FAILED. EXITING!', NotificationPriority.VERY_HIGH)
                        send_webhook(self.config.webhook_url, "Captcha Bypass Failed", "FAILED TO BYPASS CAPTCHA. EXITING!", 16711680)
                        import os
                        os._exit(1)
            else:
                sleep(_delay)

if __name__ == "__main__":
    print(f'\n[*] Starting OwO Bot Helper...')
    config = ConfigManager()
    debugger.setup(config.debug)
    
    if config.log_mode: menu = LogMenu()
    elif config.compact_mode: menu = CompactMenu()
    else: menu = MainMenu()
    
    session = DiscordWrapper(config=config, menu=menu, auto_connect=True)
    receiver = Receiver(session=session, config=config, menu=menu)
    scheduler = Scheduler(session=session, config=config, menu=menu, captcha=receiver.captcha)
    receiver.scheduler = scheduler
    dispatcher = Dispatcher(session=session, config=config, menu=menu, sch=scheduler, rcv=receiver)
    
    rcv_thread = Thread(target=receiver.run, daemon=True, name='Receiver')
    sch_thread = Thread(target=scheduler.run, args=(dispatcher,), daemon=True, name='Scheduler')
    dsp_thread = Thread(target=dispatcher.run, daemon=True, name='Dispatcher')
    
    rcv_thread.start()
    sch_thread.start()
    dsp_thread.start()

    menu.run(
        config=config,
        dispatcher=dispatcher,
        profile=receiver.profile,
        scheduler=scheduler,
        threads=[rcv_thread, sch_thread, dsp_thread]
    )
    
    session.disconnect()
    exit(f'\n[!] User exited.')