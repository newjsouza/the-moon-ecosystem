import asyncio
import os
import ast
import json
import time
import hashlib
import difflib
import subprocess
import logging
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta

from core.agent_base import AgentBase, AgentPriority, TaskResult
from core.message_bus import MessageBus

# Third-party (optional but recommended for full functionality)
try:
    from github import Github
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False

logger = logging.getLogger("moon.agents.devops")

# ─────────────────────────────────────────────────────────────
#  Constants & Patterns
# ─────────────────────────────────────────────────────────────
PAID_MODEL_PATTERNS = ["gpt-4", "gpt-3.5", "claude-3", "gemini-1.5-pro"]
SCAN_TARGETS = ["core/", "agents/", "skills/"]
REPORT_DIR = "data/devops_reports/"
BACKUP_DIR = "data/devops_reports/auto_heal_backups/"
MAX_FILE_LINES = 2000

# ─────────────────────────────────────────────────────────────
#  Support Classes
# ─────────────────────────────────────────────────────────────

class ASTAnalyzer:
    """Analyzes Python files for structural issues using AST."""
    
    def analyze(self, file_path: str, content: str) -> List[Dict]:
        issues = []
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return [{"id": "syntax_error", "severity": "CRITICAL", "line": e.lineno, "msg": f"Erro de sintaxe: {str(e)}"}]

        # 1. Detect unused imports (basic check)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name)
        
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                used_names.add(node.id)
            elif isinstance(node, ast.Attribute):
                curr = node.value
                while isinstance(curr, ast.Attribute):
                    curr = curr.value
                if isinstance(curr, ast.Name):
                    used_names.add(curr.id)

        unused = imported_names - used_names - {"Any", "Dict", "List", "Optional", "Tuple", "Union"}
        for name in unused:
            issues.append({
                "id": "unused_import",
                "severity": "LOW",
                "msg": f"Importação possivelmente não utilizada: {name}",
                "context": name
            })

        # 2. Check for missing 'await' on critical publishes
        awaited_calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
                awaited_calls.add(node.value)

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if self._is_publish_call(node) and node not in awaited_calls:
                    issues.append({
                        "id": "missing_await_publish",
                        "severity": "HIGH",
                        "msg": f"Chamada a message_bus.publish não aguardada (missing await) em {file_path}",
                        "file": file_path,
                        "fixable": True
                    })
        return issues

    def _is_publish_call(self, node: ast.Call) -> bool:
        """Checks if a call is message_bus.publish(...) or self.message_bus.publish(...)"""
        if isinstance(node.func, ast.Attribute) and node.func.attr == "publish":
            target = node.func.value
            # Case 1: message_bus.publish
            if isinstance(target, ast.Name) and target.id == "message_bus":
                return True
            # Case 2: self.message_bus.publish
            if isinstance(target, ast.Attribute) and target.attr == "message_bus":
                if isinstance(target.value, ast.Name) and target.value.id == "self":
                    return True
        return False

class CodexComplianceChecker:
    """Verifies alignment with Moon Codex (e.g., no hardcoded secrets)."""
    
    def check(self, file_path: str, content: str) -> List[Dict]:
        issues = []
        lines = content.splitlines()
        for i, line in enumerate(lines):
            # 1. Secret detection (very simple)
            if any(key in line.lower() for key in ["api_key", "secret", "password", "token"]) and "=" in line:
                if '"' in line or "'" in line:
                    issues.append({
                        "id": "hardcoded_secret",
                        "severity": "CRITICAL",
                        "line": i+1,
                        "msg": "Possível segredo hardcoded detectado.",
                        "fixable": False
                    })
            
            # 2. Paid model usage
            if any(pattern in line.lower() for pattern in PAID_MODEL_PATTERNS):
                issues.append({
                    "id": "paid_model_usage",
                    "severity": "MEDIUM",
                    "line": i+1,
                    "msg": f"Uso de modelo pago detectado ({line.strip()}). Priorize modelos locais se possível.",
                    "fixable": False
                })
        return issues

class DependencyAuditor:
    """Audits dependencies for vulnerabilities and outdated versions."""
    
    async def audit(self, pip_audit_path: str = "pip-audit") -> List[Dict]:
        issues = []
        try:
            def run_cmd():
                return subprocess.run([pip_audit_path, "--format", "json"], capture_output=True, text=True, check=False)
            
            result = await asyncio.to_thread(run_cmd)
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                for item in data.get("dependencies", []):
                    for vuln in item.get("vulnerabilities", []):
                        issues.append({
                            "id": "vulnerable_dependency",
                            "severity": "CRITICAL",
                            "msg": f"Vulnerabilidade {vuln.get('id')} em {item.get('name')} {item.get('version')}",
                            "package": item.get('name'),
                            "fixable": True
                        })
        except Exception as e:
            logger.error(f"Pip-audit failed: {e}")
        return issues

    async def fix(self, package: str) -> bool:
        try:
            def run_fix():
                return subprocess.run(["pip", "install", "--upgrade", package], capture_output=True, text=True, check=False)
            
            result = await asyncio.to_thread(run_fix)
            return result.returncode == 0
        except Exception:
            return False

class FixGenerator:
    """Generates fixes for identified issues using LLM."""
    
    def __init__(self, llm_client: Any):
        self.llm = llm_client

    def generate(self, issue: Dict, file_path: str, content: str) -> Optional[str]:
        # Implementation of fix generation via LLM
        return None

class AutoHealer:
    """Applies fixes automatically to the codebase."""
    
    def heal(self, file_path: str, new_content: str) -> bool:
        try:
            if not os.path.exists(BACKUP_DIR):
                os.makedirs(BACKUP_DIR, exist_ok=True)
            
            # Backup
            with open(file_path, 'r') as f:
                old_content = f.read()
            backup_name = f"{os.path.basename(file_path)}_{int(time.time())}.bak"
            with open(os.path.join(BACKUP_DIR, backup_name), 'w') as f:
                f.write(old_content)
                
            # Apply fix
            with open(file_path, 'w') as f:
                f.write(new_content)
            return True
        except Exception as e:
            logger.error(f"Heal failed for {file_path}: {e}")
            return False

class GitHubPRBridge:
    """Connects with GitHub to create PRs for non-critical fixes."""
    
    def __init__(self, token: str, repo_name: str):
        self.gh = Github(token)
        self.repo = self.gh.get_repo(repo_name)

    def create_pr(self, branch: str, title: str, body: str) -> bool:
        try:
            # PR creation logic
            return True
        except Exception:
            return False

# ─────────────────────────────────────────────────────────────
#  Main Agent Class
# ─────────────────────────────────────────────────────────────

class AutonomousDevOpsRefactor(AgentBase):
    """
    Agent responsible for continuous improvement, refactoring, 
    and self-healing of the ecosystem.
    """
    
    def __init__(self, groq_client=None, message_bus=None, **kwargs):
        super().__init__()
        self.name = "AutonomousDevOpsRefactor"
        self.priority = AgentPriority.CRITICAL
        
        self.message_bus = message_bus
        self.llm = groq_client
        
        self.analyzer = ASTAnalyzer()
        self.checker = CodexComplianceChecker()
        self.auditor = DependencyAuditor()
        self.fixer = FixGenerator(llm_client=groq_client)
        self.healer = AutoHealer()
        self.bridge: Optional[GitHubPRBridge] = None # Init in initialize
        
        self.scan_interval = 24  # hours
        self._last_scan: float = 0.0
        self._is_running = False

    async def initialize(self) -> None:
        token = os.environ.get("GITHUB_TOKEN")
        repo = os.environ.get("GITHUB_REPO")
        if token and repo:
            try:
                self.bridge = GitHubPRBridge(token, repo)
                logger.info(f"GitHub PR Bridge initialized for {repo}")
            except Exception as e:
                logger.error(f"Failed to initialize GitHub PR Bridge: {e}")
                self.bridge = None
        self.is_initialized = True
        if not os.path.exists(REPORT_DIR):
            os.makedirs(REPORT_DIR, exist_ok=True)
            
        logger.info(f"{self.name} initialized.")

    async def _run_loop(self) -> None:
        while True:
            if time.time() - self._last_scan > self.scan_interval * 3600:
                await self._run_scan()
            await asyncio.sleep(3600)

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        if task == "run_scan":
            return await self._run_scan()
        elif task == "audit_dependencies":
            issues = await self.auditor.audit()
            return TaskResult(success=True, data={"issues": issues})
        else:
            return TaskResult(success=False, error=f"Task unknown: {task}")

    async def _run_scan(self) -> TaskResult:
        self._is_running = True
        logger.info("Starting global DevOps scan...")
        issues_list: List[Dict[str, Any]] = []
        actions: List[str] = []
        summary = {"critical": 0, "high": 0, "medium": 0, "low": 0, "fixable": 0}
        
        # 1. Scan Files
        files_to_scan = self._get_scan_files()
        for file_path in files_to_scan:
            try:
                with open(file_path, 'r') as f:
                    content = f.read()
                
                if len(content.splitlines()) > MAX_FILE_LINES:
                    continue
                
                # Structural & Compliance
                results = self.analyzer.analyze(file_path, content)
                results += self.checker.check(file_path, content)
                
                if results:
                    summary["fixable"] += 1
                    for issue in results:
                        issue["file"] = file_path
                        issues_list.append(issue)
                        summary[issue["severity"].lower()] += 1
                
            except Exception as e:
                logger.error(f"Error scanning {file_path}: {e}")

        # 2. Auto-Healing
        for issue in [i for i in issues_list if i["severity"] == "CRITICAL" and i.get("fixable")]:
            try:
                with open(issue["file"], 'r') as f:
                    current_content = f.read()
                fix = self.fixer.generate(issue, issue["file"], current_content)
                if fix:
                    if self.healer.heal(issue["file"], fix):
                        actions.append(f"Auto-healed critical issue in {issue['file']}")
            except Exception as e:
                logger.error(f"Error during auto-healing for {issue['file']}: {e}")

        # 3. Audit Dependencies
        pip_audit_path = "pip-audit"
        if os.path.exists("./.venv/bin/pip-audit"):
            pip_audit_path = "./.venv/bin/pip-audit"
        elif os.path.exists("./venv/bin/pip-audit"):
            pip_audit_path = "./venv/bin/pip-audit"

        vulnerabilities = await self.auditor.audit(pip_audit_path=pip_audit_path)
        for issue in vulnerabilities:
            issues_list.append(issue)
            summary[issue["severity"].lower()] += 1

        # Final Report Assembly
        report = {
            "version": "1.0",
            "timestamp": datetime.now().isoformat(),
            "issues": issues_list,
            "actions_taken": actions,
            "summary": summary
        }
        
        # 4. Save & Notify
        report_path = os.path.join(REPORT_DIR, f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=4)
            
        await self._publish_report(report)
        
        self._last_scan = time.time()
        self._is_running = False
        return TaskResult(success=True, data={"report_path": report_path, "summary": summary})

    async def _publish_report(self, report: Dict[str, Any]) -> None:
        if not self.message_bus:
            return

        summary = report.get("summary")
        if not isinstance(summary, dict):
             return

        message = {
            "type": "devops_report",
            "critical": summary.get("critical", 0),
            "high": summary.get("high", 0),
            "medium": summary.get("medium", 0),
            "low": summary.get("low", 0),
            "actions": report.get("actions_taken", [])
        }
        await self.message_bus.publish(self.name, "devops.scan_complete", message)

    def _get_scan_files(self) -> List[str]:
        target_files = []
        for target in SCAN_TARGETS:
            if os.path.isdir(target):
                for root, _, files in os.walk(target):
                    for file in files:
                        if file.endswith(".py"):
                            target_files.append(os.path.join(root, file))
        return target_files
