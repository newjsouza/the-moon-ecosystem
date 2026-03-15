# Pipeline de Personalização do The Moon - Qwen2.5-0.5B

## Visão Geral do Processo

```
Qwen2.5-0.5B (base) 
    → Fine-tuning com dados do The Moon 
    → Modelo FP16 
    → Conversão para GGUF 
    → Quantização (Q4_K_M) 
    → Modelfile personalizado 
    → Ollama (the_moon)
```

---

## Passo 1: Preparar Dados para Fine-tuning

Crie um arquivo `training_data.jsonl` com exemplos no formato instruction:

```jsonl
{"instruction": "Liste os arquivos do diretório atual", "input": "", "output": "Use o módulo os ou pathlib para listar arquivos."}
{"instruction": "O que é o Orchestrator do The Moon?", "input": "", "output": "O Orchestrator é o componente central que coordena múltiplos agentes e roteia comandos do usuário para o agente correto."}
{"instruction": "Como executar testes no projeto?", "input": "", "output": "Use 'python tdd.py test' para executar testes unitários."}
{"instruction": "O que é o protocolo MCP?", "input": "", "output": "MCP (Model Context Protocol) é um protocolo para conectar LLMs a ferramentas externas como Playwright, filesystem, etc."}
{"instruction": "Liste os comandos Docker disponíveis", "input": "", "output": "docker-compose up (iniciar), docker-compose down (parar), docker ps (listar containers)."}
{"instruction": "Como fazer lint do código?", "input": "", "output": "Execute 'ruff check .' para verificar código ou 'python tdd.py lint'."}
{"instruction": "O que é o ai-jail?", "input": "", "output": "ai-jail é um sandbox de segurança para executar código gerado por IA com restrições."}
{"instruction": "Quais LLMs estão integrados?", "input": "", "output": "Groq, OpenAI, Anthropic (Claude), Ollama (Qwen, Llama, Mistral)."}
```

---

## Passo 2: Fine-tuning com Unsloth (Mais Rápido)

```bash
# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou: venv\Scripts\activate  # Windows

# Instalar Unsloth
pip install unsloth

# Criar script de fine-tuning
cat > finetune_the_moon.py << 'EOF'
from unsloth import FastLanguageModel
import torch

max_seq_length = 2048
dtype = None
load_in_4bit = True

# Carregar modelo base
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "Qwen/Qwen2.5-0.5B-Instruct",
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)

# Adicionar LoRA adapters
model = FastLanguageModel.get_peft_model(
    model,
    r = 16,
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    lora_alpha = 16,
    lora_dropout = 0,
    bias = "none",
    use_gradient_checkpointing = "unsloth",
    random_state = 3407,
)

# Carregar dados
from datasets import load_dataset
dataset = load_dataset("json", data_files="training_data.jsonl", split="train")

def formatting_prompts_func(examples):
    instructions = examples["instruction"]
    inputs = examples["input"]
    outputs = examples["output"]
    texts = []
    for instruction, input_text, output in zip(instructions, inputs, outputs):
        text = f"""### Instruction
{instruction}

### Response
{output}""" + tokenizer.eos_token
        texts.append(text)
    return {"text": texts}

dataset = dataset.map(formatting_prompts_func, batched=True)

# Treinar
from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    training_arguments = TrainingArguments(
        per_device_train_batch_size = 2,
        gradient_accumulation_steps = 4,
        warmup_steps = 10,
        num_train_epochs = 3,
        learning_rate = 2e-4,
        fp16 = not torch.cuda.is_bf16_supported(),
        bf16 = torch.cuda.is_bf16_supported(),
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "outputs",
    ),
)

trainer.train()

# Salvar modelo fine-tuned
model.save_pretrained("the_moon_lora")
tokenizer.save_pretrained("the_moon_lora")

print("Fine-tuning concluído!")
EOF

python finetune_the_moon.py
```

---

## Passo 3: Converter para GGUF e Quantizar

```bash
# Clonar e preparar llama.cpp
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
pip install -r requirements.txt
make -j$(nproc)

# Converter LoRA para FP16 e gerar GGUF
python ./unsloth/merge_embeddings.py the_moon_lora --output the_moon_fp16

# OU usando método alternativo com Unsloth (mais fácil):
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained("the_moon_lora")
FastLanguageModel.for_inference(model)
model.save_pretrained_gguf("the_moon_gguf", tokenizer, quantization_method = "f16")

# Quantizar para Q4_K_M (mais leve, boa qualidade)
cd llama.cpp
./quantize the_moon_gguf/f16.gguf the_moon_q4.gguf q4_k_m

# Verificar tamanho
ls -lh the_moon_q4.gguf
```

---

## Passo 4: Criar Modelfile Personalizado

```bash
# Criar diretório para o modelo
mkdir -p ~/.ollama/models/the_moon

# Copiar modelo quantizado
cp the_moon_q4.gguf ~/.ollama/models/the_moon/

# Criar Modelfile
cat > ~/.ollama/models/the_moon/Modelfile << 'EOF'
FROM ./the_moon_q4.gguf

SYSTEM """
Você é o assistente de IA do projeto The Moon (também conhecido como Jarvis/Super-Agente).

## Sobre o Projeto
The Moon é um ecossistema de agentes de IA para automação e produtividade, desenvolvido em Python.

## Arquitetura do Sistema
- Orchestrator: Coordena múltiplos agentes e roteia comandos
- OllamaAgent: Executa LLMs locais offline
- GroqAgent: Integração com API Groq
- Playwright MCP: Automação de navegador

## Stack Tecnológico
- Python 3.11+, Supabase, Groq, OpenAI, Anthropic
- Docker, Playwright, Redis, Ollama

## Estrutura de Diretórios
- core/orchestrator.py - Nucleo do sistema
- agents/ - Agentes especializados
- ai-jail/ - Sandbox de segurança
- tests/ - Testes pytest
- infrastructure/ - Docker Compose
- Super-Agente/ - Agentes avançados

## Comandos Úteis
- python tdd.py test - Executar testes
- python tdd.py lint - Verificar código
- docker-compose up - Iniciar infraestrutura

## Regras de Resposta
- Use português brasileiro
- Forneça exemplos práticos
- Seja conciso e direto
- Quando appropriate, sugira código Python
"""

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_ctx 2048
EOF

# Criar modelo no Ollama
ollama create the_moon -f ~/.ollama/models/the_moon/Modelfile
```

---

## Passo 5: Testar o Modelo

```bash
# Testar o modelo personalizado
ollama run the_moon "O que é o Orchestrator do The Moon?"

# Listar modelos
ollama list
```

---

## Tamanho Esperado

| Formato | Tamanho Aproximado |
|---------|-------------------|
| Qwen2.5-0.5B (FP16) | ~1 GB |
| Qwen2.5-0.5B (Q8_0) | ~500 MB |
| Qwen2.5-0.5B (Q4_K_M) | ~350 MB |
| Qwen2.5-0.5B (Q3_K_L) | ~280 MB |

---

## Comandos Rápidos (Resumo)

```bash
# 1. Fine-tuning
python finetune_the_moon.py

# 2. Converter e quantizar
python -c "from unsloth import FastLanguageModel; m, t = FastLanguageModel.from_pretrained('the_moon_lora'); m.save_pretrained_gguf('the_moon_gguf', t, quantization_method='q4_k_m')"

# 3. Criar no Ollama
ollama create the_moon -f Modelfile

# 4. Usar
ollama run the_moon
```

---

## Dicas

1. **Para ainda mais leveza**: Use `q3_k_m` ou `q2_k` (menor qualidade)
2. **Para melhor qualidade**: Use `q5_k_m` ou `q6_k`
3. **Dados de treinamento**: Adicione mais exemplos ao `training_data.jsonl` sobre o sistema
4. **Iteração**: Teste o modelo e ajuste o training data conforme necessário
