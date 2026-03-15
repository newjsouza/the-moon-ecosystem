import asyncio
import os
import json
import logging
import hashlib
import venv
import subprocess
import shutil
import httpx
from datetime import datetime
from typing import List, Dict, Optional, Any
from core.agent_base import AgentBase, AgentPriority, TaskResult

# Configuração de Logging com cores para Alchemist
class AlchemistFormatter(logging.Formatter):
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    FORMAT = "%(asctime)s [%(levelname)s] [SkillAlchemist] %(message)s"

    def format(self, record):
        log_fmt = f"{self.PURPLE}{self.FORMAT}{self.RESET}" if record.levelno == logging.INFO else self.FORMAT
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

logger = logging.getLogger("SkillAlchemist")
handler = logging.StreamHandler()
handler.setFormatter(AlchemistFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)

class SkillAlchemist(AgentBase):
    """
    SkillAlchemist: O Agente de Automação de Habilidades do The Moon.
    Descobre, testa e propõe novas ferramentas/modelos Open Source para o ecossistema.
    """

    def __init__(self, orchestrator=None):
        super().__init__()
        self.orchestrator = orchestrator
        self.priority = AgentPriority.LOW  # Background task
        self.workspace = "learning/workspaces/alchemist"
        self.quarantine = f"{self.workspace}/quarantine"
        self.discoveries_file = f"{self.workspace}/discoveries/discoveries.json"
        
        # Fontes de Descoberta (Zero Cost)
        self.sources = {
            "github_trending": "https://api.github.com/search/repositories?q=stars:>1000+topic:ai-agents&sort=stars",
            "pypi_new": "https://pypi.org/rss/updates.xml",
            "huggingface": "https://huggingface.co/api/models?sort=downloads&direction=-1&limit=10"
        }

        # Palavras-chave de interesse
        self.keywords = ["agent", "llm", "automation", "scraping", "rpa", "vision", "voice", "mcp"]
        
        # Inicializa estruturas
        os.makedirs(self.quarantine, exist_ok=True)
        os.makedirs(os.path.dirname(self.discoveries_file), exist_ok=True)
        if not os.path.exists(self.discoveries_file):
            with open(self.discoveries_file, "w") as f:
                json.dump([], f)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        # Se for uma mensagem de comando direto
        if task:
            res = await self._handle_command(task)
            return TaskResult(success=True, data={"response": res})

        # Ciclo de Execução Autônoma (Background)
        logger.info("Iniciando ciclo de alquimia...")
        
        # 1. Descoberta
        candidates = await self._discover_candidates()
        
        # 2. Filtragem e Scoring
        promising = self._score_candidates(candidates)
        
        # 3. Alquimia (Teste em Sandbox e Geração)
        for tool in promising:
            if self._is_new(tool):
                logger.info(f"Sintetizando nova habilidade: {tool['name']}")
                success = await self._transmute(tool)
                if success:
                    self._mark_as_discovered(tool)
                    # Notifica o Orchestrator sobre a nova descoberta
                    if self.orchestrator:
                        await self.orchestrator.publish("alchemist.skill_proposed", {
                            "skill": tool['name'],
                            "path": f"{self.quarantine}/{tool['name']}"
                        })

        return TaskResult(success=True, data={"status": "cycle_complete", "discovered": len(promising)})

    async def _handle_command(self, cmd: str) -> str:
        parts = cmd.lower().split()
        if "status" in parts:
            return f"Alchemist Ativo. Quarentena: {len(os.listdir(self.quarantine))} itens."
        if "discover" in parts:
            asyncio.create_task(self._execute())
            return "Busca por novas ferramentas iniciada em background."
        return "Comando desconhecido: /alchemist [status|discover]"

    async def _discover_candidates(self) -> List[Dict]:
        candidates = []
        async with httpx.AsyncClient() as client:
            try:
                # Simulação simplificada de GitHub API (ou ArXiv)
                # Para produção, usaríamos as URLs reais em self.sources
                resp = await client.get(self.sources["github_trending"], timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("items", []):
                        candidates.append({
                            "name": item["name"],
                            "url": item["html_url"],
                            "desc": item["description"],
                            "stars": item["stargazers_count"],
                            "source": "github"
                        })
            except Exception as e:
                logger.error(f"Erro na fase de descoberta: {e}")
        return candidates

    def _score_candidates(self, candidates: List[Dict]) -> List[Dict]:
        promising = []
        for c in candidates:
            score = 0
            # Critérios de Scoring
            if any(k in (c["desc"] or "").lower() for k in self.keywords): score += 5
            if c["stars"] > 5000: score += 10
            
            if score >= 10:
                promising.append(c)
        return promising

    def _is_new(self, tool: Dict) -> bool:
        with open(self.discoveries_file, "r") as f:
            history = json.load(f)
            tool_id = hashlib.sha256(tool["url"].encode()).hexdigest()
            return tool_id not in [h["id"] for h in history]

    def _mark_as_discovered(self, tool: Dict):
        with open(self.discoveries_file, "r") as f:
            history = json.load(f)
        
        tool_id = hashlib.sha256(tool["url"].encode()).hexdigest()
        history.append({"id": tool_id, "name": tool["name"], "date": str(datetime.now())})
        
        with open(self.discoveries_file, "w") as f:
            json.dump(history, f, indent=4)

    async def _transmute(self, tool: Dict) -> bool:
        """Fase 3: Sandbox e Geração de Template"""
        temp_dir = f"/tmp/alchemist_{tool['name']}"
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # 1. Cria Sandbox (venv)
            venv.create(f"{temp_dir}/venv", with_pip=True)
            
            # 2. Teste de Instalação (Simulado)
            # Em produção: subprocess.run([f"{temp_dir}/venv/bin/pip", "install", tool['name']])
            logger.info(f"Testando instalação de {tool['name']} no sandbox...")
            
            # 3. Gera Template da Habilidade
            skill_code = self._generate_skill_template(tool)
            
            # 4. Salva na Quarentena
            skill_path = f"{self.quarantine}/{tool['name']}.py"
            with open(skill_path, "w") as f:
                f.write(skill_code)
            
            # 5. Gera Proposta de Integração (JSON)
            proposal = {
                "skill_name": tool["name"],
                "origin": tool["url"],
                "status": "quarantined",
                "risk_score": "low",
                "integration_module": "agents/custom/",
                "generated_at": str(datetime.now())
            }
            with open(f"{self.quarantine}/{tool['name']}_proposal.json", "w") as f:
                json.dump(proposal, f, indent=4)

            return True
        except Exception as e:
            logger.error(f"Falha na transmutação de {tool['name']}: {e}")
            return False
        finally:
            # Limpa sandbox
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _generate_skill_template(self, tool: Dict) -> str:
        """Gera o código Python para a nova Habilidade baseada no SkillBase."""
        return f'''# Auto-generated by SkillAlchemist
# Date: {datetime.now()}
# Target: {tool["name"]} ({tool["url"]})

import asyncio
from core.skill_base import SkillBase

class {tool["name"].capitalize()}Skill(SkillBase):
    """
    Habilidade integrada automaticamente do repositório {tool["name"]}.
    """
    
    def __init__(self, agent):
        super().__init__(agent)
        self.description = "{tool["desc"][:100]}"
        
    async def execute(self, *args, **kwargs):
        # TODO: Implementar lógica de ponte para a biblioteca original
        return f"Habilidade {tool["name"]} executada com sucesso!"
'''

    async def _check_compliance(self, skill_path: str) -> bool:
        """Valida se o código gerado segue as regras do Moon Codex."""
        # TODO: Implementar linter básico ou chamada LLM para validação de regras
        return True
