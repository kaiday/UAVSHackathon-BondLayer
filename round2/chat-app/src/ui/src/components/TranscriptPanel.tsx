interface TranscriptPanelProps {
  transcript: Record<string, string>
}

export default function TranscriptPanel({ transcript }: TranscriptPanelProps) {
  return (
    <div className="transcript-panel">
      <div className="transcript-content">
        {/* System Prompt */}
        {transcript.system_prompt && (
          <div className="transcript-section">
            <h5>System Prompt</h5>
            <pre>{transcript.system_prompt}</pre>
          </div>
        )}

        {/* User Query */}
        {transcript.user_query && (
          <div className="transcript-section">
            <h5>User Query</h5>
            <p>{transcript.user_query}</p>
          </div>
        )}

        {/* Parsed Intent */}
        {transcript.parsed_intent && (
          <div className="transcript-section">
            <h5>Parsed Intent</h5>
            <p>{transcript.parsed_intent}</p>
          </div>
        )}

        {/* Processing Steps */}
        {(transcript.intent_parse || transcript.fan_out || transcript.ranking) && (
          <div className="transcript-section">
            <h5>Processing Steps</h5>
            <div className="steps-log">
              {transcript.intent_parse && <p>• {transcript.intent_parse}</p>}
              {transcript.fan_out && <p>• {transcript.fan_out}</p>}
              {transcript.ranking && <p>• {transcript.ranking}</p>}
            </div>
          </div>
        )}

        {/* Model Completion */}
        {transcript.completion && (
          <div className="transcript-section">
            <h5>Model Completion</h5>
            <p>{transcript.completion}</p>
          </div>
        )}

        {/* Model Info */}
        {transcript.model && (
          <div className="transcript-section model-info">
            <small>Model: {transcript.model}</small>
          </div>
        )}
      </div>
    </div>
  )
}
