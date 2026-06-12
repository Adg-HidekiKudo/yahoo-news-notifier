# services/speech_service.py
import pyttsx3

class SpeechService:
    def __init__(self):
        self.engine = pyttsx3.init()

    def speak(self, text: str):
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            print(f"⚠️ 音声読み上げ失敗: {e}")
