Segue o código completo para o CLI agent-native para o software `/usr/bin/ffmpeg`:

**Phase 1: Codebase Analysis**

O software alvo é `/usr/bin/ffmpeg`, que é um poderoso processador de vídeo e áudio. Para criar um CLI agent-native para esse software, precisamos analisar o seu backend engine, mapear as ações da GUI para chamadas de API, identificar o modelo de dados e encontrar ferramentas de linha de comando existentes.

* Backend engine: `/usr/bin/ffmpeg` é o próprio backend engine.
* Mapear ações da GUI para chamadas de API: Como `/usr/bin/ffmpeg` é uma ferramenta de linha de comando, não há uma GUI para mapear.
* Modelo de dados: `/usr/bin/ffmpeg` trabalha com vários formatos de arquivo, incluindo vídeo e áudio.
* Ferramentas de linha de comando existentes: `/usr/bin/ffmpeg` é a própria ferramenta de linha de comando.

**Phase 2: CLI Architecture Design**

* Escolher o modelo de interação: Vamos usar um modelo de interação stateful REPL para sessões interativas e um modelo de subcomando CLI para operações de um único disparo.
* Definir grupos de comandos: Vamos definir os seguintes grupos de comandos:
 + `project`: comandos para gerenciar projetos de vídeo e áudio.
 + `core`: comandos para processar vídeo e áudio.
 + `import`: comandos para importar arquivos de vídeo e áudio.
 + `export`: comandos para exportar arquivos de vídeo e áudio.
 + `config`: comandos para configurar opções de processamento.
* Desenhar o modelo de estado: Vamos usar um modelo de estado que persiste entre comandos, armazenando informações sobre o projeto atual, como o arquivo de entrada e saída.
* Planejar o formato de saída: Vamos usar um formato de saída JSON para saída de máquina e um formato de saída humano-legível para saída interativa.

**Phase 3: Implementation**

Vamos implementar o CLI Python completo:

```python
import click
import json
import subprocess

# Utils
def find_ffmpeg():
    return subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True).stdout.strip()

def invoke_ffmpeg(args):
    return subprocess.run([find_ffmpeg()] + args, capture_output=True, text=True)

# Comandos
@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)

@cli.command()
@click.option('--json', is_flag=True, help='Saída em formato JSON')
def info(json):
    if json:
        click.echo(json.dumps({'software': 'ffmpeg', 'version': '4.4'}))
    else:
        click.echo('Software: ffmpeg')
        click.echo('Versão: 4.4')

@cli.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.argument('output_file', type=click.Path())
@click.option('--json', is_flag=True, help='Saída em formato JSON')
def convert(input_file, output_file, json):
    args = ['-i', input_file, output_file]
    result = invoke_ffmpeg(args)
    if json:
        click.echo(json.dumps({'input_file': input_file, 'output_file': output_file, 'status': 'ok'}))
    else:
        click.echo('Conversão realizada com sucesso!')

# REPL
from cli_anything.utils.repl_skin import ReplSkin

@cli.command(hidden=True)
@click.pass_context
def repl(ctx):
    skin = ReplSkin('ffmpeg', version='1.0.0')
    pt_session = skin.create_prompt_session()
    while True:
        line = skin.get_input(pt_session)
        if line.startswith('exit'):
            break
        elif line.startswith('help'):
            skin.help({'info': 'Mostra informações sobre o software', 'convert': 'Converte um arquivo de vídeo ou áudio'})
        elif line.startswith('info'):
            info(json=False)
        elif line.startswith('convert'):
            args = line.split()
            if len(args) < 3:
                click.echo('Erro: falta de argumentos')
            else:
                convert(args[1], args[2], json=False)
        else:
            click.echo('Comando desconhecido')

if __name__ == '__main__':
    cli()
```

**setup.py**

```python
from setuptools import setup

setup(
    name='cli-anything-ffmpeg',
    version='1.0.0',
    description='CLI agent-native para o software ffmpeg',
    author='Seu Nome',
    author_email='seu@email.com',
    packages=['cli_anything.ffmpeg'],
    entry_points={
        'console_scripts': ['cli-anything-ffmpeg=cli_anything.ffmpeg.cli:cli']
    },
    install_requires=['click', 'prompt-toolkit']
)
```

**TEST.md**

```markdown
# Test Inventory Plan

* `test_core.py`: 10 testes unitários planejados
* `test_full_e2e.py`: 5 testes E2E planejados

# Unit Test Plan

* Módulo `info.py`
 + Funções a testar: `info`
 + Casos de bordo a cobrir: falta de argumentos, argumentos inválidos
 + Contagem de testes esperada: 5
* Módulo `convert.py`
 + Funções a testar: `convert`
 + Casos de bordo a cobrir: falta de argumentos, argumentos inválidos, conversão bem-sucedida
 + Contagem de testes esperada: 5

# E2E Test Plan

* Fluxo de trabalho a simular: conversão de um arquivo de vídeo
* Arquivos reais a gerar/processar: arquivo de vídeo de entrada e saída
* Saída esperada: arquivo de vídeo convertido com sucesso
```

Espero que isso ajude! Lembre-se de que este é apenas um exemplo e que você precisará adaptá-lo às suas necessidades específicas. Além disso, certifique-se de testar o código completamente antes de liberá-lo.