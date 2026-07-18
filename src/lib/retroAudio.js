/** @typedef {{ frequency: number, start: number, duration: number, volume: number, type?: OscillatorType, endFrequency?: number }} ToneOptions */

/** @type {AudioContext | null} */
let audioContext = null;

/** @returns {typeof AudioContext | null} */
function getAudioContextConstructor() {
  if (typeof window === "undefined") return null;
  return window.AudioContext || null;
}

/** @returns {Promise<AudioContext | null>} */
async function getReadyAudioContext() {
  const AudioContextConstructor = getAudioContextConstructor();
  if (!AudioContextConstructor) return null;

  if (!audioContext || audioContext.state === "closed") {
    audioContext = new AudioContextConstructor();
  }

  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }

  return audioContext;
}

/**
 * @param {AudioContext} context
 * @param {ToneOptions} options
 */
function scheduleTone(context, options) {
  const {
    frequency,
    start,
    duration,
    volume,
    type = "square",
    endFrequency = frequency
  } = options;

  const oscillator = context.createOscillator();
  const gain = context.createGain();
  const end = start + duration;

  oscillator.type = type;
  oscillator.frequency.setValueAtTime(frequency, start);
  oscillator.frequency.exponentialRampToValueAtTime(Math.max(1, endFrequency), end);

  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(volume, start + Math.min(0.012, duration / 3));
  gain.gain.exponentialRampToValueAtTime(0.0001, end);

  oscillator.connect(gain);
  gain.connect(context.destination);
  oscillator.start(start);
  oscillator.stop(end + 0.01);
}

/**
 * Plays a short sound synthesized entirely inside the local WebView.
 * No audio files are loaded and no network request is made.
 *
 * @param {"ding" | "door"} kind
 * @returns {Promise<void>}
 */
export async function playRetroTone(kind) {
  const context = await getReadyAudioContext();
  if (!context) return;

  const start = context.currentTime + 0.01;

  if (kind === "door") {
    scheduleTone(context, {
      frequency: 440,
      endFrequency: 660,
      start,
      duration: 0.1,
      volume: 0.075,
      type: "square"
    });
    scheduleTone(context, {
      frequency: 660,
      endFrequency: 880,
      start: start + 0.09,
      duration: 0.13,
      volume: 0.065,
      type: "square"
    });
    return;
  }

  scheduleTone(context, {
    frequency: 880,
    endFrequency: 1320,
    start,
    duration: 0.12,
    volume: 0.055,
    type: "sine"
  });
  scheduleTone(context, {
    frequency: 1320,
    endFrequency: 1040,
    start: start + 0.055,
    duration: 0.14,
    volume: 0.035,
    type: "sine"
  });
}

/** @returns {Promise<void>} */
export async function closeRetroAudio() {
  const context = audioContext;
  audioContext = null;
  if (context && context.state !== "closed") {
    await context.close();
  }
}
