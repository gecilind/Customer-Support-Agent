// @ts-nocheck
// AudioWorklet context: AudioWorkletProcessor, sampleRate, and registerProcessor
// are globals injected by the browser — not available in normal TypeScript scope.

/**
 * PCMProcessor
 *
 * Captures mono microphone audio at the browser's native sample rate
 * (typically 44 100 Hz or 48 000 Hz), downsamples to 16 000 Hz using
 * nearest-neighbour decimation, converts Float32 → Int16 (PCM16), and
 * posts each processed block as an ArrayBuffer to the main thread via
 * this.port.postMessage().
 *
 * When muted, process() returns without sending PCM (hard gate — zero bytes leave).
 */
class PCMProcessor extends AudioWorkletProcessor {
  private readonly targetRate = 16_000;

  private muted = true;

  constructor() {
    super();
    this.port.onmessage = (e: MessageEvent) => {
      if (e.data?.type === 'set_muted') {
        this.muted = Boolean(e.data.value);
      }
    };
  }

  process(
    inputs: Float32Array[][],
    _outputs: Float32Array[][],
    _parameters: Record<string, Float32Array>,
  ): boolean {
    if (this.muted) {
      return true;
    }

    const channel = inputs[0]?.[0];
    if (!channel || channel.length === 0) return true;

    // Ratio: how many input samples correspond to one output sample
    const ratio = sampleRate / this.targetRate;
    const outLen = Math.floor(channel.length / ratio);
    if (outLen === 0) return true;

    const pcm16 = new Int16Array(outLen);
    for (let i = 0; i < outLen; i++) {
      // Nearest-neighbour sample selection
      const src = channel[Math.floor(i * ratio)];
      // Clamp and scale Float32 [-1, 1] → Int16 [-32768, 32767]
      pcm16[i] = Math.max(-32_768, Math.min(32_767, Math.round(src * 32_767)));
    }

    // Transfer ownership of the buffer to avoid a copy
    this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    return true;
  }
}

registerProcessor('pcm-processor', PCMProcessor);
