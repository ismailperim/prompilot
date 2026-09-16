import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * A renderer that throws shows its error inside the panel; the rest of the grid keeps working.
 * Give it a `key` derived from the spec so it resets when the panel changes.
 */
export class PanelErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('panel renderer crashed', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="panel-message panel-message--error">
          <strong>This panel couldn't render.</strong>
          <span>{this.state.error.message}</span>
        </div>
      )
    }
    return this.props.children
  }
}
