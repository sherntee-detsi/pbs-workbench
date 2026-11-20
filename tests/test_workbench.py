import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job import workbench


class WorkbenchScriptTests(unittest.TestCase):
    def test_job_uses_submission_directory_without_wd_resource(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "submission directory"
            target.mkdir()
            (root / "idle.sh").write_text("pwd\n")
            profile = root / "profile.json"
            profile.write_text(json.dumps({"queue": "batch"}))
            with patch("job.workbench.files", return_value=root), patch(
                "job.places.logs_folder", return_value=directory
            ):
                script = Path(workbench.jobscript_from_json(str(profile), "workbench"))
            self.addCleanup(script.unlink, missing_ok=True)

            self.assertNotIn("#PBS -l wd", script.read_text())
            env = {**os.environ, "PBS_O_WORKDIR": str(target)}
            result = subprocess.run(
                ["bash", str(script)], cwd=directory, env=env, text=True, capture_output=True
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(target))

            env["PBS_O_WORKDIR"] = str(root / "missing")
            result = subprocess.run(
                ["bash", str(script)], cwd=directory, env=env, text=True, capture_output=True
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")

    def test_failed_submission_removes_reserved_workbench_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile.json"
            profile.write_text(json.dumps({"queue": "batch"}))
            workbenches = root / "workbenches"
            failure = subprocess.CalledProcessError(1, ["qsub"])
            with patch("job.workbench.get_profile", return_value=str(profile)), patch(
                "job.places.workbench_dir", return_value=str(workbenches)
            ), patch("job.places.logs_folder", return_value=str(root)), patch(
                "job.workbench.jobscript_from_json", return_value="job.sh"
            ), patch("job.pbsqueue.submit", side_effect=failure):
                with self.assertRaises(subprocess.CalledProcessError):
                    workbench.workbench_start("default")
            self.assertEqual(list(workbenches.iterdir()), [])
