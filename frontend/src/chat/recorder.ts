/**
 * Records the microphone to 16 kHz mono WAV in the browser — a format every
 * transcription backend accepts — and stops by itself after a pause.
 */

export interface RecorderOptions {
  /** Silence (RMS below threshold) that ends the utterance, in ms. */
  silenceMs?: number
  /** Hard stop, in ms. */
  maxMs?: number
  /** RMS threshold for "speech". */
  threshold?: number
  onLevel?: (rms: number) => void
}

export interface Recording {
  blob: Blob
  durationMs: number
  hadSpeech: boolean
}

export interface ActiveRecorder {
  stop: () => void
  done: Promise<Recording>
}

const TARGET_RATE = 16000

export async function record(opts: RecorderOptions = {}): Promise<ActiveRecorder> {
  const silenceMs = opts.silenceMs ?? 1300
  const maxMs = opts.maxMs ?? 20000
  const threshold = opts.threshold ?? 0.012

  const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
  const ctx = new AudioContext()
  const source = ctx.createMediaStreamSource(stream)
  // ScriptProcessor is deprecated but universally available and needs no worklet file.
  const processor = ctx.createScriptProcessor(4096, 1, 1)
  const chunks: Float32Array[] = []
  const started = performance.now()
  let lastSpeech = 0
  let hadSpeech = false
  let finished = false

  let resolveDone!: (r: Recording) => void
  const done = new Promise<Recording>((resolve) => {
    resolveDone = resolve
  })

  const finish = () => {
    if (finished) return
    finished = true
    processor.disconnect()
    source.disconnect()
    for (const track of stream.getTracks()) track.stop()
    void ctx.close()
    const pcm = downsample(concat(chunks), ctx.sampleRate, TARGET_RATE)
    resolveDone({ blob: encodeWav(pcm, TARGET_RATE), durationMs: performance.now() - started, hadSpeech })
  }

  processor.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0)
    chunks.push(new Float32Array(input))
    let sum = 0
    for (let i = 0; i < input.length; i++) sum += input[i] * input[i]
    const rms = Math.sqrt(sum / input.length)
    opts.onLevel?.(rms)
    const now = performance.now()
    if (rms > threshold) {
      hadSpeech = true
      lastSpeech = now
    }
    if ((hadSpeech && now - lastSpeech > silenceMs) || now - started > maxMs) finish()
  }
  source.connect(processor)
  processor.connect(ctx.destination)

  return { stop: finish, done }
}

function concat(chunks: Float32Array[]): Float32Array {
  const length = chunks.reduce((n, c) => n + c.length, 0)
  const out = new Float32Array(length)
  let offset = 0
  for (const c of chunks) {
    out.set(c, offset)
    offset += c.length
  }
  return out
}

export function downsample(input: Float32Array, from: number, to: number): Float32Array {
  if (from === to) return input
  const ratio = from / to
  const length = Math.floor(input.length / ratio)
  const out = new Float32Array(length)
  for (let i = 0; i < length; i++) {
    const start = Math.floor(i * ratio)
    const end = Math.min(Math.floor((i + 1) * ratio), input.length)
    let sum = 0
    for (let j = start; j < end; j++) sum += input[j]
    out[i] = end > start ? sum / (end - start) : 0
  }
  return out
}

export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const view = new DataView(buffer)
  const write = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i))
  }
  write(0, 'RIFF')
  view.setUint32(4, 36 + samples.length * 2, true)
  write(8, 'WAVE')
  write(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true) // PCM
  view.setUint16(22, 1, true) // mono
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  write(36, 'data')
  view.setUint32(40, samples.length * 2, true)
  let offset = 44
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]))
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return new Blob([buffer], { type: 'audio/wav' })
}
