import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner
import urwid

from job import cli, monitor, pbsqueue, profile_editor, workbench


class QueueTests(unittest.TestCase):
    @patch("job.pbsqueue.subprocess.check_output")
    def test_reads_and_sorts_pbs_queues(self, check_output):
        check_output.return_value = json.dumps({
            "Queue": {"gpu": {"queue_type": "Execution"}, "batch": {}}
        })

        self.assertEqual(pbsqueue.list_queues(), ["batch", "gpu"])
        check_output.assert_called_once_with(
            ["qstat", "-Q", "-f", "-F", "json"],
            text=True,
            stderr=subprocess.PIPE,
            timeout=10,
        )

    @patch("job.pbsqueue.subprocess.check_output")
    def test_queue_discovery_failures(self, check_output):
        cases = [
            (FileNotFoundError(), "qstat was not found"),
            (subprocess.TimeoutExpired("qstat", 10), "qstat timed out"),
            (subprocess.CalledProcessError(1, "qstat", stderr="PBS unavailable"), "PBS unavailable"),
            ("not json", "invalid qstat JSON"),
            (json.dumps({"Queue": []}), "invalid qstat JSON"),
            (json.dumps({"Queue": {}}), "no queues were reported"),
        ]
        for result, message in cases:
            with self.subTest(message=message):
                check_output.reset_mock(side_effect=True, return_value=True)
                if isinstance(result, Exception):
                    check_output.side_effect = result
                else:
                    check_output.return_value = result
                with self.assertRaisesRegex(RuntimeError, message):
                    pbsqueue.list_queues()

    def test_profile_command_reports_queue_discovery_error(self):
        with patch("job.workbench.get_profile", return_value=None), patch(
            "job.pbsqueue.list_queues", side_effect=RuntimeError("PBS unavailable")
        ):
            result = CliRunner().invoke(cli.app, ["profile"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("PBS unavailable", result.output)

    def test_editor_uses_pbs_queues_and_browses_horizontally(self):
        queues = [f"queue{i}" for i in range(8)]
        editor = profile_editor.ProfileEditor({"name": "default"}, queues)
        self.assertEqual(editor.queue.get_value(), "queue0")
        for _ in range(6):
            editor.queue.keypress((40,), "right")
        self.assertEqual(editor.queue.get_value(), "queue6")
        editor.queue.keypress((40,), "left")
        self.assertEqual(editor.queue.get_value(), "queue5")
        editor.queue.keypress((40,), "right")
        with tempfile.TemporaryDirectory() as directory:
            with patch("job.places.profile_folder", return_value=directory):
                with self.assertRaises(urwid.ExitMainLoop):
                    editor.save(force=True)
            profile = Path(directory, "default.json")
            with patch("job.places.logs_folder", return_value=directory):
                script = Path(workbench.jobscript_from_json(str(profile), "workbench"))
            self.addCleanup(script.unlink, missing_ok=True)
            self.assertIn("#PBS -q queue6", script.read_text())

    def test_existing_queue_preserved_even_if_not_reported(self):
        editor = profile_editor.ProfileEditor(
            {"name": "default", "queue": "old-queue"}, ["batch", "gpu"]
        )
        self.assertEqual(editor.queue.get_value(), "old-queue")
        canvas = b"\n".join(editor.ui.render((100, 25)).text)
        self.assertIn(b"old-queue", canvas)
        self.assertIn(b"not currently reported", canvas)

    @patch("job.pbsqueue.subprocess.check_output")
    def test_unknown_queue_is_reported_without_usage_estimate(self, check_output):
        check_output.return_value = json.dumps({
            "Jobs": {
                "123": {
                    "Resource_List": {"walltime": "01:00:00", "mem": "8gb", "ncpus": 2},
                    "Job_Name": "test",
                    "queue": "custom",
                    "job_state": "Q",
                }
            }
        })
        info = pbsqueue.info("123")
        self.assertEqual(info["queue"], "custom")
        self.assertIsNone(info["su"])
        with patch.dict("os.environ", {"USER": "test"}):
            canvas = b"\n".join(monitor.build_ui(info).render((100, 25)).text)
        self.assertIn(b"Usage: unavailable", canvas)

    def test_known_queue_usage_is_unchanged(self):
        self.assertEqual(pbsqueue.su_compute("normal", 3600, 2, 8 * 1024**3), 4)
