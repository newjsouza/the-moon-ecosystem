Segue o código completo para o CLI agent-native do software `/usr/bin/jq`:

**Setup**
```python
# setup.py
from setuptools import setup

setup(
    name='cli-anything-jq',
    version='1.0.0',
    packages=['cli_anything.jq'],
    entry_points={
        'console_scripts': [
            'cli-anything-jq=cli_anything.jq.cli:cli'
        ]
    },
    install_requires=[
        'click',
        'json'
    ]
)
```

**CLI**
```python
# cli_anything/jq/cli.py
import click
import json
from cli_anything.jq.utils import jq_backend

@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)

@cli.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.argument('query')
@click.option('--json', is_flag=True, help='Output as JSON')
def query(input_file, query, json):
    result = jq_backend.query(input_file, query)
    if json:
        click.echo(json.dumps(result))
    else:
        click.echo(result)

@cli.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--json', is_flag=True, help='Output as JSON')
def parse(input_file, json):
    result = jq_backend.parse(input_file)
    if json:
        click.echo(json.dumps(result))
    else:
        click.echo(result)

def repl():
    from cli_anything.jq.utils.repl_skin import ReplSkin
    skin = ReplSkin('jq', version='1.0.0')
    skin.print_banner()
    pt_session = skin.create_prompt_session()
    while True:
        line = skin.get_input(pt_session)
        if line.startswith('query '):
            query = line[6:]
            result = jq_backend.query(None, query)
            skin.success(result)
        elif line.startswith('parse '):
            input_file = line[6:]
            result = jq_backend.parse(input_file)
            skin.success(result)
        elif line == 'exit':
            skin.print_goodbye()
            break
        else:
            skin.error('Unknown command')

if __name__ == '__main__':
    cli()
```

**jq backend**
```python
# cli_anything/jq/utils/jq_backend.py
import subprocess
import json

def find_jq():
    jq = subprocess.run(['which', 'jq'], stdout=subprocess.PIPE)
    if jq.returncode != 0:
        raise RuntimeError('jq not found. Please install jq and try again.')
    return jq.stdout.decode().strip()

def query(input_file, query):
    jq = find_jq()
    args = [jq, query]
    if input_file:
        args.append(input_file)
    result = subprocess.run(args, stdout=subprocess.PIPE)
    return result.stdout.decode()

def parse(input_file):
    jq = find_jq()
    args = [jq, '.']
    if input_file:
        args.append(input_file)
    result = subprocess.run(args, stdout=subprocess.PIPE)
    return json.loads(result.stdout)
```

**repl skin**
```python
# cli_anything/jq/utils/repl_skin.py
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion

class ReplSkin:
    def __init__(self, name, version):
        self.name = name
        self.version = version
        self.session = None

    def print_banner(self):
        click.echo(f'{self.name} {self.version}')

    def create_prompt_session(self):
        self.session = PromptSession('>>> ')
        return self.session

    def get_input(self, session):
        return session.prompt()

    def success(self, message):
        click.echo(f'✓ {message}')

    def error(self, message):
        click.echo(f'✗ {message}')

    def warning(self, message):
        click.echo(f'⚠ {message}')

    def info(self, message):
        click.echo(f'● {message}')

    def status(self, key, value):
        click.echo(f'{key}: {value}')

    def table(self, headers, rows):
        click.echo(tabulate(rows, headers, tablefmt='grid'))

    def progress(self, current, total, message):
        click.echo(f'{message} {current}/{total}')

    def print_goodbye(self):
        click.echo('Goodbye!')
```

**TEST.md**
```markdown
# Test Inventory Plan
- `test_core.py`: 10 unit tests planned
- `test_full_e2e.py`: 5 E2E tests planned

# Unit Test Plan
- Module name: `jq_backend.py`
  - Functions to test: `find_jq`, `query`, `parse`
  - Edge cases to cover: invalid input files, invalid queries, jq not found
  - Expected test count: 5

- Module name: `repl_skin.py`
  - Functions to test: `print_banner`, `create_prompt_session`, `get_input`
  - Edge cases to cover: invalid input, empty input
  - Expected test count: 3

# E2E Test Plan
- What workflows will be simulated: querying a JSON file, parsing a JSON file
- What real files will be generated/processed: example.json
- What output proper: expected output of the query or parse operation
```

**test_core.py**
```python
import unittest
from cli_anything.jq.utils import jq_backend

class TestJqBackend(unittest.TestCase):
    def test_find_jq(self):
        jq = jq_backend.find_jq()
        self.assertIsNotNone(jq)

    def test_query(self):
        input_file = 'example.json'
        query = '.'
        result = jq_backend.query(input_file, query)
        self.assertEqual(result, '{"key": "value"}')

    def test_parse(self):
        input_file = 'example.json'
        result = jq_backend.parse(input_file)
        self.assertEqual(result, {'key': 'value'})

if __name__ == '__main__':
    unittest.main()
```

**test_full_e2e.py**
```python
import unittest
from cli_anything.jq.cli import cli

class TestE2E(unittest.TestCase):
    def test_query(self):
        input_file = 'example.json'
        query = '.'
        result = cli(query, input_file)
        self.assertEqual(result, '{"key": "value"}')

    def test_parse(self):
        input_file = 'example.json'
        result = cli(parse, input_file)
        self.assertEqual(result, {'key': 'value'})

if __name__ == '__main__':
    unittest.main()
```

Espero que isso atenda às suas necessidades. Lembre-se de que é importante testar o código completamente antes de usá-lo em produção. Além disso, é sempre uma boa prática seguir as boas práticas de codificação e documentação.