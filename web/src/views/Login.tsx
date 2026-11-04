import { useState } from 'react'
import { api, setToken, type AuthUser } from '../api'

export default function Login({ onDone }: { onDone: (u: AuthUser) => void }) {
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setErr(null)
    api.login(name, password).then((r) => { setToken(r.token); onDone(r.user) })
      .catch(() => setErr('Wrong user name or password')).finally(() => setBusy(false))
  }
  return (
    <div className="login-wrap">
      <form className="card login" onSubmit={submit}>
        <div className="kicker">VolScan · access</div>
        <h2>Sign in</h2>
        <label>User<input autoComplete="username" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>Password<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
        {err && <div className="note warn-text">{err}</div>}
        <button className="btn primary" disabled={busy || !name || !password}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="note">Every sign-in and every action is written to the audit log.</p>
      </form>
    </div>
  )
}
