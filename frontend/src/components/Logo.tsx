/** The mark: a prompt chevron that continues into a series line and lands on the latest sample. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg className="logo-mark" width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <rect width="64" height="64" rx="14" fill="var(--accent)" />
      <path d="M14 18 L26 32 L14 46" fill="none" stroke="#12151C" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M26 32 L34 39 L42 24 L50 31" fill="none" stroke="#12151C" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="50" cy="31" r="4.8" fill="#12151C" />
    </svg>
  )
}

export function Wordmark() {
  return <span className="wordmark">PromPilot</span>
}
