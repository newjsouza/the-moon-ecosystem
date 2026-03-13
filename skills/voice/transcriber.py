import os
import requests
import logging
from typing import Any, Dict
from ..skill_base import SkillBase

logger = logging.getLogger("moon.skills.voice")

class TranscriberSkill(SkillBase):
    """
    Transcription skill using Groq's Whisper implementation.
    """
    def __init__(self):
        super().__init__(name="voice_transcriber")
        self.api_key = os.getenv("GROQ_API_KEY")
        self.url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        file_path = params.get("file_path")
        if not file_path or not os.path.exists(file_path):
            return {"error": "File not found"}

        if not self.api_key:
            return {"error": "GROQ_API_KEY not set"}

        try:
            with open(file_path, "rb") as f:
                files = {
                    "file": (os.path.basename(file_path), f),
                    "model": (None, "whisper-large-v3-turbo"),
                    "language": (None, "pt"),
                    "response_format": (None, "text")
                }
                headers = {"Authorization": f"Bearer {self.api_key}"}
                response = requests.post(self.url, headers=headers, files=files)
                
                if response.status_code == 200:
                    return {"text": response.text.strip()}
                else:
                    return {"error": f"API Error {response.status_code}: {response.text}"}
        except Exception as e:
            return {"error": str(e)}
