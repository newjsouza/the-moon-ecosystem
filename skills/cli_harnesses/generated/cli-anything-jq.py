Aqui está o código completo para o CLI do software `jq`:

** Estrutura de diretórios **
```markdown
cli-anything-jq/
├── cli_anything
│   ├── jq
│   │   ├── __init__.py
│   │   ├── utils
│   │   │   ├── __init__.py
│   │   │   ├── jq_backend.py
│   │   │   ├── repl_skin.py
│   │   └── commands
│   │       ├── __init__.py
│   │       ├── parse.py
│   │       ├── query.py
│   │       └── validate.py
│   └── __init__.py
├── setup.py
└── TEST.md
```

** setup.py **
```python
from setuptools import setup, find_packages

setup(
    name='cli-anything-jq',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[
        'click',
        'prompt-toolkit',
        'jq'
    ],
    entry_points={
        'console_scripts': [
            'cli-anything-jq=cli_anything.jq.commands:cli'
        ]
    }
)
```

** cli_anything/jq/__init__.py **
```python
from .commands import cli
```

** cli_anything/jq/utils/jq_backend.py **
```python
import subprocess
import shutil

def find_jq():
    jq = shutil.which('jq')
    if jq is None:
        raise RuntimeError('jq não encontrado. Por favor, instale-o e tente novamente.')
    return jq

def parse_json(json_data):
    jq = find_jq()
    result = subprocess.run([jq, '.'], input=json_data.encode('utf-8'), capture_output=True)
    return result.stdout.decode('utf-8')

def query_json(json_data, query):
    jq = find_jq()
    result = subprocess.run([jq, query], input=json_data.encode('utf-8'), capture_output=True)
    return result.stdout.decode('utf-8')

def validate_json(json_data):
    jq = find_jq()
    result = subprocess.run([jq, '.'], input=json_data.encode('utf-8'), capture_output=True)
    if result.returncode != 0:
        raise ValueError('JSON inválido')
    return True
```

** cli_anything/jq/utils/repl_skin.py **
```python
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

class ReplSkin:
    def __init__(self, software_name, version):
        self.software_name = software_name
        self.version = version
        self.history = InMemoryHistory()

    def print_banner(self):
        print(f'{self.software_name} {self.version}')

    def create_prompt_session(self):
        return PromptSession('>> ', history=self.history)

    def get_input(self, session, prompt='>> '):
        return session.prompt(prompt)

    def help(self, commands_dict):
        print('Comandos disponíveis:')
        for command, description in commands_dict.items():
            print(f'{command}: {description}')

    def success(self, message):
        print(f'\033[92m{message}\033[0m')

    def error(self, message):
        print(f'\033[91m{message}\033[0m')

    def warning(self, message):
        print(f'\033[93m{message}\033[0m')

    def info(self, message):
        print(f'\033[94m{message}\033[0m')

    def status(self, key, value):
        print(f'{key}: {value}')

    def table(self, headers, rows):
        print('\n'.join([', '.join(row) for row in [headers] + rows]))

    def progress(self, current, total, message):
        print(f'{message} {current}/{total}')

    def print_goodbye(self):
        print('Tchau!')
```

** cli_anything/jq/commands/__init__.py **
```python
from .parse import parse_command
from .query import query_command
from .validate import validate_command

commands_dict = {
    'parse': parse_command,
    'query': query_command,
    'validate': validate_command
}
```

** cli_anything/jq/commands/parse.py **
```python
import click
from ..utils.jq_backend import parse_json

@click.command()
@click.argument('json_data', type=click.STRING)
@click.option('--json', is_flag=True, help='Saída em JSON')
def parse_command(json_data, json):
    result = parse_json(json_data)
    if json:
        click.echo({'result': result})
    else:
        click.echo(result)
```

** cli_anything/jq/commands/query.py **
```python
import click
from ..utils.jq_backend import query_json

@click.command()
@click.argument('json_data', type=click.STRING)
@click.argument('query', type=click.STRING)
@click.option('--json', is_flag=True, help='Saída em JSON')
def query_command(json_data, query, json):
    result = query_json(json_data, query)
    if json:
        click.echo({'result': result})
    else:
        click.echo(result)
```

** cli_anything/jq/commands/validate.py **
```python
import click
from ..utils.jq_backend import validate_json

@click.command()
@click.argument('json_data', type=click.STRING)
@click.option('--json', is_flag=True, help='Saída em JSON')
def validate_command(json_data, json):
    try:
        validate_json(json_data)
        if json:
            click.echo({'result': 'JSON válido'})
        else:
            click.echo('JSON válido')
    except ValueError as e:
        if json:
            click.echo({'error': str(e)})
        else:
            click.echo(str(e))
```

** cli_anything/jq/commands/cli.py **
```python
import click
from . import commands_dict
from ..utils.repl_skin import ReplSkin

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand is None:
        skin = ReplSkin('jq', '1.0.0')
        skin.print_banner()
        session = skin.create_prompt_session()
        while True:
            line = skin.get_input(session)
            if line == 'quit':
                break
            for command, func in commands_dict.items():
                if line.startswith(command):
                    func(line[len(command):].strip(), json=False)
                    break
            else:
                skin.error('Comando desconhecido')

@cli.command()
def repl():
    skin = ReplSkin('jq', '1.0.0')
    skin.print_banner()
    session = skin.create_prompt_session()
    while True:
        line = skin.get_input(session)
        if line == 'quit':
            break
        for command, func in commands_dict.items():
            if line.startswith(command):
                func(line[len(command):].strip(), json=False)
                break
        else:
            skin.error('Comando desconhecido')
```

** TEST.md **
```markdown
# Test Inventory Plan

* `test_core.py`: 10 testes unitários planejados
* `test_full_e2e.py`: 5 testes de ponta a ponta planejados

# Unit Test Plan

* Módulo `jq_backend.py`
 + Funções a testar: `parse_json`, `query_json`, `validate_json`
 + Casos de bordo: entrada inválida, saída inválida
 + Quantidade de testes: 5
* Módulo `repl_skin.py`
 + Funções a testar: `print_banner`, `create_prompt_session`, `get_input`
 + Casos de bordo: entrada inválida
 + Quantidade de testes: 3

# E2E Test Plan

* Fluxo de trabalho: parsear um arquivo JSON, realizar uma consulta e validar o resultado
* Arquivos reais a serem gerados: `input.json`, `output.json`
* Saídaesperada: `output.json` com o resultado da consulta
* Quantidade de testes: 2
```