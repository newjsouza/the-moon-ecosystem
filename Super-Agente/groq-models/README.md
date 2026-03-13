# Groq Models Configuration

## Available Models

| Model | Context | Max Output | Best For |
|-------|---------|------------|----------|
| **llama-3.3-70b-versatile** | 131K | 32K | General purpose, best overall |
| **qwen/qwen3-32b** | 131K | 40K | Coding, reasoning |
| **llama-3.1-8b-instant** | 131K | 131K | Fast responses, cheap |
| **meta-llama/llama-4-scout-17b-16e-instruct** | 131K | 8K | Latest Llama 4 |
| **moonshotai/kimi-k2-instruct** | 131K | 16K | Long context tasks |
| **openai/gpt-oss-120b** | 131K | 65K | Large model |
| **openai/gpt-oss-20b** | 131K | 65K | Medium-large model |
| **groq/compound** | 131K | 8K | Fast compound model |
| **groq/compound-mini** | 131K | 8K | Fast compound model (mini) |
| **allam-2-7b** | 4K | 4K | Arabic language |
| **canopylabs/orpheus-v1-english** | 4K | 50K | English TTS |
| **canopylabs/orpheus-arabic-saudi** | 4K | 50K | Arabic TTS |

## Quick Start

### Interactive Chat
```bash
cd Super-Agente/groq-models
python3 groq_llm.py --interactive -m llama-3.3-70b-versatile
```

### Single Prompt
```bash
python3 groq_llm.py -m llama-3.1-8b-instant -p "Hello, how are you?"
```

### Using Shell Script
```bash
./groq.sh llama-3.3-70b-versatile "What is Python?"
```

### Using Aliases
```bash
python3 groq_llm.py -m llama70b -p "Hello!"
python3 groq_llm.py -m qwen32b -p "Write a function"
python3 groq_llm.py -m compound -p "Summarize this"
```

## API Key

Your Groq API key is configured in `groq_llm.py`:
```
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
```

## Examples

### Code Generation
```bash
python3 groq_llm.py -m qwen3-32b -p "Write a Python function to fibonacci"
```

### Long Context
```bash
python3 groq_llm.py -m kimi-k2 -p "Summarize this long article..."
```

### Fast Response
```bash
python3 groq_llm.py -m llama-3.1-8b-instant -p "What is 2+2?"
```

## Notes

- Groq models are extremely fast (GPU-accelerated)
- No local hardware required
- Uses your Groq API credits
- Context window up to 131K tokens
