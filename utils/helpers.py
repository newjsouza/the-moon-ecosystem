"""
utils/helpers.py
Decorators for async execution.
"""
import asyncio
import functools
import time
from typing import Callable, Any

def async_retry(retries: int = 3, base_delay: float = 1.0):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_err = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_err = e
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
            raise last_err
        return wrapper
    return decorator

def timeout_handler(seconds: float):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
        return wrapper
    return decorator

class RateLimiter:
    def __init__(self, calls: int, period: float):
        self.calls = calls
        self.period = period
        self.timestamps = []

    async def acquire(self):
        now = time.time()
        self.timestamps = [t for t in self.timestamps if now - t < self.period]
        if len(self.timestamps) >= self.calls:
            sleep_time = self.timestamps[0] + self.period - now
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        self.timestamps.append(time.time())

def throttle(calls: int, period: float):
    limiter = RateLimiter(calls, period)
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            await limiter.acquire()
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def debounce(wait: float):
    def decorator(func):
        last_called = []
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            now = time.time()
            if last_called and now - last_called[0] < wait:
                return None
            last_called.clear()
            last_called.append(now)
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def memoize():
    cache = {}
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            if key not in cache:
                cache[key] = await func(*args, **kwargs)
            return cache[key]
        return wrapper
    return decorator
