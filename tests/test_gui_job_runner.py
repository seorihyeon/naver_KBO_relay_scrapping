import time
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from gui.jobs import JobResult, JobRunner


def _wait_for_job(runner: JobRunner, job_id: str, timeout: float = 2.0):
    deadline = time.time() + timeout
    snapshot = runner.get_snapshot(job_id)
    while snapshot is not None and not snapshot.is_terminal and time.time() < deadline:
        runner.poll()
        time.sleep(0.01)
        snapshot = runner.get_snapshot(job_id)
    runner.poll()
    return runner.get_snapshot(job_id)


def test_job_runner_collects_logs_progress_and_result():
    runner = JobRunner()
    observed = []

    def worker(ctx):
        ctx.log("info", "hello")
        ctx.set_progress(0.5, "halfway")
        return JobResult(summary="done", detail="worker completed")

    handle = runner.start_job(name="demo", source="test", worker=worker, listener=lambda event, snapshot: observed.append(event.kind))
    snapshot = _wait_for_job(runner, handle.job_id)

    assert snapshot is not None
    assert snapshot.status == "completed"
    assert snapshot.progress == 1.0
    assert snapshot.result is not None
    assert snapshot.result.summary == "done"
    assert snapshot.logs[0].message == "hello"
    assert "log" in observed
    assert "progress" in observed
    assert "result" in observed
    assert "completed" in observed


def test_job_runner_can_cancel_cooperative_jobs():
    runner = JobRunner()

    def worker(ctx):
        for _ in range(100):
            ctx.check_cancelled()
            time.sleep(0.01)
        return JobResult(summary="should not finish")

    handle = runner.start_job(name="cancel-demo", source="test", worker=worker)
    time.sleep(0.03)
    runner.cancel(handle.job_id)
    snapshot = _wait_for_job(runner, handle.job_id)

    assert snapshot is not None
    assert snapshot.status == "cancelled"
