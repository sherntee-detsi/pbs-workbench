import shlex


def parse_flags(flags: str) -> list[str]:
    return shlex.split(flags)


def command_preview(image: str, flags: str) -> str:
    try:
        rendered_flags = shlex.join(parse_flags(flags)) if flags.strip() else "$FLAGS"
    except ValueError:
        rendered_flags = flags
    rendered_image = shlex.quote(image.strip()) if image.strip() else "$IMAGE"
    return f'apptainer instance start {rendered_flags} {rendered_image} "$INSTANCE_NAME"'
