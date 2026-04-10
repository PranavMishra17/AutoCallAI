# AutoCallAI – Session Debug Log
_ElevenLabs voice connection diagnosis · 2026-04-10_

---

## Executive Summary

We have been chasing the wrong bug. **The widget approach (shadow DOM click) is fundamentally unpredictable** because we're reverse-engineering undocumented internals. The correct fix is to use the **`@elevenlabs/client` SDK directly** — installed via npm and served locally — bypassing all CDN, version-resolution, and Shadow DOM issues.

---

## Root Cause Analysis

### What worked originally
The bare-bones widget embed from DESIGN.md:
```html
<elevenlabs-convai agent-id="..."></elevenlabs-convai>
<script src="https://unpkg.com/@elevenlabs/convai-widget-embed" async></script>
```
User clicks the widget's floating orb → conversation starts. **This still works.**

### What we tried to do
Replace the widget's built-in orb with our own custom UI (blob animation, transcript panel, confirmation cards). This required *programmatically* starting/stopping the conversation and hooking into transcript events.

### Where each approach broke

| # | Approach | Failure | Why |
|---|----------|---------|-----|
| 1 | `import("esm.sh/@elevenlabs/client@1.0.2")` | 404 | Version 1.0.2 doesn't exist (jumped from 0.1.x to 0.2.0) |
| 2 | `import("esm.sh/@elevenlabs/client@1.2.0")` | livekit `/rtc/v1` 404 | SDK 1.2.0 uses `livekit-client ^2.11.4` which negotiates `/rtc/v1` — ElevenLabs server may or may not support it on the given day |
| 3 | Widget + `widget.startConversation()` | `not a function` | The `<elevenlabs-convai>` element doesn't expose `startConversation` on its prototype — only lifecycle callbacks |
| 4 | Widget + `visibility:hidden` + shadow button click | `shadowRoot` null | `visibility:hidden` / `display:none` prevents Shadow DOM from rendering in some browsers |
| 5 | Widget + off-screen positioning + shadow button click | Button found, clicked, stuck at "Connecting…" | `btn.click()` dispatches a synthetic event with `isTrusted=false`. The widget's internal React/Preact handler may use `pointerdown`/`mousedown` instead of `click`, OR it checks `isTrusted`. Either way, `getUserMedia()` (mic access) requires a trusted user gesture — programmatic `.click()` doesn't reliably propagate this. |
| 6 | Widget + synchronous `.click()` in user gesture chain | Same — stuck at "Connecting…" | Even synchronous `.click()` from within `onclick` sets `isTrusted=false` on the dispatched event. Chrome's gesture propagation through shadow DOM boundaries is implementation-specific and not guaranteed. |

### The fundamental problem
**You cannot reliably programmatically click a button inside a third-party Shadow DOM and expect browser-gated APIs (microphone) to work.** The browser's trusted-event model doesn't follow programmatic `.click()` chains across shadow boundaries.

---

## The Fix: Use the SDK directly, served locally

### Key discovery from npm registry
The `@elevenlabs/client` package follows a clear structure:

- **Versions 0.1.x**: No `livekit-client` dependency (bundled internally via microbundle)
- **Versions 0.2.0+**: Explicit `livekit-client: "^2.11.4"` dependency
- **Latest stable**: `0.16.0` (tagged `latest`), dependency: `livekit-client ^2.11.4`
- **Version 1.2.0**: Tagged `next` (pre-release), same dependency

The npm package exports a pre-built UMD at `dist/lib.umd.js` and ESM at `dist/lib.modern.js`. We can serve these directly from our Python server — **no CDN needed**.

The SDK provides `Conversation.startSession()` with full callbacks:
```js
const conversation = await Conversation.startSession({
  agentId: "agent_...",
  onConnect: ({ conversationId }) => { ... },
  onDisconnect: () => { ... },
  onMessage: (message) => { ... },
  onError: (error) => { ... },
});
```

This is **exactly** the API we need for custom UI. No widget, no shadow DOM, no button clicking.

### Plan / Execution

1. **`npm install @elevenlabs/client@0.16.0`** (latest stable, not the `next` 1.x)
2. **Copy `node_modules/@elevenlabs/client/dist/*`** to `web/vendor/`
3. **Add an `importmap`** to provide bare-module resolution for the modern ES build:
   ```html
   <script type="importmap">
     {
       "imports": {
         "livekit-client": "https://esm.sh/livekit-client@2.11.4",
         "@elevenlabs/types": "https://esm.sh/@elevenlabs/types"
       }
     }
   </script>
   ```
4. **Load the modern build dynamically**:
   ```javascript
   import("/vendor/lib.modern.js").then(mod => { ... })
   ```
5. **Call `Conversation.startSession()`** directly within the original synchronous `handleCallToggle` function.
6. **Removed** the `<elevenlabs-convai>` element and widget embed scripts completely.

### Why this works (Final Validation)
- **Trusted User Gesture**: Because `startSession` is called within the synchronous execution of an `onclick` handler, Chrome grants microphone permissions naturally.
- **No Shadow DOM**: We aren't fighting event propagation across shadow boundaries via programmatic `.click()` methods.
- **Client Tools Hooked IN**: The SDK allows passing our existing `show_confirmation` local function right into `clientTools` mapped from the LLM webhook.
- **Import Maps**: Because modern browser ES module loading (`import()`) does not know how to resolve Node.js style bare specifiers like `"livekit-client"`, the `<script type="importmap">` bridges that gap securely while letting the local `/vendor/lib.modern.js` drive the ElevenLabs specific logic.

---

## Problem History (for reference)

| # | Problem | Status |
|---|---------|--------|
| 1 | `@elevenlabs/client@1.0.2` 404 on esm.sh | Resolved (version doesn't exist) |
| 2 | livekit `/rtc/v1` path not supported | Bypassed (use modern ES bundle over UMD) |
| 3 | `startConversation` not a function on widget | Explained (not exposed on prototype) |
| 4 | `visibility:hidden` suppresses Shadow DOM | Explained (browser rendering optimization) |
| 5 | Shadow button click doesn't trigger mic permission | Explained (isTrusted=false) |
| 6 | UI stuck at "Connecting…" after synchronous click | Explained (gesture not propagated across shadow boundary) |
| 7 | **Connection via local SDK** | ✅ **Resolved** (Implemented successfully) |
