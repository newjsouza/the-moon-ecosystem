"""
core/system/audio.py
High-level audio control for Linux using wpctl.
"""
import subprocess
import re
from utils.logger import setup_logger

logger = setup_logger("AudioController")

class AudioController:
    @staticmethod
    def get_default_sink():
        """Get the ID of the default audio sink."""
        try:
            res = subprocess.check_output(["wpctl", "status"]).decode()
            # Look for the sink with '*' prefix
            match = re.search(r"\* +(\d+)\. ", res)
            if match:
                return match.group(1)
        except Exception as e:
            logger.error(f"Failed to get default sink: {e}")
        return None

    @staticmethod
    def get_volume():
        """Get current volume of the default sink (0.0 to 1.0)."""
        try:
            res = subprocess.check_output(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]).decode()
            match = re.search(r"Volume: ([\d\.]+)", res)
            if match:
                return float(match.group(1))
        except Exception as e:
            logger.error(f"Failed to get volume: {e}")
        return 0.0

    @staticmethod
    def set_volume(level: float):
        """Set volume of the default sink (0.0 to 1.0)."""
        try:
            # level must be between 0.0 and 1.5 (wpctl allows > 1.0)
            level = max(0.0, min(1.5, level))
            subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", str(level)], check=True)
            logger.info(f"Volume set to {level}")
            return True
        except Exception as e:
            logger.error(f"Failed to set volume: {e}")
        return False

    @staticmethod
    def toggle_mute():
        """Toggle mute state of the default sink."""
        try:
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"], check=True)
            logger.info("Mute toggled")
            return True
        except Exception as e:
            logger.error(f"Failed to toggle mute: {e}")
        return False

    @staticmethod
    def is_muted():
        """Check if the default sink is muted."""
        try:
            res = subprocess.check_output(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"]).decode()
            return "[MUTED]" in res
        except Exception as e:
            logger.error(f"Failed to check mute status: {e}")
        return False

    @staticmethod
    def set_mic_mute(mute: bool = True):
        """Mute or unmute the default microphone."""
        val = "1" if mute else "0"
        try:
            subprocess.run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", val], check=True)
            logger.info(f"Microphone {'muted' if mute else 'unmuted'}")
            return True
        except Exception as e:
            logger.error(f"Failed to set mic mute: {e}")
        return False

if __name__ == "__main__":
    # Simple test
    print(f"Current Volume: {AudioController.get_volume()}")
    print(f"Is Muted: {AudioController.is_muted()}")
