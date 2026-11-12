import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertCircle, ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, BadgeCheck,
  BarChart3, Bell, BookOpen, Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight,
  CircleHelp, Clock3, Copy, FileCheck2, FilePlus2, FileText, Filter, Gauge, Globe2,
  History, House, Layers3, Lightbulb, ListFilter, Menu, MessageSquareText, MoreHorizontal,
  Plus, Search, Send, Settings2, Shield, ShieldCheck, Sparkles, SpellCheck, Target,
  TrendingUp, Upload, Users, X, XCircle, Zap,
} from 'lucide-react';
import { get, patch, post } from './api.js';
import AuthScreen from './AuthScreen.jsx';
import AdminPage from './AdminPage.jsx';

const navItems = [
  { id: 'overview', label: 'Overview', icon: House },
  { id: 'content', label: 'Content review', icon: SpellCheck, badge: '3' },
  { id: 'queue', label: 'Review queue', icon: FileCheck2, reviewerOnly: true },
  { id: 'library', label: 'Brand library', icon: BookOpen },
  { id: 'history', label: 'Audit history', icon: History },
  { id: 'analytics', label: 'Analytics', icon: BarChart3 },
  { id: 'admin', label: 'Administration', icon: Settings2, adminOnly: true },
];

const pageMeta = {
  overview: ['Workspace', 'Overview'],
  content: ['Governance', 'Content review'],
  queue: ['Governance', 'Review queue'],
  library: ['Knowledge hub', 'Brand library'],
  history: ['Governance', 'Audit history'],
  analytics: ['Workspace', 'Analytics'],
  admin: ['Workspace', 'Administration'],
};

const severityOrder = { critical: 0, high: 1, medium: 2, low: 3 };
const todayLabel = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }).format(new Date()).toUpperCase();
const prettyDate = (value) => {
  if (!value) return 'Just now';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(date);
};

function App() {
  const [user, setUser] = useState(null);
  const [checkingSession, setCheckingSession] = useState(true);
  const [demoMode, setDemoMode] = useState(false);
  useEffect(() => {
    let active = true;
    Promise.allSettled([get('/api/auth/me'), get('/api/health')])
      .then(([account, health]) => {
        if (!active) return;
        if (account.status === 'fulfilled') setUser(account.value.user);
        if (health.status === 'fulfilled') setDemoMode(Boolean(health.value.demo_mode));
      })
      .finally(() => { if (active) setCheckingSession(false); });
    return () => { active = false; };
  }, []);

  if (checkingSession) return <div className="loading-screen"><div className="loading-mark"><ShieldCheck size={27} /></div><div className="loading-dots"><span /><span /><span /></div><p>Checking your secure session</p></div>;
  if (!user) return <AuthScreen demoMode={demoMode} onAuthenticated={(account) => setUser(account)} />;
  return <WorkspaceApp key={user.id} user={user} onLogout={async () => { try { await post('/api/auth/logout'); } finally { setUser(null); } }} />;
}

function WorkspaceApp({ user, onLogout }) {
  const [view, setView] = useState(user.role === 'admin' ? 'admin' : 'overview');
  const [dashboard, setDashboard] = useState(null);
  const [brand, setBrand] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [events, setEvents] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [health, setHealth] = useState(null);
  const [activeDraftId, setActiveDraftId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [mobileNav, setMobileNav] = useState(false);
  const [libraryTab, setLibraryTab] = useState('Guidelines');
  const [queueFilter, setQueueFilter] = useState('All');
  const [compose, setCompose] = useState(false);
  const [form, setForm] = useState({ title: '', channel: 'Instagram', text: '' });
  const isAdmin = user.role === 'admin';
  const canReview = isAdmin || user.role === 'reviewer';
  const initials = (user.name || user.email).split(/\s+/).map((part) => part[0]).join('').slice(0, 2).toUpperCase();

  const activeDraft = useMemo(
    () => drafts.find((draft) => draft.id === activeDraftId) || drafts[0] || null,
    [drafts, activeDraftId],
  );
  const orderedFindings = useMemo(
    () => [...(activeDraft?.findings || [])].sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity]),
    [activeDraft],
  );

  const refresh = useCallback(async () => {
    setError('');
    try {
      const [healthData, dashData, brandData, draftData, eventData, analyticsData] = await Promise.all([
        get('/api/health'),
        get('/api/dashboard'),
        get('/api/brand-library'),
        get('/api/drafts'),
        get('/api/audit-log'),
        get('/api/analytics'),
      ]);
      setHealth(healthData);
      setDashboard(dashData);
      setBrand(brandData);
      setDrafts(draftData);
      setEvents(eventData);
      setAnalytics(analyticsData);
      setActiveDraftId((current) => current || draftData[0]?.id || null);
    } catch (err) {
      setError(err.message || 'Could not connect to the BrandGuard API.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => {
    if (!toast) return undefined;
    const timer = window.setTimeout(() => setToast(''), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const reloadDraft = async (draftId) => {
    const [draft, allDrafts, dash, log, stats] = await Promise.all([
      get('/api/drafts/' + draftId),
      get('/api/drafts'),
      get('/api/dashboard'),
      get('/api/audit-log'),
      get('/api/analytics'),
    ]);
    setDrafts(allDrafts);
    setDashboard(dash);
    setEvents(log);
    setAnalytics(stats);
    setActiveDraftId(draft.id);
  };

  const runAudit = async (draftId = activeDraft?.id, includeAi = false) => {
    if (!draftId) return;
    setBusy(true);
    try {
      await post('/api/drafts/' + draftId + '/audit', { include_ai: includeAi });
      await reloadDraft(draftId);
      setToast('Brand check complete. Findings are ready for review.');
    } catch (err) {
      setToast(err.message || 'The brand check could not run.');
    } finally {
      setBusy(false);
    }
  };

  const createDraft = async (event) => {
    event.preventDefault();
    if (form.title.trim().length < 2 || form.text.trim().length < 12) return;
    setBusy(true);
    try {
      const created = await post('/api/drafts', { ...form, author: 'Maya Chen' });
      setCompose(false);
      setForm({ title: '', channel: 'Instagram', text: '' });
      await refresh();
      setActiveDraftId(created.id);
      setView('content');
      setToast('Draft saved. Run a brand check when you are ready.');
    } catch (err) {
      setToast(err.message || 'Could not save the draft.');
    } finally {
      setBusy(false);
    }
  };

  const decideFinding = async (finding, decision, suggestion) => {
    if (!activeDraft) return;
    setBusy(true);
    try {
      await patch('/api/drafts/' + activeDraft.id + '/findings/' + finding.id, {
        decision,
        suggestion,
      });
      await reloadDraft(activeDraft.id);
      setToast(decision === 'rejected' ? 'Suggestion dismissed.' : 'Correction applied to the draft.');
    } catch (err) {
      setToast(err.message || 'Could not update this finding.');
    } finally {
      setBusy(false);
    }
  };

  const sendForReview = async () => {
    if (!activeDraft) return;
    setBusy(true);
    try {
      await post('/api/drafts/' + activeDraft.id + '/submit-review');
      await reloadDraft(activeDraft.id);
      setToast('Draft sent to the review queue.');
      setView('queue');
    } catch (err) {
      setToast(err.message || 'Could not send this draft for review.');
    } finally {
      setBusy(false);
    }
  };

  const decideReview = async (draft, action, comment = '') => {
    setBusy(true);
    try {
      await post('/api/drafts/' + draft.id + '/review', {
        action,
        comment,
      });
      await refresh();
      setToast(action === 'approved' ? 'Draft approved. The decision was added to the audit trail.' : 'Revision requested and recorded.');
    } catch (err) {
      setToast(err.message || 'Could not record the review decision.');
    } finally {
      setBusy(false);
    }
  };

  const publishDraft = async (draft) => {
    setBusy(true);
    try {
      await post('/api/drafts/' + draft.id + '/publish');
      await refresh();
      setToast('Draft published after approval and resolution of all findings.');
    } catch (err) {
      setToast(err.message || 'This draft is not ready to publish.');
    } finally {
      setBusy(false);
    }
  };

  const proposeRule = async (proposal) => {
    if (!activeDraft) return;
    setBusy(true);
    try {
      await post('/api/rule-proposals', { ...proposal, draft_id: activeDraft.id });
      setToast('Feedback submitted for administrator review. Approved rules were not changed.');
    } catch (err) {
      setToast(err.message || 'Could not submit this rule proposal.');
    } finally {
      setBusy(false);
    }
  };

  const navigate = (next) => {
    setView(next);
    setMobileNav(false);
    setCompose(false);
  };

  const startNewDraft = () => {
    setForm({ title: '', channel: 'Instagram', text: '' });
    setCompose(true);
    setView('content');
  };

  if (loading) {
    return <div className="loading-screen"><div className="loading-mark"><ShieldCheck size={27} /></div><div className="loading-dots"><span /><span /><span /></div><p>Preparing your brand workspace</p></div>;
  }

  if (error && !dashboard) {
    return (
      <div className="connection-screen">
        <div className="connection-card">
          <div className="brand-mark large"><ShieldCheck size={26} /></div>
          <p className="eyebrow">BRANDGUARD AI</p>
          <h1>Connect your demo workspace</h1>
          <p className="muted">The web app is ready, but the FastAPI service is not responding. Start the API using the setup guide, then reconnect.</p>
          <div className="connection-command">cd backend · uvicorn app.main:app --reload</div>
          <button className="button button-primary full-width" onClick={refresh}><Activity size={16} /> Retry connection</button>
          <a href="http://localhost:8000/docs" target="_blank" rel="noreferrer" className="small-link">Open API documentation <ArrowUpRight size={13} /></a>
        </div>
      </div>
    );
  }

  const activeMeta = pageMeta[view] || pageMeta.overview;

  return (
    <div className="app-shell">
      <div className={'sidebar-scrim ' + (mobileNav ? 'visible' : '')} onClick={() => setMobileNav(false)} />
      <aside className={'sidebar ' + (mobileNav ? 'sidebar-open' : '')}>
        <div className="sidebar-brand">
          <div className="brand-mark"><ShieldCheck size={21} strokeWidth={2.2} /></div>
          <div className="brand-wordmark"><span>brandguard</span><small>AI GOVERNANCE</small></div>
          <button className="icon-button sidebar-collapse" aria-label="Close navigation" onClick={() => setMobileNav(false)}><X size={16} /></button>
        </div>

        <button className="workspace-switch">
          <div className="workspace-logo">A</div>
          <span className="workspace-copy"><strong>{dashboard?.organization?.name || 'Brand workspace'}</strong><small>{user.role === 'admin' ? 'Admin workspace' : 'Team workspace'}</small></span>
          <ChevronDown size={15} />
        </button>

        <div className="nav-label">WORKSPACE</div>
        <nav className="main-nav">
          {navItems.slice(0, 1).map((item) => <NavLink key={item.id} item={item} active={view === item.id} onClick={() => navigate(item.id)} />)}
        </nav>
        <div className="nav-label nav-label-spaced">GOVERNANCE</div>
        <nav className="main-nav">
          {navItems.slice(1, 3).filter((item) => !item.reviewerOnly || canReview).map((item) => <NavLink key={item.id} item={item} active={view === item.id} onClick={() => navigate(item.id)} />)}
        </nav>
        <div className="nav-label nav-label-spaced">KNOWLEDGE & INSIGHTS</div>
        <nav className="main-nav">
          {navItems.slice(3).filter((item) => !item.adminOnly || isAdmin).map((item) => <NavLink key={item.id} item={item} active={view === item.id} onClick={() => navigate(item.id)} />)}
        </nav>

        <div className="sidebar-spacer" />
        <div className="sidebar-tip">
          <div className="tip-icon"><Lightbulb size={15} /></div>
          <div><strong>Good governance, made simple.</strong><p>Every finding is linked to an approved source.</p></div>
        </div>
        <button className="sidebar-bottom-link" onClick={onLogout}><Settings2 size={16} /> Sign out</button>
        <div className="profile-row">
          <div className="avatar avatar-sage">{initials}</div>
          <div className="profile-copy"><strong>{user.name}</strong><span>{user.role}</span></div>
          <button className="icon-button" aria-label="Sign out" onClick={onLogout}><X size={16} /></button>
        </div>
      </aside>

      <main className="main-column">
        <header className="topbar">
          <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMobileNav(true)}><Menu size={20} /></button>
          <div className="breadcrumbs"><span>{activeMeta[0]}</span><ChevronRight size={14} /><strong>{activeMeta[1]}</strong></div>
          <div className="topbar-actions">
            <label className="search-field"><Search size={16} /><input aria-label="Search" placeholder="Search anything..." onKeyDown={(e) => e.key === 'Enter' && setToast('Search is ready for workspace data.')} /><kbd>⌘ K</kbd></label>
            <div className="top-divider" />
            <div className="session-role-pill"><ShieldCheck size={14} /><span>{user.role}</span></div>
            <div className="demo-mode-pill"><span /> {health?.demo_mode ? 'Demo mode' : 'Secure session'}</div>
            {canReview && <button className="top-icon-button notification-button" aria-label="Notifications" onClick={() => navigate('queue')}><Bell size={18} /><span /></button>}
            <button className="avatar avatar-sage top-avatar top-profile" onClick={onLogout} aria-label="Sign out">{initials}</button>
          </div>
        </header>

        <div className="page-scroll">
          {view === 'overview' && <OverviewPage dashboard={dashboard} events={events} onNavigate={navigate} onNewDraft={startNewDraft} onOpenDraft={(id) => { setActiveDraftId(id); setView('content'); }} />}
          {view === 'content' && (
            <ContentPage
              drafts={drafts} activeDraft={activeDraft} activeDraftId={activeDraftId} setActiveDraftId={setActiveDraftId} health={health}
              compose={compose} setCompose={setCompose} form={form} setForm={setForm} onCreate={createDraft}
              findings={orderedFindings} onAudit={runAudit} onDecision={decideFinding}
              onSubmitReview={sendForReview} busy={busy} role={user.role} canReview={canReview} onNewDraft={startNewDraft} onProposeRule={proposeRule}
              onApprove={(draft) => decideReview(draft, 'approved', 'Approved after human review.')}
              onRequestChanges={(draft) => decideReview(draft, 'changes_requested', 'Please review the open findings and update the approved claims.')}
              onPublish={publishDraft}
            />
          )}
          {view === 'queue' && canReview && <QueuePage drafts={drafts} filter={queueFilter} setFilter={setQueueFilter} role={user.role} onOpen={(id) => { setActiveDraftId(id); setView('content'); }} onReview={decideReview} busy={busy} />}
          {view === 'library' && <LibraryPage brand={brand} tab={libraryTab} setTab={setLibraryTab} onRefresh={refresh} onNotify={setToast} canManage={isAdmin} />}
          {view === 'history' && <HistoryPage events={events} />}
          {view === 'analytics' && <AnalyticsPage analytics={analytics} dashboard={dashboard} onOpenLibrary={() => navigate('library')} />}
          {view === 'admin' && isAdmin && <AdminPage onNotify={setToast} onOpenDraft={(id) => { setActiveDraftId(id); setView('content'); }} />}
        </div>
      </main>
      {toast && <div className="toast"><CheckCircle2 size={17} />{toast}<button onClick={() => setToast('')} aria-label="Dismiss"><X size={15} /></button></div>}
    </div>
  );
}

function NavLink({ item, active, onClick }) {
  const Icon = item.icon;
  return <button className={'nav-link ' + (active ? 'active' : '')} onClick={onClick}><Icon size={18} strokeWidth={active ? 2.1 : 1.8} /><span>{item.label}</span>{item.badge && <b>{item.badge}</b>}</button>;
}

function SectionTitle({ eyebrow, title, description, action }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>{action}</div>;
}

function OverviewPage({ dashboard, events, onNavigate, onNewDraft, onOpenDraft }) {
  const metrics = dashboard?.metrics || {};
  const firstDraft = dashboard?.drafts?.[0];
  const activeIssues = firstDraft?.findings?.filter((item) => item.decision === 'open') || [];
  const criticalCount = activeIssues.filter((item) => item.severity === 'critical').length;
  return (
    <div className="page-content">
      <div className="welcome-line">
        <div><div className="eyebrow">{todayLabel} <span className="live-dot" /></div><h1>Good morning, Maya <span className="wave">✦</span></h1><p>Your brand is looking consistent. Here’s what needs your attention today.</p></div>
        <div className="welcome-actions"><button className="button button-secondary" onClick={() => onNavigate('analytics')}><BarChart3 size={16} /> View insights</button><button className="button button-primary" onClick={onNewDraft}><Plus size={17} /> New content check</button></div>
      </div>
      <div className="metric-grid">
        <MetricCard icon={ShieldCheck} iconTone="green" label="Brand alignment" value={(metrics.brand_score ?? 92) + '%'} foot="↑ 4 pts this month" footTone="positive" ring={metrics.brand_score ?? 92} />
        <MetricCard icon={Clock3} iconTone="blue" label="Awaiting review" value={metrics.awaiting_review ?? 3} foot="Across 2 content channels" footTone="neutral" />
        <MetricCard icon={AlertCircle} iconTone="amber" label="Open findings" value={metrics.open_findings ?? 6} foot={(metrics.critical_findings ?? 2) + ' critical need attention'} footTone="warning" />
        <MetricCard icon={TrendingUp} iconTone="purple" label="Approval rate" value={(metrics.approval_rate ?? 94) + '%'} foot="↑ 6% vs. last month" footTone="positive" />
      </div>
      <div className="dashboard-grid">
        <section className="panel attention-panel">
          <div className="panel-heading"><div><div className="eyebrow">ACTION NEEDED</div><h2>Needs your attention</h2></div><button className="text-button" onClick={() => onNavigate('queue')}>View queue <ArrowRight size={14} /></button></div>
          {firstDraft ? (
            <div className="attention-card">
              <div className="attention-card-top"><div className="channel-icon instagram-icon"><Layers3 size={17} /></div><div className="attention-title"><strong>{firstDraft.title}</strong><span>{firstDraft.author} · {firstDraft.channel} · {prettyDate(firstDraft.updated_at)}</span></div><span className="status-pill status-review">Needs review</span></div>
              <p className="attention-excerpt">“{firstDraft.text.slice(0, 146)}{firstDraft.text.length > 146 ? '…' : ''}”</p>
              <div className="attention-bottom"><div className="issue-count"><span className="issue-dot critical" />{criticalCount} critical <span className="issue-dot high" />{activeIssues.filter((f) => f.severity === 'high').length} high <span className="issue-dot medium" />{activeIssues.filter((f) => ['medium', 'low'].includes(f.severity)).length} other</div><button className="button button-dark small-button" onClick={() => onOpenDraft(firstDraft.id)}>Review content <ArrowRight size={14} /></button></div>
            </div>
          ) : <EmptyState icon={FileText} title="No drafts yet" text="Create a draft to start your first brand check." action={<button className="button button-primary" onClick={onNewDraft}><Plus size={15} /> Start a check</button>} />}
          <div className="quick-actions"><button onClick={() => onNavigate('library')}><BookOpen size={16} /><span><strong>Update brand knowledge</strong><small>Keep approved sources current</small></span><ChevronRight size={15} /></button><button onClick={() => onNavigate('analytics')}><Gauge size={16} /><span><strong>See recurring patterns</strong><small>Find what your team can improve</small></span><ChevronRight size={15} /></button></div>
        </section>
        <section className="panel health-panel">
          <div className="panel-heading"><div><div className="eyebrow">BRAND HEALTH</div><h2>Looking good</h2></div><button className="icon-button subtle"><MoreHorizontal size={19} /></button></div>
          <div className="health-summary"><div className="health-ring"><div><strong>{metrics.brand_score ?? 92}</strong><span>out of 100</span></div></div><div className="health-copy"><div className="health-chip"><span /> Consistent this week</div><p>Your team is following the approved voice and messaging across channels.</p></div></div>
          <div className="health-divider" />
          <div className="health-breakdown"><span>Guideline adherence</span><div className="mini-progress"><i style={{ width: '94%' }} /></div><b>94%</b></div>
          <div className="health-breakdown"><span>Terminology</span><div className="mini-progress"><i style={{ width: '89%' }} /></div><b>89%</b></div>
          <div className="health-breakdown"><span>Approved claims</span><div className="mini-progress"><i style={{ width: '97%' }} /></div><b>97%</b></div>
          <button className="health-link" onClick={() => onNavigate('analytics')}>Explore brand health <ArrowRight size={14} /></button>
        </section>
        <section className="panel activity-panel">
          <div className="panel-heading"><div><div className="eyebrow">LATEST UPDATES</div><h2>Recent activity</h2></div><button className="text-button" onClick={() => onNavigate('history')}>Full history <ArrowRight size={14} /></button></div>
          <ActivityList events={events.slice(0, 4)} />
        </section>
        <section className="panel insight-panel">
          <div className="insight-icon"><Sparkles size={19} /></div><div className="insight-copy"><div className="eyebrow">A QUICK INSIGHT</div><h3>One small habit makes a big difference</h3><p>Most recent issues came from outdated offer details. Add an expiry date to promotional facts so they stay fresh.</p><button className="text-button" onClick={() => onNavigate('library')}>Review approved facts <ArrowRight size={14} /></button></div><div className="insight-decoration">✳</div>
        </section>
      </div>
      <div className="page-footnote"><Shield size={13} /> Human review stays in control. BrandGuard AI supports decisions; it never publishes content.</div>
    </div>
  );
}

function MetricCard({ icon: Icon, iconTone, label, value, foot, footTone, ring }) {
  return <div className="metric-card"><div className="metric-top"><div className={'metric-icon ' + iconTone}><Icon size={17} /></div>{ring && <div className="metric-trend"><ArrowUpRight size={13} /> 4.8%</div>}</div><div className="metric-label">{label}</div><div className="metric-value">{value}</div><div className={'metric-foot ' + footTone}>{footTone === 'positive' && <ArrowUpRight size={13} />}{footTone === 'warning' && <AlertCircle size={13} />}{foot}</div></div>;
}

function ContentPage({ drafts, activeDraft, activeDraftId, setActiveDraftId, health, compose, setCompose, form, setForm, onCreate, findings, onAudit, onDecision, onSubmitReview, busy, role, canReview, onNewDraft, onApprove, onRequestChanges, onPublish, onProposeRule }) {
  const [suggestions, setSuggestions] = useState({});
  const [includeGemini, setIncludeGemini] = useState(false);
  useEffect(() => { setIncludeGemini(false); }, [activeDraftId]);
  const openCount = findings.filter((finding) => finding.decision === 'open').length;
  const acceptedCount = findings.filter((finding) => finding.decision === 'accepted').length;
  const displayedText = activeDraft?.text || '';
  const renderExcerpt = (text) => {
    if (!displayedText || !text) return displayedText;
    const index = displayedText.toLowerCase().indexOf(text.toLowerCase());
    if (index < 0) return displayedText;
    return <>{displayedText.slice(0, index)}<mark>{displayedText.slice(index, index + text.length)}</mark>{displayedText.slice(index + text.length)}</>;
  };
  return (
    <div className="page-content content-page">
      <SectionTitle eyebrow="PRE-PUBLICATION WORKFLOW" title="Content review" description="Check a draft against approved brand knowledge before it goes live." action={<button className="button button-primary" onClick={onNewDraft}><Plus size={16} /> New content</button>} />
      {compose ? (
        <form className="compose-panel" onSubmit={onCreate}>
          <div className="compose-heading"><div><h2>Start a new content check</h2><p>Paste a draft and choose where it will appear.</p></div><button type="button" className="icon-button" onClick={() => setCompose(false)} aria-label="Close"><X size={18} /></button></div>
          <div className="compose-fields"><label>Content title<input required minLength="2" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="e.g. Daily Veil launch announcement" /></label><label>Channel<select value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}><option>Instagram</option><option>Email</option><option>Blog</option><option>Paid ad</option><option>Website</option><option>Press release</option></select></label></div>
          <label className="compose-copy-label">Draft copy<textarea required minLength="12" rows="7" value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} placeholder="Paste the content you want to review…" /></label>
          <div className="compose-footer"><span><ShieldCheck size={15} /> Your draft stays in this demo workspace.</span><button className="button button-primary" type="submit" disabled={busy}><FilePlus2 size={15} /> Save draft</button></div>
        </form>
      ) : (
        <>
          <div className="audit-toolbar">
            <div className="draft-picker"><FileText size={17} /><select value={activeDraft?.id || activeDraftId || ''} onChange={(e) => setActiveDraftId(e.target.value)} aria-label="Choose draft">{drafts.map((draft) => <option key={draft.id} value={draft.id}>{draft.title}</option>)}</select><ChevronDown size={14} /></div>
            <div className="audit-toolbar-right"><span className="saved-indicator"><span /> Saved {activeDraft ? prettyDate(activeDraft.updated_at) : ''}</span><button className="button button-secondary" onClick={() => setCompose(true)}><Plus size={15} /> New draft</button></div>
          </div>
          {!activeDraft ? <EmptyState icon={FileText} title="Create a draft to begin" text="Your content audit will show here." action={<button className="button button-primary" onClick={() => setCompose(true)}>Create a draft</button>} /> : (
            <>
              <div className="audit-layout">
                <section className="panel editor-panel">
                  <div className="editor-heading"><div><div className="eyebrow">DRAFT CONTENT</div><h2>{activeDraft.title}</h2><div className="draft-meta"><span className="channel-tag"><Layers3 size={13} /> {activeDraft.channel}</span><span>Created by {activeDraft.author}</span><span>Revision {activeDraft.revision}</span></div></div><button className="icon-button" aria-label="More draft options"><MoreHorizontal size={18} /></button></div>
                  <div className="editor-document"><div className="document-label"><span>CONTENT</span><span>{activeDraft.text.length} characters</span></div><div className="document-copy">{findings.some((item) => item.decision === 'open') ? renderExcerpt(findings.find((item) => item.decision === 'open')?.excerpt) : displayedText}</div></div>
                  <div className="ai-consent-row"><label className={'ai-consent ' + (!health?.gemini_configured ? 'disabled' : '')}><input type="checkbox" checked={includeGemini} disabled={!health?.gemini_configured} onChange={(e) => setIncludeGemini(e.target.checked)} /><span><strong>Include optional Gemini review</strong><small>{health?.gemini_configured ? 'Your draft text will be sent to Google for added analysis.' : 'Set a Gemini key in the server environment to enable.'}</small></span></label><div className="editor-tip"><ShieldCheck size={14} /><span>Deterministic checks run without external AI.</span></div></div>
                  <div className="editor-bottom"><div className="editor-tip"><Sparkles size={15} /><span>Findings cite approved brand sources.</span></div><button className="button button-dark" onClick={() => onAudit(activeDraft.id, includeGemini)} disabled={busy}><Zap size={15} />{busy ? 'Checking…' : 'Run brand check'}</button></div>
                  {activeDraft.review_comment && <div className="review-note"><MessageSquareText size={15} /><div><strong>Reviewer note</strong><span>{activeDraft.review_comment}</span></div></div>}
                  {activeDraft.status !== 'published' && <div className="submit-review-row"><div><strong>Human approval before publication</strong><span>{activeDraft.status === 'approved' ? 'Approved. Resolve every remaining finding to enable publication.' : 'Send this checked draft to an authorized reviewer.'}</span></div><div className="inline-actions">{activeDraft.status !== 'in_review' && <button className="button button-secondary" onClick={onSubmitReview} disabled={busy || !activeDraft.analysis_mode}><Send size={14} /> Submit for review</button>}{canReview && ['in_review', 'needs_review', 'changes_requested'].includes(activeDraft.status) && <><button className="button button-quiet" onClick={() => onRequestChanges(activeDraft)} disabled={busy}>Request changes</button><button className="button button-primary" onClick={() => onApprove(activeDraft)} disabled={busy}><BadgeCheck size={15} /> Approve</button></>}{canReview && activeDraft.status === 'approved' && <button className="button button-primary" onClick={() => onPublish(activeDraft)} disabled={busy || openCount > 0}><Globe2 size={14} /> Publish</button>}</div></div>}
                </section>
                <section className="audit-summary-panel">
                  <div className="summary-head"><div><span className="eyebrow">BRAND CHECK</span><h2>Review report</h2></div><div className="report-glyph"><ShieldCheck size={18} /></div></div>
                  <div className="report-score-row"><div className="report-score"><strong>{Math.max(42, 100 - (findings.length * 8))}</strong><span>/ 100</span></div><div className="report-score-copy"><strong>{openCount ? 'A few things to review' : 'Ready for review'}</strong><span>{activeDraft.analysis_mode || 'Run a check to analyze this draft'}</span></div></div>
                  <div className="severity-stack"><SeverityRow label="Critical" count={findings.filter((f) => f.severity === 'critical' && f.decision === 'open').length} tone="critical" /><SeverityRow label="High" count={findings.filter((f) => f.severity === 'high' && f.decision === 'open').length} tone="high" /><SeverityRow label="Medium & low" count={findings.filter((f) => ['medium', 'low'].includes(f.severity) && f.decision === 'open').length} tone="medium" /></div>
                  <div className="report-note"><Lightbulb size={15} /><span>Suggested changes keep the author's intent. You decide what to apply.</span></div>
                  <div className="report-provider"><span className="provider-dot" /><span>{activeDraft.provider_note || 'The demo checks approved facts and terminology without external AI.'}</span></div>
                </section>
              </div>
              <div className="findings-heading"><div><div className="eyebrow">EVIDENCE & ACTIONS</div><h2>Findings <span>{findings.length}</span></h2></div><div className="findings-filter"><ListFilter size={15} /><span>Severity ranked</span></div></div>
              {findings.length ? <div className="finding-list">{findings.map((finding) => <FindingCard key={finding.id} finding={finding} suggestion={suggestions[finding.id] ?? finding.suggestion} setSuggestion={(value) => setSuggestions((current) => ({ ...current, [finding.id]: value }))} onDecision={onDecision} busy={busy} />)}</div> : <EmptyState icon={ShieldCheck} title="No findings yet" text="Run the brand check to compare this draft with the approved brand library." />}
              <RuleProposalForm onSubmit={onProposeRule} busy={busy} />
              <div className="audit-disclaimer"><Shield size={14} /> BrandGuard AI supports review. It does not guarantee compliance or publish content automatically.</div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function RuleProposalForm({ onSubmit, busy }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: '', proposed_text: '', rationale: '' });
  if (!open) return <div className="rule-feedback"><span><Lightbulb size={15} /> Have feedback that could improve brand guidance?</span><button className="text-button" onClick={() => setOpen(true)}>Propose a rule update <ArrowRight size={13} /></button></div>;
  return <form className="rule-proposal-form" onSubmit={async (event) => { event.preventDefault(); await onSubmit(form); setForm({ title: '', proposed_text: '', rationale: '' }); setOpen(false); }}><div><strong>Propose an improvement</strong><p>Your suggestion goes to an administrator for review. It will not change approved rules unless approved.</p></div><label>Proposal title<input required minLength="3" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label><label>Proposed guidance<textarea required minLength="12" rows="3" value={form.proposed_text} onChange={(e) => setForm({ ...form, proposed_text: e.target.value })} /></label><label>Why should this change?<textarea required minLength="8" rows="2" value={form.rationale} onChange={(e) => setForm({ ...form, rationale: e.target.value })} /></label><div className="inline-actions"><button type="button" className="button button-quiet" onClick={() => setOpen(false)}>Cancel</button><button className="button button-primary" disabled={busy}>Submit for admin review</button></div></form>;
}

function SeverityRow({ label, count, tone }) { return <div className="severity-row"><span className={'severity-dot ' + tone} /><span>{label}</span><strong>{count}</strong></div>; }

function FindingCard({ finding, suggestion, setSuggestion, onDecision, busy }) {
  const [expanded, setExpanded] = useState(true);
  const complete = finding.decision !== 'open';
  return (
    <article className={'finding-card ' + (complete ? 'finding-complete' : '')}>
      <div className="finding-topline">
        <div className={'severity-icon ' + finding.severity}>{finding.severity === 'critical' ? <AlertCircle size={16} /> : finding.severity === 'high' ? <AlertCircle size={16} /> : finding.severity === 'medium' ? <Lightbulb size={16} /> : <SpellCheck size={16} />}</div>
        <span className={'severity-label ' + finding.severity}>{finding.severity}</span><span className="finding-category">{finding.category}</span><span className="confidence"><Target size={12} /> {finding.confidence}% match</span>
        {complete && <span className={'decision-label ' + finding.decision}>{finding.decision === 'accepted' ? <><Check size={13} /> Applied</> : <><X size={13} /> Dismissed</>}</span>}
        <button className="icon-button finding-toggle" onClick={() => setExpanded(!expanded)} aria-label={expanded ? 'Collapse finding' : 'Expand finding'}>{expanded ? <ChevronDown size={17} /> : <ChevronRight size={17} />}</button>
      </div>
      <h3>{finding.title}</h3>
      <p className="finding-explanation">{finding.explanation}</p>
      {expanded && <div className="finding-detail-grid">
        <div className="evidence-box"><div className="box-label"><span className="evidence-mark" /> FLAGGED TEXT</div><div className="quote-text">“{finding.excerpt}”</div><div className="source-reference"><BookOpen size={13} /><span>From draft</span></div></div>
        <div className="evidence-box approved-box"><div className="box-label"><span className="approved-mark" /> APPROVED SOURCE</div><div className="approved-source-title">{finding.source_title}</div><div className="approved-source-copy">“{finding.source_excerpt || 'Review this language against the approved brand guidelines.'}”</div><div className="source-reference"><FileCheck2 size={13} /><span>Evidence reference</span><ArrowUpRight size={12} /></div></div>
        <div className="suggestion-box"><div className="box-label"><Sparkles size={13} /> SUGGESTED CORRECTION</div>{!complete ? <textarea aria-label="Edit suggested correction" value={suggestion || ''} onChange={(e) => setSuggestion(e.target.value)} rows={2} /> : <div className="accepted-suggestion">{suggestion || 'Suggestion dismissed by reviewer.'}</div>}{!complete && <div className="suggestion-actions"><button className="button button-primary mini-button" onClick={() => onDecision(finding, suggestion === finding.suggestion ? 'accepted' : 'edited', suggestion)} disabled={busy || !suggestion}><Check size={14} /> Apply correction</button><button className="button button-quiet mini-button" onClick={() => onDecision(finding, 'rejected', '')} disabled={busy}><X size={14} /> Dismiss</button></div>}</div>
      </div>}
    </article>
  );
}

function QueuePage({ drafts, filter, setFilter, role, onOpen, onReview, busy }) {
  const queued = drafts.filter((draft) => ['needs_review', 'in_review', 'changes_requested'].includes(draft.status));
  const shown = filter === 'All' ? queued : queued.filter((draft) => draft.status === filter.toLowerCase().replaceAll(' ', '_'));
  return (
    <div className="page-content">
      <SectionTitle eyebrow="HUMAN OVERSIGHT" title="Review queue" description="Give every piece of content a thoughtful human decision before it is published." action={<div className="queue-status"><span className="live-dot" /> {queued.length} items waiting</div>} />
      <div className="queue-toolbar"><div className="queue-tabs">{['All', 'Needs review', 'In review', 'Changes requested'].map((item) => <button key={item} className={filter === item ? 'selected' : ''} onClick={() => setFilter(item)}>{item}<span>{item === 'All' ? queued.length : queued.filter((draft) => draft.status === item.toLowerCase().replaceAll(' ', '_')).length}</span></button>)}</div><button className="button button-secondary"><Filter size={15} /> Filter</button></div>
      {shown.length ? <div className="queue-list">{shown.map((draft, index) => {
        const open = draft.findings?.filter((finding) => finding.decision === 'open') || [];
        return <article className="queue-card" key={draft.id}><div className="queue-card-main"><div className={'queue-avatar queue-avatar-' + (index % 4)}>{(draft.author || 'M').split(' ').map((word) => word[0]).join('').slice(0, 2)}</div><div className="queue-card-copy"><div className="queue-title-line"><h3>{draft.title}</h3><span className={'status-pill status-' + draft.status}>{draft.status.replaceAll('_', ' ')}</span></div><p>{draft.author} <span>·</span> {draft.channel} <span>·</span> Submitted {prettyDate(draft.updated_at)}</p><div className="queue-issue-line"><span className="issue-counter"><AlertCircle size={13} /> {open.length} open findings</span><span className="queue-score"><ShieldCheck size={13} /> {Math.max(42, 100 - open.length * 8)} score</span></div></div></div><div className="queue-card-actions"><button className="button button-secondary" onClick={() => onOpen(draft.id)}>Inspect findings</button>{role !== 'member' && <><button className="icon-button queue-revise" title="Request changes" onClick={() => onReview(draft, 'changes_requested', 'Please review the open findings and update the approved claims.') } disabled={busy}><MessageSquareText size={16} /></button><button className="button button-primary" onClick={() => onReview(draft, 'approved', 'Approved after human review.')} disabled={busy}><Check size={15} /> Approve</button></>}</div></article>;
      })}</div> : <EmptyState icon={BadgeCheck} title="All caught up" text="There are no drafts in this queue for the selected view." />}
      <div className="queue-human-note"><Users size={17} /><div><strong>Automation informs. People decide.</strong><span>Only an authorized reviewer can record a final approval decision.</span></div><button className="text-button" onClick={() => setFilter('All')}>How approvals work <ArrowRight size={14} /></button></div>
    </div>
  );
}

function LibraryPage({ brand, tab, setTab, onRefresh, onNotify, canManage }) {
  const [sourceModal, setSourceModal] = useState(false);
  const [sourceForm, setSourceForm] = useState({ title: '', type: 'Guideline', content: '' });
  const [savingSource, setSavingSource] = useState(false);
  const tabs = ['Guidelines', 'Approved facts', 'Terminology', 'Assets'];
  const sourceItems = brand?.sources || [];
  const facts = brand?.facts || [];
  const terms = brand?.terminology || [];
  const assets = brand?.assets || [];
  return (
    <div className="page-content">
      <SectionTitle eyebrow="APPROVED SOURCE OF TRUTH" title="Brand library" description="The knowledge that powers every review. Keep it current, clear, and easy to trust." action={canManage && <button className="button button-primary" onClick={() => setSourceModal(true)}><Plus size={15} /> Add guideline</button>} />
      <div className="library-overview"><div className="library-overview-icon"><BookOpen size={20} /></div><div><strong>{brand?.organization?.name || 'Aster & Oak'} brand profile</strong><span>Approved for use across {sourceItems.length + facts.length + terms.length + assets.length} knowledge items</span></div><div className="library-updated"><span className="live-dot" /> All sources current</div></div>
      <div className="library-tabs">{tabs.map((item) => <button key={item} className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{item}<span>{item === 'Guidelines' ? sourceItems.length : item === 'Approved facts' ? facts.length : item === 'Terminology' ? terms.length : assets.length}</span></button>)}</div>
      {tab === 'Guidelines' && <div className="source-grid">{sourceItems.map((source, index) => <article className="source-card" key={source.id}><div className="source-card-top"><div className={'source-type-icon source-type-' + index}><BookOpen size={17} /></div><span className="approved-pill"><Check size={12} /> {source.status}</span><button className="icon-button"><MoreHorizontal size={17} /></button></div><div className="eyebrow">{source.type}</div><h3>{source.title}</h3><p>{source.summary}</p><div className="source-card-foot"><span><Clock3 size={13} /> Updated {source.updated}</span><button className="text-button">View source <ArrowRight size={13} /></button></div></article>)}</div>}
      {tab === 'Approved facts' && <div className="facts-table panel"><div className="table-head"><span>APPROVED FACT</span><span>VALUE</span><span>STATUS</span><span>LAST UPDATED</span></div>{facts.map((fact) => <div className="fact-row" key={fact.id}><div className="fact-name"><span className="fact-icon"><BadgeCheck size={15} /></span><span><strong>{fact.title}</strong><small>{fact.source_excerpt}</small></span></div><strong className="fact-value">{fact.match_key === 'hydration' ? fact.value + ' hours' : fact.match_key === 'discount' ? fact.value + '% off' : fact.value}</strong><span className="approved-pill"><Check size={12} /> Approved</span><span className="fact-date">{fact.updated}</span></div>)}</div>}
      {tab === 'Terminology' && <div className="terms-grid">{terms.map((term) => <article className="term-card panel" key={term.id}><div className="term-heading"><div className="term-icon"><SpellCheck size={16} /></div><span className="approved-pill"><Check size={12} /> Active</span></div><div className="term-map"><div><span>PREFERRED</span><strong>{term.preferred}</strong></div><ArrowRight size={16} /><div><span>AVOID</span><strong className="term-avoid">{term.avoid.join(', ')}</strong></div></div><p>{term.reason}</p></article>)}</div>}
      {tab === 'Assets' && <div className="asset-grid">{assets.map((asset, index) => <article className="asset-card panel" key={asset.id}><div className={'asset-preview asset-preview-' + index}><span className="asset-monogram">{index === 0 ? 'A&O' : 'A'}</span><span className="asset-stamp">{asset.type}</span></div><div className="asset-info"><div><h3>{asset.name}</h3><p>{asset.details}</p></div><span className="approved-pill"><Check size={12} /> {asset.status}</span></div></article>)}</div>}
      <div className="library-footnote"><ShieldCheck size={15} /><span>Reviews use only knowledge marked approved. Draft or expired sources are excluded from checks.</span></div>
      {canManage && sourceModal && <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setSourceModal(false)}><form className="source-modal" onSubmit={async (e) => { e.preventDefault(); setSavingSource(true); try { await post('/api/brand-library/sources', sourceForm); await onRefresh(); setSourceModal(false); setSourceForm({ title: '', type: 'Guideline', content: '' }); onNotify('Approved source added to the brand library.'); } catch (err) { onNotify(err.message || 'Could not add this source.'); } finally { setSavingSource(false); } }}><div className="compose-heading"><div><div className="eyebrow">BRAND KNOWLEDGE</div><h2>Add an approved source</h2><p>New sources are available to future checks in this workspace.</p></div><button type="button" className="icon-button" onClick={() => setSourceModal(false)} aria-label="Close"><X size={18} /></button></div><label>Source title<input required minLength="2" value={sourceForm.title} onChange={(e) => setSourceForm({ ...sourceForm, title: e.target.value })} placeholder="e.g. Product claims guide" /></label><label>Source type<select value={sourceForm.type} onChange={(e) => setSourceForm({ ...sourceForm, type: e.target.value })}><option>Guideline</option><option>Messaging policy</option><option>Campaign guidance</option></select></label><label>Approved content<textarea required minLength="12" rows="6" value={sourceForm.content} onChange={(e) => setSourceForm({ ...sourceForm, content: e.target.value })} placeholder="Paste approved guidance or source text…" /></label><div className="compose-footer"><span><ShieldCheck size={14} /> Stored in this workspace.</span><button className="button button-primary" type="submit" disabled={savingSource}><Check size={14} /> {savingSource ? 'Saving…' : 'Add approved source'}</button></div></form></div>}
    </div>
  );
}

function HistoryPage({ events }) {
  const [query, setQuery] = useState('');
  const filtered = events.filter((event) => (event.draft_title + event.action + event.actor).toLowerCase().includes(query.toLowerCase()));
  return (
    <div className="page-content">
      <SectionTitle eyebrow="TRACEABLE BY DESIGN" title="Audit history" description="A clear record of how content changes and decisions were made." action={<button className="button button-secondary" onClick={() => window.print()}><Copy size={15} /> Export history</button>} />
      <div className="history-overview"><div className="history-stat"><div className="history-stat-icon"><History size={17} /></div><div><strong>{events.length}</strong><span>recent events</span></div></div><div className="history-stat"><div className="history-stat-icon purple"><Users size={17} /></div><div><strong>3</strong><span>active reviewers</span></div></div><div className="history-stat"><div className="history-stat-icon amber"><Clock3 size={17} /></div><div><strong>Every action</strong><span>is time-stamped</span></div></div></div>
      <div className="history-list-panel panel"><div className="history-list-heading"><div><h2>Recent activity</h2><span>All workspace actions</span></div><label className="search-field history-search"><Search size={15} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search the audit log" /></label></div><ActivityList events={filtered} detailed /></div>
    </div>
  );
}

function AnalyticsPage({ analytics, dashboard, onOpenLibrary }) {
  const metrics = dashboard?.metrics || {};
  const bars = analytics?.weekly_activity || [];
  const categoryCounts = analytics?.category_counts || {};
  const maxCount = Math.max(...Object.values(categoryCounts), 1);
  const categoryNames = Object.keys(categoryCounts).length ? Object.keys(categoryCounts) : ['Approved facts', 'Claims', 'Terminology'];
  return (
    <div className="page-content">
      <SectionTitle eyebrow="GOVERNANCE INSIGHTS" title="Analytics" description="Spot repeat patterns and improve the guidance your team relies on." action={<button className="button button-secondary"><Clock3 size={15} /> Last 30 days <ChevronDown size={14} /></button>} />
      <div className="demo-data-note"><Sparkles size={14} /><span>Illustrative demo baseline plus activity in this workspace. Replace sample records before using analytics operationally.</span></div>
      <div className="analytics-kpis"><MetricCard icon={FileText} iconTone="green" label="Content reviewed" value={analytics?.total_drafts || 27} foot="↑ 12% from last month" footTone="positive" /><MetricCard icon={BadgeCheck} iconTone="blue" label="Approved" value={analytics?.approved || 18} foot="After human review" footTone="neutral" /><MetricCard icon={Gauge} iconTone="purple" label="Approval rate" value={(metrics.approval_rate || 94) + '%'} foot="↑ 6% this month" footTone="positive" /><MetricCard icon={Clock3} iconTone="amber" label="Avg. review time" value={(metrics.avg_review_hours || 2.4) + 'h'} foot="↓ 18% faster" footTone="positive" /></div>
      <div className="analytics-grid">
        <section className="panel chart-panel"><div className="panel-heading"><div><div className="eyebrow">WORKFLOW ACTIVITY</div><h2>Reviews over time</h2></div><div className="chart-legend"><span /> Content reviews</div></div><div className="chart-total"><strong>{analytics?.total_drafts || 27}</strong><span>items reviewed</span><em><ArrowUpRight size={13} /> 12.4%</em></div><div className="bar-chart">{bars.map((item, index) => <div className="chart-column" key={item.day}><div className="bar-pair"><i style={{ height: item.value + '%' }} className={index === 5 ? 'highlight' : ''} /><i style={{ height: Math.max(10, item.value * 0.55) + '%' }} /></div><span>{item.day}</span></div>)}</div></section>
        <section className="panel category-panel"><div className="panel-heading"><div><div className="eyebrow">RECURRING FINDINGS</div><h2>What gets flagged</h2></div><button className="icon-button subtle"><MoreHorizontal size={18} /></button></div><div className="category-list">{categoryNames.map((name, index) => { const count = categoryCounts[name] || [8, 5, 3][index % 3]; return <div className="category-item" key={name}><div className="category-info"><span className={'category-bullet bullet-' + index} /><strong>{name}</strong><span>{count} issues</span></div><div className="category-track"><i style={{ width: Math.max(14, count / maxCount * 100) + '%' }} className={'category-fill fill-' + index} /></div></div>; })}</div><div className="category-insight"><Lightbulb size={15} /><span>Adding clearer claim guidance may prevent repeat flags.</span></div></section>
        <section className="panel outcomes-panel"><div className="panel-heading"><div><div className="eyebrow">REVIEW OUTCOMES</div><h2>Human decisions</h2></div><div className="outcome-period">Last 30 days</div></div><div className="outcome-circles"><div className="outcome-circle approved"><strong>72%</strong><span>Approved</span></div><div className="outcome-circle changes"><strong>22%</strong><span>Changes requested</span></div><div className="outcome-circle dismissed"><strong>6%</strong><span>Not approved</span></div></div><div className="outcomes-note"><Users size={15} /> People made the final call on every draft.</div></section>
        <section className="panel recommendations-panel"><div className="panel-heading"><div><div className="eyebrow">NEXT BEST ACTION</div><h2>Strengthen your guidance</h2></div><div className="recommend-icon"><Sparkles size={16} /></div></div><p>Update your promotion guidance with expiry dates. It can help creators avoid using offers after they end.</p><button className="button button-secondary" onClick={onOpenLibrary}>Open brand library <ArrowRight size={14} /></button></section>
      </div>
    </div>
  );
}

function ActivityList({ events, detailed = false }) {
  if (!events?.length) return <div className="activity-empty">No activity has been recorded yet.</div>;
  return <div className={'activity-list ' + (detailed ? 'detailed' : '')}>{events.map((event, index) => {
    const action = (event.action || '').toLowerCase();
    const tone = action.includes('approv') ? 'success' : action.includes('suggestion') ? 'purple' : action.includes('changes') ? 'amber' : 'blue';
    const icon = action.includes('approv') ? <Check size={14} /> : action.includes('suggestion') ? <Sparkles size={14} /> : action.includes('changes') ? <MessageSquareText size={14} /> : <FileCheck2 size={14} />;
    return <div className="activity-row" key={event.id || index}><div className={'activity-icon ' + tone}>{icon}</div><div className="activity-copy"><strong>{event.action}</strong><span>{event.actor} · {event.draft_title}</span>{detailed && <small>{event.detail}</small>}</div><time>{prettyDate(event.created_at)}</time></div>;
  })}</div>;
}

function EmptyState({ icon: Icon, title, text, action }) {
  return <div className="empty-state"><div className="empty-icon"><Icon size={21} /></div><h3>{title}</h3><p>{text}</p>{action}</div>;
}

export default App;
