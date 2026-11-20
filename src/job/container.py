import shlex
import re


def instance_name(job_id: str) -> str:
    return "pbs-workbench-" + re.sub(r"[^a-zA-Z0-9._-]", "_", job_id)


def parse_flags(flags: str) -> list[str]:
    return shlex.split(flags)


def command_preview(image: str, flags: str, ssh: bool = False) -> str:
    try:
        rendered_flags = shlex.join(parse_flags(flags)) if flags.strip() else "$FLAGS"
    except ValueError:
        rendered_flags = flags
    rendered_image = shlex.quote(image.strip()) if image.strip() else "$IMAGE"
    home_bind = ' --bind "$HOME:$HOME"' if ssh else ""
    return f'apptainer instance start {rendered_flags}{home_bind} {rendered_image} "$INSTANCE_NAME"'
