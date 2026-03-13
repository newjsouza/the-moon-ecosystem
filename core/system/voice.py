"""
core/system/voice.py
Audio recording using PipeWire (pw-record).
"""
import subprocess
import os
import signal
from utils.logger import setup_logger

logger = setup_logger("VoiceRecorder")

class VoiceRecorder:
    def __init__(self, output_path="/tmp/moon_voice.wav"):
        self.output_path = output_path
        self._process = None

    def start_recording(self):
        """Start recording audio from default source."""
        if self._process:
            logger.warning("Recording already in progress.")
            return

        try:
            logger.info(f"Starting recording to {self.output_path}")
            # pw-record saves to wav by default if extension is .wav
            self._process = subprocess.Popen(
                ["pw-record", self.output_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")

    def stop_recording(self):
        """Stop recording and return the path to the audio file."""
        if not self._process:
            logger.warning("No recording in progress.")
            return None

        try:
            logger.info("Stopping recording")
            # Send SIGINT to stop pw-record gracefully
            os.killpg(os.getpgid(self._process.pid), signal.SIGINT)
            self._process.wait(timeout=2)
        except Exception as e:
            logger.error(f"Error stopping recording: {e}")
            self._process.kill()
        finally:
            self._process = None
        
        if os.path.exists(self.output_path):
            return self.output_path
        return None

if __name__ == "__main__":
    # Test
    import time
    recorder = VoiceRecorder()
    recorder.start_recording()
    time.sleep(3)
    path = recorder.stop_recording()
    print(f"Recorded to: {path}")
