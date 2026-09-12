import type { TranscriptCall } from '../types'

interface Props {
  transcript: TranscriptCall[]
}

/** Every model call, verbatim. A demo that shows only a parsed winner is asking
 *  to be taken on trust. */
export default function TranscriptPanel({ transcript }: Props) {
  if (!transcript?.length) {
    return <div className="transcript"><p>No model calls recorded yet.</p></div>
  }

  return (
    <div className="transcript">
      {transcript.map((call, i) => (
        <article key={i} className="transcript-call">
          <header>
            <span className="call-label">{call.label}</span>
            <span className="call-model">{call.model}</span>
            <span className="call-latency">{call.latency_ms} ms</span>
          </header>
          <details>
            <summary>System prompt</summary>
            <pre>{call.system}</pre>
          </details>
          <details>
            <summary>Prompt</summary>
            <pre>{call.prompt}</pre>
          </details>
          <details open>
            <summary>Completion</summary>
            <pre>{call.completion}</pre>
          </details>
        </article>
      ))}
    </div>
  )
}
