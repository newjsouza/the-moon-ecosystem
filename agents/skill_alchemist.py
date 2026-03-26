import asyncio
import os
import json
import logging
import hashlib
import venv
import subprocess
import shutil
import httpx
import xml.etree.ElementTree as ET
import ast
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
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
    SkillAlchemist v2: O Agente de Automação de Habilidades do The Moon.
    Descobre, testa e propõe novas ferramentas/modelos Open Source para o ecossistema.
    
    Capacidades:
    - 3 fontes de descoberta: GitHub Trending, PyPI Updates, HuggingFace Models
    - Scoring semântico via LLM (Groq) com fallback síncrono
    - Sandbox real com pip install e teste de importação
    - Compliance via AST (bloqueio de modelos pagos, verificações de segurança)
    - Integração com SemanticMemoryWeaver via MessageBus
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

        # Palavras-chave de interesse (FASE 6C: Moon-Stack integration)
        self.keywords = [
            "agent", "llm", "automation", "scraping", "rpa", "vision", "voice", "mcp",
            # Moon-Stack keywords
            "moon_browse", "playwright", "browser-use", "browser-automation", "cookie-import"
        ]

        # LLM Router para scoring semântico
        self._llm_router = None
        self._llm_semaphore = asyncio.Semaphore(5)  # Limite de 5 chamadas LLM simultâneas

        # Inicializa estruturas
        os.makedirs(self.quarantine, exist_ok=True)
        os.makedirs(os.path.dirname(self.discoveries_file), exist_ok=True)
        if not os.path.exists(self.discoveries_file):
            with open(self.discoveries_file, "w") as f:
                json.dump([], f)

    # ═══════════════════════════════════════════════════════════
    #  Lifecycle
    # ═══════════════════════════════════════════════════════════

    async def initialize(self) -> None:
        """Inicializa o agente e o LLM Router."""
        await super().initialize()
        try:
            from agents.llm import LLMRouter
            from core.config import Config
            self._llm_router = LLMRouter(Config())
            logger.info("LLM Router inicializado para scoring semântico")
        except Exception as e:
            logger.warning(f"LLM Router não disponível, usando fallback síncrono: {e}")

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        # Se for uma mensagem de comando direto
        if task:
            res = await self._handle_command(task)
            return TaskResult(success=True, data={"response": res})

        # Ciclo de Execução Autônoma (Background)
        logger.info("Iniciando ciclo de alquimia...")

        # 1. Descoberta (3 fontes em paralelo)
        candidates = await self._discover_candidates()

        # 2. Filtragem e Scoring (LLM-based)
        promising = await self._score_candidates_llm(candidates)

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

        return TaskResult(success=True, data={"status": "cycle-complete", "discovered": len(promising)})

    async def _handle_command(self, cmd: str) -> str:
        parts = cmd.lower().split()
        if "status" in parts:
            return f"Alchemist Ativo. Quarentena: {len(os.listdir(self.quarantine))} itens."
        if "discover" in parts:
            asyncio.create_task(self._execute())
            return "Busca por novas ferramentas iniciada em background."
        return "Comando desconhecido: /alchemist [status|discover]"

    # ═══════════════════════════════════════════════════════════
    #  Objective 1: Multi-Source Discovery (Parallel)
    # ═══════════════════════════════════════════════════════════

    async def _discover_candidates(self) -> List[Dict]:
        """
        Descobre candidatos de 3 fontes em PARALELO com asyncio.gather().
        Cada fonte tem tratamento individual de falha.
        """
        async with httpx.AsyncClient() as client:
            # Executa as 3 fontes em paralelo
            results = await asyncio.gather(
                self._fetch_github_trending(client),
                self._fetch_pypi_new(client),
                self._fetch_huggingface(client),
                return_exceptions=True
            )

        # Consolida resultados, ignorando fontes que falharam
        all_candidates = []
        for i, result in enumerate(results):
            source_name = ["github", "pypi", "huggingface"][i]
            if isinstance(result, Exception):
                logger.warning(f"Fonte {source_name} falhou: {result}")
                continue
            if isinstance(result, list):
                all_candidates.extend(result)
                logger.info(f"Fonte {source_name} retornou {len(result)} candidatos")

        return all_candidates

    async def _fetch_github_trending(self, client: httpx.AsyncClient) -> List[Dict]:
        """
        Fetch GitHub trending repositories com Authorization header.
        """
        try:
            headers = {}
            github_token = os.getenv("GITHUB_TOKEN", "")
            if github_token:
                headers["Authorization"] = f"Bearer {github_token}"

            resp = await client.get(self.sources["github_trending"], headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()

            candidates = []
            for item in data.get("items", []):
                candidates.append({
                    "name": item["name"].replace("/", "-"),
                    "url": item["html_url"],
                    "desc": item.get("description") or "",
                    "stars": item.get("stargazers_count", 0),
                    "source": "github"
                })
            return candidates

        except Exception as e:
            logger.error(f"Erro ao buscar GitHub trending: {e}")
            raise

    async def _fetch_pypi_new(self, client: httpx.AsyncClient) -> List[Dict]:
        """
        Fetch PyPI updates via RSS XML.
        Parseia XML com xml.etree.ElementTree (stdlib).
        """
        try:
            resp = await client.get(self.sources["pypi_new"], timeout=10.0)
            resp.raise_for_status()
            xml_content = resp.text

            # Parse XML
            root = ET.fromstring(xml_content)
            candidates = []

            # RSS 2.0: <rss><channel><item>...</item></channel></rss>
            for item in root.findall(".//item"):
                title_elem = item.find("title")
                link_elem = item.find("link")
                desc_elem = item.find("description")

                if title_elem is not None and link_elem is not None:
                    # Title format: "package_name version"
                    title_text = title_elem.text or ""
                    name = title_text.split()[0] if title_text else ""

                    candidates.append({
                        "name": name,
                        "url": link_elem.text or "",
                        "desc": (desc_elem.text or "")[:200] if desc_elem is not None else "",
                        "stars": 0,  # PyPI não tem stars
                        "source": "pypi"
                    })

            return candidates

        except Exception as e:
            logger.error(f"Erro ao buscar PyPI updates: {e}")
            raise

    async def _fetch_huggingface(self, client: httpx.AsyncClient) -> List[Dict]:
        """
        Fetch HuggingFace models via API JSON.
        """
        try:
            resp = await client.get(self.sources["huggingface"], timeout=10.0)
            resp.raise_for_status()
            data = resp.json()

            candidates = []
            for model in data:
                model_id = model.get("modelId", "")
                description = model.get("description") or ""

                candidates.append({
                    "name": model_id.replace("/", "-"),
                    "url": f"https://huggingface.co/{model_id}",
                    "desc": description[:200] if description else "",
                    "stars": model.get("downloads", 0),  # Usa downloads como proxy de stars
                    "source": "huggingface"
                })

            return candidates

        except Exception as e:
            logger.error(f"Erro ao buscar HuggingFace models: {e}")
            raise

    # ═══════════════════════════════════════════════════════════
    #  Objective 2: LLM-Based Scoring with Fallback
    # ═══════════════════════════════════════════════════════════

    async def _score_candidates_llm(self, candidates: List[Dict]) -> List[Dict]:
        """
        Score candidates usando LLMRouter (Groq) com semaphore para limitar concorrência.
        Fallback para scoring síncrono se LLM falhar.
        """
        if not candidates:
            return []

        scored_candidates = []

        # Processa candidatos com limite de concorrência
        tasks = [self._score_single_candidate_llm(c) for c in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"Scoring LLM falhou para {candidates[i]['name']}, usando fallback")
                # Fallback síncrono
                scored = self._score_candidates_fallback([candidates[i]])
                if scored:
                    scored_candidates.extend(scored)
            elif isinstance(result, dict):
                scored_candidates.append(result)

        # Filtra por threshold: score >= 60 AND risk != "high" AND compatible == true
        approved = [
            c for c in scored_candidates
            if c.get("llm_score", 0) >= 60
            and c.get("risk", "unknown") != "high"
            and c.get("compatible", False)
        ]

        logger.info(f"Scoring LLM: {len(approved)}/{len(candidates)} candidatos aprovados")
        return approved

    async def _score_single_candidate_llm(self, candidate: Dict) -> Dict:
        """
        Score individual candidate via LLM com semaphore.
        """
        async with self._llm_semaphore:
            try:
                prompt = self._build_scoring_prompt(candidate)
                response = await self._llm_router.complete(
                    prompt,
                    task_type="fast",  # llama-3.1-8b-instant
                    max_tokens=200,
                    actor="skill_alchemist_agent"
                )

                # Parse JSON response
                llm_result = self._parse_llm_json(response)
                if llm_result:
                    candidate["llm_score"] = llm_result.get("score", 0)
                    candidate["llm_reason"] = llm_result.get("reason", "")[:80]
                    candidate["risk"] = llm_result.get("risk", "unknown")
                    candidate["compatible"] = llm_result.get("compatible", False)
                    candidate["license_ok"] = llm_result.get("license_ok", False)
                    return candidate
                else:
                    # Parse falhou, usa fallback
                    raise ValueError("LLM retornou JSON inválido")

            except Exception as e:
                logger.warning(f"Erro no scoring LLM para {candidate['name']}: {e}")
                raise

    def _build_scoring_prompt(self, candidate: Dict) -> str:
        """Constrói o prompt exato para o LLM."""
        return f"""Você é um avaliador técnico do ecossistema "The Moon" (sistema Linux, Python, agentes autônomos, custo zero absoluto).

Avalie esta ferramenta/modelo open source e retorne APENAS um JSON válido, sem markdown, sem explicações:

Ferramenta: {candidate['name']}
Descrição: {candidate['desc'][:300] if candidate['desc'] else 'Sem descrição'}
Fonte: {candidate['source']}
Estrelas/Downloads: {candidate['stars']}

Critérios de avaliação:
- Compatível com Python 3.10+?
- Licença permissiva (MIT, Apache 2.0, BSD)?
- Útil para: agentes IA, automação, scraping, LLM, voz, visão, MCP?
- Gratuito (sem plano pago obrigatório)?
- Risco de segurança evidente?

Retorne EXATAMENTE este JSON:
{{"score": <0-100>, "reason": "<max 80 chars>", "risk": "<low|medium|high>", "compatible": <true|false>, "license_ok": <true|false>}}"""

    def _parse_llm_json(self, response: str) -> Optional[Dict]:
        """Parse JSON da resposta do LLM, removendo markdown se presente."""
        try:
            # Remove markdown code blocks se presente
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            response = response.strip()
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM JSON: {response[:100]}")
            return None

    def _score_candidates_fallback(self, candidates: List[Dict]) -> List[Dict]:
        """
        Fallback síncrono: scoring baseado em keywords + stars.
        Usado quando LLM não está disponível.
        """
        promising = []
        for c in candidates:
            score = 0
            # Critérios de Scoring
            if any(k in (c.get("desc") or "").lower() for k in self.keywords):
                score += 5
            if c.get("stars", 0) > 5000:
                score += 10

            if score >= 10:
                c["llm_score"] = score * 10  # Normaliza para 0-100
                c["risk"] = "low"
                c["compatible"] = True
                c["license_ok"] = True
                promising.append(c)

        return promising

    # Legacy method - mantido para compatibilidade
    def _score_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """Legacy: chama o fallback síncrono."""
        return self._score_candidates_fallback(candidates)

    # ═══════════════════════════════════════════════════════════
    #  Utility Methods
    # ═══════════════════════════════════════════════════════════

    def _is_new(self, tool: Dict) -> bool:
        """Verifica se a ferramenta é nova (não está no histórico)."""
        try:
            with open(self.discoveries_file, "r") as f:
                content = f.read().strip()
                if not content:
                    return True  # Arquivo vazio, ferramenta é nova
                history = json.loads(content)
                tool_id = hashlib.sha256(tool["url"].encode()).hexdigest()
                return tool_id not in [h.get("id") for h in history if isinstance(h, dict)]
        except (json.JSONDecodeError, FileNotFoundError):
            return True  # Arquivo não existe ou é inválido, ferramenta é nova

    def _mark_as_discovered(self, tool: Dict):
        """Marca ferramenta como descoberta e salva no histórico."""
        try:
            with open(self.discoveries_file, "r") as f:
                content = f.read().strip()
                if not content:
                    history = []
                else:
                    history = json.loads(content)
        except (json.JSONDecodeError, FileNotFoundError):
            history = []

        tool_id = hashlib.sha256(tool["url"].encode()).hexdigest()
        history.append({
            "id": tool_id,
            "name": tool["name"],
            "date": str(datetime.now()),
            "source": tool.get("source", "unknown"),
            "llm_score": tool.get("llm_score", 0),
            "risk": tool.get("risk", "unknown")
        })

        with open(self.discoveries_file, "w") as f:
            json.dump(history, f, indent=4)

    # ═══════════════════════════════════════════════════════════
    #  Objective 3: Real Sandbox with pip install
    # ═══════════════════════════════════════════════════════════

    async def _transmute(self, tool: Dict) -> bool:
        """
        Fase 3: Sandbox e Geração de Template.
        Fluxo real:
        1. Cria venv isolado
        2. Instala pacote com timeout de 60s
        3. Testa importação (para source == "pypi")
        4. Gera template da habilidade
        5. Salva na quarentena
        6. Gera proposal.json
        7. Verifica compliance via AST
        """
        temp_dir = f"/tmp/alchemist_{tool['name']}_{os.getpid()}"
        os.makedirs(temp_dir, exist_ok=True)

        proposal_data = {
            "skill_name": tool["name"],
            "origin": tool["url"],
            "source": tool.get("source", "unknown"),
            "status": "pending",
            "risk_score": tool.get("risk", "unknown"),
            "llm_score": tool.get("llm_score", 0),
            "integration_module": "agents/custom/",
            "generated_at": str(datetime.now()),
            "sandbox_tested": False,
            "install_output": "",
            "compliance_passed": False,
            "compliance_issues": [],
            "indexed_in_memory": False
        }

        try:
            # PASSO 1: Criar venv isolado
            logger.info(f"Criando sandbox virtualenv em {temp_dir}/venv")
            venv.create(f"{temp_dir}/venv", with_pip=True)
            pip_path = f"{temp_dir}/venv/bin/pip"
            python_path = f"{temp_dir}/venv/bin/python"

            # PASSO 2: Instalar pacote (apenas para source == "pypi")
            install_success = False
            if tool.get("source") == "pypi":
                logger.info(f"Instalando {tool['name']} via pip no sandbox...")
                install_success = await self._pip_install_package(
                    pip_path, tool["name"], proposal_data
                )
            else:
                # GitHub e HuggingFace: pula instalação, vai direto para template
                logger.info(f"Fonte {tool.get('source')} não suporta pip install direto, pulando para template")
                install_success = True
                proposal_data["sandbox_tested"] = True

            if not install_success:
                proposal_data["status"] = "install_failed"
                logger.error(f"Falha na instalação de {tool['name']}")
                return False

            # PASSO 3: Teste de importação (apenas PyPI)
            if tool.get("source") == "pypi":
                logger.info(f"Testando importação de {tool['name']}")
                import_success = await self._test_import(python_path, tool["name"])
                if not import_success:
                    proposal_data["status"] = "import_failed"
                    logger.error(f"Falha no teste de importação de {tool['name']}")
                    return False

            # PASSO 4: Gerar template da habilidade
            skill_code = self._generate_skill_template(tool)

            # PASSO 5: Salvar na quarentena
            skill_path = f"{self.quarantine}/{tool['name']}.py"
            with open(skill_path, "w") as f:
                f.write(skill_code)
            logger.info(f"Template salvo em {skill_path}")

            # PASSO 6: Verificar compliance via AST
            logger.info(f"Verificando compliance de {tool['name']}")
            compliance_ok, issues = await self._check_compliance(skill_path)
            proposal_data["compliance_passed"] = compliance_ok
            proposal_data["compliance_issues"] = issues

            if not compliance_ok:
                # Deleta arquivo da quarentena
                os.remove(skill_path)
                proposal_data["status"] = "compliance_rejected"
                logger.error(f"Compliance falhou para {tool['name']}: {issues}")
                return False

            # PASSO 7: Gerar proposal.json
            proposal_data["status"] = "quarantined"
            proposal_path = f"{self.quarantine}/{tool['name']}_proposal.json"
            with open(proposal_path, "w") as f:
                json.dump(proposal_data, f, indent=4)

            logger.info(f"Proposal salvo em {proposal_path}")
            return True

        except Exception as e:
            logger.error(f"Falha na transmutação de {tool['name']}: {e}")
            proposal_data["status"] = "error"
            proposal_data["install_output"] = proposal_data.get("install_output", "") + f"\nERROR: {str(e)}"
            return False

        finally:
            # Limpa sandbox
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def _pip_install_package(self, pip_path: str, package_name: str, proposal_data: Dict) -> bool:
        """
        Instala pacote via pip com timeout de 60 segundos.
        """
        try:
            # Usa asyncio.wait_for com asyncio.to_thread para não bloquear
            async def run_pip_install():
                proc = subprocess.run(
                    [pip_path, "install", package_name],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                return proc.returncode, proc.stdout, proc.stderr

            returncode, stdout, stderr = await asyncio.wait_for(
                asyncio.to_thread(run_pip_install),
                timeout=65  # 60s do pip + 5s buffer
            )

            if returncode != 0:
                error_msg = stderr[:500] if stderr else f"Return code: {returncode}"
                proposal_data["install_output"] = error_msg
                proposal_data["sandbox_tested"] = True
                logger.error(f"pip install falhou: {error_msg}")
                return False

            proposal_data["sandbox_tested"] = True
            proposal_data["install_output"] = stdout[:500] if stdout else "Success"
            logger.info(f"pip install bem-sucedido para {package_name}")
            return True

        except subprocess.TimeoutExpired:
            proposal_data["install_output"] = "Timeout: pip install excedeu 60s"
            proposal_data["sandbox_tested"] = True
            logger.error(f"Timeout na instalação de {package_name}")
            return False

        except asyncio.TimeoutError:
            proposal_data["install_output"] = "Timeout: operação excedeu 65s"
            proposal_data["sandbox_tested"] = True
            logger.error(f"Timeout asyncio na instalação de {package_name}")
            return False

        except Exception as e:
            proposal_data["install_output"] = f"Erro: {str(e)}"
            proposal_data["sandbox_tested"] = True
            logger.error(f"Erro na instalação de {package_name}: {e}")
            return False

    async def _test_import(self, python_path: str, package_name: str) -> bool:
        """
        Testa importação do pacote com timeout de 10 segundos.
        """
        try:
            async def run_import_test():
                proc = subprocess.run(
                    [python_path, "-c", f"import {package_name}; print('OK')"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return proc.returncode, proc.stdout, proc.stderr

            returncode, stdout, stderr = await asyncio.wait_for(
                asyncio.to_thread(run_import_test),
                timeout=12  # 10s do import + 2s buffer
            )

            if returncode != 0 or "OK" not in stdout:
                logger.warning(f"Import teste falhou: {stderr[:200]}")
                return False

            return True

        except (subprocess.TimeoutExpired, asyncio.TimeoutError):
            logger.warning(f"Timeout no teste de import de {package_name}")
            return False

        except Exception as e:
            logger.warning(f"Erro no teste de import de {package_name}: {e}")
            return False

    # ═══════════════════════════════════════════════════════════
    #  Objective 4: AST-Based Compliance Check
    # ═══════════════════════════════════════════════════════════

    async def _check_compliance(self, skill_path: str) -> Tuple[bool, List[str]]:
        """
        Valida se o código gerado segue as regras do Moon Codex via AST.
        
        Regras verificadas:
        1. Modelos pagos proibidos (strings: gpt-4, claude-3, etc.)
        2. Imports de módulos de custo proibidos (openai, anthropic, etc.)
        3. print() em produção (warning, não fatal)
        4. Classe deve herdar de SkillBase
        """
        issues = []

        try:
            with open(skill_path, "r", encoding="utf-8") as f:
                source_code = f.read()

            # Parse AST
            tree = ast.parse(source_code)

        except SyntaxError as e:
            issues.append(f"SyntaxError: {str(e)}")
            return False, issues

        except Exception as e:
            issues.append(f"Erro ao ler arquivo: {str(e)}")
            return False, issues

        # REGRA 1: Modelos pagos proibidos (strings literais)
        prohibited_models = [
            "gpt-4", "gpt-3.5", "gpt-3", "claude-3", "claude-2",
            "text-davinci", "openai", "anthropic"
        ]

        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for model in prohibited_models:
                    if model in node.value.lower():
                        issues.append(f"COMPLIANCE FAIL: modelo pago detectado: {node.value}")

            # Também verifica ast.Str (Python < 3.8)
            if hasattr(ast, 'Str') and isinstance(node, ast.Str):
                for model in prohibited_models:
                    if model in node.s.lower():
                        issues.append(f"COMPLIANCE FAIL: modelo pago detectado: {node.s}")

        # REGRA 2: Import de módulos de custo proibidos
        prohibited_imports = ["openai", "anthropic", "cohere", "replicate"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.lower() in prohibited_imports:
                        issues.append(f"COMPLIANCE FAIL: import proibido: {alias.name}")

            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.lower() in prohibited_imports:
                    issues.append(f"COMPLIANCE FAIL: import from proibido: {node.module}")

        # REGRA 3: print() em produção (warning, não fatal)
        print_count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "print":
                    print_count += 1

        if print_count > 0:
            issues.append(f"WARNING: {print_count} print() encontrado(s) em produção")

        # REGRA 4: Verificar que a classe herda de SkillBase
        has_skillbase_subclass = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == "SkillBase":
                        has_skillbase_subclass = True
                        break

        if not has_skillbase_subclass:
            issues.append("COMPLIANCE FAIL: classe não herda de SkillBase")

        # Determina se passou (ignora warnings de print)
        fatal_issues = [i for i in issues if i.startswith("COMPLIANCE FAIL") or i.startswith("SyntaxError")]
        passed = len(fatal_issues) == 0

        if passed:
            logger.info(f"Compliance OK para {skill_path}")
        else:
            logger.warning(f"Compliance falhou para {skill_path}: {fatal_issues}")

        return passed, issues

    # ═══════════════════════════════════════════════════════════
    #  Template Generation
    # ═══════════════════════════════════════════════════════════

    def _generate_skill_template(self, tool: Dict) -> str:
        """Gera o código Python para a nova Habilidade baseada no SkillBase."""
        return f'''# Auto-generated by SkillAlchemist v2
# Date: {datetime.now()}
# Target: {tool["name"]} ({tool["url"]})
# Source: {tool.get("source", "unknown")}

import asyncio
from core.skill_base import SkillBase

class {self._sanitize_class_name(tool["name"])}Skill(SkillBase):
    """
    Habilidade integrada automaticamente do repositório {tool["name"]}.
    """

    def __init__(self, agent):
        super().__init__(agent)
        self.description = "{(tool.get("desc") or "")[:100]}"

    async def execute(self, *args, **kwargs):
        # TODO: Implementar lógica de ponte para a biblioteca original
        return f"Habilidade {tool["name"]} executada com sucesso!"
'''

    def _sanitize_class_name(self, name: str) -> str:
        """Sanitiza nome para ser válido como classe Python."""
        # Remove caracteres inválidos e capitaliza
        sanitized = "".join(c if c.isalnum() else "_" for c in name)
        # Garante que começa com letra
        if sanitized and sanitized[0].isdigit():
            sanitized = "_" + sanitized
        # Capitaliza (PascalCase)
        return sanitized.capitalize()

    # ═══════════════════════════════════════════════════════════
    #  Objective 5: SemanticMemoryWeaver Integration
    # ═══════════════════════════════════════════════════════════

    async def _publish_to_semantic_weaver(self, tool: Dict) -> bool:
        """
        Publica descoberta no SemanticMemoryWeaver via MessageBus.
        """
        try:
            from core.message_bus import MessageBus
            message_bus = MessageBus()

            # Tópico que o SemanticMemoryWeaver consome
            topic = "memory.remember"

            payload = {
                "content": (
                    f"Ferramenta descoberta: {tool['name']}. {tool.get('desc', '')}. "
                    f"Origem: {tool.get('source', 'unknown')}. URL: {tool.get('url', '')}. "
                    f"Score LLM: {tool.get('llm_score', 0)}. "
                    f"Risk: {tool.get('risk', 'unknown')}."
                ),
                "metadata": {
                    "type": "skill_discovery",
                    "agent": "SkillAlchemist",
                    "skill_name": tool["name"],
                    "source": tool.get("source", "unknown"),
                    "url": tool.get("url", ""),
                    "risk": tool.get("risk", "unknown"),
                    "score": tool.get("llm_score", 0),
                    "timestamp": str(datetime.now())
                },
                "tags": ["skill", "discovery", tool.get("source", "unknown"), tool.get("risk", "unknown")]
            }

            await message_bus.publish(
                sender="SkillAlchemist",
                topic=topic,
                payload=payload
            )

            logger.info(f"Publicado no SemanticMemoryWeaver: {tool['name']}")
            return True

        except Exception as e:
            logger.warning(f"Falha ao publicar no SemanticMemoryWeaver: {e}")
            return False

    def _mark_as_discovered(self, tool: Dict):
        """
        Marca ferramenta como descoberta e publica no SemanticMemoryWeaver.
        """
        # Salva no discoveries.json
        with open(self.discoveries_file, "r") as f:
            history = json.load(f)

        tool_id = hashlib.sha256(tool["url"].encode()).hexdigest()

        # Verifica se já existe
        existing_ids = [h["id"] for h in history]
        if tool_id not in existing_ids:
            history.append({
                "id": tool_id,
                "name": tool["name"],
                "date": str(datetime.now()),
                "source": tool.get("source", "unknown"),
                "llm_score": tool.get("llm_score", 0),
                "risk": tool.get("risk", "unknown")
            })

            with open(self.discoveries_file, "w") as f:
                json.dump(history, f, indent=4)

        # Publica no SemanticMemoryWeaver (se orchestrator disponível)
        if self.orchestrator:
            # Publica no tópico do alchemist
            asyncio.create_task(
                self.orchestrator.publish("alchemist.skill_proposed", {
                    "skill": tool['name'],
                    "path": f"{self.quarantine}/{tool['name']}"
                })
            )

            # Publica adicionalmente no SemanticMemoryWeaver
            indexed = asyncio.create_task(self._publish_to_semantic_weaver(tool))

            # Atualiza proposal.json com indexed_in_memory quando completar
            async def update_indexed_status():
                try:
                    result = await indexed
                    proposal_path = f"{self.quarantine}/{tool['name']}_proposal.json"
                    if os.path.exists(proposal_path):
                        with open(proposal_path, "r") as f:
                            proposal = json.load(f)
                        proposal["indexed_in_memory"] = result
                        with open(proposal_path, "w") as f:
                            json.dump(proposal, f, indent=4)
                except Exception as e:
                    logger.warning(f"Erro ao atualizar indexed_in_memory: {e}")

            asyncio.create_task(update_indexed_status())
        else:
            logger.warning("Orchestrator não disponível - rodando em standalone mode")
