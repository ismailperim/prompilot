import { useState } from 'react'
import type { CatalogStatus, MetricEntry, NewPanelSpec, PanelSpec, SystemStatus } from '../api/types'
import { MetricBrowser } from '../catalog/MetricBrowser'
import { suggestQuery } from '../catalog/suggest'
import { PanelForm, type FormState } from './PanelForm'

type Tab = 'build' | 'metrics'

interface Props {
  status: SystemStatus | null
  catalog: CatalogStatus | null
  editing: PanelSpec | null
  onSubmit: (spec: NewPanelSpec) => Promise<void>
  onCancelEdit: () => void
  onRebuildCatalog: () => void
}

export function Sidebar({ status, catalog, editing, onSubmit, onCancelEdit, onRebuildCatalog }: Props) {
  const [tab, setTab] = useState<Tab>('build')
  const [seed, setSeed] = useState<{ key: number; values: Partial<FormState> }>({ key: 0, values: {} })
  const llm = status?.llm

  function pickMetric(metric: MetricEntry) {
    const s = suggestQuery(metric)
    onCancelEdit()
    setSeed((prev) => ({ key: prev.key + 1, values: { expr: s.expr, legend: s.legend, unit: s.unit, title: s.title } }))
    setTab('build')
  }

  const activeTab: Tab = editing ? 'build' : tab

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

      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={activeTab === 'build'} className="tab" onClick={() => setTab('build')}>
          {editing ? 'Edit panel' : 'Build a panel'}
        </button>
        <button
          role="tab"
          aria-selected={activeTab === 'metrics'}
          className="tab"
          onClick={() => {
            onCancelEdit()
            setTab('metrics')
          }}
        >
          Metrics{catalog?.metricCount ? <span className="tab__count">{catalog.metricCount}</span> : null}
        </button>
      </div>

      {activeTab === 'build' ? (
        <PanelForm
          key={editing ? `edit:${editing.id}` : `new:${seed.key}`}
          editing={editing}
          initial={seed.values}
          onSubmit={onSubmit}
          onCancel={onCancelEdit}
        />
      ) : (
        <MetricBrowser status={catalog} onPick={pickMetric} onRebuild={onRebuildCatalog} />
      )}
    </aside>
  )
}
