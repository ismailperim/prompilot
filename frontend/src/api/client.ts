export interface Health {
  status: string
  prometheus_url: string
  llm_enabled: boolean
}

export async function fetchHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch('/healthz', { signal })
  if (!response.ok) {
    throw new Error(`healthz failed: ${response.status}`)
  }
  return (await response.json()) as Health
}
