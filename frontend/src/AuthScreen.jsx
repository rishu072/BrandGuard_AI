import { useState } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle2, Eye, EyeOff, LockKeyhole, Mail, ShieldCheck, UserPlus } from 'lucide-react';
import { get, post } from './api.js';

export default function AuthScreen({ demoMode, onAuthenticated }) {
  const [mode, setMode] = useState('login');
  const [step, setStep] = useState('credentials');
  const [purpose, setPurpose] = useState('login');
  const [form, setForm] = useState({ email: '', password: '', name: '', organization_name: '' });
  const [code, setCode] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [demoCode, setDemoCode] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const clearMessages = () => { setError(''); setNotice(''); };

  const submitCredentials = async (event) => {
    event.preventDefault();
    clearMessages();
    setBusy(true);
    try {
      if (mode === 'register') {
        const result = await post('/api/auth/register', form);
        setPurpose('verify_email');
        setStep('otp');
        setNotice(result.message || 'Check your email for a verification code.');
      } else {
        const result = await post('/api/auth/login', { email: form.email, password: form.password });
        setPurpose(result.purpose || 'login');
        setStep('otp');
        setNotice(result.message || 'Enter the code sent to your email.');
      }
    } catch (err) {
      setError(err.message || 'We could not complete that request.');
    } finally {
      setBusy(false);
    }
  };

  const submitCode = async (event) => {
    event.preventDefault();
    clearMessages();
    setBusy(true);
    try {
      const result = await post('/api/auth/verify', { email: form.email, code, purpose });
      onAuthenticated(result.user);
    } catch (err) {
      setError(err.message || 'That code could not be verified.');
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    clearMessages();
    setBusy(true);
    try {
      const result = await post('/api/auth/resend', { email: form.email, purpose });
      setNotice(result.message || 'If eligible, a new code was sent.');
      setDemoCode('');
    } catch (err) {
      setError(err.message || 'Could not resend the code.');
    } finally {
      setBusy(false);
    }
  };

  const openDemoInbox = async () => {
    clearMessages();
    setBusy(true);
    try {
      const result = await get('/api/dev/mailbox?email=' + encodeURIComponent(form.email));
      const message = [...(result.messages || [])].reverse().find((item) => item.purpose === purpose);
      if (!message) throw new Error('No demo email is available yet. Request a code first.');
      setDemoCode(message.code);
      setNotice('Local demo mailbox · code expires at ' + new Date(message.expires_at).toLocaleTimeString());
    } catch (err) {
      setError(err.message || 'Could not open the demo mailbox.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-backdrop"><span /><span /><span /></div>
      <section className="auth-card">
        <div className="auth-brand"><div className="brand-mark large"><ShieldCheck size={27} /></div><div><strong>brandguard</strong><small>AI GOVERNANCE</small></div></div>
        <div className="auth-heading">
          <span className="eyebrow">SECURE BRAND WORKSPACE</span>
          <h1>{step === 'otp' ? 'Verify it’s you' : mode === 'register' ? 'Create your workspace' : 'Welcome back'}</h1>
          <p>{step === 'otp' ? `Enter the six-digit code sent to ${form.email}.` : mode === 'register' ? 'Start reviewing every draft against your approved brand rules.' : 'Sign in to review content and keep your brand consistent.'}</p>
        </div>
        {error && <div className="auth-message error" role="alert">{error}</div>}
        {notice && <div className="auth-message success"><CheckCircle2 size={15} />{notice}</div>}

        {step === 'credentials' ? (
          <form className="auth-form" onSubmit={submitCredentials}>
            {mode === 'register' && <>
              <label>Full name<input autoComplete="name" minLength="2" required value={form.name} onChange={(e) => update('name', e.target.value)} placeholder="Your name" /></label>
              <label>Organization<input autoComplete="organization" minLength="2" required value={form.organization_name} onChange={(e) => update('organization_name', e.target.value)} placeholder="Your company or team" /></label>
            </>}
            <label>Email address<div className="auth-input-icon"><Mail size={16} /><input autoComplete="email" type="email" required value={form.email} onChange={(e) => update('email', e.target.value)} placeholder="you@company.com" /></div></label>
            <label>Password<div className="auth-input-icon"><LockKeyhole size={16} /><input autoComplete={mode === 'register' ? 'new-password' : 'current-password'} type={showPassword ? 'text' : 'password'} minLength={mode === 'register' ? 10 : undefined} required value={form.password} onChange={(e) => update('password', e.target.value)} placeholder={mode === 'register' ? 'At least 10 characters' : 'Your password'} /><button type="button" className="password-toggle" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? <EyeOff size={15} /> : <Eye size={15} />}</button></div></label>
            {mode === 'register' && <small className="auth-hint">Use at least 10 characters with an uppercase letter, lowercase letter, and number.</small>}
            <button className="button button-primary full-width auth-submit" disabled={busy}>{busy ? 'Please wait…' : mode === 'register' ? <><UserPlus size={16} /> Create account</> : <>Continue securely <ArrowRight size={16} /></>}</button>
          </form>
        ) : (
          <form className="auth-form" onSubmit={submitCode}>
            <label>One-time code<input className="otp-input" autoComplete="one-time-code" inputMode="numeric" pattern="[0-9]{6}" maxLength="6" required value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="000000" /></label>
            <small className="auth-hint">Codes expire in 10 minutes and work once. Too many attempts lock this code.</small>
            {demoMode && <button type="button" className="button button-secondary full-width" disabled={busy} onClick={openDemoInbox}>Open local demo mailbox</button>}
            {demoCode && <div className="demo-code"><span>DEMO CODE</span><strong>{demoCode}</strong></div>}
            <button className="button button-primary full-width auth-submit" disabled={busy || code.length !== 6}>{busy ? 'Verifying…' : 'Verify and sign in'}</button>
            <button type="button" className="text-button auth-resend" disabled={busy} onClick={resend}>Resend code</button>
          </form>
        )}

        {step === 'credentials' ? (
          <div className="auth-switch">{mode === 'register' ? 'Already have an account?' : 'New to BrandGuard AI?'} <button onClick={() => { setMode(mode === 'register' ? 'login' : 'register'); clearMessages(); }}>{mode === 'register' ? 'Sign in' : 'Create an account'}</button></div>
        ) : <button className="auth-back" onClick={() => { setStep('credentials'); setCode(''); setDemoCode(''); clearMessages(); }}><ArrowLeft size={14} /> Back to sign in</button>}
        <div className="auth-security"><ShieldCheck size={15} /><span>Protected workspace · Email verified · Human approval before publishing</span></div>
      </section>
      <div className="auth-footer">BRANDGUARD AI <span>·</span> CREATE CONFIDENTLY. PUBLISH CONSISTENTLY.</div>
    </div>
  );
}
