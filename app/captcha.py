#------------------------ IMPORTS --------------------------#
from __future__ import annotations

from . import *
from .utils import debugger
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
MAX_CAPTCHA_REGENS = 3

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
    answers: list = field(default_factory=list)
    captcha_image: str = None
    
    #Backend
    _ocr_url: str = field(default='https://api.ocr.space/parse/image', repr=False)
    _word_list: list[str] = field(init=False, repr=False)
    _raw_answers: list[str] = field(default_factory=list)
    _engines: list[int] = field(init=False, repr=False)
    _max_timeout: int = field(default=20, repr=False)
    _captcha_length: int = 6
    
    #Counters
    regens: int = 0
    
    #Flags
    busy: bool = False
    detected: bool = False
    solving: bool = False
    regenerating: bool = False

    #OCR Settings
    is_overlay_required: bool = field(default=False, repr=False)
    detect_orientation: bool = field(default=True, repr=False)
    scale: bool = field(default=False, repr=False)
    language: str = field(default='eng', repr=False)
    
    def __post_init__(self) -> None:
        self._word_list = ['captcha', 'verify', 'Anti-bot']
        self._engines = [2, 1, 3, 5]
    
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
    
    def request(self, engine: int) -> None:
        #Todo: make this function less complex and better structured
        '''Makes a request to the OCR api and appends the result (if valid) to the answers list.'''
        if not self.detected: 
            return None

        payload = {
            'apikey': self.api_key,
            'url': self.captcha_image,
            'isOverlayRequired': self.is_overlay_required,
            'detectOrientation': self.detect_orientation,
            'scale': self.scale,
            'OCREngine': engine,
            'language': self.language
        }
        
        try:
            request = post(self._ocr_url, data=payload, timeout=self._max_timeout)
            response = loads(request.content.decode())
        except exceptions.ReadTimeout as e:
            #Took too long to respond
            self.menu.notify(f'[!] Engine {engine} took too long to respond.', NotificationPriority.LOW)
            if engine == self._engines[-1]:
                self.solving = False
            debugger.log(e, f'{self.name} - request timeout | {self}')
            return None
        except Exception as e:
            debugger.log(e, f'{self.name} - request')
            raise UnkownCaptchaError(e)
        
        if response['OCRExitCode'] == 1:
            if self.detected:
                answer = self.filter(response['ParsedResults'][0]['ParsedText'])
                if answer:
                    #To avoid conflicts due to multi-threading, it must not be duplicate, 
                    #it must not be solved and must be busy (to garatee that the object it's the same)
                    if answer not in self.answers and self.detected:
                        self.answers.append(answer)
                    else:
                        #Duplicate result
                        pass
            
            if engine == self._engines[-1]:
                self.solving = False
            return None     

    def gemini_request(self) -> None:
        '''Makes a request to Gemini AI to solve the captcha.'''
        if not self.detected or not self.captcha_image or not GEMINI_AVAILABLE or not self.gemini_api_key:
            if not self.gemini_api_key and self.captcha_image:
                self.menu.notify("[!] Gemini API key missing, skipping Gemini solver.", NotificationPriority.LOW)
            self.solving = False
            return

        try:
            client = genai.Client(api_key=self.gemini_api_key)
            
            # Download image
            res = requests.get(self.captcha_image)
            image_bytes = res.content
            mime_type = res.headers.get('Content-Type', 'image/png')
            
            # Prompt for Gemini - more descriptive to help with stylized text
            prompt = (
                "This is a captcha image from a Discord bot with stylized, multi-colored characters. "
                "Please identify and extract the 4 to 8 character alphanumeric code. "
                "Only return the code itself, with no spaces, punctuation, or extra text."
            )
            
            vision_response = client.models.generate_content(
                model='gemini-3-flash',
                contents=[
                    prompt,
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                ]
            )
            
            answer = self.filter(vision_response.text.strip())
            
            if answer:
                if answer not in self.answers and self.detected:
                    self.answers.append(answer)
                    self.menu.notify(f'[*] Gemini solved captcha: "{answer}"')
            
        except Exception as e:
            self.menu.notify(f'[!] Gemini error: {str(e)}', NotificationPriority.LOW)
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
                # Pattern: /verify RRDP
                code_match = re.search(r'/verify\s+([a-zA-Z0-9]{4,8})', clean_text)
            
            if code_match:
                code = code_match.group(1)
                if code.lower() not in ['result', 'code']:
                    self.answers.append(code)
                    self.menu.notify(f'[*] Extracted code from text: "{code}"')
                    self.solving = False
                    self.busy = False
                    return None

        # 2. Try Gemini first if available
        if self.captcha_image and GEMINI_AVAILABLE and self.gemini_api_key:
            gemini_thread = Thread(target=self.gemini_request, daemon=True)
            gemini_thread.start()
            # If Gemini is working, we might want to wait a bit or let it run in parallel with OCR
            # For now, let's run OCR as well for redundancy
        
        # 3. Fallback/Parallel OCR if image is present
        if self.captcha_image:
            for engine in self._engines:
                async_request = Thread(target=self.request, args=(engine,), daemon=True)
                async_request.start()
                sleep(0.5)
        else:
            if not self.solving: # If Gemini didn't start/is not available
                self.solving = False
                self.menu.notify('[!] No captcha image found for OCR.')
        
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