# Audio, Clipboard, Reconnect and UX

## Optional audio

Audio is disabled by default and explicitly marked **Experimental**. Enable **Android audio** before connecting. The current browser playback implementation accepts the Opus stream and provides mute and volume controls, but interruptions and noticeable delay may occur. If Android cannot capture or encode audio, the browser reports audio as unavailable while video and control remain connected.

## Clipboard

- **Paste PC clipboard** reads the browser clipboard and sends it to the focused Android field.
- **Paste typed text** uses the text box when browser clipboard permission is unavailable.
- **Copy Android clipboard** writes the most recently received Android clipboard text to the PC clipboard.
- Automatic synchronization is optional and constrained by the configured maximum size.

Clipboard text is not written to diagnostics.

## Reconnect

Automatic reconnect uses bounded retry attempts and increasing delays. Manual reconnect is available when disconnected. A deliberate Disconnect cancels automatic reconnect.

## Layout and accessibility

- `F11` toggles the Android screen stage fullscreen.
- Workspace layouts: Auto, Screen focus and Compact panels.
- Interactive controls use visible keyboard focus outlines.
- Status changes use an ARIA live region.
- The Android canvas uses a normal pointer cursor.

## Storage roots

The Explorer exposes internal shared-storage roots and dynamically detected removable SD cards. Removable cards are accepted only at Android paths matching `/storage/XXXX-XXXX`. Internal Documents is canonicalized to `/sdcard/Documents`.
