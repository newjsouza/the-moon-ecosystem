"""
core/workspace/computer.py
Implements the AgentMachine (Hypothetical Computer).
"""
import os
import shutil
import logging
from typing import List, Dict

logger = logging.getLogger("moon.workspace.computer")

class AgentMachine:
    def __init__(self, room_id: str, computer_path: str):
        self.room_id = room_id
        self.path = computer_path
        self._init_environment()

    def _init_environment(self):
        """Sets up the initial files for the virtual computer."""
        os.makedirs(self.path, exist_ok=True)
        readme_path = os.path.join(self.path, "README.md")
        if not os.path.exists(readme_path):
            with open(readme_path, "w") as f:
                f.write(f"# Computador do Agente: {self.room_id}\n")
                f.write("Este é o seu ambiente de desenvolvimento autônomo.\n")
                f.write("Aqui você pode criar rascunhos de código, testar lógica e gerenciar novas ferramentas.\n")
        
        # Create standard folders
        os.makedirs(os.path.join(self.path, "src"), exist_ok=True)
        os.makedirs(os.path.join(self.path, "tests"), exist_ok=True)
        os.makedirs(os.path.join(self.path, "output"), exist_ok=True)

    def write_file(self, filename: str, content: str, subdir: str = "src"):
        """Writes a file to the virtual machine."""
        target_dir = os.path.join(self.path, subdir)
        os.makedirs(target_dir, exist_ok=True)
        file_path = os.path.join(target_dir, filename)
        with open(file_path, "w") as f:
            f.write(content)
        logger.info(f"File {filename} written to {self.room_id}'s computer.")

    def read_file(self, filename: str, subdir: str = "src") -> str:
        """Reads a file from the virtual machine."""
        file_path = os.path.join(self.path, subdir, filename)
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return f.read()
        return f"File {filename} not found."

    def list_files(self) -> Dict[str, List[str]]:
        """Lists all files in the virtual machine organized by directory."""
        files = {}
        for root, dirs, filenames in os.walk(self.path):
            rel_path = os.path.relpath(root, self.path)
            if rel_path == ".": rel_path = "root"
            files[rel_path] = filenames
        return files

    def clear_output(self):
        """Cleans the output directory."""
        output_dir = os.path.join(self.path, "output")
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
            os.makedirs(output_dir, exist_ok=True)
