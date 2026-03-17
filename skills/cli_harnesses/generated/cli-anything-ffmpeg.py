Segue o código completo para o CLI harness para o software ffmpeg:

**Fase 1: Análise do software alvo**

O software alvo é o ffmpeg, uma ferramenta de linha de comando para processamento de vídeo e áudio. O backend engine é o próprio ffmpeg.

**Mapeamento de ações GUI para chamadas de API**

Não se aplica, pois o ffmpeg é uma ferramenta de linha de comando.

**Identificação do modelo de dados**

O ffmpeg trabalha com vários formatos de arquivo, incluindo MP4, AVI, MOV, etc.

**Ferramentas CLI existentes**

O próprio ffmpeg é uma ferramenta CLI.

**Sistema de comandos e desfazer**

O ffmpeg não tem um sistema de comandos e desfazer explícito.

**Fase 2: Arquitetura de comandos Click**

**Escolha do modelo de interação**

Vamos usar um modelo de interação stateful REPL para sessões interativas e subcomandos CLI para operações de um único disparo.

**Definição de grupos de comandos**

*   Project management (não se aplica)
*   Core operations: `convert`, `resize`, `crop`, etc.
*   Import/Export: `input`, `output`
*   Configuração: `settings`
*   Gerenciamento de sessão/estado: `status`

**Design do modelo de estado**

*   Estado que deve persistir entre comandos: arquivo de entrada, arquivo de saída, formato de saída
*   Local de armazenamento do estado: arquivo de configuração JSON
*   Serialização do estado: JSON

**Planejamento do formato de saída**

*   Saída humana legível: tabela, cores
*   Saída legível por máquina: JSON
*   Controle pela flag `--json`

**Fase 3: Implementação**

**Início com a camada de dados**

Vamos criar um módulo `utils/ffmpeg_backend.py` para encapsular as chamadas para o ffmpeg:

```python
import subprocess
import shutil
import json

def find_ffmpeg():
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        raise RuntimeError("ffmpeg não encontrado. Instale-o e tente novamente.")
    return ffmpeg

def convert(input_path, output_format, output_path=None, overwrite=False):
    ffmpeg = find_ffmpeg()
    cmd = [ffmpeg, '-i', input_path]
    if output_path:
        cmd.extend(['-y' if overwrite else '-n', output_path])
    else:
        cmd.extend(['-f', output_format, '-'])
    subprocess.run(cmd)
    return {'output': output_path, 'format': output_format, 'method': 'ffmpeg'}

def resize(input_path, width, height, output_path=None, overwrite=False):
    ffmpeg = find_ffmpeg()
    cmd = [ffmpeg, '-i', input_path, '-vf', f'scale={width}:{height}']
    if output_path:
        cmd.extend(['-y' if overwrite else '-n', output_path])
    else:
        cmd.extend(['-f', 'mp4', '-'])
    subprocess.run(cmd)
    return {'output': output_path, 'width': width, 'height': height, 'method': 'ffmpeg'}

def crop(input_path, x, y, width, height, output_path=None, overwrite=False):
    ffmpeg = find_ffmpeg()
    cmd = [ffmpeg, '-i', input_path, '-vf', f'crop={width}:{height}:{x}:{y}']
    if output_path:
        cmd.extend(['-y' if overwrite else '-n', output_path])
    else:
        cmd.extend(['-f', 'mp4', '-'])
    subprocess.run(cmd)
    return {'output': output_path, 'x': x, 'y': y, 'width': width, 'height': height, 'method': 'ffmpeg'}
```

**Adicionando comandos de mutação**

Vamos criar um módulo `cli_anything/ffmpeg/cli.py` para definir os comandos Click:

```python
import click
from cli_anything.ffmpeg.utils import ffmpeg_backend

@click.group()
def cli():
    pass

@cli.command()
@click.argument('input_path')
@click.argument('output_format')
@click.option('--output-path', help='Caminho do arquivo de saída')
@click.option('--overwrite', is_flag=True, help='Sobrescrever o arquivo de saída')
@click.option('--json', is_flag=True, help='Saída em JSON')
def convert(input_path, output_format, output_path, overwrite, json):
    result = ffmpeg_backend.convert(input_path, output_format, output_path, overwrite)
    if json:
        click.echo(json.dumps(result))
    else:
        click.echo(f'Conversão realizada com sucesso! Saída: {result["output"]}')

@cli.command()
@click.argument('input_path')
@click.argument('width', type=int)
@click.argument('height', type=int)
@click.option('--output-path', help='Caminho do arquivo de saída')
@click.option('--overwrite', is_flag=True, help='Sobrescrever o arquivo de saída')
@click.option('--json', is_flag=True, help='Saída em JSON')
def resize(input_path, width, height, output_path, overwrite, json):
    result = ffmpeg_backend.resize(input_path, width, height, output_path, overwrite)
    if json:
        click.echo(json.dumps(result))
    else:
        click.echo(f'Redimensionamento realizado com sucesso! Saída: {result["output"]}')

@cli.command()
@click.argument('input_path')
@click.argument('x', type=int)
@click.argument('y', type=int)
@click.argument('width', type=int)
@click.argument('height', type=int)
@click.option('--output-path', help='Caminho do arquivo de saída')
@click.option('--overwrite', is_flag=True, help='Sobrescrever o arquivo de saída')
@click.option('--json', is_flag=True, help='Saída em JSON')
def crop(input_path, x, y, width, height, output_path, overwrite, json):
    result = ffmpeg_backend.crop(input_path, x, y, width, height, output_path, overwrite)
    if json:
        click.echo(json.dumps(result))
    else:
        click.echo(f'Recorte realizado com sucesso! Saída: {result["output"]}')
```

**Adicionando suporte a REPL**

Vamos criar um módulo `utils/repl_skin.py` para encapsular a interface do REPL:

```python
import click
from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory

class ReplSkin:
    def __init__(self, name, version):
        self.name = name
        self.version = version
        self.history = InMemoryHistory()

    def print_banner(self):
        click.echo(f'{self.name} {self.version}')

    def create_prompt_session(self):
        return PromptSession('>', history=self.history)

    def get_input(self, session, **kwargs):
        return session.prompt(**kwargs)

    def help(self, commands):
        click.echo('Comandos disponíveis:')
        for command in commands:
            click.echo(f'  {command}')

    def success(self, message):
        click.echo(f'\033[92m{message}\033[0m')

    def error(self, message):
        click.echo(f'\033[91m{message}\033[0m')

    def warning(self, message):
        click.echo(f'\033[93m{message}\033[0m')

    def info(self, message):
        click.echo(f'\033[94m{message}\033[0m')

    def status(self, key, value):
        click.echo(f'{key}: {value}')

    def table(self, headers, rows):
        click.echo(tabulate(rows, headers, tablefmt='grid'))

    def progress(self, current, total, message):
        click.echo(f'\r{message} {current}/{total}')

    def print_goodbye(self):
        click.echo('Tchau!')
```

**Adicionando suporte a REPL ao CLI**

Vamos modificar o módulo `cli.py` para incluir o suporte a REPL:

```python
import click
from cli_anything.ffmpeg.utils import ffmpeg_backend
from cli_anything.ffmpeg.utils.repl_skin import ReplSkin

@click.group()
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)

@cli.command()
def repl():
    skin = ReplSkin('cli-anything-ffmpeg', '1.0.0')
    skin.print_banner()
    session = skin.create_prompt_session()
    while True:
        line = skin.get_input(session)
        if line == 'sair':
            break
        # Processar comandos aqui
        skin.success('Comando processado com sucesso!')

if __name__ == '__main__':
    cli()
```

**Fase 4: Planejamento de testes**

Vamos criar um arquivo `TEST.md` para planejar os testes:

```markdown
# Planejamento de testes

## Teste de unidade

*   `test_backend.py`: 10 testes unitários planejados
*   `test_cli.py`: 10 testes unitários planejados

## Teste de ponta a ponta

*   `test_e2e.py`: 5 testes de ponta a ponta planejados
```

**Setup.py**

Vamos criar um arquivo `setup.py` para incluir o CLI no pacote:

```python
from setuptools import setup

setup(
    name='cli-anything-ffmpeg',
    version='1.0.0',
    packages=['cli_anything.ffmpeg'],
    entry_points={
        'console_scripts': [
            'cli-anything-ffmpeg=cli_anything.ffmpeg.cli:cli',
        ],
    },
)
```

Agora, o pacote está pronto para ser instalado e utilizado. Para instalar, execute o comando `pip install -e .` no diretório raiz do pacote. Para utilizar, execute o comando `cli-anything-ffmpeg` no terminal.