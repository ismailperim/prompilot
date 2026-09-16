import { useState } from 'react'
import type { CatalogStatus, MetricEntry, NewPanelSpec, PanelSpec, SystemStatus } from '../api/types'
import { MetricBrowser } from '../catalog/MetricBrowser'
import { suggestQuery } from '../catalog/suggest'
import { ChatPanel } from '../chat/ChatPanel'
import { PanelForm, type FormState } from './PanelForm'

type Tab = 'chat' | 'build' | 'metrics'

interface Props {
  status: SystemStatus | null
  catalog: CatalogStatus | null
  editing: PanelSpec | null
  onSubmit: (spec: NewPanelSpec) => Promise<void>
  onCancelEdit: () => void
  onRebuildCatalog: () => void
}

export function Sidebar({ status, catalog, editing, onSubmit, onCancelEdit, onRebuildCatalog }: Props) {
  const llmEnabled = Boolean(status?.llm.enabled)
  // null = "not chosen yet": land on Chat when an LLM is configured, else on Build.
  const [tab, setTab] = useState<Tab | null>(null)
  const [seed, setSeed] = useState<{ key: number; values: Partial<FormState> }>({ key: 0, values: {} })

  function pickMetric(metric: MetricEntry) {
    const s = suggestQuery(metric)
    onCancelEdit()
    setSeed((prev) => ({ key: prev.key + 1, values: { expr: s.expr, legend: s.legend, unit: s.unit, title: s.title } }))
    setTab('build')
  }

  const activeTab: Tab = editing ? 'build' : (tab ?? (llmEnabled ? 'chat' : 'build'))
  const select = (next: Tab) => {
    if (next !== 'build') onCancelEdit()
    setTab(next)
  }

  return (
    <aside className="sidebar">
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={activeTab === 'chat'} className="tab" onClick={() => select('chat')}>
          Chat
        </button>
        <button role="tab" aria-selected={activeTab === 'build'} className="tab" onClick={() => select('build')}>
          {editing ? 'Edit panel' : 'Build'}
        </button>
        <button role="tab" aria-selected={activeTab === 'metrics'} className="tab" onClick={() => select('metrics')}>
          Metrics{catalog?.metricCount ? <span className="tab__count">{catalog.metricCount}</span> : null}
        </button>
      </div>

      {activeTab === 'chat' && <ChatPanel status={status} />}
      {activeTab === 'build' && (
        <PanelForm
          key={editing ? `edit:${editing.id}` : `new:${seed.key}`}
          editing={editing}
          initial={seed.values}
          onSubmit={onSubmit}
          onCancel={onCancelEdit}
        />
      )}
      {activeTab === 'metrics' && <MetricBrowser status={catalog} onPick={pickMetric} onRebuild={onRebuildCatalog} />}
    </aside>
  )
}
