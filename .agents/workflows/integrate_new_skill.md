---
description: Como integrar uma nova Skill ao ecossistema The Moon
---

# Fluxo de Trabalho: Integração de Nova Skill

Siga estes passos para adicionar uma nova funcionalidade (Skill) ao projeto:

1. **Pesquisa e Planejamento**:
   - Analise se a funcionalidade já existe em projetos de referência (ex: Jarvis).
   - Defina os requisitos e as APIs necessárias (priorize APIs gratuitas).

2. **Estrutura de Diretórios**:
   - Crie uma pasta em `skills/[nome_da_skill]`.
   - Crie os arquivos base: `models.py`, `service.py`, `manager.py`.

3. **Implementação do Modelo**:
   - Defina os data classes em `models.py` para estruturar os dados da skill.

4. **Gerenciamento de Credenciais**:
   - Se a skill exige tokens ou chaves, utilize o `CredentialManager` em `credential_manager.py` (ou adapte o existente) para armazenamento seguro via XOR+Base64.

5. **Serviço e Lógica**:
   - Implemente a lógica de baixo nível em `service.py`.

6. **Gerenciador da Skill**:
   - Em `manager.py`, crie a classe que herda de `SkillBase`.
   - Implemente o método assíncrono `execute(params)`.

7. **Configuração e Dependências**:
   - Adicione chaves necessárias ao `.env` com placeholders.
   - Atualize o `requirements.txt`.

8. **Automação de Setup (Opcional, mas Recomendado)**:
   - Crie um `setup.py` para guiar o usuário na configuração inicial (ex: OAuth2).
// turbo
   - Utilize o `browser_subagent` para automatizar o máximo possível deste setup.

9. **Verificação**:
   - Crie e execute testes em `tests/`.
   - Gere um `walkthrough.md` com evidências (screenshots/gravações).

---
**Objetivo**: Manter a autonomia do sistema e o custo zero.
