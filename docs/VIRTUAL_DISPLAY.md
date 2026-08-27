# Virtual Secondary Display

Virtual Display mode creates a separate Android display with its own pixel dimensions and density. It does not change the physical phone screen and is not a Windows monitor.

## Profiles

| Profile | Resolution | DPI | Bitrate | FPS | Mode |
|---|---:|---:|---:|---:|---|
| ChatGPT Desktop | 1600×900 | 240 | 12 Mbps | 60 | Fixed |
| Full HD Desktop | 1920×1080 | 240 | 16 Mbps | 60 | Fixed |
| Low Bandwidth | 1280×720 | 200 | 6 Mbps | 30 | Fixed |
| Flexible Window | 1280×960 initial | 200 | 16 Mbps | 60 | Flex |

System decorations and keep-active are enabled by default. Local IME policy keeps the Android keyboard associated with the virtual display when supported by the device.

## Application selection

The browser queries launchable packages and displays the localized application labels reported by Android's PackageManager. The installed-application and running-application dropdowns share that package-to-label catalog; a readable package-derived label is used only when Android's label query is unavailable. ChatGPT uses the exact package `com.openai.chatgpt`. Manual package entry is validated and cannot contain whitespace, quotes, separators, or command fragments.

## Fixed versus flex

Fixed mode retains the requested Android resolution. Flex mode converts material browser content-size changes into bounded `RESIZE_DISPLAY` requests. One-pixel changes are ignored to prevent feedback loops.

## Cleanup

Stopping the session terminates scrcpy and releases its virtual display. `destroyContentOnClose=false` requests content preservation/migration where Android supports it; it does not keep the virtual display alive after the server exits.
