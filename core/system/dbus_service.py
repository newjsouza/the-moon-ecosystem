"""
core/system/dbus_service.py
D-Bus communication layer.
"""
import sys
import os
from utils.logger import setup_logger

logger = setup_logger("DbusService")

try:
    import pydbus
    from gi.repository import GLib
except ImportError:
    logger.warning("pydbus not found. D-Bus functionality will be limited.")
    pydbus = None

class MoonDbusObject:
    """
    <node>
        <interface name='com.themoon.Control'>
            <method name='GetStatus'>
                <arg type='s' name='status' direction='out'/>
            </method>
            <method name='ExecuteCommand'>
                <arg type='s' name='command' direction='in'/>
                <arg type='s' name='result' direction='out'/>
            </method>
        </interface>
    </node>
    """
    def GetStatus(self):
        return "The Moon Ecosystem is Active"

    def ExecuteCommand(self, command):
        logger.info(f"D-Bus command received: {command}")
        return f"Executed: {command}"

class DbusService:
    def __init__(self):
        self.bus = None
        self.loop = None
        if pydbus:
            try:
                self.bus = pydbus.SessionBus()
                self.bus.publish("com.themoon.Control", MoonDbusObject())
                logger.info("D-Bus service published as com.themoon.Control")
            except Exception as e:
                logger.error(f"Failed to publish D-Bus service: {e}")

    def run(self):
        if not self.bus:
            logger.error("D-Bus service not initialized.")
            return
        
        logger.info("D-Bus main loop starting...")
        self.loop = GLib.MainLoop()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            self.loop.quit()

if __name__ == "__main__":
    # Test service
    service = DbusService()
    if service.bus:
        service.run()
