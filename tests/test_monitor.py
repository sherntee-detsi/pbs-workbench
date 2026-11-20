import io
import unittest
from unittest.mock import patch

import urwid
from typer.testing import CliRunner

from job import cli, monitor


HINT = (
    "Run 'job monitor' to monitor, 'job end' to stop the job, or "
    "'job ssh-config' for details on SSHing into the job container.\n"
)


def job_info(state):
    return {
        "used": {"walltime": 60, "memory": 1024**3, "cpu": 0},
        "requested": {"walltime": 3600, "memory": 8 * 1024**3},
        "job_id": "123.server",
        "profile": "test",
        "state": state,
        "hostname": "compute-42",
        "comment": "waiting",
        "su": None,
    }


class MonitorTests(unittest.TestCase):
    def test_background_button_is_visible_and_activated_by_enter(self):
        for state in ("Q", "R"):
            with self.subTest(state=state), patch.dict("os.environ", {"USER": "alice"}):
                ui = monitor.build_ui(
                    job_info(state), "pbs-workbench-123.server", {"port": 23456}
                )
                canvas = b"\n".join(ui.render((80, 24), focus=True).text)
                self.assertIn(b"Leave Running In Background", canvas)
                with self.assertRaises(urwid.ExitMainLoop):
                    ui.keypress((80, 24), "enter")

    def test_start_and_monitor_leave_job_running_and_print_hint(self):
        def press_button(loop):
            try:
                loop.widget.keypress((80, 24), "enter")
            except urwid.ExitMainLoop:
                pass

        for command, current in (("start", None), ("monitor", ["/tmp/00"])):
            with self.subTest(command=command), patch(
                "job.workbench.workbench_current", return_value=current
            ), patch("job.workbench.workbench_start", return_value="/tmp/00"), patch(
                "job.workbench.get_job_id", return_value="123.server"
            ), patch("job.pbsqueue.info", return_value=job_info("Q")), patch(
                "job.workbench.workbench_stop"
            ) as stop, patch("job.pbsqueue.delete") as delete, patch(
                "urwid.MainLoop.run", press_button
            ), patch.dict("os.environ", {"USER": "alice"}):
                result = CliRunner().invoke(cli.app, [command])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(result.stderr, HINT)
                self.assertEqual(result.stdout, "123.server\n")
                stop.assert_not_called()
                delete.assert_not_called()

    def test_control_c_prints_hint(self):
        with patch("job.workbench.get_job_id", return_value="123.server"), patch(
            "job.pbsqueue.info", return_value=job_info("Q")
        ), patch("urwid.MainLoop.run", side_effect=KeyboardInterrupt), patch(
            "sys.stderr", new_callable=io.StringIO
        ) as stderr, patch.dict("os.environ", {"USER": "alice"}):
            monitor.monitor("/tmp/00")
        self.assertEqual(stderr.getvalue(), HINT)

    def test_stop_alias_matches_end(self):
        for command in ("end", "stop"):
            for current in (None, ["/tmp/00"]):
                with self.subTest(command=command, current=current), patch(
                    "job.workbench.workbench_current", return_value=current
                ), patch("job.workbench.workbench_stop") as stop, patch(
                    "job.workbench.workbench_files_clean"
                ) as clean:
                    result = CliRunner().invoke(cli.app, [command])
                    self.assertEqual(result.exit_code, 0, result.output)
                    if current:
                        stop.assert_called_once_with("/tmp/00")
                    else:
                        stop.assert_not_called()
                        self.assertIn("No workbench", result.stdout)
                    clean.assert_called_once()
