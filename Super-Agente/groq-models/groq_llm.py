#!/usr/bin/env python3
"""
Groq LLM Wrapper - Use all Groq models from your account

Models available:
- llama-3.3-70b-versatile (131K ctx)
- qwen/qwen3-32b (131K ctx)
- llama-3.1-8b-instant (131K ctx)
- meta-llama/llama-4-scout-17b-16e-instruct (131K ctx)
- moonshotai/kimi-k2-instruct (131K ctx)
- openai/gpt-oss-120b (131K ctx)
- openai/gpt-oss-20b (131K ctx)
- groq/compound (131K ctx)
- groq/compound-mini (131K ctx)
- allam-2-7b (4K ctx)
- canopylabs/orpheus-v1-english (4K ctx)
- canopylabs/orpheus-arabic-saudi (4K ctx)
"""

import os
import sys
import json
import argparse

# Your Groq API Key
GROQ_API_KEY = "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"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Model aliases for easier use
MODELS = {
    # Main models
    "llama-3.3-70b": "llama-3.3-70b-versatile",
    "llama70b": "llama-3.3-70b-versatile",
    "llama3.3": "llama-3.3-70b-versatile",
    
    "qwen3-32b": "qwen/qwen3-32b",
    "qwen32b": "qwen/qwen3-32b",
    
    "llama-3.1-8b": "llama-3.1-8b-instant",
    "llama3.1": "llama-3.1-8b-instant",
    "llama8b": "llama-3.1-8b-instant",
    
    "llama-4-scout": "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama4": "meta-llama/llama-4-scout-17b-16e-instruct",
    
    "kimi-k2": "moonshotai/kimi-k2-instruct",
    "kimi": "moonshotai/kimi-k2-instruct",
    
    "gpt-oss-120b": "openai/gpt-oss-120b",
    "gptoss120b": "openai/gpt-oss-120b",
    
    "gpt-oss-20b": "openai/gpt-oss-20b",
    "gptoss20b": "openai/gpt-oss-20b",
    
    "compound": "groq/compound",
    "compound-mini": "groq/compound-mini",
    
    "allam": "allam-2-7b",
    "allam-2": "allam-2-7b",
    
    "orpheus": "canopylabs/orpheus-v1-english",
    "orpheus-en": "canopylabs/orpheus-v1-english",
    "orpheus-arabic": "canopylabs/orpheus-arabic-saudi",
}

def get_model_id(alias):
    """Get full model ID from alias"""
    if alias in MODELS:
        return MODELS[alias]
    # Check if it's already a full model ID
    for model_id in MODELS.values():
        if alias.lower() in model_id.lower():
            return model_id
    return alias

def chat(model: str, messages: list, temperature: float = 0.7, max_tokens: int = None, stream: bool = False):
    """Send a chat request to Groq API"""
    import urllib.request
    import urllib.error
    
    model_id = get_model_id(model)
    
    try:
        import requests
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens:
            data["max_tokens"] = max_tokens
        
        if stream:
            data["stream"] = True
        
        response = requests.post(
            GROQ_API_URL,
            json=data,
            headers=headers,
            timeout=120
        )
        
        if response.status_code != 200:
            print(f"Error: {response.status_code} - {response.text}", file=sys.stderr)
            return None
        
        result = response.json()
        return result.get('choices', [{}])[0].get('message', {}).get('content', '')
        
    except ImportError:
        # Fallback to urllib
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens:
            data["max_tokens"] = max_tokens
        
        if stream:
            data["stream"] = True
        
        req = urllib.request.Request(
            GROQ_API_URL,
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('choices', [{}])[0].get('message', {}).get('content', '')

def interactive(model: str = "llama-3.3-70b-versatile"):
    """Start an interactive chat session"""
    print(f"Groq Chat - Model: {get_model_id(model)}")
    print("Type 'quit' or 'exit' to end session")
    print("Type 'switch <model>' to change model")
    print("-" * 50)
    
    messages = []
    
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        
        if user_input.lower() in ['quit', 'exit']:
            break
        
        if user_input.lower().startswith('switch '):
            model = user_input[7:].strip()
            print(f"Switched to model: {get_model_id(model)}")
            continue
        
        if not user_input:
            continue
        
        messages.append({"role": "user", "content": user_input})
        
        response = chat(model, messages)
        
        if response:
            print(f"\nAssistant: {response}")
            messages.append({"role": "assistant", "content": response})
        else:
            print("Failed to get response")

def main():
    parser = argparse.ArgumentParser(description="Groq LLM Wrapper")
    parser.add_argument("-m", "--model", default="llama-3.3-70b-versatile", 
                       help="Model to use (default: llama-3.3-70b-versatile)")
    parser.add_argument("-p", "--prompt", help="Single prompt to send")
    parser.add_argument("--interactive", "-i", action="store_true", help="Start interactive chat")
    parser.add_argument("--temp", type=float, default=0.7, help="Temperature (default: 0.7)")
    parser.add_argument("--max-tokens", type=int, help="Max tokens")
    
    args = parser.parse_args()
    
    if args.interactive or args.prompt is None:
        interactive(args.model)
    else:
        messages = [{"role": "user", "content": args.prompt}]
        response = chat(args.model, messages, temperature=args.temp, max_tokens=args.max_tokens)
        if response:
            print(response)

if __name__ == "__main__":
    main()
