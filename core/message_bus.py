"""
core/message_bus.py
Pub/Sub system for agent communication.
"""
import asyncio
from typing import Any, Callable, Dict, List
import time

class Message:
    def __init__(self, sender: str, topic: str, payload: Any, target: str = None):
        self.sender = sender
        self.topic = topic
        self.payload = payload
        self.target = target
        self.timestamp = time.time()

class MessageBus:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MessageBus, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        self.subscribers: Dict[str, List[Callable]] = {}
        self.history: List[Message] = []
        self._initialized = True

    def subscribe(self, topic: str, callback: Callable):
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(callback)

    def unsubscribe(self, topic: str, callback: Callable):
        if topic in self.subscribers:
            self.subscribers[topic].remove(callback)

    async def publish(self, sender: str, topic: str, payload: Any, target: str = None):
        message = Message(sender, topic, payload, target)
        self.history.append(message)
        
        callbacks = self.subscribers.get(topic, [])
        tasks = []
        for cb in callbacks:
            if asyncio.iscoroutinefunction(cb):
                tasks.append(asyncio.create_task(cb(message)))
            else:
                cb(message)
        
        if tasks:
            await asyncio.gather(*tasks)

    def get_history(self) -> List[Message]:
        return self.history
