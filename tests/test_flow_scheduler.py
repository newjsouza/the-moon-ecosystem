"""tests/test_flow_scheduler.py — Testes do sistema de agendamento de flows"""

import asyncio
import tempfile
import json
import time
from unittest.mock import AsyncMock, Mock
from core.flow_scheduler import ScheduledJob, FlowScheduler, get_flow_scheduler


class TestScheduledJob:
    def test_scheduled_job_creation(self):
        """Testa campos obrigatórios e defaults."""
        job = ScheduledJob(
            job_id="test-job",
            flow_name="test-flow",
            job_type="flow",
            context={"key": "value"},
            schedule_type="daily",
            time_of_day="07:30",
            enabled=True,
            created_at=time.time()
        )
        
        assert job.job_id == "test-job"
        assert job.flow_name == "test-flow"
        assert job.job_type == "flow"
        assert job.context == {"key": "value"}
        assert job.schedule_type == "daily"
        assert job.time_of_day == "07:30"
        assert job.enabled is True

    def test_compute_next_run_daily(self):
        """Testa '07:30' → timestamp do próximo 07:30."""
        job = ScheduledJob(
            job_id="test-job",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="daily",
            time_of_day="07:30",
            enabled=True,
            created_at=time.time()
        )
        
        next_run = job.compute_next_run()
        assert isinstance(next_run, float)
        assert next_run > time.time()

    def test_compute_next_run_interval(self):
        """Testa every=60 → time.time() + 3600."""
        job = ScheduledJob(
            job_id="test-job",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="interval",
            interval_minutes=60,
            enabled=True,
            created_at=time.time()
        )
        
        next_run = job.compute_next_run()
        expected = time.time() + (60 * 60)  # 60 minutes in seconds
        # Allow for a small time difference
        assert abs(next_run - expected) < 5

    def test_compute_next_run_once(self):
        """Testa run_at fixo → sem recalcular."""
        fixed_time = time.time() + 100
        job = ScheduledJob(
            job_id="test-job",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="once",
            run_at=fixed_time,
            enabled=True,
            created_at=time.time()
        )
        
        next_run = job.compute_next_run()
        assert next_run == fixed_time

    def test_is_due_true(self):
        """Testa next_run_at no passado → is_due()=True."""
        past_time = time.time() - 100  # 100 seconds ago
        job = ScheduledJob(
            job_id="test-job",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="once",
            run_at=past_time,
            next_run_at=past_time,  # Set next_run_at to the past time
            enabled=True,
            created_at=time.time()
        )
        
        assert job.is_due() is True

    def test_is_due_false(self):
        """Testa next_run_at no futuro → is_due()=False."""
        future_time = time.time() + 100  # 100 seconds in future
        job = ScheduledJob(
            job_id="test-job",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="once",
            run_at=future_time,
            next_run_at=future_time,  # Set next_run_at to the future time
            enabled=True,
            created_at=time.time()
        )
        
        assert job.is_due() is False

    def test_is_due_disabled(self):
        """Testa enabled=False → is_due()=False."""
        past_time = time.time() - 100  # In the past
        job = ScheduledJob(
            job_id="test-job",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="once",
            run_at=past_time,
            next_run_at=past_time,  # Set next_run_at to the past time
            enabled=False,  # But disabled
            created_at=time.time()
        )
        
        assert job.is_due() is False


class TestFlowScheduler:
    def test_scheduler_singleton(self):
        """Testa singleton - mesma instância."""
        sched1 = get_flow_scheduler()
        sched2 = get_flow_scheduler()
        
        assert sched1 is sched2

    def test_scheduler_add_job(self):
        """Testa add_job retorna job_id."""
        scheduler = FlowScheduler()
        job = ScheduledJob(
            job_id="test-job",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="daily",
            time_of_day="07:30",
            enabled=True,
            created_at=time.time()
        )
        
        job_id = scheduler.add_job(job)
        assert job_id == "test-job"

    def test_scheduler_remove_job(self):
        """Testa remove por job_id."""
        scheduler = FlowScheduler()
        job = ScheduledJob(
            job_id="test-job",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="daily",
            time_of_day="07:30",
            enabled=True,
            created_at=time.time()
        )
        
        scheduler.add_job(job)
        removed = scheduler.remove_job("test-job")
        
        assert removed is True
        assert scheduler.get_job("test-job") is None

    def test_scheduler_enable_disable(self):
        """Testa enable/disable alteram enabled."""
        scheduler = FlowScheduler()
        job = ScheduledJob(
            job_id="test-job",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="once",
            run_at=time.time() + 1000,
            enabled=True,
            created_at=time.time()
        )
        
        scheduler.add_job(job)
        
        # Initially enabled
        assert scheduler.get_job("test-job").enabled is True
        
        # Disable
        scheduler.disable_job("test-job")
        assert scheduler.get_job("test-job").enabled is False
        
        # Enable
        scheduler.enable_job("test-job")
        assert scheduler.get_job("test-job").enabled is True

    def test_scheduler_list_jobs_all(self):
        """Testa lista todos."""
        scheduler = FlowScheduler()
        job1 = ScheduledJob(
            job_id="test-job-1",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="daily",
            time_of_day="07:30",
            enabled=True,
            created_at=time.time()
        )
        job2 = ScheduledJob(
            job_id="test-job-2",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="daily",
            time_of_day="08:00",
            enabled=False,
            created_at=time.time()
        )
        
        scheduler.add_job(job1)
        scheduler.add_job(job2)
        
        all_jobs = scheduler.list_jobs()
        assert len(all_jobs) == 2
        job_ids = {job.job_id for job in all_jobs}
        assert "test-job-1" in job_ids
        assert "test-job-2" in job_ids

    def test_scheduler_list_jobs_enabled_only(self):
        """Testa filtra por enabled=True."""
        scheduler = FlowScheduler()
        job1 = ScheduledJob(
            job_id="test-job-1",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="daily",
            time_of_day="07:30",
            enabled=True,
            created_at=time.time()
        )
        job2 = ScheduledJob(
            job_id="test-job-2",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="daily",
            time_of_day="08:00",
            enabled=False,
            created_at=time.time()
        )
        
        scheduler.add_job(job1)
        scheduler.add_job(job2)
        
        enabled_jobs = scheduler.list_jobs(enabled_only=True)
        assert len(enabled_jobs) == 1
        assert enabled_jobs[0].job_id == "test-job-1"

    def test_scheduler_get_stats(self):
        """Testa stats retorna totais."""
        scheduler = FlowScheduler()
        job1 = ScheduledJob(
            job_id="test-job-1",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="daily",
            time_of_day="07:30",
            enabled=True,
            created_at=time.time()
        )
        job2 = ScheduledJob(
            job_id="test-job-2",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="daily",
            time_of_day="08:00",
            enabled=False,
            created_at=time.time()
        )
        
        scheduler.add_job(job1)
        scheduler.add_job(job2)
        
        stats = scheduler.get_stats()
        assert stats["total_jobs"] == 2
        assert stats["enabled_jobs"] == 1
        assert stats["disabled_jobs"] == 1
        assert stats["total_runs"] == 0

    def test_scheduler_load_from_file(self):
        """Testa carrega config/scheduled_jobs.json."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            data = {
                "jobs": [
                    {
                        "job_id": "loaded-job",
                        "flow_name": "test-flow",
                        "job_type": "flow",
                        "context": {},
                        "schedule_type": "daily",
                        "time_of_day": "07:30",
                        "enabled": True,
                        "created_at": time.time()
                    }
                ]
            }
            json.dump(data, f)
            temp_file = f.name
        
        scheduler = FlowScheduler()
        count = scheduler.load_from_file(temp_file)
        
        assert count == 1
        jobs = scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].job_id == "loaded-job"

    def test_scheduler_save_and_reload(self):
        """Testa salvar e recarregar round-trip (tmp)."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_file = f.name
        
        scheduler = FlowScheduler()
        job = ScheduledJob(
            job_id="test-job",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="daily",
            time_of_day="07:30",
            enabled=True,
            created_at=time.time()
        )
        
        scheduler.add_job(job)
        scheduler.save_to_file(temp_file)
        
        # Create new scheduler and load
        new_scheduler = FlowScheduler()
        count = new_scheduler.load_from_file(temp_file)
        
        assert count == 1
        jobs = new_scheduler.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].job_id == "test-job"

    def test_tick_runs_due_jobs(self):
        """Testa _tick executa jobs devidos."""
        scheduler = FlowScheduler()
        
        # Create a mock orchestrator
        mock_orchestrator = Mock()
        mock_flow = Mock()
        mock_flow.execute = AsyncMock()
        mock_result = Mock()
        mock_result.run_id = "test-run-id"
        mock_flow.execute.return_value = mock_result
        
        mock_orchestrator.flow_registry.get.return_value = mock_flow
        scheduler.set_orchestrator(mock_orchestrator)
        
        # Add a job that's due
        job = ScheduledJob(
            job_id="due-job",
            flow_name="test-flow",
            job_type="flow",
            context={},
            schedule_type="once",
            run_at=time.time() - 10,  # Due now
            enabled=True,
            created_at=time.time()
        )
        scheduler.add_job(job)
        
        # Run tick
        # Since _tick is async, we need to create a mock event loop
        import asyncio
        async def run_tick():
            await scheduler._tick()
            return True
        
        # Execute the async tick function
        asyncio.run(run_tick())
        
        # Check that execute was called
        assert mock_flow.execute.called


class TestOrchestratorIntegration:
    def test_flow_schedule_command_registered(self):
        """Testa /flow-schedule no CommandRegistry."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        match = orch.registry.resolve("/flow-schedule apex_pipeline 07:30")
        assert match is not None, "Comando /flow-schedule não encontrado"
        entry, remainder = match
        assert remainder == "apex_pipeline 07:30"

    def test_flow_jobs_command_registered(self):
        """Testa /flow-jobs no CommandRegistry."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        match = orch.registry.resolve("/flow-jobs")
        assert match is not None, "Comando /flow-jobs não encontrado"
        entry, remainder = match
        assert remainder == ""

    def test_flow_unschedule_command_registered(self):
        """Testa /flow-unschedule no CommandRegistry."""
        from core.orchestrator import Orchestrator
        
        orch = Orchestrator()
        orch._register_builtin_commands()
        
        match = orch.registry.resolve("/flow-unschedule test-job")
        assert match is not None, "Comando /flow-unschedule não encontrado"
        entry, remainder = match
        assert remainder == "test-job"