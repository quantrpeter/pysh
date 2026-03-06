"""
Job control for pysh.

Tracks background processes and provides fg/bg/jobs functionality.
"""

import os
import sys
import signal
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Job:
    num: int
    pid: int
    description: str
    running: bool = True


class JobManager:
    def __init__(self):
        self._jobs: Dict[int, Job] = {}
        self._next_num = 1

    @property
    def last_job_num(self) -> int:
        return self._next_num - 1

    def add_job(self, pid: int, description: str) -> Job:
        job = Job(num=self._next_num, pid=pid, description=description)
        self._jobs[self._next_num] = job
        self._next_num += 1
        return job

    def reap(self):
        """Check for finished background jobs and report them."""
        to_remove = []
        for num, job in self._jobs.items():
            try:
                pid, status = os.waitpid(job.pid, os.WNOHANG)
                if pid != 0:
                    if os.WIFEXITED(status):
                        code = os.WEXITSTATUS(status)
                        state = "Done" if code == 0 else f"Exit {code}"
                    elif os.WIFSIGNALED(status):
                        state = f"Killed by signal {os.WTERMSIG(status)}"
                    else:
                        state = "Done"
                    print(f"[{num}]  {state}\t\t{job.description}")
                    to_remove.append(num)
            except ChildProcessError:
                to_remove.append(num)

        for num in to_remove:
            del self._jobs[num]

    def list_jobs(self) -> list:
        self.reap()
        result = []
        for num in sorted(self._jobs.keys()):
            job = self._jobs[num]
            state = "Running" if job.running else "Stopped"
            result.append((num, state, job.pid, job.description))
        return result

    def get_job(self, spec: Optional[str] = None) -> Optional[Job]:
        """Get a job by spec (%N, %%, or None for most recent)."""
        if not self._jobs:
            return None
        if spec is None or spec in ('%%', '%+', '%'):
            return self._jobs.get(max(self._jobs.keys()))
        if spec.startswith('%') and spec[1:].isdigit():
            return self._jobs.get(int(spec[1:]))
        return None

    def remove_job(self, num: int):
        self._jobs.pop(num, None)

    def foreground(self, job: Job) -> int:
        """Bring a job to the foreground and wait for it."""
        try:
            os.kill(job.pid, signal.SIGCONT)
        except ProcessLookupError:
            self.remove_job(job.num)
            return 1

        job.running = True
        try:
            _, status = os.waitpid(job.pid, 0)
            self.remove_job(job.num)
            if os.WIFEXITED(status):
                return os.WEXITSTATUS(status)
            if os.WIFSIGNALED(status):
                return 128 + os.WTERMSIG(status)
            return 1
        except ChildProcessError:
            self.remove_job(job.num)
            return 0

    def background(self, job: Job):
        """Resume a stopped job in the background."""
        try:
            os.kill(job.pid, signal.SIGCONT)
            job.running = True
            print(f"[{job.num}] {job.pid}")
        except ProcessLookupError:
            self.remove_job(job.num)
