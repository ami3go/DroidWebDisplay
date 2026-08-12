export const VIRTUAL_DISPLAY_PROFILES = {
    "low-latency": {
        label: "Low Latency — Interactive",
        profileId: "low-latency",
        sizeMode: "fixed",
        width: 1280,
        height: 720,
        dpi: 220,
        startApp: "com.openai.chatgpt",
        forceStopBeforeLaunch: false,
        keepActive: true,
        systemDecorations: true,
        destroyContentOnClose: true,
        imePolicy: "local",
        preserveAspectRatio: true,
        videoCodec: "h264",
        videoBitRate: 10_000_000,
        maxFps: 60,
    },
    "chatgpt-desktop": {
        label: "ChatGPT Desktop — Recommended",
        profileId: "chatgpt-desktop",
        sizeMode: "fixed",
        width: 1600,
        height: 900,
        dpi: 240,
        startApp: "com.openai.chatgpt",
        forceStopBeforeLaunch: false,
        keepActive: true,
        systemDecorations: true,
        destroyContentOnClose: true,
        imePolicy: "local",
        preserveAspectRatio: true,
        videoCodec: "h264",
        videoBitRate: 12_000_000,
        maxFps: 60,
    },
    "full-hd-desktop": {
        label: "Full HD Desktop",
        profileId: "full-hd-desktop",
        sizeMode: "fixed",
        width: 1920,
        height: 1080,
        dpi: 240,
        startApp: "com.openai.chatgpt",
        forceStopBeforeLaunch: false,
        keepActive: true,
        systemDecorations: true,
        destroyContentOnClose: true,
        imePolicy: "local",
        preserveAspectRatio: true,
        videoCodec: "h264",
        videoBitRate: 16_000_000,
        maxFps: 60,
    },
    "low-bandwidth": {
        label: "Low Bandwidth",
        profileId: "low-bandwidth",
        sizeMode: "fixed",
        width: 1280,
        height: 720,
        dpi: 200,
        startApp: "com.openai.chatgpt",
        forceStopBeforeLaunch: false,
        keepActive: true,
        systemDecorations: true,
        destroyContentOnClose: true,
        imePolicy: "local",
        preserveAspectRatio: true,
        videoCodec: "h264",
        videoBitRate: 6_000_000,
        maxFps: 30,
    },
    "flexible-window": {
        label: "Flexible Window",
        profileId: "flexible-window",
        sizeMode: "flex",
        width: 1280,
        height: 960,
        dpi: 200,
        startApp: "com.openai.chatgpt",
        forceStopBeforeLaunch: false,
        keepActive: true,
        systemDecorations: true,
        destroyContentOnClose: true,
        imePolicy: "local",
        preserveAspectRatio: true,
        videoCodec: "h264",
        videoBitRate: 16_000_000,
        maxFps: 60,
    },
};
const PACKAGE_PATTERN = /^[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+$/;
export function validateDisplayForm(values) {
    if (values.displayMode === "physical")
        return [];
    const errors = [];
    if (!Number.isInteger(values.width) || values.width < 640 || values.width > 3840)
        errors.push("Width must be 640–3840 pixels.");
    if (!Number.isInteger(values.height) || values.height < 480 || values.height > 2160)
        errors.push("Height must be 480–2160 pixels.");
    if (!Number.isInteger(values.dpi) || values.dpi < 120 || values.dpi > 640)
        errors.push("DPI must be 120–640.");
    if (!Number.isFinite(values.videoBitRateMbps) || values.videoBitRateMbps < 2 || values.videoBitRateMbps > 50)
        errors.push("Bitrate must be 2–50 Mbps.");
    if (!Number.isInteger(values.maxFps) || values.maxFps < 15 || values.maxFps > 120)
        errors.push("Frame rate must be 15–120 fps.");
    if (values.startApp && !PACKAGE_PATTERN.test(values.startApp))
        errors.push("Application must be an exact Android package name.");
    if (!values.startApp && !values.systemDecorations)
        errors.push("Select an application when system decorations are disabled.");
    return errors;
}
export function buildSessionRequest(values, serial) {
    const errors = validateDisplayForm(values);
    if (errors.length)
        throw new Error(errors.join(" "));
    if (values.displayMode === "physical") {
        return {
            serial,
            displayMode: "physical",
            video: true,
            audio: false,
            control: true,
            videoCodec: "h264",
            maxSize: 1600,
            videoBitRate: 10_000_000,
            maxFps: 60,
        };
    }
    return {
        serial,
        displayMode: "virtual",
        video: true,
        audio: false,
        control: true,
        videoCodec: "h264",
        maxSize: 0,
        videoBitRate: Math.round(values.videoBitRateMbps * 1_000_000),
        maxFps: values.maxFps,
        virtualDisplay: {
            profileId: values.profileId,
            sizeMode: values.sizeMode,
            width: values.width,
            height: values.height,
            dpi: values.dpi,
            startApp: values.startApp,
            forceStopBeforeLaunch: values.forceStopBeforeLaunch,
            keepActive: values.keepActive,
            systemDecorations: values.systemDecorations,
            destroyContentOnClose: values.destroyContentOnClose,
            imePolicy: values.imePolicy,
            preserveAspectRatio: values.preserveAspectRatio,
        },
    };
}
export function alignedFlexSize(containerWidth, containerHeight, initialWidth, initialHeight, preserveAspectRatio) {
    let width = Math.max(640, Math.min(3840, Math.floor(containerWidth)));
    let height = Math.max(480, Math.min(2160, Math.floor(containerHeight)));
    if (preserveAspectRatio && initialWidth > 0 && initialHeight > 0) {
        const ratio = initialWidth / initialHeight;
        if (width / height > ratio)
            width = Math.floor(height * ratio);
        else
            height = Math.floor(width / ratio);
    }
    width = Math.max(640, Math.min(3840, Math.floor(width / 16) * 16));
    height = Math.max(480, Math.min(2160, Math.floor(height / 16) * 16));
    return { width, height };
}
//# sourceMappingURL=display-config.js.map