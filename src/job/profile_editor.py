import json
import urwid as uw
import os

from job import places as ps


PALETTE = [
    ("label", "light gray", "default"),
    ("queue focus", "black", "light gray"),
]
PROJECT = os.environ.get("PROJECT", "")

DEFAULT_CONFIG = {
    "name": "default",
    "resources": {
        "ncpus": "8",
        "mem": "32GB",
        "walltime": "8:00:00",
        "jobfs": "",
        "storage": [],
    },
}

if PROJECT:
    DEFAULT_CONFIG["project"] = PROJECT

def WithLabel(label, widget):
    return (uw.Text(("label", label + " ")), widget)


def Table(rows_data):
    """
    Build a centred progress bar table.

    Args:
        rows_data: list of (uw.Text(), widget) tuples

    Returns:
        A uw.Padding widget containing a uw.Pile of uw.Columns rows
    """
    LABEL_WIDTH = max(len(r[0].text) for r in rows_data)

    rows = []
    for label, widget in rows_data:
        rows.append(
            uw.Columns(
                [
                    ("fixed", LABEL_WIDTH, label),
                    widget,
                ]
            )
        )

    return uw.Padding(uw.Pile(rows), align="right", left=1)


class QueueSelector(uw.WidgetWrap):
    def __init__(self, options, default=None):
        self.options = options
        self.index = options.index(default) if default in options else 0
        self.text = uw.Text("")
        super().__init__(uw.AttrMap(self.text, None, "queue focus"))
        self.update_text()

    def selectable(self):
        return True

    def update_text(self):
        self.text.set_text(f"< {self.get_value()} >  (left/right)")

    def keypress(self, size, key):
        if key in ("left", "right"):
            self.index = (self.index + (1 if key == "right" else -1)) % len(self.options)
            self.update_text()
            return None
        return key

    def get_value(self):
        return self.options[self.index]


class EditEnter(uw.Edit):
    def keypress(self, size, key):
        if key == "enter":
            self.edit_pos = 0
            return "down"
        if key == "down":
            self.edit_pos = 0
        if key == "up":
            self.edit_pos = 0
        return super().keypress(size, key)


class TabbedPile(uw.Pile):
    def keypress(self, size, key):
        if key == "tab":
            # If we are at the end (buttons) go to the first
            # If we are not, then go to the end.
            if self.focus_position == len(self.contents) - 1:
                self.focus_position = 3  # first one.
            else:
                self.focus_position = (
                    len(self.contents) - 1
                )  # jump to last widget (buttons)
            return

        return super().keypress(size, key)


class ProfileEditor:
    def __init__(self, config: dict, queues: list[str]):
        self.exit_message = None
        self.advanced = False
        resources = config.get("resources", DEFAULT_CONFIG["resources"])
        self.saved_project = config.get("project")

        self.name = EditEnter("", config.get("name", ""))
        self.project = EditEnter("", config.get("project", PROJECT)) if PROJECT else None
        self.ncpus = EditEnter(
            "", resources.get("ncpus", DEFAULT_CONFIG["resources"]["ncpus"])
        )
        self.walltime = EditEnter(
            "", resources.get("walltime", DEFAULT_CONFIG["resources"]["walltime"])
        )
        self.mem = EditEnter(
            "", resources.get("mem", DEFAULT_CONFIG["resources"]["mem"])
        )
        self.jobfs = EditEnter(
            "", resources.get("jobfs", DEFAULT_CONFIG["resources"]["jobfs"])
        )
        self.storage = EditEnter(
            "",
            "+".join(resources.get("storage", DEFAULT_CONFIG["resources"]["storage"])),
        )

        saved_queue = config.get("queue")
        missing_queue = saved_queue and saved_queue not in queues
        queue_options = [*queues, saved_queue] if missing_queue else queues
        self.queue = QueueSelector(options=queue_options, default=saved_queue)
        queue_widgets = [self.queue]
        if missing_queue:
            queue_widgets.append(uw.Text("Saved queue is not currently reported by PBS."))
        self.queue_column = uw.Pile(queue_widgets)

        btn_save = uw.Button("Save")
        self.btn_advanced = uw.Button("Advanced", on_press=self.toggle_advanced)
        btn_quit = uw.Button("Quit")
        uw.connect_signal(btn_save, "click", lambda _: self.save())
        uw.connect_signal(btn_quit, "click", lambda _: self.quit())

        buttons = uw.Padding(
            uw.Columns(
                [("pack", btn_save), ("pack", self.btn_advanced), ("pack", btn_quit)],
                dividechars=4,
            ),
            left=2,
        )

        div = uw.Divider("─")
        header = [div, uw.Text("PBS Workbench Profile Editor", align="center"), div]

        self.body = Table(self.profile_rows())

        ui = []
        ui.extend(header)
        ui.append(self.body)
        ui.append(div)
        ui.append(buttons)

        self.ui = uw.Filler(TabbedPile(ui), "top")
        self.loop = uw.MainLoop(self.ui, palette=PALETTE)

    def profile_rows(self):
        rows = [
            WithLabel("Name:", self.name),
            WithLabel("Queue:", self.queue_column),
        ]
        if self.project is not None:
            rows.append(WithLabel("Project:", self.project))
        rows.extend([
            WithLabel("CPUs:", self.ncpus),
            WithLabel("RAM:", self.mem),
            WithLabel("Walltime:", self.walltime),
        ])
        if self.advanced:
            rows.extend([
                WithLabel("Jobfs:", self.jobfs),
                WithLabel("Storage:", self.storage),
            ])
        return rows

    def toggle_advanced(self, button):
        self.advanced = not self.advanced
        button.set_label("Hide advanced" if self.advanced else "Advanced")
        self.body.original_widget = Table(self.profile_rows()).original_widget

    def save(self, force=False):
        filename = self.name.get_edit_text() + ".json"
        path = f"{ps.profile_folder()}/{filename}"

        if not force:
            if os.path.exists(path):
                # This might be the most horrible thing I've done in recent memory
                dialogue = uw.LineBox(
                    uw.Filler(
                        uw.Padding(
                            uw.Pile(
                                [
                                    uw.Text(
                                        f"Profile {self.name.get_edit_text()} already exist"
                                    ),
                                    uw.Columns(
                                        [
                                            (
                                                "pack",
                                                uw.Button(
                                                    "Back",
                                                    on_press=lambda _: setattr(
                                                        self.loop, "widget", self.ui
                                                    ),
                                                ),
                                            ),
                                            (
                                                "pack",
                                                uw.Button(
                                                    "Save anyway",
                                                    on_press=lambda _: (
                                                        setattr(
                                                            self.loop, "widget", self.ui
                                                        ),
                                                        self.save(force=True),
                                                    ),
                                                ),
                                            ),
                                        ],
                                        dividechars=2,
                                    ),
                                ]
                            ),
                            align="center",
                        )
                    )
                )
                overlay = uw.Overlay(
                    dialogue,
                    self.ui,
                    align="center",
                    width=("relative", 80),
                    valign="middle",
                    height=10,
                )
                self.loop.widget = overlay
                return

        config = {
            "name": self.name.get_edit_text(),
            "queue": self.queue.get_value(),
            "resources": {
                "ncpus": self.ncpus.get_edit_text(),
                "mem": self.mem.get_edit_text(),
                "walltime": self.walltime.get_edit_text(),
            },
        }
        project = self.project.get_edit_text() if self.project is not None else self.saved_project
        if project:
            config["project"] = project
        jobfs = self.jobfs.get_edit_text().strip()
        if jobfs:
            config["resources"]["jobfs"] = jobfs
        storage = self.storage.get_edit_text().strip()
        if storage:
            config["resources"]["storage"] = storage.split("+")

        with open(path, "w") as f:
            f.writelines(json.dumps(config, indent = 4))
        
        self.quit("Profile saved")
        

    def quit(self, message = None):
        self.exit_message = message
        raise uw.ExitMainLoop()
        
    def run(self):
        self.loop.run()
        if self.exit_message:
            print(self.exit_message)
