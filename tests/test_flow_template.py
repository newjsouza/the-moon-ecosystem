"""tests/test_flow_template.py — Testes do sistema de templates de flows"""

import json
import tempfile
import os
from unittest.mock import AsyncMock, Mock
import pytest
from core.flow_template import FlowTemplate, FlowTemplateVar, FlowTemplateRegistry, get_template_registry


class TestFlowTemplate:
    def test_flow_template_var_creation(self):
        """Testa FlowTemplateVar com campos corretos."""
        var = FlowTemplateVar(name="topic", description="Assunto do post", default="tech")
        
        assert var.name == "topic"
        assert var.description == "Assunto do post"
        assert var.default == "tech"

    def test_flow_template_creation(self):
        """Testa FlowTemplate com todos campos."""
        var = FlowTemplateVar(name="topic", description="Assunto", default="default")
        template = FlowTemplate(
            name="blog_template",
            domain="blog",
            description="Template para posts",
            variables=[var],
            steps=[
                {"name": "step1", "agent": "writer", "task": "Write about {topic}"},
                {"name": "step2", "agent": "reviewer", "task": "Review {topic}"}
            ],
            tags=["blog", "writing"],
            version="1.0.0"
        )
        
        assert template.name == "blog_template"
        assert template.domain == "blog"
        assert template.description == "Template para posts"
        assert len(template.variables) == 1
        assert len(template.steps) == 2
        assert template.tags == ["blog", "writing"]
        assert template.version == "1.0.0"

    def test_flow_template_instantiate(self):
        """Testa substituição de {topic} e {tone} corretamente."""
        topic_var = FlowTemplateVar(name="topic", description="Topic", default="default_topic")
        tone_var = FlowTemplateVar(name="tone", description="Tone", default="default_tone")
        
        template = FlowTemplate(
            name="test_template",
            domain="test",
            description="Test template",
            variables=[topic_var, tone_var],
            steps=[
                {"name": "step1", "agent": "writer", "task": "Write about {topic} in {tone} tone"},
                {"name": "step2", "agent": "reviewer", "task": "Review {topic} content"}
            ]
        )
        
        values = {"topic": "Python", "tone": "technical"}
        flow = template.instantiate(values)
        
        assert len(flow.steps) == 2
        assert flow.steps[0].task == "Write about Python in technical tone"
        assert flow.steps[1].task == "Review Python content"

    def test_flow_template_instantiate_defaults(self):
        """Testa uso de defaults para vars não fornecidas."""
        topic_var = FlowTemplateVar(name="topic", description="Topic", default="default_topic")
        tone_var = FlowTemplateVar(name="tone", description="Tone", default="formal")
        
        template = FlowTemplate(
            name="test_template",
            domain="test",
            description="Test template",
            variables=[topic_var, tone_var],
            steps=[
                {"name": "step1", "agent": "writer", "task": "Write about {topic} in {tone} tone"}
            ]
        )
        
        # Only provide topic, tone should use default
        values = {"topic": "Python"}
        flow = template.instantiate(values)
        
        assert flow.steps[0].task == "Write about Python in formal tone"

    def test_flow_template_get_variables_prompt(self):
        """Testa string legível de variáveis."""
        topic_var = FlowTemplateVar(name="topic", description="Assunto do post", default="tech")
        tone_var = FlowTemplateVar(name="tone", description="Tom do post", default="técnico")
        
        template = FlowTemplate(
            name="test_template",
            domain="test",
            description="Test template",
            variables=[topic_var, tone_var],
            steps=[]
        )
        
        prompt = template.get_variables_prompt()
        expected = "Variáveis: topic (Assunto do post), tone (Tom do post)"
        assert prompt == expected

    def test_flow_template_get_variables_prompt_empty(self):
        """Testa string quando não há variáveis."""
        template = FlowTemplate(
            name="test_template",
            domain="test",
            description="Test template",
            variables=[],
            steps=[]
        )
        
        prompt = template.get_variables_prompt()
        assert prompt == "Nenhuma variável."

    def test_flow_template_to_dict(self):
        """Testa serialização correta."""
        topic_var = FlowTemplateVar(name="topic", description="Assunto", default="tech")
        template = FlowTemplate(
            name="blog_template",
            domain="blog",
            description="Template para posts",
            variables=[topic_var],
            steps=[
                {"name": "step1", "agent": "writer", "task": "Write about {topic}"}
            ],
            tags=["blog"],
            version="1.0.0"
        )
        
        data = template.to_dict()
        
        assert data["name"] == "blog_template"
        assert data["domain"] == "blog"
        assert data["description"] == "Template para posts"
        assert len(data["variables"]) == 1
        assert data["variables"][0]["name"] == "topic"
        assert len(data["steps"]) == 1
        assert data["tags"] == ["blog"]
        assert data["version"] == "1.0.0"

    def test_flow_template_from_dict(self):
        """Testa desserialização round-trip."""
        data = {
            "name": "blog_template",
            "domain": "blog",
            "description": "Template para posts",
            "version": "1.0.0",
            "tags": ["blog", "writing"],
            "variables": [
                {"name": "topic", "description": "Assunto", "default": "tech"}
            ],
            "steps": [
                {"name": "step1", "agent": "writer", "task": "Write about {topic}"}
            ]
        }
        
        template = FlowTemplate.from_dict(data)
        
        assert template.name == "blog_template"
        assert template.domain == "blog"
        assert template.description == "Template para posts"
        assert template.version == "1.0.0"
        assert len(template.variables) == 1
        assert template.variables[0].name == "topic"
        assert len(template.steps) == 1
        assert template.steps[0]["task"] == "Write about {topic}"


class TestFlowTemplateRegistry:
    def test_template_registry_singleton(self):
        """Testa singleton - mesma instância."""
        reg1 = get_template_registry()
        reg2 = get_template_registry()
        
        assert reg1 is reg2

    def test_template_registry_register_and_get(self):
        """Testa registrar e recuperar por nome."""
        registry = FlowTemplateRegistry()
        var = FlowTemplateVar(name="topic", description="Assunto", default="tech")
        template = FlowTemplate(
            name="test_template",
            domain="test",
            description="Test template",
            variables=[var],
            steps=[]
        )
        
        registry.register(template)
        retrieved = registry.get("test_template")
        
        assert retrieved is not None
        assert retrieved.name == "test_template"
        assert retrieved.domain == "test"

    def test_template_registry_list_by_domain(self):
        """Testa filtrar por domínio."""
        registry = FlowTemplateRegistry()
        
        var1 = FlowTemplateVar(name="topic", description="Assunto", default="tech")
        template1 = FlowTemplate(
            name="template1",
            domain="blog",
            description="Blog template",
            variables=[var1],
            steps=[]
        )
        
        var2 = FlowTemplateVar(name="sport", description="Esporte", default="football")
        template2 = FlowTemplate(
            name="template2",
            domain="sports",
            description="Sports template",
            variables=[var2],
            steps=[]
        )
        
        registry.register(template1)
        registry.register(template2)
        
        blog_templates = registry.list_by_domain("blog")
        sports_templates = registry.list_by_domain("sports")
        
        assert len(blog_templates) == 1
        assert blog_templates[0].name == "template1"
        
        assert len(sports_templates) == 1
        assert sports_templates[0].name == "template2"

    def test_template_registry_discover(self):
        """Testa discover() carrega flow_templates/*.json."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a temporary template file
            template_data = {
                "name": "discovered_template",
                "domain": "test",
                "description": "Discovered template",
                "version": "1.0.0",
                "tags": ["test"],
                "variables": [
                    {"name": "param", "description": "Test param", "default": "default"}
                ],
                "steps": [
                    {"name": "step1", "agent": "test_agent", "task": "Do {param}"}
                ]
            }
            
            template_file = os.path.join(temp_dir, "discovered_template.json")
            with open(template_file, "w") as f:
                json.dump(template_data, f)
            
            registry = FlowTemplateRegistry()
            count = registry.discover(temp_dir)
            
            assert count == 1
            template = registry.get("discovered_template")
            assert template is not None
            assert template.name == "discovered_template"
            assert template.domain == "test"

    def test_template_registry_list_templates(self):
        """Testa list_templates retorna todos."""
        registry = FlowTemplateRegistry()
        
        var = FlowTemplateVar(name="topic", description="Assunto", default="tech")
        template1 = FlowTemplate(
            name="template1",
            domain="blog",
            description="Blog template",
            variables=[var],
            steps=[]
        )
        
        template2 = FlowTemplate(
            name="template2",
            domain="sports",
            description="Sports template",
            variables=[var],
            steps=[]
        )
        
        registry.register(template1)
        registry.register(template2)
        
        all_templates = registry.list_templates()
        
        assert len(all_templates) == 2
        names = {t.name for t in all_templates}
        assert "template1" in names
        assert "template2" in names


class TestFlowTemplateCommands:
    @pytest.mark.asyncio
    async def test_flow_new_command_registered(self):
        """Testa se /flow-new está no CommandRegistry."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        match = orch.registry.resolve("/flow-new blog topic=test")
        assert match is not None, "Comando /flow-new não encontrado"
        entry, remainder = match
        assert remainder == "blog topic=test"

    @pytest.mark.asyncio
    async def test_flow_templates_command_registered(self):
        """Testa se /flow-templates está no CommandRegistry."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        match = orch.registry.resolve("/flow-templates blog")
        assert match is not None, "Comando /flow-templates não encontrado"
        entry, remainder = match
        assert remainder == "blog"

    @pytest.mark.asyncio
    async def test_flow_new_command_no_args(self):
        """Testa /flow-new sem argumentos retorna erro com templates disponíveis."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        # First, add a mock template for testing
        var = FlowTemplateVar(name="topic", description="Assunto", default="tech")
        template = FlowTemplate(
            name="blog",
            domain="blog",
            description="Blog template",
            variables=[var],
            steps=[
                {"name": "step1", "agent": "writer", "task": "Write about {topic}"}
            ]
        )
        orch.template_registry.register(template)
        
        match = orch.registry.resolve("/flow-new")
        assert match is not None
        entry, remainder = match
        result = await entry.handler(remainder, {})
        
        assert "Uso:" in result
        assert "blog" in result

    @pytest.mark.asyncio
    async def test_flow_new_command_unknown_template(self):
        """Testa /flow-new com template desconhecido."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        match = orch.registry.resolve("/flow-new nonexistent")
        assert match is not None
        entry, remainder = match
        result = await entry.handler(remainder, {})
        
        assert "não encontrado" in result
        assert "Disponíveis:" in result

    @pytest.mark.asyncio
    async def test_flow_new_command_with_vars(self):
        """Testa /flow-new com variáveis instancia e executa com mock."""
        from core.orchestrator import Orchestrator
        from core.moon_flow import FlowResult
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        # Add a mock template
        topic_var = FlowTemplateVar(name="topic", description="Assunto", default="default_topic")
        template = FlowTemplate(
            name="blog",
            domain="blog",
            description="Blog template",
            variables=[topic_var],
            steps=[
                {"name": "step1", "agent": "writer", "task": "Write about {topic}"}
            ]
        )
        orch.template_registry.register(template)
        
        # Mock the flow execution
        original_instantiate = template.instantiate
        template.instantiate = lambda values: original_instantiate(values)
        
        # Since we can't fully execute without external dependencies,
        # we'll test the instantiation part
        match = orch.registry.resolve("/flow-new blog topic=Python")
        assert match is not None
        entry, remainder = match
        
        # Mock the flow execute method to avoid actual execution
        from unittest.mock import patch
        with patch('core.moon_flow.MoonFlow.execute') as mock_execute:
            mock_result = Mock()
            mock_result.success = True
            mock_result.run_id = "test-run-id"
            mock_result.total_time = 1.0
            mock_result.error = None
            mock_execute.return_value = mock_result
            
            result = await entry.handler(remainder, {})
            
            assert "executado com sucesso" in result
            assert "test-run-id" in result