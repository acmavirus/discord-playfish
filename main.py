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
        '''Checks if event is targeted to the user (sent by the application to the selected channel),
        also defines the self.event.'''
        if not response:
            return False
        
        try:
            e = response['d']
            e_name = response['t']
            
            if not isinstance(e, dict):
                return False
            
            # For MESSAGE_UPDATE, some fields might be missing.
            # We must ensure it's from the same channel and potentially the same bot.
            e_channel = e.get('channel_id')
            
            # If channel_id is missing (rare but possible in some updates), 
            # we rely on the fact that we're only listening for relevant events.
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
        '''Main loop, continuously checks for new gateway events and properly handles it.'''
        self.is_ready = True
        while True:
            try:
                response = self.session.receive_event()
            except WebSocketConnectionClosedException as e:
                debugger.log(e, f'{self.name} - run - reconnection')
                #Connection lost
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
                #Invalid/Irrelevant gateway event
                continue
            
            self.message.make(self.event)
            
            if self.captcha.detected and not self.captcha.regenerating:
                # Check for success message (handling emojis like ✅)
                if 'You may now continue' in self.message.content or \
                   'You currently do not have an active captcha' in self.message.content:
                    # Captcha bypassed
                    self.menu.rcv_bypasses += 1
                    self.captcha.reset()
                    self.menu.notify('[*] Captcha bypassed !')
                    desktop_notification("Captcha Bypassed!", "The captcha has been successfully bypassed.")
                    continue
                elif self.message.content.find('Incorrect code') > -1:
                    self.menu.notify('[*] Incorrect code.', NotificationPriority.LOW)
                    continue
                else:
                    # Not a confirmation/failure, might be an update to the captcha message itself
                    # Try to detect/solve again in case the code just appeared (text captcha update)
                    if self.captcha.detect(self.event):
                        self.captcha.solve(self.event)
                    continue
            elif self.captcha.regenerating:
                # Check if the "new event" is actually a success message (e.g. if we sent regen but it was already solved)
                if 'You may now continue' in self.message.content or \
                   'You currently do not have an active captcha' in self.message.content:
                     self.menu.rcv_bypasses += 1
                     self.captcha.reset()
                     self.menu.notify('[*] Captcha bypassed (during regen check)!')
                     continue

                if self.captcha.detect(self.event):
                    self.captcha.solve(self.event)
                    continue
                else:
                    #No detection while regenerating
                    debugger.log(self, f'{self.name} - run (No detection while regenerating)')
                    exit()
            else:
                if self.captcha.detect(self.event):
                    self.menu.notify('[!] Captcha detected !', NotificationPriority.NORMAL)
                    desktop_notification("Captcha Detected!", "Autofishbot has detected a captcha. Attempting to solve...")
                    self.captcha.solve(self.event)
                    continue
                else:
                    if self.message.title:
                        #Normal messages
                        if self.message.title == self.category.farm:
                            #Farm (/play or button) messages
                            self.menu.items = self.message.build()
                            self.menu.rcv_streak += 1
                        elif self.message.title.find(self.category.profile) > -1:
                            #Profile (/profile) messages
                            self.profile.update(self.message.description)
                            self.menu.notify('[*] Profile updated.')
                        elif self.message.title.find(self.category.charms) > -1:
                            #Charms (/charms) messages
                            self.profile.charms.update(self.message.description)
                            self.menu.notify('[*] Charms updated.')
                        elif self.message.title.find(self.category.buffs) > -1:
                            #Buffs/multipliers (/buffs) messages
                            self.profile.buffs.update(self.message.description)
                            self.menu.notify('[*] Buffs updated.')
                        elif self.message.title.find(self.category.quests) > -1:
                            #Quest list (/quests) messages
                            self.profile.quests.update(self.message.description)
                            self.menu.notify('[*] Quests updated.')
                        elif self.message.title.find(self.category.leaderboard) > -1:
                            #Leaderboard (/pos) messages
                            self.profile.leaderboard.update(self.message.description)
                            self.menu.notify('[*] Leaderboards updated.')
                        # Detect boost expiration in titled messages
                        elif self.message.title.lower().find('boost ended') > -1:
                            self.menu.notify(f'[!] {self.message.title}!', NotificationPriority.HIGH)
                            desktop_notification("Boost Ended!", f"{self.message.title}")
                            
                            if 'fish' in self.message.title.lower() or 'farm' in self.message.title.lower():
                                self.scheduler.schedule(self.scheduler.commands.morefarm)
                            elif 'treasure' in self.message.title.lower():
                                self.scheduler.schedule(self.scheduler.commands.moretreasure)
                            elif 'quantity' in self.message.title.lower():
                                self.scheduler.schedule(self.scheduler.commands.morequantity)
                        else:
                            #Unhandled titled message
                            self.menu.notify(f'{sanitize(self.message.title)}: {sanitize(self.message.description)}')
                            pass
                    else:
                        #Untitled messages
                        if self.message.content:
                            if self.message.content.find('You must wait') > -1:
                                #Intentional short cooldown
                                self.menu.notify(
                                    '[*] If automatic, this short cooldown is intentional to ensure non-bot behavior.', 
                                    NotificationPriority.VERY_LOW
                                    )
                                pass
                            else:
                                #Untitled message
                                if 'sold' in self.message.untitled.lower():
                                    if self.profile.receive_sell_message(self.message.untitled):
                                        self.menu.notify('[*] Stats updated (Sell).')
                                
                                self.menu.notify(f'[*] {self.message.untitled}')
                        else:
                            #Untitled with empty content  - probably embeded only with description
                            if 'sold' in self.message.untitled.lower():
                                if self.profile.receive_sell_message(self.message.untitled):
                                    self.menu.notify('[*] Stats updated (Sell).')

                            if menu.is_alive:
                                self.menu.notify(f'[*] {self.message.untitled}')
                            else:
                                if self.message.untitled.find('You hired a worker for the next') > -1 \
                                    or self.message.untitled.find('You already have a worker working') > -1:
                                    print(f'[*] {self.message.untitled}')
                                
                                # Boost expiration detection
                                if self.message.untitled.find('farming boost ended') > -1:
                                    self.menu.notify('[!] Farming boost ended! Re-scheduling...', NotificationPriority.HIGH)
                                    desktop_notification("Boost Ended!", "Farming boost has ended. Re-scheduling...")
                                    self.scheduler.schedule(self.scheduler.commands.morefarm)
                                elif self.message.untitled.find('treasure boost ended') > -1:
                                    self.menu.notify('[!] Treasure boost ended! Re-scheduling...', NotificationPriority.HIGH)
                                    desktop_notification("Boost Ended!", "Treasure boost has ended. Re-scheduling...")
                                    self.scheduler.schedule(self.scheduler.commands.moretreasure)
                                elif self.message.untitled.find('quantity boost ended') > -1:
                                    self.menu.notify('[!] Quantity boost ended! Re-scheduling...', NotificationPriority.HIGH)
                                    desktop_notification("Boost Ended!", "Quantity boost has ended. Re-scheduling...")
                                    self.scheduler.schedule(self.scheduler.commands.morequantity)
                                elif self.message.untitled.find('worker') > -1 and self.message.untitled.find('ended') > -1:
                                    self.menu.notify('[!] Worker ended! Re-scheduling...', NotificationPriority.HIGH)
                                    desktop_notification("Worker Ended!", "Worker has ended. Re-scheduling...")
                                    self.scheduler.schedule(self.scheduler.commands.worker)
                                elif self.message.untitled.lower().find('boost has ended') > -1:
                                    self.menu.notify(f'[!] Boost ended: {self.message.untitled}', NotificationPriority.HIGH)
                                    desktop_notification("Boost Ended!", f"A boost has ended: {self.message.untitled}")
                            pass

        self.is_ready = False
        exit()
        
@dataclass(slots=True)
class Dispatcher:
    '''Dispatcher class, responsible for making, sending commands related to
    captcha and fish commands.'''
    #Pointers
    session: DiscordWrapper
    config: ConfigManager
    menu: BaseMenu
    sch: Scheduler
    rcv: Receiver
    captcha: Captcha = field(init=False)
    message: Message = field(init=False)
    
    #Objects
    cooldown: CooldownManager = field(init=False)
    
    #Flags
    in_cooldown: bool = False
    paused: bool = False

    def __post_init__(self) -> None:
        #Setting up pointers to improve organization
        self.captcha = self.rcv.captcha
        self.message = self.rcv.message
        
        #Instantiate cooldown manager
        self.cooldown = CooldownManager(user_cooldown=self.config.user_cooldown)
        
    def make_command(self, cmd: str, name: str, value: str, type: int = 3) -> tuple:
        '''Builds a tuple containing the command (str) and the 'options' parameter (dict).'''
        parameters = {
            "type": type,
            "name": name,
            "value": value
        }
        return (cmd, parameters)

    @property
    def name(self) -> str:
        '''Returns the class name in the correct format.'''
        return f'{self.__class__.__name__}'

    @property
    def pause(self) -> None:
        '''Play/Pause switch.'''
        if self.sch.status == SchStatus.BREAK:
            self.sch.interrupt_break()
        if self.paused:
            self.paused = False
            self.menu.notify('[*] Autofarmbot resumed.')
        else:
            self.paused = True
            self.menu.notify('[*] Autofarmbot paused.')
    
    @property
    def timeout(self) -> float:
        '''Timeout cooldown for general commands (other than fish commands).'''
        return self.cooldown.custom(
            mu= uniform(3, 5),
            sigma= random()
        )
    
    def run(self) -> None:
        '''Main loop, send commands'''
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
                    except IndexError:
                        continue
                else:
                    if self.captcha.regens < MAX_CAPTCHA_REGENS:
                        self.captcha.regens += 1
                        self.menu.notify(f'[!] Regenerating captcha ({self.captcha.regens + 1}/{MAX_CAPTCHA_REGENS + 1})', NotificationPriority.HIGH)

                        #This will force a new event to be analyzed by the 
                        #detect() method but also keep the captcha.regens counter
                        self.captcha.regenerating = True
                        
                        cmd, param = self.make_command('verify', 'answer', 'regen')
                        self.session.request(command=cmd, parameters=param, category=COMMAND)

                        #?Further testing needed
                    else:
                        self.menu.notify(f'[!] CAPTCHA BYPASS FAILED. EXITING TO PROTECT ACCOUNT!', NotificationPriority.VERY_HIGH)
                        desktop_notification("Captcha Bypass Failed!", "Autofishbot failed to bypass captcha. Exiting to protect your account!")
                        import os
                        os._exit(1)
            else:
                while  self.captcha.busy \
                    or self.captcha.regenerating \
                    or self.sch.status in [SchStatus.BUSY, SchStatus.BREAK]:
                        sleep(_delay)
                
                if not self.captcha.detected and not self.paused and self.menu.is_alive:
                    _start = time()
                    
                    if self.message.id:
                        # Tight sell cycle: if auto_sell is enabled and sell button is present, click it
                        if self.config.auto_sell and self.message.sell_id:
                            self.session.request(message_id=self.message.id, custom_id=self.message.sell_id, category=BUTTON)
                            # Increased delay between sell and farm to 1.2s - 2.0s to avoid "wait 0.2s" error
                            sleep(uniform(1.2, 2.0))
                            # Reset IDs after sell to force usage of new IDs from the updated message or slash command
                            self.message.reset_ids()

                        if self.message.play_id:
                            if self.session.request(message_id=self.message.id, custom_id=self.message.play_id, category=BUTTON):
                                # Successfull interaction, reset ids to wait for next message
                                self.message.reset_ids()
                            else:
                                # Failed interaction, reset ids to trigger usage of slash commands
                                self.message.reset_ids()
                        else:
                            self.session.request(command='farm', category=COMMAND)
                    else:
                        self.session.request(command='farm', category=COMMAND)

                    self.in_cooldown = True
                    # Calculate remaining time: target_cd - elapsed_time
                    # Use max(0, ...) to ensure we don't sleep if we already exceeded the target cooldown
                    elapsed = time() - _start
                    target_cd = self.cooldown.new()
                    remaining = target_cd - elapsed
                    
                    if remaining > 0:
                        sleep(remaining)
                        
                    self.in_cooldown = False
                else:
                    sleep(_delay)

#------------------------ INIT --------------------------#
if __name__ == "__main__":
    print(f'\n[*] Starting...')
    
    #Loads config
    config = ConfigManager()
    
    #Setup debugger
    debugger.setup(config.debug)
    
    #Instantiate menu
    if config.log_mode:
        menu = LogMenu()
    elif config.compact_mode:
        menu = CompactMenu()
    else:
        menu = MainMenu()
    
    #Instantiate session
    session = DiscordWrapper(
        config=config, 
        menu=menu, 
        auto_connect=True)
    
    #Instantiate receiver
    receiver = Receiver(
        session=session, 
        config=config, 
        menu=menu)
    
    #Instantiate Scheduler
    scheduler = Scheduler(
        session=session, 
        config=config, 
        menu=menu,
        captcha=receiver.captcha)
    
    receiver.scheduler = scheduler

    #Instantiate dispatcher
    dispatcher = Dispatcher(
        session=session,
        config=config,
        menu=menu,
        sch=scheduler,
        rcv=receiver)
    
    #Async flow
    rcv_thread = Thread(target=receiver.run, daemon=True, name='Receiver')
    sch_thread = Thread(target=scheduler.run, args=(dispatcher,), daemon=True, name='Scheduler')
    dsp_thread = Thread(target=dispatcher.run, daemon=True, name='Dispatcher')
    
    rcv_thread.start()
    sch_thread.start()
    dsp_thread.start()

    #Start menu
    menu.run(
        config=config,
        dispatcher=dispatcher,
        profile=receiver.profile,
        scheduler=scheduler,
        threads=[rcv_thread, sch_thread, dsp_thread]
    )
    
    if config.fish_on_exit and menu.rcv_streak > 0:
        cmd, data = scheduler.commands.worker.data
        session.request(command=cmd, parameters=data)
        sleep(3)

    session.disconnect()
    exit(f'\n[!] User exited.')