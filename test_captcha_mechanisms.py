# // Copyright by AcmaTvirus
import os
import re
import base64
import requests
import time
from google import genai
from google.genai import types

# API Keys
OCR_API_KEY = "K88923571488957"
GEMINI_API_KEY = "AIzaSyBP_p-8BC-nz4bLixK_5zT0hcfRx-Dorqo"
TWO_CAPTCHA_API_KEY = "bd3633035edf0226876af966e56550a3"

IMAGES = [
    r"c:\Users\Administrator\Desktop\dicord-bot-python\autofishbot-main\assets\222.png",
    r"c:\Users\Administrator\Desktop\dicord-bot-python\autofishbot-main\assets\222222.png",
    r"c:\Users\Administrator\Desktop\dicord-bot-python\autofishbot-main\assets\1207368280562737224.png"
]

def filter_captcha(value):
    if value:
        ans = re.sub('[^a-zA-Z0-9]', '', value)
        if 4 <= len(ans) <= 8:
            return ans
    return None

def test_gemini(image_path):
    print(f"Testing Gemini for: {os.path.basename(image_path)}")
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        with open(image_path, "rb") as f:
            image_bytes = f.read()
            
        prompt = (
            "This is a captcha image from a Discord bot with stylized, multi-colored characters. "
            "Please identify and extract the 4 to 8 character alphanumeric code. "
            "Only return the code itself, with no spaces, punctuation, or extra text."
        )
        
        vision_response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=[
                prompt,
                types.Part.from_bytes(data=image_bytes, mime_type="image/png")
            ]
        )
        
        result = vision_response.text.strip()
        filtered = filter_captcha(result)
        print(f"  > Gemini Raw: {result}")
        print(f"  > Gemini Filtered: {filtered}")
        return filtered
    except Exception as e:
        print(f"  > Gemini Error: {e}")
        return None

def test_ocr_space(image_path, engine=2):
    print(f"Testing OCR Space (Engine {engine}) for: {os.path.basename(image_path)}")
    try:
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')
            
        payload = {
            'apikey': OCR_API_KEY,
            'base64Image': f"data:image/png;base64,{base64_image}",
            'OCREngine': engine,
            'language': 'eng'
        }
        
        response = requests.post('https://api.ocr.space/parse/image', data=payload, timeout=20)
        data = response.json()
        
        if data.get('OCRExitCode') == 1:
            result = data['ParsedResults'][0]['ParsedText'].strip()
            filtered = filter_captcha(result)
            print(f"  > OCR Raw: {result}")
            print(f"  > OCR Filtered: {filtered}")
            return filtered
        else:
            print(f"  > OCR Error: {data.get('ErrorMessage')}")
            return None
    except Exception as e:
        print(f"  > OCR Error: {e}")
        return None

def test_2captcha(image_path):
    print(f"Testing 2Captcha for: {os.path.basename(image_path)}")
    try:
        with open(image_path, "rb") as f:
            base64_image = base64.b64encode(f.read()).decode('utf-8')
            
        # Post the captcha
        payload = {
            'key': TWO_CAPTCHA_API_KEY,
            'method': 'base64',
            'body': base64_image,
            'json': 1
        }
        
        response = requests.post('http://2captcha.com/in.php', data=payload)
        res_data = response.json()
        
        if res_data.get('status') != 1:
            print(f"  > 2Captcha Post Error: {res_data.get('request')}")
            return None
            
        captcha_id = res_data.get('request')
        print(f"  > 2Captcha ID: {captcha_id}, waiting for result...")
        
        # Polling for results
        for _ in range(20):
            time.sleep(5)
            res_url = f"http://2captcha.com/res.php?key={TWO_CAPTCHA_API_KEY}&action=get&id={captcha_id}&json=1"
            res_response = requests.get(res_url)
            res_data = res_response.json()
            
            if res_data.get('status') == 1:
                result = res_data.get('request')
                filtered = filter_captcha(result)
                print(f"  > 2Captcha Raw: {result}")
                print(f"  > 2Captcha Filtered: {filtered}")
                return filtered
            elif res_data.get('request') == 'CAPCHA_NOT_READY':
                continue
            else:
                print(f"  > 2Captcha Error: {res_data.get('request')}")
                return None
        
        print(f"  > 2Captcha Timeout.")
        return None
    except Exception as e:
        print(f"  > 2Captcha Error: {e}")
        return None

if __name__ == "__main__":
    for img in IMAGES:
        print("-" * 50)
        # Test Gemini
        test_gemini(img)
        # Test 2Captcha
        test_2captcha(img)
        # Test OCR Space
        test_ocr_space(img, engine=1)

# Copyright by AcmaTvirus

# Copyright by AcmaTvirus
