import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import urwid

from job import profile_editor, workbench


class AdvancedProfileTests(unittest.TestCase):
    def save_and_script(self, editor, directory):
        with patch("job.places.profile_folder", return_value=directory):
            with self.assertRaises(urwid.ExitMainLoop):
                editor.save(force=True)
        profile = Path(directory, "default.json")
        with patch("job.places.logs_folder", return_value=directory):
            script = Path(workbench.jobscript_from_json(str(profile), "workbench"))
        self.addCleanup(script.unlink, missing_ok=True)
        return json.loads(profile.read_text()), script.read_text()

    def test_arrow_navigation_and_advanced_tab(self):
        editor = profile_editor.ProfileEditor({"name": "default"}, ["batch", "gpu"])
        size = (100, 25)
        editor.ui.render(size, focus=True)
        editor.ui.keypress(size, "down")
        editor.ui.keypress(size, "right")
        self.assertEqual(editor.queue.get_value(), "gpu")
        editor.ui.keypress(size, "down")
        editor.ui.keypress(size, "left")
        self.assertEqual(editor.queue.get_value(), "gpu")
        editor.ui.keypress(size, "up")
        editor.ui.keypress(size, "left")
        self.assertEqual(editor.queue.get_value(), "batch")

        lines = editor.ui.render(size).text
        canvas = b"\n".join(lines)
        self.assertNotIn(b"Jobfs:", canvas)
        self.assertNotIn(b"Storage:", canvas)
        self.assertLess(canvas.index(b"Job *"), canvas.index(b"Advanced"))
        self.assertLess(canvas.index(b"Advanced"), canvas.index(b"Container"))
        tab_row = next(i for i, line in enumerate(lines) if b"Job *" in line)
        self.assertEqual(lines[tab_row + 1].strip(), b"")
        self.assertIn(b"Name:", lines[tab_row + 2])

        editor.ui.keypress(size, "up")
        editor.ui.keypress(size, "up")
        editor.ui.keypress(size, "right")
        editor.ui.keypress(size, "enter")
        self.assertEqual(editor.current_tab, "advanced")
        canvas = b"\n".join(editor.ui.render(size).text)
        self.assertIn(b"Jobfs:", canvas)
        self.assertIn(b"Storage:", canvas)
        editor.jobfs.set_edit_text("25GB")
        editor.storage.set_edit_text("scratch/project")
        editor.ui.keypress(size, "left")
        editor.ui.keypress(size, "enter")
        self.assertEqual(editor.current_tab, "job")
        self.assertNotIn(b"Jobfs:", b"\n".join(editor.ui.render(size).text))
        self.assertEqual(editor.jobfs.get_edit_text(), "25GB")
        self.assertEqual(editor.storage.get_edit_text(), "scratch/project")

    def test_empty_advanced_fields_are_omitted_from_pbs(self):
        editor = profile_editor.ProfileEditor(profile_editor.DEFAULT_CONFIG, ["batch"])
        self.assertEqual(editor.jobfs.get_edit_text(), "")
        self.assertEqual(editor.storage.get_edit_text(), "")
        with tempfile.TemporaryDirectory() as directory:
            config, script = self.save_and_script(editor, directory)
        self.assertNotIn("jobfs", config["resources"])
        self.assertNotIn("storage", config["resources"])
        self.assertNotIn("#PBS -l jobfs=", script)
        self.assertNotIn("#PBS -l storage=", script)

    def test_existing_hidden_values_are_saved_and_can_be_cleared(self):
        config = {
            "name": "default",
            "resources": {"jobfs": "25GB", "storage": ["scratch/project", "gdata/project"]},
        }
        editor = profile_editor.ProfileEditor(config, ["batch"])
        with tempfile.TemporaryDirectory() as directory:
            saved, script = self.save_and_script(editor, directory)
        self.assertEqual(saved["resources"]["jobfs"], "25GB")
        self.assertEqual(saved["resources"]["storage"], ["scratch/project", "gdata/project"])
        self.assertIn("#PBS -l jobfs=25GB", script)
        self.assertIn("#PBS -l storage=scratch/project+gdata/project", script)

        editor.jobfs.set_edit_text("")
        editor.storage.set_edit_text("")
        with tempfile.TemporaryDirectory() as directory:
            saved, script = self.save_and_script(editor, directory)
        self.assertNotIn("jobfs", saved["resources"])
        self.assertNotIn("storage", saved["resources"])
        self.assertNotIn("#PBS -l jobfs=", script)
        self.assertNotIn("#PBS -l storage=", script)
