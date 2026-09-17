import { BookOpen, Database, MessageSquare, SlidersHorizontal } from 'lucide-react'
import { useState } from 'react'
import type { CatalogStatus, MetricEntry, NewPanelSpec, PanelSpec, SystemStatus } from '../api/types'
import { MetricBrowser } from '../catalog/MetricBrowser'
import { suggestQuery } from '../catalog/suggest'
import { ChatPanel } from '../chat/ChatPanel'
import { NotesPanel } from '../knowledge/NotesPanel'
import { PanelForm, type FormState } from './PanelForm'

export type SidebarTab = 'chat' | 'build' | 'metrics' | 'notes'

interface Props {
  status: SystemStatus | null
  catalog: CatalogStatus | null
  editing: PanelSpec | null
  tab: SidebarTab | null
  onTab: (tab: SidebarTab) => void
  onSubmit: (spec: NewPanelSpec) => Promise<void>
  onCancelEdit: () => void
  onRebuildCatalog: () => void
}

export function Sidebar({ status, catalog, editing, tab, onTab, onSubmit, onCancelEdit, onRebuildCatalog }: Props) {
  const llmEnabled = Boolean(status?.llm.enabled)
  const [seed, setSeed] = useState<{ key: number; values: Partial<FormState> }>({ key: 0, values: {} })

  function pickMetric(metric: MetricEntry) {
    const s = suggestQuery(metric)
    onCancelEdit()
    setSeed((prev) => ({ key: prev.key + 1, values: { expr: s.expr, legend: s.legend, unit: s.unit, title: s.title } }))
    onTab('build')
  }

  const activeTab: SidebarTab = editing ? 'build' : (tab ?? (llmEnabled ? 'chat' : 'build'))
  const select = (next: SidebarTab) => {
    if (next !== 'build') onCancelEdit()
    onTab(next)
  }

  return (
    <aside className="sidebar">
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={activeTab === 'chat'} className="tab" onClick={() => select('chat')}>
          <MessageSquare size={15} />
          Chat
        </button>
        <button role="tab" aria-selected={activeTab === 'build'} className="tab" onClick={() => select('build')}>
          <SlidersHorizontal size={15} />
          {editing ? 'Edit' : 'Build'}
        </button>
        <button role="tab" aria-selected={activeTab === 'metrics'} className="tab" onClick={() => select('metrics')}>
          <Database size={15} />
          Metrics
          {catalog?.metricCount ? <span className="tab__count">{catalog.metricCount}</span> : null}
        </button>
        <button role="tab" aria-selected={activeTab === 'notes'} className="tab" onClick={() => select('notes')}>
          <BookOpen size={15} />
          Notes
        </button>
      </div>

      <div className="sidebar__body">
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
        {activeTab === 'notes' && <NotesPanel />}
      </div>
    </aside>
  )
}
