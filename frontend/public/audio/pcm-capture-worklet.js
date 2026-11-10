function highPassCoefficients(inputRate, cutoffHz = 85) {
  const clamped = Math.min(cutoffHz, inputRate * 0.2);
  const omega = (2 * Math.PI * clamped) / inputRate;
  const cosW = Math.cos(omega);
  const alpha = Math.sin(omega) / (2 * Math.SQRT2);
  const a0 = 1 + alpha;
  const norm = (1 + cosW) / 2;
  return {
    b0: norm / a0,
    b1: -(1 + cosW) / a0,
    b2: norm / a0,
    a1: (-2 * cosW) / a0,
    a2: (1 - alpha) / a0,
  };
}

function lowPassKernel(inputRate, outputRate, length = 63) {
  const cutoff = Math.min(outputRate * 0.45, inputRate * 0.45);
  const normalized = cutoff / inputRate;
  const center = (length - 1) / 2;
  const taps = new Float32Array(length);
  let sum = 0;
  for (let i = 0; i < length; i += 1) {
    const offset = i - center;
    const sinc = offset === 0
      ? 2 * normalized
      : Math.sin(2 * Math.PI * normalized * offset) / (Math.PI * offset);
    const window = 0.54 - 0.46 * Math.cos((2 * Math.PI * i) / (length - 1));
    taps[i] = sinc * window;
    sum += taps[i];
  }
  for (let i = 0; i < length; i += 1) taps[i] /= sum;
  return taps;
}

class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.targetRate = options.processorOptions?.targetSampleRate || 16000;
    this.hpf = highPassCoefficients(sampleRate, 85);
    this.hpfZ1 = 0;
    this.hpfZ2 = 0;
    this.kernel = lowPassKernel(sampleRate, this.targetRate);
    this.history = new Float32Array(this.kernel.length);
    this.historyIndex = 0;
    this.inputIndex = 0;
    this.previous = 0;
    this.nextOutput = 0;
    this.frame = new Int16Array(512);
    this.frameIndex = 0;
    this.muted = false;
    this.ttsPlaying = false;
    this.noiseFloor = 0.004;
    this.hangoverSamples = 0;
    this.hangoverDuration = Math.round(sampleRate * 0.3);
    this.gateGain = 1;
    this.attackCoeff = 1 - Math.exp(-1 / Math.max(1, sampleRate * 0.003));
    this.releaseCoeff = 1 - Math.exp(-1 / Math.max(1, sampleRate * 0.05));
    this.monoScratch = new Float32Array(128);
    this.port.onmessage = event => {
      if (event.data?.type === "mute") {
        this.muted = Boolean(event.data.value);
        this.frameIndex = 0;
        this.history.fill(0);
        this.hpfZ1 = 0;
        this.hpfZ2 = 0;
        this.previous = 0;
        this.hangoverSamples = 0;
        this.gateGain = 1;
      } else if (event.data?.type === "tts_playing") {
        this.ttsPlaying = Boolean(event.data.value);
      }
    };
  }

  highPass(sample) {
    const out = this.hpf.b0 * sample + this.hpfZ1;
    this.hpfZ1 = this.hpf.b1 * sample - this.hpf.a1 * out + this.hpfZ2;
    this.hpfZ2 = this.hpf.b2 * sample - this.hpf.a2 * out;
    return out;
  }

  filter(sample) {
    this.history[this.historyIndex] = sample;
    let sum = 0;
    let index = this.historyIndex;
    for (let tap = 0; tap < this.kernel.length; tap += 1) {
      sum += this.kernel[tap] * this.history[index];
      index = index === 0 ? this.history.length - 1 : index - 1;
    }
    this.historyIndex = (this.historyIndex + 1) % this.history.length;
    return sum;
  }

  emit(sample) {
    const clipped = Math.max(-1, Math.min(1, sample));
    this.frame[this.frameIndex++] = clipped < 0 ? clipped * 32768 : clipped * 32767;
    if (this.frameIndex === 512) {
      const buffer = new ArrayBuffer(1024);
      const view = new DataView(buffer);
      for (let i = 0; i < 512; i += 1) view.setInt16(i * 2, this.frame[i], true);
      this.port.postMessage(buffer, [buffer]);
      this.frameIndex = 0;
    }
  }

  process(inputs, outputs) {
    const channels = inputs[0];
    const output = outputs[0]?.[0];
    if (output) output.fill(0);
    if (!channels || channels.length === 0 || this.muted) return true;

    const frameLength = channels[0].length;
    if (this.monoScratch.length < frameLength) {
      this.monoScratch = new Float32Array(frameLength);
    }

    let energy = 0;
    for (let i = 0; i < frameLength; i += 1) {
      // Explicitly downmix every input channel to mono instead of silently discarding stereo.
      let mono = 0;
      for (let channel = 0; channel < channels.length; channel += 1) {
        mono += channels[channel][i] || 0;
      }
      mono /= channels.length;
      const hp = this.highPass(mono);
      this.monoScratch[i] = hp;
      energy += hp * hp;
    }

    const rms = Math.sqrt(energy / frameLength);
    if (rms < this.noiseFloor * 1.8) {
      const alpha = rms < this.noiseFloor ? 0.05 : 0.002;
      this.noiseFloor = Math.max(0.0005, Math.min(0.03, this.noiseFloor + alpha * (rms - this.noiseFloor)));
    }
    const threshold = this.ttsPlaying
      ? Math.max(0.015, this.noiseFloor * 4.0)
      : Math.max(0.008, this.noiseFloor * 2.8);
    if (rms >= threshold) {
      this.hangoverSamples = this.hangoverDuration;
    } else if (this.hangoverSamples > 0) {
      this.hangoverSamples = Math.max(0, this.hangoverSamples - frameLength);
    }

    const targetGain = rms >= threshold || this.hangoverSamples > 0 ? 1 : (this.ttsPlaying ? 0.08 : 0.15);
    const ratio = sampleRate / this.targetRate;
    for (let i = 0; i < frameLength; i += 1) {
      const coeff = targetGain > this.gateGain ? this.attackCoeff : this.releaseCoeff;
      this.gateGain += coeff * (targetGain - this.gateGain);
      const filtered = this.filter(this.monoScratch[i] * this.gateGain);
      const position = this.inputIndex;
      while (this.nextOutput <= position) {
        const fraction = position === 0 ? 0 : Math.max(0, Math.min(1, this.nextOutput - (position - 1)));
        const sample = position === 0 ? filtered : this.previous + (filtered - this.previous) * fraction;
        this.emit(sample);
        this.nextOutput += ratio;
      }
      this.previous = filtered;
      this.inputIndex += 1;
    }
    return true;
  }
}

registerProcessor("pcm-capture-processor", PcmCaptureProcessor);
