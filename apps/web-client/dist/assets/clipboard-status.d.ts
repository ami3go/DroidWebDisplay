/** Status headlines shared between the controller and the copy write-through.
 *
 * `bindAndroidCopyWriteThrough` in main.ts has to perform
 * `navigator.clipboard.writeText` inside the click or keypress that asked for
 * the copy, because that write needs transient user activation. It therefore
 * watches the status line for the controller's reply instead of awaiting a
 * promise across the gesture boundary.
 *
 * That makes these four strings a contract between the two modules, not display
 * copy: rewording one at a call site silently stops the Copy button writing to
 * the PC clipboard, with no test failure and no console error. Change them here
 * so both sides move together.
 */
export declare const CLIPBOARD_STATUS: {
    readonly copying: "Copying";
    readonly copied: "Clipboard copied";
    readonly received: "Clipboard received";
    readonly notConfirmed: "Copy not confirmed";
};
