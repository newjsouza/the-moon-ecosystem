"""
core/system/manager.py
Central handler for system-level operations.
"""
import asyncio
from core.system.audio import AudioController
from agents.llm import LlmAgent
from utils.logger import setup_logger

logger = setup_logger("SystemManager")

class SystemManager:
    def __init__(self):
        self.audio = AudioController()
        self.llm = LlmAgent()
        logger.info("SystemManager initialized")

    def process_voice_command(self, audio_path: str):
        """Process a voice command from a captured audio file."""
        if not audio_path:
            logger.warning("No audio path provided for processing.")
            return

        # Use an event loop to run async transcription and LLM processing
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._handle_voice_async(audio_path))
        finally:
            loop.close()

    async def _handle_voice_async(self, audio_path: str):
        logger.info(f"Processing voice file: {audio_path}")
        
        # 1. Transcribe
        transcribed_text = await self.llm.transcribe(audio_path)
        logger.info(f"Transcribed Text: {transcribed_text}")
        
        if not transcribed_text or transcribed_text.startswith("Error"):
            logger.error(f"Transcription error: {transcribed_text}")
            return

        # 2. Extract Intent using LLM
        prompt = (
            f"O usuário disse: '{transcribed_text}'. "
            "Extraia o comando de sistema equivalente. Responda APENAS com um JSON no formato: "
            "{\"intent\": \"nome_da_intencao\", \"params\": {\"chave\": \"valor\"}} "
            "Intenções suportadas: volume_set, volume_mute, mic_mute, open_app, sys_info. "
            "Se for abrir um app, use intent 'open_app' e param 'app_name'."
        )
        
        result = await self.llm._execute(prompt)
        if result.success:
            import json
            import re
            try:
                # Clean JSON string (sometimes LLM adds markdown)
                match = re.search(r"\{.*\}", result.data["response"], re.DOTALL)
                if match:
                    json_str = match.group()
                    intent_data = json.loads(json_str)
                    self.handle_intent(intent_data["intent"], intent_data.get("params", {}))
                else:
                    logger.error(f"No JSON found in LLM response: {result.data['response']}")
            except Exception as e:
                logger.error(f"Failed to parse LLM intent: {e} | Response: {result.data['response']}")

    def handle_intent(self, intent: str, params: dict = None):
        """Route system intents to the correct controller."""
        params = params or {}
        logger.info(f"Handling intent: {intent} with params: {params}")
        
        if intent == "volume_set":
            level = params.get("level", 0.5)
            # Try to handle percentage or float
            if isinstance(level, str) and "%" in level:
                level = float(level.replace("%", "")) / 100.0
            return self.audio.set_volume(float(level))
        
        elif intent == "volume_mute":
            return self.audio.toggle_mute()
        
        elif intent == "mic_mute":
            mute = params.get("mute", True)
            return self.audio.set_mic_mute(mute)
        
        elif intent == "open_app":
            app = params.get("app_name")
            if app:
                import subprocess
                subprocess.Popen(["xdg-open", f"https://www.google.com/search?q={app}"]) # Fallback or specific logic
                # Better: subprocess.Popen([app]) if it's a binary
                try:
                    subprocess.Popen([app.lower()])
                    logger.info(f"Opening application: {app}")
                    return True
                except:
                    logger.warning(f"Could not open binary {app}, using search fallback.")
            return False
        
        else:
            logger.warning(f"Unknown system intent: {intent}")
            return False

if __name__ == "__main__":
    manager = SystemManager()
    print("System Manager Ready")
