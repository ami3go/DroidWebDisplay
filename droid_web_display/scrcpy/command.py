from __future__ import annotations

import re

from droid_web_display.models import DisplayImePolicy, DisplayMode, SessionOptions

_SCID_PATTERN = re.compile(r"^[0-9a-f]{8}$")


def socket_name(scid: int) -> str:
    if scid < 0 or scid > 0x7FFFFFFF:
        raise ValueError("scid must be a 31-bit non-negative integer")
    return f"scrcpy_{scid:08x}"


def build_server_arguments(version: str, scid: int, options: SessionOptions) -> tuple[str, ...]:
    """Build the shortest v4.1-compatible server argument list.

    The native scrcpy client omits values that equal the server defaults. This is
    not merely cosmetic: some Samsung app_process builds abort with
    ``stack corruption detected (-fstack-protector)`` when supplied with an
    unnecessarily long argument vector. Keep this ordering and default
    suppression aligned with scrcpy v4.1 app/src/server.c.
    """
    options.validate()
    scid_text = f"{scid:08x}"
    if not _SCID_PATTERN.fullmatch(scid_text):
        raise ValueError("Invalid scrcpy session identifier")

    args: list[str] = [
        version,
        f"scid={scid_text}",
        f"log_level={options.log_level}",
    ]

    if not options.video:
        args.append("video=false")
    elif options.video_bit_rate:
        args.append(f"video_bit_rate={options.video_bit_rate}")

    if not options.audio:
        args.append("audio=false")
    else:
        if options.audio_codec != "opus":
            args.append(f"audio_codec={options.audio_codec}")
        if options.audio_bit_rate != 128_000 and options.audio_codec != "raw":
            args.append(f"audio_bit_rate={options.audio_bit_rate}")

    if options.video and options.video_codec != "h264":
        args.append(f"video_codec={options.video_codec}")
    if options.video and options.max_size:
        args.append(f"max_size={options.max_size}")
    if options.video and options.max_fps:
        args.append(f"max_fps={options.max_fps}")

    args.append("tunnel_forward=true")

    if options.control:
        # scrcpy suppresses the direct GetClipboard response while its native
        # clipboard listener is enabled. DroidWebDisplay needs a deterministic
        # Clipboard device message for the Copy button/Ctrl+C path, including
        # when Android's primary-clip listener does not emit a change event.
        args.append("clipboard_autosync=false")
    else:
        args.append("control=false")
    if not options.cleanup:
        args.append("cleanup=false")

    if options.display_mode == DisplayMode.VIRTUAL:
        virtual = options.virtual_display
        assert virtual is not None
        args.append(f"new_display={virtual.width}x{virtual.height}/{virtual.dpi}")
        if virtual.flex_display:
            args.append("flex_display=true")
        if virtual.ime_policy != DisplayImePolicy.DEFAULT:
            args.append(f"display_ime_policy={virtual.ime_policy.value}")
        if not virtual.destroy_content_on_close:
            args.append("vd_destroy_content=false")
        if not virtual.system_decorations:
            args.append("vd_system_decorations=false")
        if virtual.keep_active:
            args.append("keep_active=true")

    return tuple(args)
