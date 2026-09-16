import type { NewPanelSpec, PanelSpec, SystemStatus } from '../api/types'
import { PanelForm } from './PanelForm'

interface Props {
  status: SystemStatus | null
  editing: PanelSpec | null
  onSubmit: (spec: NewPanelSpec) => Promise<void>
  onCancelEdit: () => void
}

export function Sidebar({ status, editing, onSubmit, onCancelEdit }: Props) {
  const llm = status?.llm

  return (
    <aside className="sidebar">
      <section className="card card--chat">
        <h3 className="card__title">Ask for a chart</h3>
        {llm?.enabled ? (
          <p className="card__text">
            Chat is coming in the next release. Model configured: <code>{llm.model}</code>.
          </p>
        ) : (
          <>
            <p className="card__text">
              Connect an OpenAI-compatible model to describe charts in plain language — PromPilot finds the metric,
              writes the PromQL and adds the panel.
            </p>
            <pre className="card__code">{`LLM_BASE_URL=http://ollama:11434/v1
LLM_MODEL=llama3.1`}</pre>
          </>
        )}
      </section>

      <PanelForm key={editing?.id ?? 'new'} editing={editing} onSubmit={onSubmit} onCancel={onCancelEdit} />
    </aside>
  )
}
