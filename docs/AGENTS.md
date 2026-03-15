# 🤖 Mapa de Agentes — The Moon Ecosystem

## Camada: Core
| Agente | Arquivo | Prioridade | Depende de |
|--------|---------|-----------|-----------|
| Orchestrator | `core/orchestrator.py` | — | MessageBus, WorkspaceManager |
| WatchdogAgent | `agents/watchdog.py` | CRITICAL | — |
| NexusIntelligence | `agents/nexus_intelligence.py` | HIGH | MessageBus, Groq |

## Camada: Inteligência
| Agente | Arquivo | Prioridade | Depende de |
|--------|---------|-----------|-----------|
| SemanticMemoryWeaver | `agents/semantic_memory_weaver.py` | HIGH | Groq, sentence-transformers |
| OpenCodeAgent | `agents/opencode.py` | HIGH | httpx, Groq (fallback) |
| LlmAgent | `agents/llm_agent.py` | HIGH | Groq |

## Camada: Operacional
| Agente | Arquivo | Prioridade | Depende de |
|--------|---------|-----------|-----------|
| BettingAnalystAgent | `agents/sports/` | MEDIUM | Football-data.org, Groq |
| EconomicSentinel | `agents/economic_sentinel.py` | HIGH | httpx, Groq |
| GithubAgent | `agents/github_agent.py` | MEDIUM | PyGithub |
| AutonomousDevOpsRefactor | `agents/autonomous_devops_refactor.py` | MEDIUM | PyGithub, Groq |

## Camada: Interface
| Agente | Arquivo | Prioridade | Depende de |
|--------|---------|-----------|-----------|
| MoonBot (Telegram) | `agents/telegram/bot.py` | HIGH | AsyncGroq, python-telegram-bot>=20 |
| OmniChannelStrategist | `agents/omni_channel_strategist.py` | MEDIUM | tweepy, httpx, Groq |
| HardwareSynergyBridge | `agents/hardware_synergy_bridge.py` | HIGH | GTK3, sounddevice, Groq |

## Camada: Inovação
| Agente | Arquivo | Prioridade | Depende de |
|--------|---------|-----------|-----------|
| SkillAlchemist | `agents/skill_alchemist.py` | LOW | httpx, Groq, venv |

## Ordem de registro no main.py
```
WatchdogAgent → LlmAgent → OpenCodeAgent → GithubAgent →
BettingAnalystAgent → EconomicSentinel → SemanticMemoryWeaver →
OmniChannelStrategist → HardwareSynergyBridge → AutonomousDevOpsRefactor →
SkillAlchemist → NexusIntelligence  ← SEMPRE POR ÚLTIMO
```

## Topics do MessageBus
```
Publicados:    betting.result | blog.published | content.published
               devops.scan_complete | alchemist.proposal
               sentinel.alert | watchdog.alert | voice.interaction

Assina Nexus:  betting.* | blog.* | content.* | devops.* |
               alchemist.* | sentinel.* | watchdog.* | voice.*
```
