import assert from "node:assert/strict";
import test from "node:test";
import { AuthController } from "../dist/assets/auth-controller.js";

function fakeElement(overrides = {}) {
  return {
    hidden: false,
    textContent: "",
    value: "",
    disabled: false,
    addEventListener() {},
    replaceChildren() {},
    append() {},
    focus() {},
    ...overrides,
  };
}

function authElements() {
  return {
    gate: fakeElement({ hidden: true }),
    form: fakeElement(),
    title: fakeElement({ textContent: "Create bridge PIN" }),
    explanation: fakeElement(),
    pin: fakeElement(),
    confirmRow: fakeElement({ hidden: false }),
    confirmPin: fakeElement(),
    duration: fakeElement({ value: "1-hour" }),
    customRow: fakeElement({ hidden: true }),
    customValue: fakeElement({ value: "10" }),
    customUnit: fakeElement({ value: "minutes" }),
    label: fakeElement(),
    error: fakeElement(),
    submit: fakeElement({ textContent: "Create PIN and unlock" }),
    securityCard: fakeElement({ hidden: false }),
    sessionSummary: fakeElement(),
    sessionList: fakeElement(),
    refreshSessions: fakeElement(),
    logout: fakeElement(),
    currentPin: fakeElement(),
    newPin: fakeElement(),
    confirmNewPin: fakeElement(),
    changePin: fakeElement(),
    revokeAllPin: fakeElement(),
    revokeAll: fakeElement(),
    securityStatus: fakeElement(),
  };
}

async function flushAsyncListener() {
  await new Promise((resolve) => setImmediate(resolve));
}

test("auth-required reopens the configured unlock form and preserves typed PIN on duplicate 401s", async (t) => {
  const bus = new EventTarget();
  const previousAdd = globalThis.addEventListener;
  const previousRemove = globalThis.removeEventListener;
  const previousDispatch = globalThis.dispatchEvent;
  globalThis.addEventListener = bus.addEventListener.bind(bus);
  globalThis.removeEventListener = bus.removeEventListener.bind(bus);
  globalThis.dispatchEvent = bus.dispatchEvent.bind(bus);
  t.after(() => {
    if (previousAdd === undefined) delete globalThis.addEventListener;
    else globalThis.addEventListener = previousAdd;
    if (previousRemove === undefined) delete globalThis.removeEventListener;
    else globalThis.removeEventListener = previousRemove;
    if (previousDispatch === undefined) delete globalThis.dispatchEvent;
    else globalThis.dispatchEvent = previousDispatch;
  });

  let statusCalls = 0;
  const api = {
    async authStatus() {
      statusCalls += 1;
      return {
        configured: true,
        authenticated: false,
        trustModel: "pc-local",
        phoneAuthoritative: false,
        csrfToken: null,
        currentSession: null,
        durationChoices: ["1-hour"],
        customDuration: { minimumSeconds: 300, maximumSeconds: 315360000 },
        networkAccess: { mode: "local-only", secure: false, url: "http://127.0.0.1:8765" },
      };
    },
  };
  const elements = authElements();
  new AuthController(elements, api);

  bus.dispatchEvent(new Event("droidwebdisplay-auth-required"));
  await flushAsyncListener();

  assert.equal(statusCalls, 1);
  assert.equal(elements.gate.hidden, false);
  assert.equal(elements.title.textContent, "Unlock DroidWebDisplay");
  assert.equal(elements.confirmRow.hidden, true);
  assert.equal(elements.submit.textContent, "Unlock");
  assert.equal(elements.securityStatus.textContent, "Session expired or revoked. Authenticate again.");

  elements.pin.value = "123456";
  bus.dispatchEvent(new Event("droidwebdisplay-auth-required"));
  await flushAsyncListener();

  assert.equal(statusCalls, 1, "duplicate auth-required events must not re-render an already-open gate");
  assert.equal(elements.pin.value, "123456", "a duplicate 401 must not clear the PIN while the user is typing");
});
