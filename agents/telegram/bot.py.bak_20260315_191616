import os
import logging
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from pydub import AudioSegment
import tempfile
from dotenv import load_dotenv
import sys
from pathlib import Path
import edge_tts

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.append(str(root_dir))

from agents.sports.manager import SportsManager

load_dotenv()

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure pydub and environment
ffmpeg_path = os.path.join(root_dir, "infrastructure", "ffmpeg")
ffprobe_path = os.path.join(root_dir, "infrastructure", "ffprobe")

if os.path.exists(ffmpeg_path):
    AudioSegment.converter = ffmpeg_path
    if os.path.exists(ffprobe_path):
        AudioSegment.ffprobe = ffprobe_path
        # Force add to PATH so other tools (like pydub's background calls) find it
        infrastructure_dir = os.path.join(root_dir, "infrastructure")
        os.environ["PATH"] += os.pathsep + infrastructure_dir
    logger.info(f"Using static ffmpeg/ffprobe at: {ffmpeg_path}")
else:
    logger.warning(f"Static ffmpeg not found at {ffmpeg_path}. Audio processing might fail.")

class MoonSportsBot:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        self.sports_manager = SportsManager()
        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN not found in .env. Bot will not start.")

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "🚀 *The Moon - Sports Analysis Bot*\n\n"
            "Eu sou seu assistente de análise de apostas. Posso processar texto e áudio.\n\n"
            "Comandos:\n"
            "/status - Ver status da banca\n"
            "/odds - Ver odds de hoje\n"
            "/ajuda - Lista de comandos",
            parse_mode='Markdown'
        )

    async def _get_match_context(self, user_text: str) -> str:
        """Determines if the user wants matches and returns them as context."""
        user_text_lower = user_text.lower()
        days_offset = -1
        
        if "amanhã" in user_text_lower:
            days_offset = 1
        elif "hoje" in user_text_lower:
            days_offset = 0
            
        if days_offset != -1:
            try:
                matches = await self.sports_manager.get_upcoming_opportunities(days_offset)
                date_str = "hoje" if days_offset == 0 else "amanhã"
                
                if matches:
                    context = f"Aqui estão os JOGOS REAIS agendados para {date_str} (fonte oficial Football-data.org):\n"
                    for m in matches:
                        context += f"- {m['teams']} ({m['competition']}) às {m['utcDate']}\n"
                    context += "\nDIRETRIZ CRÍTICA: Responda ao usuário baseando-se EXCLUSIVAMENTE nesta lista. Se o usuário perguntar por times não citados aqui, informe que, no momento, o nosso provedor de dados oficial não está cobrindo esses jogos específicos. JAMAIS tente adivinhar ou usar conhecimento prévio do modelo para datas futuras. Diga: 'Meus dados live atuais não mostram esse jogo'."
                    return context
                else:
                    return f"ALERTA DE DADOS: O provedor Football-data.org retornou ZERO jogos para {date_str} nas 13 ligas acompanhadas. Informe ao usuário: 'No momento, não existem jogos das ligas monitoradas agendados/em andamento para {date_str}'. NÃO OFEREÇA EXEMPLOS."
            except Exception as e:
                logger.error(f"Error in _get_match_context: {e}")
                return "AVISO: Houve um erro ao acessar o provedor de dados. Informe ao usuário que o serviço de dados está temporariamente indisponível."
        return ""

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages using Groq with real context"""
        user_text = update.message.text
        logger.info(f"Received text: {user_text}")
        
        match_context = await self._get_match_context(user_text)
        system_prompt = "Você é um assistente especialista em apostas esportivas do ecossistema 'The Moon'. Responda de forma analítica, profissional e direta em português. "
        if match_context:
            system_prompt += f"\nCONTEXTO REAL ATUALIZADO:\n{match_context}"
        else:
            system_prompt += "\nAVISO: Se o usuário perguntar sobre jogos específicos e você não tiver o CONTEXTO REAL, informe que precisa que ele especifique a data (hoje/amanhã) ou que no momento você não tem os dados live. NUNCA use dados de exemplo ou inventados."

        try:
            completion = self.groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ]
            )
            response = completion.choices[0].message.content
            await update.message.reply_text(response)
        except Exception as e:
            logger.error(f"Error calling Groq: {e}")
            await update.message.reply_text("Desculpe, tive um problema ao processar sua mensagem.")

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle voice messages: Transcription -> Groq -> Response"""
        logger.info("Received voice message")
        await update.message.reply_text("🎧 Ouvindo áudio... transcrevendo...")

        try:
            # 1. Download voice file
            voice_file = await context.bot.get_file(update.message.voice.file_id)
            
            with tempfile.TemporaryDirectory() as tmpdir:
                oga_path = os.path.join(tmpdir, "voice.oga")
                wav_path = os.path.join(tmpdir, "voice.wav")
                
                await voice_file.download_to_drive(oga_path)
                
                # 2. Convert OGA to WAV using pydub (requires ffmpeg)
                audio = AudioSegment.from_ogg(oga_path)
                audio.export(wav_path, format="wav")
                
                # 3. Transcribe with Groq Whisper
                with open(wav_path, "rb") as file:
                    transcription = self.groq_client.audio.transcriptions.create(
                        file=(wav_path, file.read()),
                        model="whisper-large-v3",
                        language="pt"
                    )
                
                transcribed_text = transcription.text
                logger.info(f"Transcribed: {transcribed_text}")
                
                # 4. Process transcribed text with Groq LLM
                await update.message.reply_text(f"📝 *Transcrição:* {transcribed_text}", parse_mode='Markdown')
                
                match_context = await self._get_match_context(transcribed_text)
                system_prompt = "Você é um assistente especialista em apostas esportivas do ecossistema 'The Moon'. Responda de forma analítica, profissional e direta em português. "
                if match_context:
                    system_prompt += f"\nCONTEXTO REAL ATUALIZADO:\n{match_context}"
                else:
                    system_prompt += "\nAVISO: Se o usuário perguntar sobre jogos específicos e você não tiver o CONTEXTO REAL, informe que você não tem acesso aos dados live para esse período específico no momento. NUNCA use dados de exemplo ou inventados."

                completion = self.groq_client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": transcribed_text}
                    ]
                )
                response = completion.choices[0].message.content
                
                # 5. Generate audio response
                await update.message.reply_text("🎙️ Gerando resposta em áudio...")
                audio_response_path = os.path.join(tmpdir, "response.mp3")
                communicate = edge_tts.Communicate(response, "pt-BR-AntonioNeural")
                await communicate.save(audio_response_path)
                
                # 6. Send audio response back
                with open(audio_response_path, "rb") as audio_file:
                    await update.message.reply_voice(voice=audio_file, caption="Aqui está minha análise.")
                
                await update.message.reply_text(response)

        except Exception as e:
            logger.error(f"Error handling voice: {e}")
            await update.message.reply_text("Houve um erro ao processar seu áudio. Verifique se o ffmpeg está instalado corretamente.")

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        # Placeholder for actual banca status integration
        await update.message.reply_text("💰 *Status da Banca*\nBanca Total: R$ 1000.00\nROI Mensal: +15%", parse_mode='Markdown')

    async def get_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /id command to show Chat ID"""
        chat_id = update.effective_chat.id
        await update.message.reply_text(f"🆔 Seu Chat ID é: `{chat_id}`", parse_mode='Markdown')

    def run(self):
        """Run the bot"""
        if not self.token:
            return
            
        application = ApplicationBuilder().token(self.token).build()
        
        application.add_handler(CommandHandler('start', self.start))
        application.add_handler(CommandHandler('status', self.status))
        application.add_handler(CommandHandler('id', self.get_id))
        application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_message))
        application.add_handler(MessageHandler(filters.VOICE, self.handle_voice))
        
        logger.info("Starting Telegram bot...")
        application.run_polling()

if __name__ == '__main__':
    bot = MoonSportsBot()
    bot.run()
