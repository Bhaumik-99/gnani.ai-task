export type CaptureController = {
  setMuted: (muted: boolean) => void;
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
  private nextStart = 0;
  private muted = false;

  constructor(context: AudioContext) {
    this.context = context;
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    if (muted) this.stop();
  }

  enqueuePcm16(data: ArrayBuffer, sampleRate: number): boolean {
    if (this.muted) return true;
    if (!data.byteLength || data.byteLength % 2 !== 0 || !Number.isFinite(sampleRate) || sampleRate < 8000 || sampleRate > 48000) return false;
    if (this.nextStart - this.context.currentTime > 4) return false;
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
    this.sources.add(source);
    source.onended = () => this.sources.delete(source);
    source.start(startAt);
    return true;
  }

  stop(): void {
    for (const source of this.sources) {
      try { source.stop(); } catch { /* The source may already have ended. */ }
      source.disconnect();
    }
    this.sources.clear();
    this.nextStart = this.context.currentTime;
  }
}
