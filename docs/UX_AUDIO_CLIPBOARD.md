# Audio, Clipboard, Reconnect and UX

## Optional audio

Audio is disabled by default and explicitly marked **Experimental**. Enable **Android audio** before connecting. The current browser playback implementation accepts the Opus stream and provides mute and volume controls, but interruptions and noticeable delay may occur. If Android cannot capture or encode audio, the browser reports audio as unavailable while video and control remain connected.

## Clipboard

Clipboard behavior is a protected compatibility surface. Before changing clipboard, keyboard shortcuts, browser focus/permission handling, scrcpy control messages, or scrcpy session arguments, read `docs/contracts/CLIPBOARD.md`.

- **Paste PC clipboard** reads the browser clipboard and sends it to the focused Android field.
- **Paste typed text** uses the text box when browser clipboard permission is unavailable.
- **Copy Android clipboard** requests the current Android selection and writes the returned text to the PC clipboard.
- Automatic Android -> PC synchronization relies on scrcpy native clipboard change notifications.
- Automatic PC -> Android synchronization is optional and browser-permission constrained.
- Manual Copy/Ctrl+C and automatic Android -> PC synchronization are independent requirements; fixing one must not disable the other.
- Ctrl+C works across the app except while editing a PC field or copying selected PC text.
- Automatic synchronization is constrained by the configured maximum size.

Clipboard text is not written to diagnostics.

## Reconnect

When **Auto-reconnect** is checked, the browser watches for the selected authorized USB device, connects it when it becomes available, and retries unexpected session failures with bounded attempts and increasing delays. Unchecking it leaves connection startup entirely manual. A deliberate **Disconnect** pauses automatic connection for that phone until the user presses **Connect** or unplugs and reconnects USB.

## Layout and accessibility

- `F11` toggles the Android screen stage fullscreen.
- Workspace layouts: Auto, Screen focus and Compact panels.
- Interactive controls use visible keyboard focus outlines.
- Status changes use an ARIA live region.
- The Android canvas uses a normal pointer cursor.

## Storage roots

The Explorer exposes internal shared-storage roots and dynamically detected removable SD cards. Removable cards are accepted only at Android paths matching `/storage/XXXX-XXXX`. Internal Documents is canonicalized to `/sdcard/Documents`.
