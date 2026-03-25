import json
import tempfile
from pathlib import Path
import pytest
from core.skill_manifest import SkillManifest, SkillRegistry, get_skill_registry


def test_skill_manifest_creation():
    """Testa criação de SkillManifest com campos obrigatórios e defaults."""
    manifest = SkillManifest(
        name="test_skill",
        version="1.0.0",
        description="A test skill",
        domains=["test", "example"],
        commands=["cmd1", "cmd2"],
        examples=["example1", "example2"],
        fallback="alternative_skill"
    )
    
    assert manifest.name == "test_skill"
    assert manifest.version == "1.0.0"
    assert manifest.description == "A test skill"
    assert manifest.domains == ["test", "example"]
    assert manifest.commands == ["cmd1", "cmd2"]
    assert manifest.examples == ["example1", "example2"]
    assert manifest.fallback == "alternative_skill"
    assert manifest.cost == "zero"
    assert manifest.requires_key is False


def test_registry_singleton():
    """Testa que get_skill_registry retorna a mesma instância."""
    registry1 = get_skill_registry()
    registry2 = get_skill_registry()
    
    assert registry1 is registry2
    assert isinstance(registry1, SkillRegistry)
    assert isinstance(registry2, SkillRegistry)


def test_registry_register_and_get():
    """Testa registro e recuperação de manifest por nome."""
    registry = SkillRegistry()
    manifest = SkillManifest(
        name="test_skill",
        version="1.0.0",
        description="A test skill",
        domains=["test"],
        commands=["cmd1"],
        examples=["example1"]
    )
    
    registry.register(manifest)
    retrieved = registry.get("test_skill")
    
    assert retrieved is manifest
    assert retrieved.name == "test_skill"


def test_registry_list_by_domain():
    """Testa filtragem de manifests por domínio."""
    registry = SkillRegistry()
    manifest1 = SkillManifest(
        name="skill1",
        version="1.0.0",
        description="Skill for test domain",
        domains=["test", "other"],
        commands=["cmd1"],
        examples=["example1"]
    )
    manifest2 = SkillManifest(
        name="skill2",
        version="1.0.0",
        description="Skill for other domain",
        domains=["other", "different"],
        commands=["cmd2"],
        examples=["example2"]
    )
    
    registry.register(manifest1)
    registry.register(manifest2)
    
    test_skills = registry.list_by_domain("test")
    assert len(test_skills) == 1
    assert test_skills[0].name == "skill1"
    
    other_skills = registry.list_by_domain("other")
    assert len(other_skills) == 2  # Both manifests have "other" domain
    names = {skill.name for skill in other_skills}
    assert names == {"skill1", "skill2"}


def test_registry_list_all():
    """Testa listagem de todos os manifests registrados."""
    registry = SkillRegistry()
    manifest1 = SkillManifest(
        name="skill1",
        version="1.0.0",
        description="First skill",
        domains=["test"],
        commands=["cmd1"],
        examples=["example1"]
    )
    manifest2 = SkillManifest(
        name="skill2",
        version="1.0.0",
        description="Second skill",
        domains=["other"],
        commands=["cmd2"],
        examples=["example2"]
    )
    
    registry.register(manifest1)
    registry.register(manifest2)
    
    all_skills = registry.list_all()
    
    assert len(all_skills) == 2
    names = {skill.name for skill in all_skills}
    assert names == {"skill1", "skill2"}


def test_load_from_file():
    """Testa leitura de manifest de arquivo JSON."""
    # Create a temporary file with skill.json content
    temp_dir = tempfile.mkdtemp()
    skill_file = Path(temp_dir) / "skill.json"
    
    skill_data = {
        "name": "file_skill",
        "version": "2.0.0",
        "description": "Skill loaded from file",
        "domains": ["file", "load"],
        "commands": ["load_cmd"],
        "examples": ["load_example"],
        "fallback": "backup_skill",
        "cost": "zero",
        "requires_key": False
    }
    
    with open(skill_file, 'w') as f:
        json.dump(skill_data, f)
    
    registry = SkillRegistry()
    loaded_manifest = registry.load_from_file(str(skill_file))
    
    assert loaded_manifest.name == "file_skill"
    assert loaded_manifest.version == "2.0.0"
    assert loaded_manifest.description == "Skill loaded from file"
    assert loaded_manifest.domains == ["file", "load"]
    assert loaded_manifest.commands == ["load_cmd"]
    assert loaded_manifest.examples == ["load_example"]
    assert loaded_manifest.fallback == "backup_skill"
    assert loaded_manifest.cost == "zero"
    assert loaded_manifest.requires_key is False


def test_discover():
    """Testa descoberta de arquivos skill.json em um diretório."""
    # Create a temporary directory structure
    temp_base = tempfile.mkdtemp()
    skills_dir = Path(temp_base) / "skills"
    sub_dir = skills_dir / "sub"
    skills_dir.mkdir(parents=True, exist_ok=True)
    sub_dir.mkdir(parents=True, exist_ok=True)

    # Now create two files named exactly "skill.json" in different locations
    skill_json1 = skills_dir / "skill.json"
    skill_json2 = sub_dir / "skill.json"

    skill_json1_data = {
        "name": "main_skill",
        "version": "1.0.0",
        "description": "Main skill",
        "domains": ["main"],
        "commands": ["main_cmd"],
        "examples": ["main_example"]
    }

    skill_json2_data = {
        "name": "nested_skill",
        "version": "1.0.0",
        "description": "Nested skill",
        "domains": ["nested"],
        "commands": ["nested_cmd"],
        "examples": ["nested_example"]
    }

    with open(skill_json1, 'w') as f:
        json.dump(skill_json1_data, f)

    with open(skill_json2, 'w') as f:
        json.dump(skill_json2_data, f)
    
    # Test discovery from the skills directory
    registry = SkillRegistry()
    count = registry.discover(str(skills_dir))
    
    assert count == 2  # Should find the two "skill.json" files
    
    # Verify both skills were loaded
    main_skill = registry.get("main_skill")
    assert main_skill is not None
    assert main_skill.name == "main_skill"
    
    nested_skill = registry.get("nested_skill")
    assert nested_skill is not None
    assert nested_skill.name == "nested_skill"


def test_architect_skill_registry():
    """Testa que o ArchitectAgent inicializa o skill_registry corretamente."""
    from agents.architect import ArchitectAgent
    from core.message_bus import MessageBus
    
    bus = MessageBus()
    architect = ArchitectAgent(bus)
    
    # Verify that the skill registry exists and is properly initialized
    assert hasattr(architect, 'skill_registry')
    assert architect.skill_registry is not None
    assert hasattr(architect.skill_registry, 'discover')
    assert hasattr(architect.skill_registry, 'get')
    assert hasattr(architect.skill_registry, 'list_by_domain')


def test_architect_get_skills_for_domain():
    """Testa o método get_skills_for_domain do ArchitectAgent."""
    from agents.architect import ArchitectAgent
    from core.message_bus import MessageBus
    
    bus = MessageBus()
    architect = ArchitectAgent(bus)
    
    # This test verifies the method exists and can be called
    # Since we don't have specific skills in the test environment,
    # we just verify the method exists and returns a list
    result = architect.get_skills_for_domain("nonexistent_domain")
    assert isinstance(result, list)
    
    # We can also test with a temporary skill added to the registry
    temp_manifest = SkillManifest(
        name="temp_test_skill",
        version="1.0.0",
        description="Temporary test skill",
        domains=["test_domain"],
        commands=["test_cmd"],
        examples=["test_example"]
    )
    architect.skill_registry.register(temp_manifest)
    
    result = architect.get_skills_for_domain("test_domain")
    assert "temp_test_skill" in result
    assert isinstance(result, list)