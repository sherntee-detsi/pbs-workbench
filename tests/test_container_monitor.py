import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job import container, monitor, workbench


class ContainerMonitorTests(unittest.TestCase):
    def test_running_instance_requires_matching_ready_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = str(Path(directory, "workbenches", "00"))
            job_id = "123[4].server"
            name = container.instance_name(job_id)
            self.assertEqual(name, "pbs-workbench-123_4_.server")
            self.assertIsNone(workbench.running_container_instance(marker, job_id))
            ready = Path(workbench.container_ready_dir(marker), name)
            ready.parent.mkdir(parents=True)
            ready.write_text("different job\n")
            self.assertIsNone(workbench.running_container_instance(marker, job_id))
            ready.write_text(f"{job_id}\n")
            self.assertEqual(workbench.running_container_instance(marker, job_id), name)

    def test_monitor_displays_shell_only_for_ready_running_container(self):
        info = {
            "used": {"walltime": 60, "memory": 1024**3, "cpu": 0},
            "requested": {"walltime": 3600, "memory": 8 * 1024**3},
            "job_id": "123[4].server",
            "profile": "test",
            "state": "R",
            "hostname": "compute-42",
            "comment": "",
            "su": None,
        }
        name = container.instance_name(info["job_id"])
        with patch.dict("os.environ", {"USER": "alice"}):
            without_container = b"\n".join(monitor.build_ui(info).render((180, 40)).text)
            with_container = b"\n".join(monitor.build_ui(info, name).render((180, 40)).text)
            info["state"] = "Q"
            queued = b"\n".join(monitor.build_ui(info, name).render((180, 40)).text)
        self.assertNotIn(b"Container shell:", without_container)
        self.assertNotIn(b"Container shell:", queued)
        self.assertIn(b"Container shell:", with_container)
        self.assertIn(
            b"ssh -t alice@compute-42 'module load apptainer && apptainer shell "
            b"instance://pbs-workbench-123_4_.server'",
            with_container,
        )
