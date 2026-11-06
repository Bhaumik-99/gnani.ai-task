export async function requestRawMicrophone(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone capture is unavailable.");
  return navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, noiseSuppression: false, echoCancellation: false, autoGainControl: false },
    video: false,
  });
}

export function stopMicrophone(stream?: MediaStream) {
  stream?.getTracks().forEach((track) => track.stop());
}

export function encodePcm16(floatSamples: Float32Array): string {
  const pcm = new Int16Array(floatSamples.length);
  for (let i = 0; i < floatSamples.length; i++) {
    const sample = Math.max(-1, Math.min(1, floatSamples[i]));
    pcm[i] = sample < 0 ? sample * 32768 : sample * 32767;
  }
  const bytes = new Uint8Array(pcm.buffer);
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}
