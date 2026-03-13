# AI Jail - Sandbox para Agentes de IA

> Baseado no conceito do Método Akita: isolar operações perigosas para proteger o sistema.

## Visão Geral

O AI Jail é um sandbox que executa código gerado por agentes de IA em um ambiente isolado, protegendo o sistema host de operações potencialmente perigosas.

## Funcionalidades

- **Execução Isolada**: Código executado em diretório temporário isolado
- **Timeout**: Limite de tempo para evitar loops infinitos
- **Limite de Recursos**: Controle de memória e tamanho de arquivo
- **Firewall de Comandos**: Blocklist de comandos perigosos (`rm -rf /`, `dd if=`, etc.)
- **Allowlist de Diretórios**: Apenas diretórios permitidos podem ser acessados
- **Controle de Rede**: Opção de desabilitar acesso à rede
- **Logging**: Todos os comandos são logados para auditoria

## Uso

```python
from ai_jail import AIJail, JailConfig, create_safe_jail

# Configuração padrão (segura)
with create_safe_jail() as jail:
    result = jail.execute_python("print('Hello from sandbox!')")
    print(result.stdout)

# Configuração personalizada
config = JailConfig(
    allowed_dirs=["/tmp/myapp"],
    max_execution_time=60,
    allow_network=False
)

with AIJail(config) as jail:
    result = jail.execute_bash("ls -la")
```

## API

### JailConfig

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|--------|-----------|
| allowed_dirs | List[str] | [] | Diretórios permitidos |
| max_execution_time | int | 30s | Tempo máximo de execução |
| max_memory_mb | int | 512 | Limite de memória |
| max_file_size_mb | int | 10 | Tamanho máximo de arquivo |
| allow_network | bool | False | Permitir acesso à rede |
| allow_subprocess | bool | False | Permitir subprocessos |
| blocked_commands | List[str] | [...] | Comandos bloqueados |

### ExecutionResult

| Campo | Tipo | Descrição |
|-------|------|-----------|
| success | bool | Se a execução foi bem-sucedida |
| stdout | str | Saída padrão |
| stderr | str | Erros |
| return_code | int | Código de retorno |
| execution_time | float | Tempo de execução |
| blocked_operations | List[str] | Operações bloqueadas |

## Linha de Comando

```bash
python ai_jail.py "ls -la"
python ai_jail.py --code "print('test')" --timeout 10
```

## Exemplo de Integração com Agente

```python
async def agent_execute_code(agent, code: str) -> str:
    """Execute code from agent in sandbox."""
    with create_safe_jail() as jail:
        result = await asyncio.wait_for(
            jail.execute_python(code),
            timeout=30
        )
        
        if result.success:
            return result.stdout
        else:
            return f"Error: {result.stderr}"
```

## Logs

Os logs de execução são armazenados em memória e podem ser exportados:

```python
jail.export_log("execution_log.json")
```

---

*Baseado no conceito do Akita: O agente nunca diz "não" - implementa o que você pedir. O AI Jail é o "freio", o code review automático, "o adulto na sala".*
