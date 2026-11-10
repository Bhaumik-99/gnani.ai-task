export type CaptureController = {
  setMuted: (muted: boolean) => void;
  setDucking: (active: boolean) => void;
  stop: () => void;
};

export async function startPcmCapture(
  context: AudioContext,
  stream: MediaStream,
  onFrame: (frame: ArrayBuffer) => void,
  targetSampleRate = 16000,
): Promise<CaptureController> {
  if (!context.audioWorklet) throw new Error("AudioWorklet is not supported by this browser.");
  let source: MediaStreamAudioSourceNode | undefined;
  let node: AudioWorkletNode | undefined;
  let silentGain: GainNode | undefined;
  try {
    await context.audioWorklet.addModule("/audio/pcm-capture-worklet.js");
    source = context.createMediaStreamSource(stream);
    node = new AudioWorkletNode(context, "pcm-capture-processor", {
      numberOfInputs: 1,
      numberOfOutputs: 1,
      outputChannelCount: [1],
      processorOptions: { targetSampleRate },
    });
    silentGain = context.createGain();
    silentGain.gain.value = 0;
    node.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
      if (event.data instanceof ArrayBuffer) onFrame(event.data);
    };
    source.connect(node);
    node.connect(silentGain);
    silentGain.connect(context.destination);
    let stopped = false;
    return {
      setMuted: (muted) => node?.port.postMessage({ type: "mute", value: muted }),
      setDucking: (active) => node?.port.postMessage({ type: "tts_playing", value: active }),
      stop: () => {
        if (stopped) return;
        stopped = true;
        if (node) {
          node.port.onmessage = null;
          node.port.close();
          node.disconnect();
        }
        source?.disconnect();
        silentGain?.disconnect();
      },
    };
  } catch (error) {
    source?.disconnect();
    node?.disconnect();
    node?.port.close();
    silentGain?.disconnect();
    throw error;
  }
}

export function stopMicrophone(stream?: MediaStream): void {
  stream?.getTracks().forEach(track => track.stop());
}

export class PcmStreamPlayer {
  private readonly context: AudioContext;
  private readonly sources = new Set<AudioBufferSourceNode>();
  private readonly onPlaybackChange?: (playing: boolean) => void;
  private nextStart = 0;
  private muted = false;

  constructor(context: AudioContext, onPlaybackChange?: (playing: boolean) => void) {
    this.context = context;
    this.onPlaybackChange = onPlaybackChange;
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    if (muted) this.stop();
  }

  enqueuePcm16(data: ArrayBuffer, sampleRate: number): boolean {
    if (this.muted) return true;
    if (!data.byteLength || data.byteLength % 2 !== 0 || !Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 48000) return false;
    if (this.context.state === "suspended") void this.context.resume();
    // Timbre delivers PCM chunks faster than real time; allow up to 120s of buffered speech.
    if (this.nextStart - this.context.currentTime > 120) return false;
    const view = new DataView(data);
    const samples = new Float32Array(data.byteLength / 2);
    for (let index = 0; index < samples.length; index += 1) {
      samples[index] = view.getInt16(index * 2, true) / 32768;
    }
    const buffer = this.context.createBuffer(1, samples.length, sampleRate);
    buffer.copyToChannel(samples, 0);
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.context.destination);
    const startAt = Math.max(this.context.currentTime + 0.025, this.nextStart);
    this.nextStart = startAt + buffer.duration;
    const wasEmpty = this.sources.size === 0;
    this.sources.add(source);
    if (wasEmpty) this.onPlaybackChange?.(true);
    source.onended = () => {
      this.sources.delete(source);
      if (this.sources.size === 0) this.onPlaybackChange?.(false);
    };
    source.start(startAt);
    return true;
  }

  stop(): void {
    const hadSources = this.sources.size > 0;
    for (const source of this.sources) {
      try { source.stop(); } catch { /* The source may already have ended. */ }
      source.disconnect();
    }
    this.sources.clear();
    this.nextStart = this.context.currentTime;
    if (hadSources) this.onPlaybackChange?.(false);
  }
}
