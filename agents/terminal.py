"""
agents/terminal.py
Execução autônoma de comandos no terminal.
"""
import asyncio
import re
from core.agent_base import AgentBase, TaskResult, AgentPriority
from utils.logger import setup_logger

class TerminalAgent(AgentBase):
    def __init__(self):
        super().__init__()
        self.priority = AgentPriority.CRITICAL
        self.description = "Terminal Automator"
        self.logger = setup_logger("TerminalAgent")
        
        # Security blacklist (comandos perigosos)
        self.blacklist = [
            r"rm\s+-rf", r"rm\s+/", "mkfs", "reboot", "shutdown", 
            "halt", "dd", ":(){:|:&};:", "> /dev/sda"
        ]

    def _is_safe(self, command: str) -> bool:
        for pattern in self.blacklist:
            if re.search(pattern, command):
                return False
        return True

    async def _execute(self, task: str, **kwargs) -> TaskResult:
        command = kwargs.get("command", task)
        if not command:
            return TaskResult(success=False, error="Nenhum comando fornecido")

        if not self._is_safe(command):
            self.logger.warning(f"Comando bloqueado por segurança: {command}")
            return TaskResult(success=False, error="Comando não permitido por motivos de segurança.")

        self.logger.info(f"Executando comando no terminal: {command}")
        
        try:
            # Executa o comando sub-processo shell
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Espera a conclusão e captura os logs
            stdout, stderr = await process.communicate()
            
            output = stdout.decode().strip()
            errors = stderr.decode().strip()

            if process.returncode == 0:
                return TaskResult(success=True, data={"output": output})
            else:
                return TaskResult(success=False, error=errors, data={"output": output})
                
        except Exception as e:
            return TaskResult(success=False, error=str(e))
