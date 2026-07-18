import { readFile, writeFile } from "node:fs/promises";

const file = new URL("../src/App.svelte", import.meta.url);
let source = await readFile(file, "utf8");

function replaceExactly(label, before, after) {
  const count = source.split(before).length - 1;
  if (count !== 1) {
    throw new Error(`${label}: expected exactly one match, found ${count}`);
  }
  source = source.replace(before, after);
}

replaceExactly(
  "audio helper import",
  '  import { onMount } from "svelte";\n',
  '  import { onMount } from "svelte";\n  import { closeRetroAudio, playRetroTone } from "./lib/retroAudio.js";\n'
);

replaceExactly(
  "remote audio declarations",
  `  const RETRO_SOUND_PREF_KEY = "mutinychat-retro-sounds-enabled";\n  const USERNAME_PREF_KEY = "mutinychat-username";\n  const DING_SOUND_URL = "https://assets.mixkit.co/active_storage/sfx/933/933-preview.mp3";\n  const DOOR_SOUND_URL = "https://assets.mixkit.co/active_storage/sfx/2867/2867-preview.mp3";\n  /** @type {HTMLAudioElement | null} */\n  let dingAudio = null;\n  /** @type {HTMLAudioElement | null} */\n  let doorAudio = null;\n`,
  `  const RETRO_SOUND_PREF_KEY = "mutinychat-retro-sounds-enabled";\n  const USERNAME_PREF_KEY = "mutinychat-username";\n`
);

replaceExactly(
  "remote audio playback",
  `  /** @param {"ding" | "door"} kind */\n  function playRetroSound(kind) {\n    if (!retroSoundsEnabled || typeof window === "undefined") {\n      return;\n    }\n\n    const audio = kind === "door" ? doorAudio : dingAudio;\n    if (!audio) {\n      return;\n    }\n\n    audio.currentTime = 0;\n    void audio.play().catch(() => {\n      // Browser may block autoplay before any user interaction.\n    });\n  }\n`,
  `  /** @param {"ding" | "door"} kind */\n  function playRetroSound(kind) {\n    if (!retroSoundsEnabled || typeof window === "undefined") {\n      return;\n    }\n\n    void playRetroTone(kind).catch(() => {\n      // Audio is optional and must never interrupt chat behavior.\n    });\n  }\n`
);

replaceExactly(
  "startup audio downloads",
  `    dingAudio = new Audio(DING_SOUND_URL);\n    dingAudio.volume = 0.45;\n    doorAudio = new Audio(DOOR_SOUND_URL);\n    doorAudio.volume = 0.4;\n`,
  ""
);

replaceExactly(
  "audio teardown",
  `      dingAudio = null;\n      doorAudio = null;\n`,
  `      void closeRetroAudio().catch(() => {\n        // Audio cleanup is best-effort during component teardown.\n      });\n`
);

for (const forbidden of [
  "mixkit.co",
  "assets.mixkit.co",
  "DING_SOUND_URL",
  "DOOR_SOUND_URL",
  "new Audio("
]) {
  if (source.includes(forbidden)) {
    throw new Error(`Forbidden remote-audio reference remains: ${forbidden}`);
  }
}

await writeFile(file, source, "utf8");
console.log("Applied C1 local-audio patch to src/App.svelte");
