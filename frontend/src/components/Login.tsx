import { useState, type FormEvent } from 'react'
import { ApiError, api } from '../api/client'
import { LogoMark, Wordmark } from './Logo'

export function Login({ onSuccess }: { onSuccess: () => void }) {
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.auth.login(password)
      onSuccess()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="app app--centered">
      <form className="card card--dialog" onSubmit={submit}>
        <div className="brand">
          <LogoMark size={22} />
          <Wordmark />
        </div>
        <h2 className="card__title">Sign in</h2>
        <label className="field login__field">
          <span>Password</span>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus autoComplete="current-password" required />
        </label>
        {error && (
          <p className="form__error" role="alert">
            {error}
          </p>
        )}
        <button className="btn btn--primary" type="submit" disabled={busy || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}
