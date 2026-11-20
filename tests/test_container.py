import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import urwid

from job import profile_editor, workbench


class ContainerProfileTests(unittest.TestCase):
    def test_tab_preview_and_profile_round_trip(self):
        editor = profile_editor.ProfileEditor({"name": "default"}, ["batch"])
        size = (100, 25)
        editor.ui.render(size, focus=True)
        editor.ui.keypress(size, "up")
        editor.ui.keypress(size, "right")
        editor.ui.keypress(size, "enter")
        canvas = b"\n".join(editor.ui.render(size, focus=True).text)
        self.assertIn(b"Image:", canvas)
        self.assertIn(b"Flags:", canvas)
        self.assertIn(b"Container command:", canvas)
        self.assertIn(b'apptainer instance start $FLAGS $IMAGE "$INSTANCE_NAME"', canvas)

        editor.image.set_edit_text("docker://example/image:tag")
        editor.flags.set_edit_text('--bind "/path with spaces:/data" --nv')
        canvas = b"\n".join(editor.ui.render(size).text)
        self.assertIn(b'docker://example/image:tag', canvas)
        self.assertIn(b"'/path with spaces:/data'", canvas)
        editor.set_tab("job")
        editor.set_tab("container")
        with tempfile.TemporaryDirectory() as directory:
            with patch("job.places.profile_folder", return_value=directory):
                with self.assertRaises(urwid.ExitMainLoop):
                    editor.save(force=True)
            saved = json.loads(Path(directory, "default.json").read_text())
        self.assertEqual(saved["container"]["image"], "docker://example/image:tag")
        self.assertEqual(saved["container"]["flags"], '--bind "/path with spaces:/data" --nv')
        reopened = profile_editor.ProfileEditor(saved, ["batch"])
        self.assertEqual(reopened.image.get_edit_text(), saved["container"]["image"])
        self.assertEqual(reopened.flags.get_edit_text(), saved["container"]["flags"])

    def test_invalid_flags_are_reported_without_saving(self):
        editor = profile_editor.ProfileEditor({"name": "default"}, ["batch"])
        editor.image.set_edit_text("image.sif")
        editor.flags.set_edit_text("--bind 'unclosed")
        with tempfile.TemporaryDirectory() as directory, patch(
            "job.places.profile_folder", return_value=directory
        ):
            editor.save(force=True)
            self.assertEqual(list(Path(directory).iterdir()), [])
        self.assertEqual(editor.current_tab, "container")
        self.assertIn("Invalid flags", editor.container_error.text)


class ContainerJobTests(unittest.TestCase):
    def run_job(self, root, image, flags, fail=False, terminate=False):
        root = Path(root)
        idle = Path(workbench.__file__).parent / "data" / "idle.sh"
        action = "kill -s TERM $$" if terminate else "break"
        (root / "idle.sh").write_text(idle.read_text().replace("sleep 30", action))
        profile = root / "profile.json"
        profile.write_text(json.dumps({
            "queue": "batch",
            "container": {"image": image, "flags": flags},
        }))
        marker = root / "workbench"
        marker.touch()
        executable = root / "apptainer"
        executable.write_text(
            '#!/bin/sh\nprintf "<%s>\\n" "$@" >> "$TRACE"\n'
            + ('exit 42\n' if fail else 'exit 0\n')
        )
        executable.chmod(0o755)
        with patch("job.workbench.files", return_value=root), patch(
            "job.places.logs_folder", return_value=str(root)
        ):
            script = Path(workbench.jobscript_from_json(str(profile), str(marker)))
        self.addCleanup(script.unlink, missing_ok=True)
        env = {
            **os.environ,
            "PATH": f"{root}:{os.environ['PATH']}",
            "PBS_O_WORKDIR": str(root),
            "PBS_JOBID": "123[4].server",
            "TRACE": str(root / "trace"),
        }
        result = subprocess.run(["bash", str(script)], env=env, text=True, capture_output=True)
        trace = (root / "trace").read_text() if (root / "trace").exists() else ""
        return result, trace, marker

    def test_start_and_stop_with_safe_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            image = f"image $(touch {directory}/injected).sif"
            result, trace, marker = self.run_job(
                directory, image, '--bind "/path with spaces:/data" --nv'
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                trace.splitlines(),
                ["<instance>", "<start>", "<--bind>", "</path with spaces:/data>",
                 "<--nv>", f"<{image}>", "<pbs-workbench-123_4_.server>",
                 "<instance>", "<stop>", "<pbs-workbench-123_4_.server>"],
            )
            self.assertFalse(Path(directory, "injected").exists())
            self.assertFalse(marker.exists())

    def test_empty_image_skips_apptainer(self):
        with tempfile.TemporaryDirectory() as directory:
            result, trace, marker = self.run_job(directory, "", "--bind 'unclosed")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(trace, "")
            self.assertFalse(marker.exists())

    def test_start_failure_ends_job_without_stopping_an_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            result, trace, marker = self.run_job(directory, "image.sif", "", fail=True)
            self.assertEqual(result.returncode, 42)
            self.assertIn("<start>", trace)
            self.assertNotIn("<stop>", trace)
            self.assertFalse(marker.exists())

    def test_sigterm_stops_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            result, trace, marker = self.run_job(directory, "image.sif", "", terminate=True)
            self.assertEqual(result.returncode, 143)
            self.assertIn("<stop>", trace)
            self.assertFalse(marker.exists())
