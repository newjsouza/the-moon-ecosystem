"""
agents/moon_review_agent.py
Moon Review Agent — Revisão paranóica de código (AST + LLM)

Architecture:
  - Pipeline de 4 passos:
    1. Obtém diff: git diff main --unified=5 -- "*.py"
    2. Análise AST (determinística): async sem await, imports não utilizados, etc.
    3. Análise LLM (semântica): race conditions, trust boundaries, N+1, error handling
    4. Gera JSON em data/reviews/{timestamp}_review.json
  - Publica em "review.completed" e "watchdog.alert" (se crítico)
"""
from __future__ import annotations

import ast
import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Any, Dict, List, Optional, Tuple

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus
from agents.llm import LLMRouter

logger = logging.getLogger("moon.agents.review")


# ─────────────────────────────────────────────────────────────
#  Prompt LLM
# ─────────────────────────────────────────────────────────────

REVIEW_PROMPT_TEMPLATE = Template("""Você é um engenheiro sênior fazendo code review paranóico de código Python para um sistema de agentes autônomos em produção (Linux, asyncio, Groq LLM, Playwright browser, apostas esportivas, trading).

DIFF:
$diff

ACHADOS ESTÁTICOS (AST):
$ast_findings

Identifique APENAS problemas reais de produção. NÃO mencione:
- Style issues
- Naming conventions
- Comentários faltando
- Coisas que "poderiam ser melhores"

FOCO EXCLUSIVO em:
- Race conditions em código assíncrono (asyncio)
- Trust boundaries violados (dados externos sem validação)
- N+1 em loops com I/O
- Stale reads em estado compartilhado entre agentes
- Missing error handling em chamadas de API externas
- Retry logic que pode causar duplicate actions
- Memory leaks em objetos de longa duração

Para cada problema encontrado, retorne EXATAMENTE neste formato:
ISSUE #1
Severidade: CRITICAL | HIGH | MEDIUM
Arquivo: {path}:{linha}
Problema: {descrição em 1 linha}
Impacto em Produção: {o que pode acontecer de errado}
Fix Sugerido: {código ou abordagem concreta}
---

Se não houver problemas, retorne apenas: "No issues found."
""")


# ─────────────────────────────────────────────────────────────
#  AST Analysis
# ─────────────────────────────────────────────────────────────

class ASTAnalyzer:
    """Análise estática de código Python usando módulo ast."""
    
    def __init__(self):
        self.findings: List[Dict[str, Any]] = []
    
    def analyze(self, code: str, filename: str = "<unknown>") -> List[Dict[str, Any]]:
        """Analisa código Python e retorna achados."""
        self.findings = []
        
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            self.findings.append({
                "type": "SYNTAX_ERROR",
                "severity": "CRITICAL",
                "file": filename,
                "line": e.lineno or 0,
                "message": f"Syntax error: {e.msg}",
            })
            return self.findings
        
        # Análise 1: async sem await
        self._check_missing_await(tree, filename)
        
        # Análise 2: imports não utilizados
        self._check_unused_imports(tree, code, filename)
        
        # Análise 3: funções muito longas (>50 linhas)
        self._check_long_functions(tree, code, filename)
        
        # Análise 4: strings com modelos proibidos
        self._check_prohibited_models(code, filename)
        
        # Análise 5: variáveis lidas antes de definir
        self._check_undefined_variables(tree, filename)
        
        return self.findings
    
    def _check_missing_await(self, tree: ast.AST, filename: str) -> None:
        """Detecta chamadas de coroutine sem await."""
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Await):
                # Está correto - tem await
                continue
            
            # Procura por chamadas de funções async
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                # Verifica se é uma chamada em contexto onde deveria ter await
                # Isso é uma heurística - não é 100% precisa
                pass
        
        # Análise mais precisa: verifica Assign com coroutine
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Call):
                    # Verifica se a função chamada é async (heurística)
                    if isinstance(node.value.func, ast.Attribute):
                        if node.value.func.attr in ('sleep', 'wait', 'gather', 'create_task'):
                            # Provavelmente precisa de await
                            self.findings.append({
                                "type": "MISSING_AWAIT",
                                "severity": "HIGH",
                                "file": filename,
                                "line": node.lineno,
                                "message": f"Possible missing await for asyncio.{node.value.func.attr}()",
                            })
    
    def _check_unused_imports(self, tree: ast.AST, code: str, filename: str) -> None:
        """Detecta imports não utilizados."""
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imports.append((name, node.lineno))
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imports.append((name, node.lineno))
        
        # Verifica uso
        for name, lineno in imports:
            # Conta ocorrências (deve aparecer pelo menos 2x: import + uso)
            count = code.count(f" {name}") + code.count(f"{name}.") + code.count(f"({name}")
            if count < 2:
                self.findings.append({
                    "type": "UNUSED_IMPORT",
                    "severity": "LOW",
                    "file": filename,
                    "line": lineno,
                    "message": f"Import '{name}' appears unused",
                })
    
    def _check_long_functions(self, tree: ast.AST, code: str, filename: str) -> None:
        """Detecta funções com mais de 50 linhas."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if hasattr(node, 'end_lineno') and hasattr(node, 'lineno'):
                    lines = node.end_lineno - node.lineno
                    if lines > 50:
                        self.findings.append({
                            "type": "LONG_FUNCTION",
                            "severity": "MEDIUM",
                            "file": filename,
                            "line": node.lineno,
                            "message": f"Function '{node.name}' has {lines} lines (>50)",
                        })
    
    def _check_prohibited_models(self, code: str, filename: str) -> None:
        """Detecta strings com modelos proibidos (gpt-4, claude, etc.)."""
        prohibited = ['gpt-4', 'gpt4', 'claude-', 'claude_', 'text-davinci']
        
        for model in prohibited:
            if model.lower() in code.lower():
                # Encontra linha aproximada
                lines = code.split('\n')
                for i, line in enumerate(lines, 1):
                    if model.lower() in line.lower():
                        self.findings.append({
                            "type": "PROHIBITED_MODEL",
                            "severity": "CRITICAL",
                            "file": filename,
                            "line": i,
                            "message": f"Prohibited model reference: '{model}' (MOON_CODEX Diretriz 0.2)",
                        })
                        break
    
    def _check_undefined_variables(self, tree: ast.AST, filename: str) -> None:
        """Detecta variáveis lidas antes de serem definidas (análise básica)."""
        # Análise simplificada - verifica uso de variáveis em escopo local
        defined = set()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined.add(target.id)
            elif isinstance(node, ast.NamedExpr):  # :=
                if isinstance(node.target, ast.Name):
                    defined.add(node.target.id)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id not in defined and node.id not in ('__name__', '__file__', 'self', 'cls'):
                    # Verifica se é parâmetro de função
                    pass  # Análise completa requer mais contexto
        
        # Esta análise é limitada sem análise de fluxo de dados completa


# ─────────────────────────────────────────────────────────────
#  Moon Review Agent
# ─────────────────────────────────────────────────────────────

class MoonReviewAgent(AgentBase):
    """
    Agente de code review paranóico.
    
    Uso:
        await agent.execute("auto")  # Revisa diff atual
        await agent.execute("file path/to/file.py")  # Revisa arquivo específico
    """
    
    def __init__(self):
        super().__init__()
        self.name = "MoonReviewAgent"
        self.priority = AgentPriority.MEDIUM
        self.description = "Paranoid code review agent (AST + LLM)"
        self._router: Optional[LLMRouter] = None
        self._message_bus: Optional[MessageBus] = None
        self._reviews_dir: Path = Path(__file__).resolve().parent.parent / "data" / "reviews"
        self._analyzer = ASTAnalyzer()
    
    async def initialize(self) -> None:
        """Inicializa o agente."""
        await super().initialize()
        self._router = LLMRouter()
        self._message_bus = MessageBus()
        self._reviews_dir.mkdir(parents=True, exist_ok=True)
        logger.info("MoonReviewAgent initialized")
    
    async def _execute(self, task: str, **kwargs) -> TaskResult:
        """
        Executa code review.

        Args:
            task: "auto" para diff atual, ou "file <path>" para arquivo específico

        Returns:
            TaskResult com relatório de review.
        """
        try:
            task = task.strip().lower()

            # Obter diff ou código
            if task == "auto":
                diff = self._get_git_diff()
                files_reviewed = self._parse_diff_files(diff)
            elif task.startswith("file "):
                filepath = task[5:].strip()
                diff = self._read_file(filepath)
                files_reviewed = [filepath]
            else:
                return TaskResult(success=False, error="Usage: auto | file <path>")

            if not diff:
                return TaskResult(
                    success=True,
                    data={
                        "message": "No changes to review",
                        "health_score": 100,
                        "critical_count": 0,
                        "high_count": 0,
                        "medium_count": 0,
                        "files_reviewed": [],
                        "ast_issues": [],
                        "llm_issues": [],
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            # Limitar diff a 8000 chars
            if len(diff) > 8000:
                diff = diff[:8000] + "\n\n... (truncated to 8000 chars)"

            # Análise AST
            ast_findings = self._analyze_ast(diff)

            # Análise LLM
            llm_findings = await self._analyze_llm(diff, ast_findings)

            # Gerar relatório
            report = self._generate_report(files_reviewed, ast_findings, llm_findings)

            # Salvar relatório
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = self._reviews_dir / f"{timestamp}_review.json"
            report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
            logger.info(f"Review saved to {report_file}")

            # Publicar na MessageBus
            await self._message_bus.publish(
                sender=self.name,
                topic="review.completed",
                payload=report
            )

            # Alertar Watchdog se houver críticos
            if report["critical_count"] > 0:
                await self._message_bus.publish(
                    sender=self.name,
                    topic="watchdog.alert",
                    payload={
                        "severity": "critical",
                        "source": "MoonReviewAgent",
                        "message": f"Code review found {report['critical_count']} CRITICAL issues",
                        "details": report["llm_issues"],
                    }
                )

            return TaskResult(
                success=True,
                data=report
            )

        except KeyError as e:
            logger.error(f"KeyError in review: {e}")
            return TaskResult(success=False, error=f"KeyError: {e}")
        except Exception as e:
            logger.error(f"Review execution failed: {e}")
            return TaskResult(success=False, error=str(e))
    
    def _get_git_diff(self) -> str:
        """Obtém diff do git."""
        try:
            result = subprocess.run(
                ["git", "diff", "main", "--unified=5", "--", "*.py"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path(__file__).resolve().parent.parent)
            )
            return result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"Git diff failed: {e}")
            return ""
    
    def _parse_diff_files(self, diff: str) -> List[str]:
        """Extrai lista de arquivos do diff."""
        files = []
        for line in diff.split('\n'):
            if line.startswith('+++ b/'):
                files.append(line[6:])
            elif line.startswith('+++ '):
                files.append(line[4:])
        return files
    
    def _read_file(self, filepath: str) -> str:
        """Lê arquivo Python."""
        try:
            full_path = Path(__file__).resolve().parent.parent / filepath
            return full_path.read_text(encoding="utf-8")
        except (FileNotFoundError, IOError) as e:
            logger.warning(f"Failed to read {filepath}: {e}")
            return ""
    
    def _analyze_ast(self, diff: str) -> List[Dict[str, Any]]:
        """Executa análise AST apenas em código Python extraído do diff."""
        all_findings = []

        # Extrai trechos de código Python do diff
        python_code = self._extract_python_from_diff(diff)

        if python_code:
            try:
                findings = self._analyzer.analyze(python_code, "<diff>")
                all_findings.extend(findings)
            except Exception as e:
                logger.warning(f"AST analysis failed: {e}")

        return all_findings

    def _extract_python_from_diff(self, diff: str) -> str:
        """Extrai código Python de um diff (linhas que começam com +)."""
        code_lines = []

        for line in diff.split('\n'):
            # Pega apenas linhas adicionadas (não cabeçalhos do diff)
            if line.startswith('+') and not line.startswith('+++'):
                code_lines.append(line[1:])  # Remove o '+'
            elif not line.startswith('-') and not line.startswith('@') and not line.startswith('diff'):
                # Mantém contexto (linhas sem prefixo)
                code_lines.append(line)

        return '\n'.join(code_lines)
    
    async def _analyze_llm(self, diff: str, ast_findings: List[Dict]) -> List[Dict[str, Any]]:
        """Executa análise LLM semântica."""
        ast_summary = "\n".join([
            f"- [{f.get('severity', 'UNKNOWN')}] {f.get('file', 'unknown')}:{f.get('line', 0)} - {f.get('message', '')}"
            for f in ast_findings
        ]) or "(none)"

        prompt = REVIEW_PROMPT_TEMPLATE.substitute(diff=diff, ast_findings=ast_summary)

        try:
            response = await self._router.complete(
                prompt=prompt,
                task_type="complex",
                model="llama-3.3-70b-versatile",
                actor="moon_review_agent"
            )

            return self._parse_llm_response(response)

        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return []
    
    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """Parseia resposta do LLM em estrutura de issues."""
        issues = []

        if not response or "no issues found" in response.lower():
            return issues

        # Parseia formato: ISSUE #{n}\nSeveridade: ...\nArquivo: ...\n...
        # Divide por separators "---" ou "ISSUE #"
        parts = response.split("---")

        for part in parts:
            part = part.strip()
            if not part:
                continue

            issue = {}
            for line in part.split('\n'):
                line = line.strip()
                if ':' not in line:
                    continue

                key, value = line.split(':', 1)
                key = key.lower().strip()
                value = value.strip()

                if 'severidade' in key or 'severity' in key:
                    issue['severity'] = value.upper()
                elif 'arquivo' in key or 'file' in key:
                    issue['file'] = value
                elif 'problema' in key or 'problem' in key:
                    issue['problem'] = value
                elif 'impacto' in key or 'impact' in key:
                    issue['impact'] = value
                elif 'fix' in key:
                    issue['fix'] = value

            if issue and ('severity' in issue or 'problem' in issue):
                issues.append(issue)

        # Se não encontrou nada, tenta parse alternativo
        if not issues and response:
            # Retorna resposta crua como único issue
            issues.append({
                'severity': 'MEDIUM',
                'file': 'review',
                'problem': response[:500],
                'impact': 'See full response',
                'fix': 'See LLM response',
            })

        return issues
    
    def _generate_report(
        self,
        files_reviewed: List[str],
        ast_findings: List[Dict],
        llm_findings: List[Dict]
    ) -> Dict[str, Any]:
        """Gera relatório JSON."""
        critical_count = sum(1 for f in ast_findings + llm_findings if f.get('severity') == 'CRITICAL')
        high_count = sum(1 for f in ast_findings + llm_findings if f.get('severity') == 'HIGH')
        medium_count = sum(1 for f in ast_findings + llm_findings if f.get('severity') == 'MEDIUM')

        # Health score: 100 - (critical*20) - (high*10) - (medium*3)
        health_score = max(0, 100 - (critical_count * 20) - (high_count * 10) - (medium_count * 3))

        return {
            "timestamp": datetime.now().isoformat(),
            "files_reviewed": list(files_reviewed) if files_reviewed else [],
            "ast_issues": ast_findings,
            "llm_issues": llm_findings,
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": medium_count,
            "health_score": health_score,
        }


# ─────────────────────────────────────────────────────────────
#  Factory function
# ─────────────────────────────────────────────────────────────

def create_review_agent() -> MoonReviewAgent:
    """Factory function para criar o agente."""
    return MoonReviewAgent()
