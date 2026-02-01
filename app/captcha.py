#------------------------ IMPORTS --------------------------#
from __future__ import annotations

from . import *
from .utils import debugger, desktop_notification
from .menu import NotificationPriority
from requests import post, exceptions
from threading import Thread
from time import sleep
from json import loads
import re
try:
    from google import genai
    from google.genai import types
    import requests
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

#------------------------ CONSTANTS --------------------------#
MAX_CAPTCHA_REGENS = 1

#------------------------- CLASSES ---------------------------#
class UnkownCaptchaError(Exception):
    pass

#Todo: make a captcha status (like scheduler class)


@dataclass
class Captcha:
    '''Catpcha class, detects and solves captchas.'''
    #Todo: split this class in chaptcha "controller" and captcha datatype
    #Pointers
    menu: BaseMenu = field(repr=False)
    
    #Components
    api_key: str = field(repr=False)
    gemini_api_key: str = field(default='', repr=False)
    gemini_model: str = field(default='gemini-2.0-flash', repr=False)
    answers: list = field(default_factory=list)
    captcha_image: str = None
    
    #Backend
    _word_list: list[str] = field(init=False, repr=False)
    _raw_answers: list[str] = field(default_factory=list)
    _max_timeout: int = field(default=20, repr=False)
    _captcha_length: int = 6
    
    #Counters
    regens: int = 0
    
    #Flags
    busy: bool = False
    detected: bool = False
    solving: bool = False
    regenerating: bool = False
    
    def __post_init__(self) -> None:
        self._word_list = ['captcha', 'verify', 'Anti-bot', 'Antibot']
    
    @property
    def name(self) -> str:
        '''Returns the class name in the correct format.'''
        return f'{self.__class__.__name__}'
    
    def filter(self, value: str) -> str:
        '''Filters results from the API. Valid results -> alphanumeric and length 4-8.'''
        if value:
            ans = re.sub('[^a-zA-Z0-9]', '', value)
            if 4 <= len(ans) <= 8:
                return ans
            else: 
                #Invalid result
                return None
        else:
            return None
    
    def gemini_request(self) -> None:
        '''Makes a request to Gemini AI to solve the captcha with automatic model fallback.'''
        if not self.detected or not self.captcha_image or not GEMINI_AVAILABLE or not self.gemini_api_key:
            if not self.gemini_api_key and self.captcha_image:
                self.menu.notify("[!] Gemini API key missing, skipping Gemini solver.", NotificationPriority.LOW)
            self.solving = False
            return

        # Danh sách model thử nghiệm theo thứ tự ưu tiên
        models_to_try = [self.gemini_model]
        fallbacks = ['gemini-3-flash', 'gemini-2.0-flash']
        for fb in fallbacks:
            if fb not in models_to_try:
                models_to_try.append(fb)

        try:
            client = genai.Client(api_key=self.gemini_api_key)
            
            # Download image
            res = requests.get(self.captcha_image)
            image_bytes = res.content
            mime_type = res.headers.get('Content-Type', 'image/png')
            
            # Prompt for Gemini
            prompt = (
                "This is a captcha image from a Discord bot with stylized, multi-colored characters. "
                "Please identify and extract the 4 to 8 character alphanumeric code. "
                "Only return the code itself, with no spaces, punctuation, or extra text."
            )
            
            success = False
            for model_name in models_to_try:
                try:
                    vision_response = client.models.generate_content(
                        model=model_name,
                        contents=[
                            prompt,
                            types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                        ]
                    )
                    
                    answer = self.filter(vision_response.text.strip())
                    
                    if answer:
                        if answer not in self.answers and self.detected:
                            self.answers.append(answer)
                            self.menu.notify(f'[*] Gemini ({model_name}) solved captcha: "{answer}"')
                            desktop_notification("Captcha Solved!", f"Gemini solved captcha with code: {answer}")
                        success = True
                        break # Thoát vòng lặp nếu thành công
                except Exception as e:
                    error_msg = str(e)
                    if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
                        self.menu.notify(f'[!] Gemini {model_name} hết quota, đang thử model tiếp theo...', NotificationPriority.LOW)
                        continue # Thử model tiếp theo
                    else:
                        self.menu.notify(f'[!] Gemini error ({model_name}): {error_msg}', NotificationPriority.LOW)
                        break # Lỗi khác không liên quan đến quota thì dừng lại
            
        except Exception as e:
            self.menu.notify(f'[!] Gemini request error: {str(e)}', NotificationPriority.LOW)
            debugger.log(e, f'{self.name} - gemini_request')
        
        self.solving = False
            
    def detect(self, event: dict) -> bool:
        '''Attempts to detect any captchas in the event.'''
        self.busy = True

        event_str = str(event)
        for target in self._word_list:
            if event_str.find(target) > -1:
                self.detected = True
                break
        
        if self.detected:
            # 1. Search in Embeds (Image and Thumbnail)
            embeds = event.get('embeds', [])
            for embed in embeds:
                # Check large image
                img_url = embed.get('image', {}).get('url')
                if img_url:
                    self.captcha_image = img_url
                    self.busy = False
                    return True
                # Check thumbnail
                thumb_url = embed.get('thumbnail', {}).get('url')
                if thumb_url:
                    self.captcha_image = thumb_url
                    self.busy = False
                    return True
            
            # 2. Search in Attachments
            attachments = event.get('attachments', [])
            for attachment in attachments:
                if any(ext in attachment.get('filename', '').lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                    self.captcha_image = attachment.get('url')
                    if self.captcha_image:
                        self.busy = False
                        return True
            
            # 3. Keyword detected but no image found (might be a text-only captcha)
            self.busy = False
            return True
        else:
            self.busy = False
            self.reset()
            return False

    def solve(self, event: dict = None) -> None:
        '''Attempts to solve the captcha using text extraction or OCR.'''
        self.busy = True
        self.solving = True
        self.regenerating = False
        self.answers = [] #Reset answers for redundancy
        
        # 1. Try text extraction first
        if event:
            # Extract content and all embed descriptions/fields
            text_blocks = [event.get('content', '')]
            for embed in event.get('embeds', []):
                text_blocks.append(embed.get('title', ''))
                text_blocks.append(embed.get('description', ''))
                for f in embed.get('fields', []):
                    text_blocks.append(f.get('name', ''))
                    text_blocks.append(f.get('value', ''))
            
            # Combine and clean markdown symbols
            full_text = ' '.join(filter(None, text_blocks))
            clean_text = re.sub(r'[\*_`~]', '', full_text)
            
            # Pattern: Code: RRDP
            code_match = re.search(r'Code:\s*([a-zA-Z0-9]{4,8})', clean_text)
            if not code_match:
                # Pattern: playing: pMbn
                code_match = re.search(r'playing:\s*([a-zA-Z0-9]{4,8})', clean_text)
            
            if not code_match:
                # Pattern: /verify [code] (Avoid matching "with" which is part of the instruction)
                code_match = re.search(r'/verify\s+(?!with\b)([a-zA-Z0-9]{4,8})', clean_text)
            
            # Filter out common instructions/system words
            blacklist = ['with', 'command', 'using', 'click', 'verify', 'result', 'code', 'please', 'type', 'regen']
            if code_match:
                code = code_match.group(1)
                if code.lower() not in blacklist:
                    self.answers.append(code)
                    self.menu.notify(f'[*] Extracted code from text: "{code}"')
                    desktop_notification("Captcha Solved!", f"Extracted code from text: {code}")
                    self.solving = False
                    self.busy = False
                    return None

        # 2. Try Gemini
        if self.captcha_image and GEMINI_AVAILABLE and self.gemini_api_key:
            self.gemini_request()
        else:
            self.solving = False
            if not self.captcha_image:
                self.menu.notify('[!] No captcha image found.')
        
        self.busy = False
        return None
    
    def reset(self) -> None:
        '''Reset all attrs to default values.'''
        self.answers = []
        self.busy = False
        self.detected = False
        self.regenerating = False
        self.regens = 0
        return None
        
        
# --------- INIT ---------#
if __name__ == "__main__":
    pass