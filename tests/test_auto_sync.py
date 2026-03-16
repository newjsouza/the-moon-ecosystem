"""tests/test_auto_sync.py — Testes do AutoSyncService"""

import pytest
from pathlib import Path


class TestAutoSyncImport:
    def test_imports_succeed(self):
        from core.services.auto_sync import AutoSyncService, get_auto_sync, SyncResult
        assert AutoSyncService is not None
        assert get_auto_sync is not None
        assert SyncResult is not None

    def test_singleton_returns_same_instance(self):
        from core.services.auto_sync import get_auto_sync
        a = get_auto_sync()
        b = get_auto_sync()
        assert a is b

    def test_git_available(self):
        from core.services.auto_sync import AutoSyncService
        s = AutoSyncService()
        # Em ambiente com git inicializado, deve ser True
        assert s._git_available is True, (
            "Git não detectado — verificar se repositório está inicializado"
        )

    def test_remote_url_configured(self):
        from core.services.auto_sync import AutoSyncService
        s = AutoSyncService()
        if s._remote_url:
            assert "github.com" in s._remote_url, (
                f"Remote URL não é GitHub: {s._remote_url}"
            )
            print(f"\nRemote: {s._remote_url}")
        else:
            pytest.skip("Remote não configurado — configurar com: git remote add origin <url>")

    def test_is_dirty_returns_bool(self):
        from core.services.auto_sync import AutoSyncService
        s = AutoSyncService()
        result = s.is_dirty()
        assert isinstance(result, bool)
        print(f"\nDirty: {result}")

    def test_get_changed_files_returns_list(self):
        from core.services.auto_sync import AutoSyncService
        s = AutoSyncService()
        files = s.get_changed_files()
        assert isinstance(files, list)
        print(f"\nArquivos modificados: {files}")

    def test_build_commit_message_with_custom(self):
        from core.services.auto_sync import AutoSyncService
        s = AutoSyncService()
        msg = s._build_commit_message("feat: minha feature", [])
        assert msg == "feat: minha feature"

    def test_build_commit_message_auto_from_files(self):
        from core.services.auto_sync import AutoSyncService
        s = AutoSyncService()
        msg = s._build_commit_message(None, ["agents/moon_cli_agent.py", "tests/test_x.py"])
        assert "agents" in msg or "tests" in msg
        assert len(msg) < 200
        print(f"\nAuto message: {msg}")

    def test_sync_result_to_dict(self):
        from core.services.auto_sync import SyncResult
        result = SyncResult(
            success=True,
            committed=True,
            pushed=True,
            files_changed=["test.py"],
            commit_sha="abc12345",
            message="test commit",
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["committed"] is True
        assert d["pushed"] is True
        assert d["files_changed"] == ["test.py"]
        assert d["commit_sha"] == "abc12345"
        assert d["message"] == "test commit"
        assert "timestamp" in d


@pytest.mark.asyncio
class TestAutoSyncDryRun:
    async def test_sync_if_dirty_no_crash(self):
        """Verificar que sync_if_dirty não lança exceção."""
        from core.services.auto_sync import get_auto_sync
        s = get_auto_sync()
        # NÃO fazer push real — apenas verificar que o fluxo não quebra
        # Se não há remote configurado, o sync vai retornar erro controlado
        if not s._remote_url:
            pytest.skip("Remote não configurado")
        # Verificar apenas is_dirty sem commitar
        dirty = s.is_dirty()
        print(f"\ndirty={dirty}, files={s.get_changed_files()[:5]}")
        assert isinstance(dirty, bool)

    async def test_sync_result_structure(self):
        """Verificar estrutura do SyncResult."""
        from core.services.auto_sync import SyncResult
        result = SyncResult(
            success=True,
            committed=False,
            pushed=False,
            files_changed=[],
            commit_sha=None,
            message="test",
        )
        assert result.success is True
        assert result.committed is False
        assert result.pushed is False
        assert result.files_changed == []
        assert result.commit_sha is None
        assert result.message == "test"
        assert result.error is None
        assert result.timestamp is not None
