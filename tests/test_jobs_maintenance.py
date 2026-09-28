import pytest
from src.jobs import (
    task_timeout_reconciler,
    job_data_purger,
    media_reconciler,
    validation_sweeper,
    key_maintenance,
    job_scheduler,
)


@pytest.mark.anyio
async def test_task_timeout_reconciler_execution():
    result = await task_timeout_reconciler.reconcile_timed_out_tasks(max_timeout_seconds=300)
    assert isinstance(result, dict)
    assert "timed_out_reconciled" in result
    assert result["timed_out_reconciled"] >= 0


@pytest.mark.anyio
async def test_job_data_purger_execution():
    result = await job_data_purger.purge_expired_records(retention_days=7)
    assert isinstance(result, dict)
    assert "purged_jobs" in result
    assert "purged_logs" in result


@pytest.mark.anyio
async def test_media_reconciler_execution():
    result = await media_reconciler.reconcile_media_assets()
    assert isinstance(result, dict)
    assert "reconciled_media_count" in result


@pytest.mark.anyio
async def test_validation_sweeper_execution():
    result = await validation_sweeper.sweep_stale_validations(ttl_days=14)
    assert isinstance(result, dict)
    assert "swept_validations" in result


@pytest.mark.anyio
async def test_key_maintenance_execution():
    result = await key_maintenance.audit_and_expire_keys()
    assert isinstance(result, dict)
    assert "expired_keys_count" in result


@pytest.mark.anyio
async def test_job_scheduler_lifecycle():
    # Test full maintenance cycle execution
    await job_scheduler.run_maintenance_cycle()

    # Test start and stop
    job_scheduler.start()
    assert job_scheduler._running is True
    await job_scheduler.stop()
    assert job_scheduler._running is False
