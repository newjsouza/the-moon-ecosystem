"""tests/test_flow_run_store.py — Testes do armazenamento de execuções de flows"""

import tempfile
import os
import time
from unittest.mock import Mock
import pytest
from core.flow_run_store import FlowRunStore, FlowRunRecord, FlowStepRun, get_flow_run_store


class TestFlowRunStore:
    def test_flow_step_run_creation(self):
        """Testa a criação de FlowStepRun."""
        step_run = FlowStepRun(
            step_name="test_step",
            agent="test_agent",
            status="running",
            started_at=time.time()
        )
        
        assert step_run.step_name == "test_step"
        assert step_run.agent == "test_agent"
        assert step_run.status == "running"
        assert isinstance(step_run.started_at, float)

    def test_flow_run_record_creation(self):
        """Testa a criação de FlowRunRecord."""
        run_record = FlowRunRecord(
            run_id="test-run-id",
            flow_name="test_flow",
            session_id="test-session",
            status="running",
            started_at=time.time()
        )
        
        assert run_record.run_id == "test-run-id"
        assert run_record.flow_name == "test_flow"
        assert run_record.session_id == "test-session"
        assert run_record.status == "running"
        assert isinstance(run_record.started_at, float)

    def test_store_save_and_load_run(self):
        """Testa salvar e carregar um run."""
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FlowRunStore(base_dir=temp_dir)
            
            run_record = FlowRunRecord(
                run_id="test-run-id",
                flow_name="test_flow",
                session_id="test-session",
                status="running",
                started_at=time.time()
            )
            
            store.save_run(run_record)
            loaded_record = store.load_run("test-run-id")
            
            assert loaded_record is not None
            assert loaded_record.run_id == "test-run-id"
            assert loaded_record.flow_name == "test_flow"

    def test_store_list_runs(self):
        """Testa a listagem de runs."""
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FlowRunStore(base_dir=temp_dir)
            
            # Create and save multiple runs
            run1 = FlowRunRecord(
                run_id="run-1",
                flow_name="test_flow",
                session_id="session-1",
                status="running",
                started_at=time.time()
            )
            run2 = FlowRunRecord(
                run_id="run-2",
                flow_name="another_flow",
                session_id="session-2",
                status="success",
                started_at=time.time()
            )
            
            store.save_run(run1)
            store.save_run(run2)
            
            all_runs = store.list_runs()
            assert len(all_runs) == 2
            
            flow_runs = store.list_runs(flow_name="test_flow")
            assert len(flow_runs) == 1
            assert flow_runs[0].run_id == "run-1"

    def test_store_filter_by_flow_name(self):
        """Testa filtragem por nome de flow."""
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FlowRunStore(base_dir=temp_dir)
            
            run1 = FlowRunRecord(
                run_id="run-1",
                flow_name="flow_a",
                session_id="session-1",
                status="running",
                started_at=time.time()
            )
            run2 = FlowRunRecord(
                run_id="run-2",
                flow_name="flow_b",
                session_id="session-2",
                status="success",
                started_at=time.time()
            )
            
            store.save_run(run1)
            store.save_run(run2)
            
            flow_a_runs = store.list_runs(flow_name="flow_a")
            assert len(flow_a_runs) == 1
            assert flow_a_runs[0].run_id == "run-1"

    def test_store_mark_finished(self):
        """Testa marcar run como finalizado."""
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FlowRunStore(base_dir=temp_dir)
            
            run_record = FlowRunRecord(
                run_id="test-run-id",
                flow_name="test_flow",
                session_id="test-session",
                status="running",
                started_at=time.time()
            )
            
            store.save_run(run_record)
            store.mark_finished("test-run-id", "success")
            
            updated_record = store.load_run("test-run-id")
            assert updated_record is not None
            assert updated_record.status == "success"
            assert updated_record.finished_at > 0

    def test_store_update_step(self):
        """Testa atualização de step."""
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FlowRunStore(base_dir=temp_dir)
            
            run_record = FlowRunRecord(
                run_id="test-run-id",
                flow_name="test_flow",
                session_id="test-session",
                status="running",
                started_at=time.time()
            )
            
            store.save_run(run_record)
            
            step_run = FlowStepRun(
                step_name="test_step",
                agent="test_agent",
                status="success",
                started_at=time.time(),
                finished_at=time.time(),
                output_summary="test output"
            )
            
            store.update_step("test-run-id", step_run)
            
            updated_record = store.load_run("test-run-id")
            assert updated_record is not None
            assert len(updated_record.steps) == 1
            assert updated_record.steps[0].step_name == "test_step"
            assert updated_record.steps[0].status == "success"

    def test_store_stats(self):
        """Testa obtenção de estatísticas."""
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FlowRunStore(base_dir=temp_dir)
            
            run1 = FlowRunRecord(
                run_id="run-1",
                flow_name="flow_a",
                session_id="session-1",
                status="success",
                started_at=time.time()
            )
            run2 = FlowRunRecord(
                run_id="run-2",
                flow_name="flow_b",
                session_id="session-2",
                status="failed",
                started_at=time.time()
            )
            
            store.save_run(run1)
            store.save_run(run2)
            
            stats = store.get_stats()
            
            assert stats["total_runs"] == 2
            assert stats["by_status"]["success"] == 1
            assert stats["by_status"]["failed"] == 1
            assert stats["by_flow"]["flow_a"] == 1
            assert stats["by_flow"]["flow_b"] == 1

    def test_store_singleton(self):
        """Testa o padrão singleton."""
        with tempfile.TemporaryDirectory() as temp_dir:
            store1 = get_flow_run_store(base_dir=temp_dir)
            store2 = get_flow_run_store(base_dir=temp_dir)
            
            # Should be the same instance
            assert store1 is store2