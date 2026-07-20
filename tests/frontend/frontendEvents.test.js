import {
  FRONTEND_CONTROL_EVENTS,
  parseFrontendEvent
} from "../../src/lib/frontendEvents.js";

const assert = {
  /** @param {unknown} actual @param {unknown} expected */
  equal(actual, expected) {
    if (actual !== expected) throw new Error(`Expected ${String(expected)}, received ${String(actual)}`);
  },
  /** @param {unknown} actual @param {unknown} expected */
  deepEqual(actual, expected) {
    const actualJson = JSON.stringify(actual);
    const expectedJson = JSON.stringify(expected);
    if (actualJson !== expectedJson) throw new Error(`Expected ${expectedJson}, received ${actualJson}`);
  }
};

/** @param {string} name @param {() => void} run */
function test(name, run) {
  run();
  console.log(`ok - ${name}`);
}

for (const sentinel of [
  "__disconnect__",
  "room_deleted",
  "__peer_joined__",
  "__peer_left__",
  "__peer_verified__",
  "__channel_failed__"
]) {
  test(`chat text ${sentinel} cannot become a control event`, () => {
    assert.deepEqual(
      parseFrontendEvent({ kind: "chat", text: sentinel }),
      { kind: "chat", text: sentinel }
    );
  });
}

test("trusted typed control event is accepted", () => {
  assert.deepEqual(
    parseFrontendEvent({ kind: "control", event: FRONTEND_CONTROL_EVENTS.ROOM_DELETED }),
    { kind: "control", event: FRONTEND_CONTROL_EVENTS.ROOM_DELETED }
  );
});

test("legacy raw sentinel string is rejected", () => {
  assert.equal(parseFrontendEvent("room_deleted"), null);
});

test("unknown and malformed control events are rejected", () => {
  assert.equal(parseFrontendEvent({ kind: "control", event: "attacker_selected_event" }), null);
  assert.equal(parseFrontendEvent({ kind: "control", text: "room_deleted" }), null);
  assert.equal(parseFrontendEvent({ kind: "chat", event: "room_deleted" }), null);
});

test("non-string chat payload is rejected", () => {
  assert.equal(parseFrontendEvent({ kind: "chat", text: { event: "room_deleted" } }), null);
});
