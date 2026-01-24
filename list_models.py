# // Copyright by AcmaTvirus
import os
from google import genai

# API Key from config
GEMINI_API_KEY = "AIzaSyBP_p-8BC-nz4bLixK_5zT0hcfRx-Dorqo"

def list_gemini_models():
    print("[*] Checking available Gemini models...")
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        # Use the models.list method to see what we have access to
        models = client.models.list()
        
        print("\nAvailable Models:")
        found_flash = False
        for model in models:
            print(f" - {model.name}")
            if 'flash' in model.name.lower():
                found_flash = True
        
        if not found_flash:
            print("\n[!] WARNING: No 'flash' models found in your list.")
            
    except Exception as e:
        print(f"\n[E] Error listing models: {str(e)}")

if __name__ == "__main__":
    list_gemini_models()

# Copyright by AcmaTvirus
