# Versioned WebSocket contract

All Phase 8 WebSocket endpoints require the `gpt_bridge_id` HttpOnly trusted-session cookie and a same-origin upgrade.

```text
/ws/v1/events
/ws/v1/sessions/{session_id}/video
/ws/v1/sessions/{session_id}/audio
/ws/v1/sessions/{session_id}/control
```

Authentication failures close with code `4401`. Origin rejection closes with `4403`.

The video/audio/control payload contract remains the pinned scrcpy v4.1 byte stream. Phase 8 introduces no new scrcpy control or media message.
