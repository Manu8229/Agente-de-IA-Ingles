const state = {
  recorder: null,
  chunks: [],
  mode: "general",
  busy: false,
};

const chat = document.querySelector("#chat");
const statusText = document.querySelector("#status");
const recordButton = document.querySelector("#recordButton");
const recordLabel = document.querySelector("#recordLabel");
const userIdInput = document.querySelector("#userId");
const phraseCount = document.querySelector("#phraseCount");
const correctionCount = document.querySelector("#correctionCount");
const repeatList = document.querySelector("#repeatList");
const learnedList = document.querySelector("#learnedList");

document.querySelectorAll(".mode-button").forEach((button) => {
  button.addEventListener("click", () => {
    state.mode = button.dataset.mode;
    document.querySelectorAll(".mode-button").forEach((item) => {
      item.classList.toggle("active", item === button);
    });
  });
});

recordButton.addEventListener("click", async () => {
  if (state.busy) return;

  if (state.recorder && state.recorder.state === "recording") {
    state.recorder.stop();
    return;
  }

  await startRecording();
});

userIdInput.addEventListener("change", () => {
  fetchProgress();
});

fetchProgress();

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = getSupportedMimeType();
    state.recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    state.chunks = [];

    state.recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) {
        state.chunks.push(event.data);
      }
    });

    state.recorder.addEventListener("stop", () => {
      stream.getTracks().forEach((track) => track.stop());
      const type = state.recorder.mimeType || "audio/webm";
      const blob = new Blob(state.chunks, { type });
      updateRecordingState(false);
      submitAudio(blob);
    });

    state.recorder.start();
    updateRecordingState(true);
  } catch (error) {
    setStatus(error.message || "Microphone unavailable", true);
  }
}

async function submitAudio(blob) {
  state.busy = true;
  setStatus("Processing");

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
  }
}

function renderTurn(payload) {
  addMessage("user", payload.transcript);

  const wrapper = document.createElement("article");
  wrapper.className = "message assistant";

  const response = document.createElement("p");
  response.textContent = payload.correction.response;
  wrapper.append(response);

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

  if (payload.audio_base64) {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = audioUrl(payload.audio_base64, payload.audio_mime_type || "audio/mpeg");
    wrapper.append(audio);
    audio.play().catch(() => {});
  }

  chat.append(wrapper);
  chat.scrollTop = chat.scrollHeight;
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
