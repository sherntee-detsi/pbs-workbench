import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import urwid

from job import profile_editor, workbench


class ProfileProjectTests(unittest.TestCase):
    def tearDown(self):
        importlib.reload(profile_editor)

    def editor_for_project(self, project, config=None):
        env = os.environ.copy()
        if project is None:
            env.pop("PROJECT", None)
        else:
            env["PROJECT"] = project
        with patch.dict(os.environ, env, clear=True):
            importlib.reload(profile_editor)
            return profile_editor.ProfileEditor(
                config if config is not None else profile_editor.DEFAULT_CONFIG,
                ["normal"],
            )

    def save_profile(self, editor, directory):
        with patch("job.places.profile_folder", return_value=directory):
            with self.assertRaises(urwid.ExitMainLoop):
                editor.save(force=True)
        return Path(directory, "default.json")

    def test_missing_or_empty_project_omits_project_and_storage_directives(self):
        for project in (None, ""):
            with self.subTest(project=project), tempfile.TemporaryDirectory() as directory:
                editor = self.editor_for_project(project)
                self.assertIsNone(editor.project)
                self.assertNotIn(b"Project:", b"\n".join(editor.ui.render((100, 25)).text))
                profile = self.save_profile(editor, directory)
                config = json.loads(profile.read_text())
                self.assertNotIn("project", config)
                self.assertNotIn("storage", config["resources"])
                with patch("job.places.logs_folder", return_value=directory):
                    script = Path(workbench.jobscript_from_json(str(profile), "workbench"))
                self.addCleanup(script.unlink, missing_ok=True)
                self.assertNotIn("#PBS -P", script.read_text())
                self.assertNotIn("#PBS -l storage=", script.read_text())

    def test_project_field_and_directive_when_set(self):
        with tempfile.TemporaryDirectory() as directory:
            editor = self.editor_for_project("abc123")
            self.assertIn(b"Project:", b"\n".join(editor.ui.render((100, 25)).text))
            profile = self.save_profile(editor, directory)
            config = json.loads(profile.read_text())
            self.assertEqual(config["project"], "abc123")
            self.assertEqual(config["resources"]["storage"], ["scratch/abc123", "gdata/abc123"])
            with patch("job.places.logs_folder", return_value=directory):
                script = Path(workbench.jobscript_from_json(str(profile), "workbench"))
            self.addCleanup(script.unlink, missing_ok=True)
            self.assertIn("#PBS -P abc123", script.read_text())

    def test_hidden_existing_project_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            editor = self.editor_for_project(None, {"name": "default", "project": "existing"})
            profile = self.save_profile(editor, directory)
            self.assertEqual(json.loads(profile.read_text())["project"], "existing")

    def test_clearing_visible_project_omits_it(self):
        with tempfile.TemporaryDirectory() as directory:
            editor = self.editor_for_project("abc123")
            editor.project.set_edit_text("")
            profile = self.save_profile(editor, directory)
            self.assertNotIn("project", json.loads(profile.read_text()))
