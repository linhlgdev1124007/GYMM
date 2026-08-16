export function availableSpeechVoices() {
  if (!("speechSynthesis" in window)) return [];
  return window.speechSynthesis.getVoices();
}

export function vietnameseVoice({ voiceUri = "", voiceName = "" } = {}) {
  if (!("speechSynthesis" in window)) return null;
  const voices = availableSpeechVoices();
  const selected = voices.find((voice) => voice.voiceURI === voiceUri)
    || voices.find((voice) => voice.name === voiceName);
  if (selected) return selected;
  return voices.find((voice) => voice.lang?.toLowerCase() === "vi-vn")
    || voices.find((voice) => voice.lang?.toLowerCase().startsWith("vi"))
    || null;
}

export function speakVietnamese(text, {
  interrupt = false,
  voiceUri = "",
  voiceName = "",
  volume = 1,
  rate = 1,
  pitch = 1,
} = {}) {
  if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return false;
  const message = String(text || "").trim();
  if (!message) return false;
  if (interrupt) window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(message);
  utterance.lang = "vi-VN";
  utterance.rate = Number(rate);
  utterance.pitch = Number(pitch);
  utterance.volume = Number(volume);
  const voice = vietnameseVoice({ voiceUri, voiceName });
  if (voice) {
    utterance.voice = voice;
    utterance.lang = voice.lang || "vi-VN";
  }
  window.speechSynthesis.speak(utterance);
  return true;
}
