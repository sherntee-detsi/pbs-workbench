import unittest
from unittest.mock import patch

from job import pbsqueue, timeout


class TimeoutTests(unittest.TestCase):
    def tearDown(self):
        timeout.set_timeout(timeout.DEFAULT_TIMEOUT)

    @patch("job.pbsqueue.subprocess.run")
    def test_pbs_commands_use_configured_timeout(self, run):
        timeout.set_timeout(2)

        pbsqueue.exists("123")

        self.assertEqual(run.call_args.kwargs["timeout"], 2)

    @patch("job.pbsqueue.subprocess.check_output")
    def test_submissions_use_configured_timeout(self, check_output):
        timeout.set_timeout(3)
        check_output.return_value = "123\n"

        with patch("job.pbsqueue.os.path.exists", return_value=True):
            self.assertEqual(pbsqueue.submit("job.sh"), "123")

        self.assertEqual(check_output.call_args.kwargs["timeout"], 3)


if __name__ == "__main__":
    unittest.main()
