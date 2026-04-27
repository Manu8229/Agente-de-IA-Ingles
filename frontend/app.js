const state = {
  recorder: null,
  stream: null,
  chunks: [],
  mode: "general",
  busy: false,
  lessonStarted: false,
  recordingStartedAt: 0,
  recorderSupported: true,
};

const chat = document.querySelector("#chat");
const statusText = document.querySelector("#status");
const startLessonButton = document.querySelector("#startLessonButton");
const recordButton = document.querySelector("#recordButton");
const recordLabel = document.querySelector("#recordLabel");
const userIdInput = document.querySelector("#userId");
const phraseCount = document.querySelector("#phraseCount");
const correctionCount = document.querySelector("#correctionCount");
const repeatList = document.querySelector("#repeatList");
const learnedList = document.querySelector("#learnedList");

document.querySelectorAll(".mode-button").forEach((button) => {
  button.addEventListener("click", () => {
    if (state.busy) return;
    state.mode = button.dataset.mode;
    document.querySelectorAll(".mode-button").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
  });
});

startLessonButton.addEventListener("click", async () => {
  if (state.busy) return;
  await startLesson();
});

recordButton.addEventListener("click", async () => {
  if (state.busy) return;

  if (isRecording()) {
    stopRecording();
    return;
  }

  await startRecording();
});

userIdInput.addEventListener("change", () => {
  fetchProgress();
});

fetchProgress();
checkRecorderSupport();

async function startLesson() {
  state.busy = true;
  setStatus("Starting");
  setControlsDisabled(true);

  const formData = new FormData();
  formData.append("user_id", currentUserId());
  formData.append("mode", state.mode);

  try {
    const response = await fetch("/api/audio/start", {
      method: "POST",
      body: formData,
    });

    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(payload.detail || "Could not start lesson");
    }

    state.lessonStarted = true;
    renderLessonStart(payload);
    setStatus(payload.warnings?.[0] || "Ready", Boolean(payload.warnings?.length));
  } catch (error) {
    setStatus(error.message || "Could not start lesson", true);
  } finally {
    state.busy = false;
    setControlsDisabled(false);
  }
}

async function startRecording() {
  try {
    ensureRecorderSupport();
    window.speechSynthesis?.cancel();
    setStatus("Allow microphone");

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    const mimeType = getSupportedMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);

    state.stream = stream;
    state.recorder = recorder;
    state.chunks = [];
    state.recordingStartedAt = Date.now();

    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) {
        state.chunks.push(event.data);
      }
    });

    recorder.addEventListener("error", () => {
      cleanupRecorder();
      updateRecordingState(false);
      setStatus("Recorder error. Try again.", true);
    });

    recorder.addEventListener("stop", () => {
      const type = recorder.mimeType || "audio/webm";
      const blob = new Blob(state.chunks, { type });
      cleanupRecorder();
      updateRecordingState(false);

      if (!blob.size) {
        setStatus("No audio captured. Try again.", true);
        return;
      }

      submitAudio(blob);
    });

    recorder.start();
    updateRecordingState(true);
  } catch (error) {
    cleanupRecorder();
    updateRecordingState(false);
    setStatus(readMicrophoneError(error), true);
  }
}

function stopRecording() {
  const recorder = state.recorder;
  if (!recorder || recorder.state !== "recording") return;

  if (Date.now() - state.recordingStartedAt < 500) {
    setStatus("Speak for a moment, then stop.");
    return;
  }

  recorder.stop();
}

async function submitAudio(blob) {
  state.busy = true;
  setStatus("Processing");
  setControlsDisabled(true);

  const formData = new FormData();
  formData.append("audio", blob, `speech-${Date.now()}${fileExtension(blob.type)}`);
  formData.append("user_id", currentUserId());
  formData.append("mode", state.mode);

  try {
    const response = await fetch("/api/audio/conversation", {
      method: "POST",
      body: formData,
    });

    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(payload.detail || "Request failed");
    }

    renderTurn(payload);
    await fetchProgress();
    setStatus(payload.warnings?.[0] || "Ready", Boolean(payload.warnings?.length));
  } catch (error) {
    setStatus(error.message || "Could not process audio", true);
  } finally {
    state.busy = false;
    setControlsDisabled(false);
  }
}

function renderLessonStart(payload) {
  const wrapper = document.createElement("article");
  wrapper.className = "message assistant";

  const response = document.createElement("p");
  response.textContent = payload.message;
  wrapper.append(response);
  appendTranslation(wrapper, payload.translation?.response_pt);

  if (payload.repeat?.length) {
    const repeat = document.createElement("div");
    repeat.className = "chips";
    payload.repeat.forEach((word) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = word;
      repeat.append(chip);
    });
    wrapper.append(repeat);
  }

  appendAudio(wrapper, payload);
  chat.append(wrapper);
  chat.scrollTop = chat.scrollHeight;
}

function renderTurn(payload) {
  addMessage("user", payload.transcript);

  const wrapper = document.createElement("article");
  wrapper.className = "message assistant";

  const response = document.createElement("p");
  response.textContent = payload.correction.response;
  wrapper.append(response);
  appendTranslation(wrapper, payload.correction.translation?.response_pt);

  if (hasCorrection(payload.correction)) {
    const correction = document.createElement("div");
    correction.className = "correction";

    const label = document.createElement("span");
    label.textContent = "Correct";

    const corrected = document.createElement("strong");
    corrected.textContent = payload.correction.corrected;

    const explanation = document.createElement("small");
    explanation.textContent = payload.correction.explanation;

    correction.append(label, corrected, explanation);
    appendTranslation(correction, payload.correction.translation?.corrected_pt);
    wrapper.append(correction);
  }

  if (payload.correction.repeat?.length) {
    const repeat = document.createElement("div");
    repeat.className = "chips";
    payload.correction.repeat.forEach((word) => {
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = word;
      repeat.append(chip);
    });
    wrapper.append(repeat);
  }

  appendAudio(wrapper, payload);

  chat.append(wrapper);
  chat.scrollTop = chat.scrollHeight;
}

function appendAudio(wrapper, payload) {
  if (payload.audio_base64) {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = audioUrl(payload.audio_base64, payload.audio_mime_type || "audio/mpeg");
    wrapper.append(audio);
    audio.play().catch(() => {
      speakLocally(payload.spoken_text);
    });
    return;
  }

  speakLocally(payload.spoken_text);
}

function appendTranslation(container, text) {
  if (!text) return;

  const translation = document.createElement("small");
  translation.className = "translation";
  translation.textContent = `PT: ${text}`;
  container.append(translation);
}

function addMessage(role, text) {
  const message = document.createElement("article");
  message.className = `message ${role}`;
  const paragraph = document.createElement("p");
  paragraph.textContent = text;
  message.append(paragraph);
  chat.append(message);
  chat.scrollTop = chat.scrollHeight;
}

async function fetchProgress() {
  try {
    const response = await fetch(`/api/audio/progress/${encodeURIComponent(currentUserId())}`);
    if (!response.ok) return;

    const progress = await response.json();
    phraseCount.textContent = progress.stats.phrases;
    correctionCount.textContent = progress.stats.corrections;
    renderWords(repeatList, progress.struggle_words, "mistake_count");
    renderWords(learnedList, progress.learned_words, "uses_count");
  } catch {
    // Progress is secondary to the voice flow.
  }
}

function renderWords(container, words, countKey) {
  container.replaceChildren();

  if (!words.length) {
    const empty = document.createElement("span");
    empty.className = "empty";
    empty.textContent = "No data yet";
    container.append(empty);
    return;
  }

  words.forEach((item) => {
    const chip = document.createElement("span");
    chip.className = "word-pill";
    chip.textContent = `${item.word} ${item[countKey]}`;
    container.append(chip);
  });
}

function hasCorrection(correction) {
  return correction.original.trim().toLowerCase() !== correction.corrected.trim().toLowerCase();
}

function updateRecordingState(isRecording) {
  recordButton.classList.toggle("recording", isRecording);
  recordButton.setAttribute("aria-pressed", String(isRecording));
  recordLabel.textContent = isRecording ? "Stop" : "Record";
  setStatus(isRecording ? "Listening" : "Processing");
}

function setStatus(text, isError = false) {
  statusText.textContent = text;
  statusText.classList.toggle("error", isError);
}

function setControlsDisabled(disabled) {
  startLessonButton.disabled = disabled;
  recordButton.disabled = disabled || !state.recorderSupported;
}

function checkRecorderSupport() {
  try {
    ensureRecorderSupport();
    state.recorderSupported = true;
    recordButton.disabled = false;
  } catch (error) {
    state.recorderSupported = false;
    recordButton.disabled = true;
    setStatus(readMicrophoneError(error), true);
  }
}

function cleanupRecorder() {
  if (state.stream) {
    state.stream.getTracks().forEach((track) => track.stop());
  }

  state.stream = null;
  state.recorder = null;
  state.chunks = [];
  state.recordingStartedAt = 0;
}

function ensureRecorderSupport() {
  if (!window.isSecureContext) {
    throw new Error("Open with http://127.0.0.1:8000 or HTTPS to use the microphone.");
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("This browser does not allow microphone capture here.");
  }

  if (!window.MediaRecorder) {
    throw new Error("This browser does not support audio recording.");
  }
}

function isRecording() {
  return state.recorder?.state === "recording";
}

function readMicrophoneError(error) {
  if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
    return "Microphone blocked. Allow microphone access in the browser.";
  }

  if (error?.name === "NotFoundError") {
    return "No microphone found.";
  }

  if (error?.name === "NotReadableError") {
    return "Microphone is already in use by another app.";
  }

  return error?.message || "Microphone unavailable.";
}

function currentUserId() {
  return userIdInput.value.trim() || "default";
}

function getSupportedMimeType() {
  const options = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/wav",
  ];
  return options.find((type) => MediaRecorder.isTypeSupported(type)) || "";
}

function fileExtension(type) {
  if (type.includes("mp4")) return ".mp4";
  if (type.includes("wav")) return ".wav";
  return ".webm";
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function audioUrl(base64, mimeType) {
  const bytes = atob(base64);
  const buffer = new Uint8Array(bytes.length);
  for (let index = 0; index < bytes.length; index += 1) {
    buffer[index] = bytes.charCodeAt(index);
  }
  return URL.createObjectURL(new Blob([buffer], { type: mimeType }));
}

function speakLocally(text) {
  if (!text || !("speechSynthesis" in window)) return;

  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";
  utterance.rate = 0.82;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}
