"""
core/system/shortcuts.py
Global shortcut listener for The Moon.
Triggers voice capture on AltGr + Alt_R/Right Ctrl.
"""
from pynput import keyboard
from core.system.voice import VoiceRecorder
from core.system.manager import SystemManager
from utils.logger import setup_logger
import threading

logger = setup_logger("ShortcutListener")

class ShortcutListener:
    def __init__(self, system_manager=None, on_press_callback=None, on_release_callback=None):
        self.recorder = VoiceRecorder()
        self.manager = system_manager or SystemManager()
        self.pressed_keys = set()
        
        # User requested: AltGR + Right Control
        self.trigger_keys = {keyboard.Key.alt_gr, keyboard.Key.ctrl_r}
        
        self.is_recording = False
        self.on_press_callback = on_press_callback
        self.on_release_callback = on_release_callback

    def on_press(self, key):
        self.pressed_keys.add(key)
        
        if all(k in self.pressed_keys for k in self.trigger_keys):
            if not self.is_recording:
                logger.info("Trigger keys detected! Starting capture...")
                self.is_recording = True
                self.recorder.start_recording()
                if self.on_press_callback:
                    self.on_press_callback()

    def on_release(self, key):
        if key in self.pressed_keys:
            self.pressed_keys.remove(key)
        
        if key in self.trigger_keys and self.is_recording:
            logger.info("Trigger key released. Stopping capture...")
            self.is_recording = False
            audio_path = self.recorder.stop_recording()
            
            # Process audio through SystemManager
            if audio_path:
                threading.Thread(target=self.manager.process_voice_command, args=(audio_path,)).start()
            
            if self.on_release_callback:
                threading.Thread(target=self.on_release_callback, args=(audio_path,)).start()

    def start(self):
        logger.info(f"Shortcut listener started. Monitorando: {self.trigger_keys}")
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()

if __name__ == "__main__":
    def result_handler(path):
        print(f"Capture finished. Audio saved at: {path}")

    listener = ShortcutListener(on_release_callback=result_handler)
    listener.start()
