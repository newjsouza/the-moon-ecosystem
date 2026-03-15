#!/usr/bin/env python3
"""
TDD Workflow - Facilita o ciclo de desenvolvimento TDD

Baseado no Método Akita:
1. Escrever teste primeiro
2. Ver teste falhar
3. Implementar código
4. Ver teste passar
5. Refatorar
6. Commit
"""
import os
import sys
import subprocess
import argparse
from pathlib import Path


class TDDWorkflow:
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.test_dir = self.project_root / "tests"
        self.src_dir = self.project_root / "Super-Agente"

    def new(self, feature_name: str):
        """Criar nova feature com estrutura TDD."""
        feature_path = self.test_dir / "unit" / f"test_{feature_name}.py"
        
        if feature_path.exists():
            print(f"Teste já existe: {feature_path}")
            return

        feature_path.parent.mkdir(parents=True, exist_ok=True)

        template = f'''"""
TDD: Testes para {feature_name}

Lembre-se:
1. Escreva o teste primeiro
2. Execute e veja falhar
3. Implemente o código mínimo
4. Execute e veja passar
5. Refatore
6. Commit
"""
import pytest
from unittest.mock import Mock, patch


class Test{feature_name.replace("_", "").title()}:
    """Testes para {feature_name}."""

    def test_basic_functionality(self):
        """Teste básico - defina o comportamento esperado."""
        # TODO: Escreva o teste primeiro
        # Exemplo:
        # result = my_function(input)
        # assert result == expected
        pass
'''
        feature_path.write_text(template)
        print(f"✓ Criado: {feature_path}")
        print("\nPróximos passos:")
        print(f"1. Edite {feature_path} e escreva o teste")
        print(f"2. Execute: python -m pytest {feature_path} -v")
        print(f"3. Veja o teste falhar")
        print(f"4. Implemente o código")

    def run_tests(self, watch: bool = False):
        """Executar testes."""
        cmd = ["pytest", "-v", "--tb=short"]
        if watch:
            cmd.append("-W")
            cmd.append("ignore::DeprecationWarning")
        
        result = subprocess.run(cmd, cwd=self.project_root)
        return result.returncode

    def run_coverage(self):
        """Executar testes com coverage."""
        result = subprocess.run(
            ["pytest", "--cov=. ", "--cov-report=term-missing", "--cov-report=html"],
            cwd=self.project_root
        )
        return result.returncode

    def lint(self):
        """Executar linting."""
        print("Running Ruff...")
        result = subprocess.run(
            ["ruff", "check", "."],
            cwd=self.project_root,
            capture_output=True,
            text=True
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return result.returncode

    def ci(self):
        """Executar CI completo (lint + testes)."""
        print("=" * 50)
        print("CI - Executando validações completas")
        print("=" * 50)
        
        print("\n[1/2] Linting...")
        lint_result = self.lint()
        
        print("\n[2/2] Testes...")
        test_result = self.run_tests()
        
        print("\n" + "=" * 50)
        if lint_result == 0 and test_result == 0:
            print("✓ CI Passed!")
        else:
            print("✗ CI Failed!")
        print("=" * 50)
        
        return lint_result == 0 and test_result == 0


def main():
    parser = argparse.ArgumentParser(description="TDD Workflow CLI")
    subparsers = parser.add_subparsers(dest="command", help="Comandos")

    subparsers.add_parser("new", help="Criar nova feature TDD").add_argument("name")

    parser_run = subparsers.add_parser("test", help="Executar testes")
    parser_run.add_argument("--watch", "-w", action="store_true", help="Watch mode")

    subparsers.add_parser("cov", help="Executar com coverage")
    subparsers.add_parser("lint", help="Executar linting")
    subparsers.add_parser("ci", help="Executar CI completo")

    args = parser.parse_args()
    
    tdd = TDDWorkflow()

    if args.command == "new":
        tdd.new(args.name)
    elif args.command == "test":
        sys.exit(tdd.run_tests(watch=args.watch))
    elif args.command == "cov":
        sys.exit(tdd.run_coverage())
    elif args.command == "lint":
        sys.exit(tdd.lint())
    elif args.command == "ci":
        sys.exit(0 if tdd.ci() else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
