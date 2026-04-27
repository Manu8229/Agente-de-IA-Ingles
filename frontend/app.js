const state = {
  recorder: null,
  stream: null,
  chunks: [],
  mode: "general",
  busy: false,
  lessonStarted: false,
  recordingStartedAt: 0,
  recorderSupported: true,
  expectedPhrase: "",
  expectedTranslation: "",
};

const chat = document.querySelector("#chat");
const statusText = document.querySelector("#status");
const startLessonButton = document.querySelector("#startLessonButton");
const recordButton = document.querySelector("#recordButton");
const recordLabel = document.querySelector("#recordLabel");
const userIdInput = document.querySelector("#userId");
const levelSelect = document.querySelector("#levelSelect");
const topicSelect = document.querySelector("#topicSelect");
const targetPhrase = document.querySelector("#targetPhrase");
const targetTranslation = document.querySelector("#targetTranslation");
const phraseCount = document.querySelector("#phraseCount");
const correctionCount = document.querySelector("#correctionCount");
const repeatList = document.querySelector("#repeatList");
const learnedList = document.querySelector("#learnedList");

document.querySelectorAll(".mode-button").forEach((button) => {
  button.addEventListener("click", () => {
    if (state.busy) return;
    setTopic(button.dataset.mode === "work" ? "work" : "daily");
  });
});

topicSelect.addEventListener("change", () => {
  if (state.busy) return;
  setTopic(topicSelect.value);
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
  setStatus("Iniciando");
  setControlsDisabled(true);

  const formData = new FormData();
  formData.append("user_id", currentUserId());
  formData.append("mode", state.mode);
  formData.append("level", currentLevel());
  formData.append("topic", currentTopic());

  try {
    const response = await fetch("/api/audio/start", {
      method: "POST",
      body: formData,
    });

    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(payload.detail || "Nao foi possivel iniciar a aula");
    }

    state.lessonStarted = true;
    setExpectedPhrase(
      payload.expected_phrase || payload.next_phrase,
      payload.translation?.next_phrase_pt,
    );
    renderLessonStart(payload);
    setStatus(payload.warnings?.[0] || "Pronto", Boolean(payload.warnings?.length));
  } catch (error) {
    setStatus(error.message || "Nao foi possivel iniciar a aula", true);
  } finally {
    state.busy = false;
    setControlsDisabled(false);
  }
}

async function startRecording() {
  try {
    ensureRecorderSupport();
    window.speechSynthesis?.cancel();
    setStatus("Permita o microfone");

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
      setStatus("Erro na gravacao. Tente novamente.", true);
    });

    recorder.addEventListener("stop", () => {
      const type = recorder.mimeType || "audio/webm";
      const blob = new Blob(state.chunks, { type });
      cleanupRecorder();
      updateRecordingState(false);

      if (!blob.size) {
        setStatus("Nenhum audio capturado. Tente novamente.", true);
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
    setStatus("Fale por um momento, depois pare.");
    return;
  }

  recorder.stop();
}

async function submitAudio(blob) {
  state.busy = true;
  setStatus("Processando");
  setControlsDisabled(true);

  const formData = new FormData();
  formData.append("audio", blob, `speech-${Date.now()}${fileExtension(blob.type)}`);
  formData.append("user_id", currentUserId());
  formData.append("mode", state.mode);
  formData.append("level", currentLevel());
  formData.append("topic", currentTopic());
  formData.append("expected_phrase", state.expectedPhrase);

  try {
    const response = await fetch("/api/audio/conversation", {
      method: "POST",
      body: formData,
    });

    const payload = await readJson(response);
    if (!response.ok) {
      throw new Error(payload.detail || "Falha na requisicao");
    }

    renderTurn(payload);
    setExpectedPhrase(
      payload.next_phrase || payload.correction.next_phrase,
      payload.correction.translation?.next_phrase_pt,
    );
    await fetchProgress();
    setStatus(payload.warnings?.[0] || "Pronto", Boolean(payload.warnings?.length));
  } catch (error) {
    setStatus(error.message || "Nao foi possivel processar o audio", true);
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
  appendTargetPrompt(wrapper, payload.expected_phrase, payload.translation?.next_phrase_pt);

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
  appendSpeechFeedback(wrapper, payload.speech_feedback);
  appendTargetPrompt(
    wrapper,
    payload.next_phrase || payload.correction.next_phrase,
    payload.correction.translation?.next_phrase_pt,
  );

  if (hasCorrection(payload.correction)) {
    const correction = document.createElement("div");
    correction.className = "correction";

    const label = document.createElement("span");
    label.textContent = "Correcao";

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
  const actions = document.createElement("div");
  actions.className = "audio-actions";

  const replayButton = document.createElement("button");
  replayButton.className = "replay-button";
  replayButton.type = "button";
  replayButton.textContent = "Ouvir de novo";

  if (payload.audio_base64) {
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.src = audioUrl(payload.audio_base64, payload.audio_mime_type || "audio/mpeg");
    actions.append(audio);
    replayButton.addEventListener("click", () => {
      audio.currentTime = 0;
      audio.play().catch(() => speakLocally(payload.spoken_text));
    });
    actions.append(replayButton);
    wrapper.append(actions);
    audio.play().catch(() => {
      speakLocally(payload.spoken_text);
    });
    return;
  }

  replayButton.addEventListener("click", () => speakLocally(payload.spoken_text));
  actions.append(replayButton);
  wrapper.append(actions);
  speakLocally(payload.spoken_text);
}

function appendSpeechFeedback(container, feedback) {
  if (!feedback) return;

  const card = document.createElement("div");
  card.className = "speech-feedback";

  const label = document.createElement("span");
  label.textContent = `${feedback.label} ${feedback.score}%`;

  const message = document.createElement("small");
  message.textContent = feedback.message;

  card.append(label, message);
  container.append(card);
}

function appendTargetPrompt(container, phrase, translation) {
  if (!phrase) return;

  const target = document.createElement("div");
  target.className = "target-prompt";

  const label = document.createElement("span");
  label.textContent = "Pratique em ingles";

  const text = document.createElement("strong");
  text.textContent = phrase;

  target.append(label, text);
  appendTranslation(target, translation);
  container.append(target);
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
    empty.textContent = "Sem dados ainda";
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
  recordLabel.textContent = isRecording ? "Parar" : "Gravar";
  setStatus(isRecording ? "Ouvindo" : "Processando");
}

function setStatus(text, isError = false) {
  statusText.textContent = text;
  statusText.classList.toggle("error", isError);
}

function setControlsDisabled(disabled) {
  startLessonButton.disabled = disabled;
  recordButton.disabled = disabled || !state.recorderSupported;
  levelSelect.disabled = disabled;
  topicSelect.disabled = disabled;
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
    throw new Error("Abra com http://127.0.0.1:8000 ou HTTPS para usar o microfone.");
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Este navegador nao permite capturar microfone aqui.");
  }

  if (!window.MediaRecorder) {
    throw new Error("Este navegador nao suporta gravacao de audio.");
  }
}

function isRecording() {
  return state.recorder?.state === "recording";
}

function readMicrophoneError(error) {
  if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
    return "Microfone bloqueado. Permita acesso ao microfone no navegador.";
  }

  if (error?.name === "NotFoundError") {
    return "Nenhum microfone encontrado.";
  }

  if (error?.name === "NotReadableError") {
    return "Microfone ja esta em uso por outro app.";
  }

  return error?.message || "Microfone indisponivel.";
}

function currentUserId() {
  return userIdInput.value.trim() || "default";
}

function currentLevel() {
  return levelSelect.value || "beginner_1";
}

function currentTopic() {
  return topicSelect.value || "daily";
}

function setTopic(topic) {
  topicSelect.value = topic;
  state.mode = topic === "work" ? "work" : "general";
  updateModeButtons();
}

function updateModeButtons() {
  document.querySelectorAll(".mode-button").forEach((item) => {
    const active =
      (item.dataset.mode === "general" && currentTopic() === "daily") ||
      (item.dataset.mode === "work" && currentTopic() === "work");
    item.classList.toggle("active", active);
  });
}

function setExpectedPhrase(phrase, translation) {
  state.expectedPhrase = phrase || "";
  state.expectedTranslation = translation || "";
  targetPhrase.textContent = state.expectedPhrase || "Inicie uma aula";
  targetTranslation.textContent = state.expectedTranslation ? `PT: ${state.expectedTranslation}` : "";
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
