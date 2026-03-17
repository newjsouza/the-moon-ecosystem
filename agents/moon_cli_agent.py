"""
agents/moon_cli_agent.py

MoonCLIAgent — Agente executor e gerador de CLI-Anything harnesses.

Implementa:
  Opção B: Executa harnesses prontos instalados (libreoffice, mermaid)
  Opção A: Gera novos harnesses via HARNESS.md + LLMRouter

Tópicos da MessageBus:
  Subscreve: "cli.execute", "cli.generate", "cli.discover"
  Publica:   "cli.result", "cli.harness_ready", "cli.discovery", "nexus.event"
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Imports do projeto (padrões reais confirmados na Fase 0 e grep)
from core.agent_base import AgentBase, TaskResult
from core.cli_harness_adapter import CLIHarnessAdapter, get_harness_adapter

logger = logging.getLogger("moon.agents.moon_cli_agent")

# Path ao HARNESS.md clonado
_HARNESS_MD_PATH = Path("/tmp/cli-anything-src/cli-anything-plugin/HARNESS.md")
_HARNESS_MD_FALLBACK = Path("skills/cli_harnesses/HARNESS.md")


class MoonCLIAgent(AgentBase):
    """
    Agente The Moon para execução e geração de CLI-Anything harnesses.

    Comandos aceitos via _execute(task):
      "list"                              → Lista harnesses disponíveis
      "discover"                          → Auto-descobre SKILL.md em site-packages
      "run <harness> [args...]"           → Executa harness com args
      "run_json <harness> [args...]"      → Executa harness com --json automático
      "generate <target_path_ou_url>"    → Gera novo harness via HARNESS.md + LLM (Opção A)
      "help <harness>"                    → Mostra --help do harness

    Notas de uso por harness:
      - libreoffice: "run libreoffice document new --type writer -o /tmp/doc.json"
      - mermaid: Requer fluxo em 3 passos:
          1. "run mermaid project new -o /tmp/proj.json"
          2. "run mermaid --project /tmp/proj.json diagram set --text 'graph TD; A --> B'"
          3. "run mermaid --project /tmp/proj.json export render /tmp/out.png -f png"
        Ou usar o método helper _mermaid_render() se implementado.
    """

    # Keywords para roteamento no ArchitectAgent DOMAIN_AGENT_MAP
    ROUTING_KEYWORDS = [
        "cli", "harness", "libreoffice", "mermaid", "diagrama",
        "documento pdf", "render pdf", "render diagrama",
        "exportar documento", "gerar cli", "instalar harness",
        "automatizar software", "cli-anything",
    ]

    def __init__(self, *args, **kwargs):
        # Padrão real: super().__init__() sem parâmetros (verificado em skill_alchemist.py)
        super().__init__()
        self._adapter: CLIHarnessAdapter = get_harness_adapter()
        self._harness_md_cache: Optional[str] = None
        logger.info(
            f"MoonCLIAgent inicializado. "
            f"Harnesses disponíveis: {[h['name'] for h in self._adapter.list_available()]}"
        )

    # ── Interface principal ───────────────────────────────────────────────────

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Ponto de entrada único do agente. Roteia para handlers específicos.
        Nunca lança exceção — erros são encapsulados em TaskResult(success=False).
        """
        if not task or not task.strip():
            return TaskResult(
                success=False,
                error="Task vazia. Use: list | discover | run <harness> [args] | run_json <harness> [args] | generate <target> | help <harness>"
            )

        parts = task.strip().split(maxsplit=1)
        action = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        handlers = {
            "list":     self._handle_list,
            "discover": self._handle_discover,
            "run":      self._handle_run,
            "run_json": self._handle_run_json,
            "generate": self._handle_generate,
            "help":     self._handle_help,
        }

        handler = handlers.get(action)
        if not handler:
            return TaskResult(
                success=False,
                error=(
                    f"Ação desconhecida: '{action}'. "
                    f"Ações válidas: {list(handlers.keys())}"
                )
            )

        try:
            return await handler(rest)
        except Exception as exc:
            logger.error(f"MoonCLIAgent._execute: erro inesperado [{action}]: {exc}", exc_info=True)
            return TaskResult(success=False, error=str(exc))

    # ── Handlers ─────────────────────────────────────────────────────────────

    async def _handle_list(self, _: str) -> TaskResult:
        """Lista harnesses disponíveis com metadados reais."""
        available = self._adapter.list_available()
        data = {
            "harnesses": available,
            "count": len(available),
            "timestamp": datetime.now().isoformat(),
        }
        await self._publish("cli.result", {
            "action": "list",
            "result": data
        })
        return TaskResult(success=True, data=data)

    async def _handle_help(self, args_str: str) -> TaskResult:
        """Executa --help no harness especificado."""
        harness_name = args_str.strip().split()[0] if args_str.strip() else ""
        if not harness_name:
            return TaskResult(
                success=False,
                error="Informe o nome do harness. Ex: 'help libreoffice'"
            )
        result = await self._adapter.run(harness_name, ["--help"])
        return TaskResult(
            success=result.success,
            data=result.to_dict(),
            error=result.raw_stderr if not result.success else None
        )

    async def _handle_run(self, args_str: str) -> TaskResult:
        """
        Executa harness com argumentos fornecidos.
        Formato: "libreoffice document new --type writer -o /tmp/doc.json"
        """
        parts = args_str.strip().split()
        if not parts:
            return TaskResult(
                success=False,
                error="Informe harness e argumentos. Ex: 'run libreoffice document new --type writer -o /tmp/doc.json'"
            )
        harness_name = parts[0]
        harness_args = parts[1:]

        result = await self._adapter.run(harness_name, harness_args)
        await self._publish("cli.result", {
            "action": "run",
            "harness": harness_name,
            "result": result.to_dict()
        })
        # Publicar no nexus para indexação histórica
        await self._publish("nexus.event", {
            "type": "cli_harness_execution",
            "harness": harness_name,
            "success": result.success,
            "duration_ms": result.duration_ms,
            "timestamp": result.timestamp
        })
        return TaskResult(
            success=result.success,
            data=result.to_dict(),
            error=result.raw_stderr[:500] if not result.success else None
        )

    async def _handle_run_json(self, args_str: str) -> TaskResult:
        """
        Executa harness com --json flag automático.
        Formato: "run_json libreoffice document new --type writer -o /tmp/doc.json"
        """
        parts = args_str.strip().split()
        if not parts:
            return TaskResult(
                success=False,
                error="Informe harness e argumentos. Ex: 'run_json libreoffice document new -o /tmp/doc.json'"
            )
        harness_name = parts[0]
        harness_args = parts[1:]

        result = await self._adapter.run_json(harness_name, harness_args)
        await self._publish("cli.result", {
            "action": "run_json",
            "harness": harness_name,
            "result": result.to_dict()
        })
        return TaskResult(
            success=result.success,
            data=result.to_dict(),
            error=result.raw_stderr[:500] if not result.success else None
        )

    async def _handle_discover(self, _: str = "") -> TaskResult:
        """
        Auto-descobre harnesses instalados via SKILL.md em site-packages.
        Busca pelo padrão: cli_anything/*/skills/SKILL.md
        """
        import site
        discovered = []
        site_dirs = site.getsitepackages()
        # Adicionar user site-packages
        user_site = site.getusersitepackages()
        if user_site:
            site_dirs = list(site_dirs) + [user_site]

        for site_dir in site_dirs:
            site_path = Path(site_dir)
            if not site_path.exists():
                continue
            skill_files = list(site_path.glob("cli_anything/*/skills/SKILL.md"))
            for skill_file in skill_files:
                # Extrair nome do harness do path
                parts = skill_file.parts
                cli_anything_idx = next(
                    (i for i, p in enumerate(parts) if p == "cli_anything"), None
                )
                if cli_anything_idx is None:
                    continue
                harness_name = parts[cli_anything_idx + 1]
                binary = f"cli-anything-{harness_name}"
                is_installed = shutil.which(binary) is not None

                try:
                    skill_content = skill_file.read_text(encoding="utf-8")[:500]
                except OSError:
                    skill_content = "(não legível)"

                discovered.append({
                    "name": harness_name,
                    "binary": binary,
                    "binary_accessible": is_installed,
                    "skill_file": str(skill_file),
                    "skill_preview": skill_content,
                })
                logger.info(
                    f"SKILL.md descoberto: {harness_name} "
                    f"({'binário ok' if is_installed else 'binário ausente'})"
                )

        await self._publish("cli.discovery", {
            "discovered": discovered,
            "count": len(discovered),
            "timestamp": datetime.now().isoformat()
        })
        return TaskResult(
            success=True,
            data={"discovered": discovered, "count": len(discovered)}
        )

    async def _handle_generate(self, target: str) -> TaskResult:
        """
        OPÇÃO A: Gera novo harness CLI via HARNESS.md + LLMRouter.
        target: path local de software OU URL de repositório GitHub.

        Usa llm.complete() com HARNESS.md como prompt base.
        Requer HARNESS.md em /tmp/cli-anything-src/cli-anything-plugin/ ou
        skills/cli_harnesses/HARNESS.md como fallback.
        """
        if not target.strip():
            return TaskResult(
                success=False,
                error="Target obrigatório. Ex: 'generate /path/to/software' ou 'generate https://github.com/user/repo'"
            )

        harness_md = self._load_harness_md()
        if not harness_md:
            return TaskResult(
                success=False,
                error=(
                    "HARNESS.md não encontrado. "
                    f"Esperado em: {_HARNESS_MD_PATH} ou {_HARNESS_MD_FALLBACK}. "
                    "Execute: cp /tmp/cli-anything-src/cli-anything-plugin/HARNESS.md skills/cli_harnesses/"
                )
            )

        target_info = self._describe_target(target)

        prompt = f"""Você é um especialista em CLI-Anything. Siga EXATAMENTE a metodologia abaixo para gerar uma CLI agent-native para o software indicado.

===== HARNESS.md (metodologia obrigatória) =====
{harness_md[:6000]}
===== FIM DO HARNESS.md =====

SOFTWARE ALVO: {target}

INFORMAÇÕES DO ALVO:
{target_info}

INSTRUÇÕES:
1. Analise o software alvo seguindo a Fase 1 (Analyze) do HARNESS.md
2. Proponha a arquitetura de comandos Click (Fase 2 - Design)
3. Implemente o CLI Python completo (Fase 3 - Implement)
4. Gere setup.py completo com entry_points para o binário

RESTRIÇÕES ABSOLUTAS:
- Sem placeholders, sem TODOs, sem strings fictícias
- Código deve ser executável imediatamente com pip install -e .
- Usar namespace cli_anything.<software_name>
- Binary name: cli-anything-<software_name>
- Output JSON via flag --json em todos os comandos
- REPL via repl_skin.py pattern

Gere o código completo agora:"""

        # Usar método REAL de LLMRouter (confirmado no grep: agents/skill_alchemist.py:85-87,305)
        try:
            from agents.llm import LLMRouter
            from core.config import Config
            llm = LLMRouter(Config())
            generated_code = await llm.complete(
                prompt=prompt,
                task_type="coding"
            )
        except Exception as exc:
            return TaskResult(
                success=False,
                error=f"Erro ao chamar LLMRouter: {exc}"
            )

        # Salvar código gerado
        # CORREÇÃO P8: Usar nome semântico cli-anything-{tool}.py em vez de hash
        # Extrair nome da ferramenta do target (ex: "harness for ffmpeg" → "ffmpeg")
        target_clean = target.lower().strip()
        if "harness for " in target_clean:
            target_clean = target_clean.replace("harness for ", "")
        tool_slug = Path(target_clean.rstrip("/")).name.lower().strip().replace(" ", "-").replace("_", "-")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("skills/cli_harnesses/generated")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"cli-anything-{tool_slug}.py"
        output_path.write_text(generated_code, encoding="utf-8")

        # Publicar evento
        await self._publish("cli.harness_ready", {
            "action": "generate",
            "target": target,
            "output_path": str(output_path),
            "generated_lines": len(generated_code.splitlines()),
            "timestamp": datetime.now().isoformat()
        })

        return TaskResult(
            success=True,
            data={
                "target": target,
                "output_path": str(output_path.resolve()),
                "generated_lines": len(generated_code.splitlines()),
                "next_steps": [
                    f"Revisar: {output_path}",
                    "Criar estrutura de package: mkdir -p <software>/agent-harness/cli_anything/<software>/",
                    "Mover código e criar setup.py",
                    "Instalar: pip install -e <software>/agent-harness/",
                    "Executar testes: pytest cli_anything/<software>/tests/"
                ]
            }
        )

    # ── Métodos auxiliares ────────────────────────────────────────────────────

    def _load_harness_md(self) -> Optional[str]:
        """Carrega HARNESS.md do path primário ou fallback."""
        if self._harness_md_cache:
            return self._harness_md_cache
        for path in [_HARNESS_MD_PATH, _HARNESS_MD_FALLBACK]:
            if path.exists():
                try:
                    self._harness_md_cache = path.read_text(encoding="utf-8")
                    logger.info(f"HARNESS.md carregado de: {path}")
                    return self._harness_md_cache
                except OSError as exc:
                    logger.warning(f"Não foi possível ler {path}: {exc}")
        return None

    def _describe_target(self, target: str) -> str:
        """Gera descrição do alvo para contextualizar o LLM."""
        if target.startswith(("http://", "https://", "git@")):
            return f"Repositório remoto: {target}"
        target_path = Path(target)
        if target_path.exists() and target_path.is_dir():
            py_files = list(target_path.rglob("*.py"))[:20]
            return (
                f"Diretório local com {len(py_files)} arquivos Python. "
                f"Exemplos: {[f.name for f in py_files[:5]]}"
            )
        return f"Target: {target} (não acessível como diretório local)"

    async def _publish(self, topic: str, payload: Any) -> None:
        """
        Publica na MessageBus usando padrão real do projeto.
        Padrão encontrado em agents/skill_alchemist.py:765-800
        Silencioso em caso de erro — não interrompe o fluxo principal.
        """
        try:
            from core.message_bus import MessageBus
            message_bus = MessageBus()
            await message_bus.publish(
                sender=self.name,  # AgentBase define self.name
                topic=topic,
                payload=payload
            )
        except Exception as exc:
            logger.debug(f"MoonCLIAgent._publish: falha ao publicar '{topic}': {exc}")
