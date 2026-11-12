import { useCallback, useEffect, useState } from 'react';
import { BadgeCheck, Building2, Check, Clock3, FileText, Plus, RefreshCw, ShieldCheck, UserPlus, Users, X } from 'lucide-react';
import { get, patch, post } from './api.js';

const emptyInvite = { email: '', name: '', role: 'member', temporary_password: '' };

export default function AdminPage({ onNotify, onOpenDraft }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [org, setOrg] = useState({ name: '', industry: '', tagline: '' });
  const [invite, setInvite] = useState(emptyInvite);
  const [source, setSource] = useState({ title: '', type: 'Guideline', content: '' });
  const [fact, setFact] = useState({ title: '', value: '', match_key: '', source_excerpt: '' });
  const [term, setTerm] = useState({ preferred: '', avoid: '', reason: '', severity: 'medium' });

  const load = useCallback(async () => {
    const result = await get('/api/admin/dashboard');
    setData(result);
    setOrg({ name: result.organization?.name || '', industry: result.organization?.industry || '', tagline: result.organization?.tagline || '' });
  }, []);
  useEffect(() => { load().catch((err) => onNotify(err.message || 'Could not load the admin dashboard.')); }, [load, onNotify]);

  const run = async (action, message) => {
    setBusy(true);
    try { await action(); await load(); onNotify(message); }
    catch (err) { onNotify(err.message || 'That change could not be saved.'); }
    finally { setBusy(false); }
  };

  if (!data) return <div className="page-content"><div className="panel admin-loading">Loading organization administration…</div></div>;
  const metrics = data.metrics || {};

  return (
    <div className="page-content admin-page">
      <div className="page-heading"><div><div className="eyebrow">PROTECTED WORKSPACE</div><h1>Administration</h1><p>Manage members, approved brand knowledge, and proposed rule changes.</p></div><button className="button button-secondary" onClick={() => load()}><RefreshCw size={14} /> Refresh</button></div>
      <div className="admin-metrics">
        <div className="admin-stat"><Users size={17} /><strong>{metrics.active_users}/{metrics.users}</strong><span>active members</span></div>
        <div className="admin-stat"><Clock3 size={17} /><strong>{metrics.pending_proposals}</strong><span>proposals awaiting review</span></div>
        <div className="admin-stat"><BadgeCheck size={17} /><strong>{metrics.approved_rules}</strong><span>approved rules and facts</span></div>
        <div className="admin-stat"><FileText size={17} /><strong>{metrics.submissions}</strong><span>content submissions</span></div>
      </div>

      <div className="admin-grid">
        <section className="panel admin-panel">
          <div className="panel-heading"><div><div className="eyebrow">ORGANIZATION</div><h2>Workspace profile</h2></div><Building2 size={18} /></div>
          <form className="admin-form" onSubmit={(e) => { e.preventDefault(); run(() => patch('/api/admin/organization', org), 'Organization profile saved.'); }}>
            <label>Organization name<input required minLength="2" value={org.name} onChange={(e) => setOrg({ ...org, name: e.target.value })} /></label>
            <label>Industry<input value={org.industry} onChange={(e) => setOrg({ ...org, industry: e.target.value })} /></label>
            <label>Tagline<input value={org.tagline} onChange={(e) => setOrg({ ...org, tagline: e.target.value })} /></label>
            <button className="button button-primary" disabled={busy}>Save profile</button>
          </form>
        </section>

        <section className="panel admin-panel">
          <div className="panel-heading"><div><div className="eyebrow">TEAM ACCESS</div><h2>Invite a member</h2></div><UserPlus size={18} /></div>
          <form className="admin-form" onSubmit={(e) => { e.preventDefault(); run(async () => { await post('/api/admin/users', invite); setInvite(emptyInvite); }, 'Invitation created. The member must verify their email.'); }}>
            <label>Name<input required minLength="2" value={invite.name} onChange={(e) => setInvite({ ...invite, name: e.target.value })} /></label>
            <label>Email<input required type="email" value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} /></label>
            <div className="admin-form-row"><label>Role<select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })}><option value="member">Member</option><option value="reviewer">Reviewer</option><option value="admin">Administrator</option></select></label><label>Temporary password<input required minLength="10" type="password" value={invite.temporary_password} onChange={(e) => setInvite({ ...invite, temporary_password: e.target.value })} /></label></div>
            <small className="admin-note">Share the temporary password securely. The invitee must verify the email address.</small>
            <button className="button button-primary" disabled={busy}><Plus size={14} /> Create invitation</button>
          </form>
        </section>
      </div>

      <section className="panel admin-panel admin-wide">
        <div className="panel-heading"><div><div className="eyebrow">MEMBERS</div><h2>Organization access</h2></div><span className="admin-count">{data.users?.length || 0} accounts</span></div>
        <div className="admin-table-wrap"><table className="admin-table"><thead><tr><th>Member</th><th>Email</th><th>Role</th><th>Status</th></tr></thead><tbody>{(data.users || []).map((member) => <tr key={member.id}><td>{member.name}</td><td>{member.email}</td><td><select value={member.role} disabled={busy} onChange={(e) => run(() => patch('/api/admin/users/' + member.id, { role: e.target.value }), 'Member role updated.')}><option value="member">Member</option><option value="reviewer">Reviewer</option><option value="admin">Administrator</option></select></td><td><button className={'admin-status ' + (member.active ? 'is-active' : 'is-disabled')} disabled={busy} onClick={() => run(() => patch('/api/admin/users/' + member.id, { active: !member.active }), member.active ? 'Member access paused.' : 'Member access restored.')}>{member.active ? 'Active' : 'Disabled'}</button></td></tr>)}</tbody></table></div>
      </section>

      <section className="panel admin-panel admin-wide">
        <div className="panel-heading"><div><div className="eyebrow">FEEDBACK REVIEW</div><h2>Rule improvement proposals</h2></div><span className="admin-count">Feedback never changes a rule by itself</span></div>
        {(data.proposals || []).length ? <div className="proposal-list">{data.proposals.map((proposal) => <article className="proposal-card" key={proposal.id}><div className="proposal-top"><div><strong>{proposal.title}</strong><span>By {proposal.submitted_by_name} · {new Date(proposal.created_at).toLocaleString()}</span></div><span className={'proposal-status ' + proposal.status}>{proposal.status}</span></div><p>{proposal.proposed_text}</p><small><b>Reason:</b> {proposal.rationale}</small>{proposal.status === 'pending' ? <div className="proposal-actions"><button className="button button-primary" disabled={busy} onClick={() => run(() => post('/api/admin/proposals/' + proposal.id + '/decision', { decision: 'approved', comment: 'Approved after administrator review.' }), 'Proposal approved and added to the active brand library.')}><Check size={14} /> Approve rule</button><button className="button button-quiet" disabled={busy} onClick={() => run(() => post('/api/admin/proposals/' + proposal.id + '/decision', { decision: 'rejected', comment: 'Not approved at this time.' }), 'Proposal rejected and recorded.') }><X size={14} /> Reject</button></div> : proposal.decision_comment && <small className="proposal-decision">Decision: {proposal.decision_comment}</small>}</article>)}</div> : <div className="admin-empty">No rule improvement proposals yet. Team feedback will appear here for review.</div>}
      </section>

      <div className="admin-grid">
        <section className="panel admin-panel">
          <div className="panel-heading"><div><div className="eyebrow">APPROVED KNOWLEDGE</div><h2>Add guideline</h2></div><ShieldCheck size={18} /></div>
          <form className="admin-form" onSubmit={(e) => { e.preventDefault(); run(async () => { await post('/api/brand-library/sources', source); setSource({ title: '', type: 'Guideline', content: '' }); }, 'Approved guideline added to the brand library.'); }}>
            <label>Title<input required minLength="2" value={source.title} onChange={(e) => setSource({ ...source, title: e.target.value })} /></label>
            <label>Type<select value={source.type} onChange={(e) => setSource({ ...source, type: e.target.value })}><option>Guideline</option><option>Claims policy</option><option>Campaign guidance</option><option>Terminology</option></select></label>
            <label>Approved text<textarea required minLength="12" rows="4" value={source.content} onChange={(e) => setSource({ ...source, content: e.target.value })} /></label>
            <button className="button button-primary" disabled={busy}><Plus size={14} /> Add approved source</button>
          </form>
        </section>

        <section className="panel admin-panel">
          <div className="panel-heading"><div><div className="eyebrow">APPROVED FACTS</div><h2>Add a verified fact</h2></div><BadgeCheck size={18} /></div>
          <form className="admin-form" onSubmit={(e) => { e.preventDefault(); run(async () => { await post('/api/brand-library/facts', fact); setFact({ title: '', value: '', match_key: '', source_excerpt: '' }); }, 'Approved fact added.'); }}>
            <label>Fact title<input required value={fact.title} onChange={(e) => setFact({ ...fact, title: e.target.value })} /></label>
            <div className="admin-form-row"><label>Approved value<input required value={fact.value} onChange={(e) => setFact({ ...fact, value: e.target.value })} /></label><label>Check type<input required placeholder="hydration, discount…" value={fact.match_key} onChange={(e) => setFact({ ...fact, match_key: e.target.value })} /></label></div>
            <label>Evidence excerpt<textarea required minLength="12" rows="3" value={fact.source_excerpt} onChange={(e) => setFact({ ...fact, source_excerpt: e.target.value })} /></label>
            <button className="button button-primary" disabled={busy}><Plus size={14} /> Add approved fact</button>
          </form>
        </section>
      </div>

      <div className="admin-grid">
        <section className="panel admin-panel">
          <div className="panel-heading"><div><div className="eyebrow">TERMINOLOGY</div><h2>Approved language</h2></div><Check size={18} /></div>
          <form className="admin-form" onSubmit={(e) => { e.preventDefault(); run(async () => { await post('/api/brand-library/terminology', { ...term, avoid: term.avoid.split(',').map((value) => value.trim()).filter(Boolean) }); setTerm({ preferred: '', avoid: '', reason: '', severity: 'medium' }); }, 'Approved terminology rule added.'); }}>
            <label>Preferred wording<input required value={term.preferred} onChange={(e) => setTerm({ ...term, preferred: e.target.value })} /></label>
            <label>Avoid (comma separated)<input required value={term.avoid} onChange={(e) => setTerm({ ...term, avoid: e.target.value })} /></label>
            <label>Reason<textarea required minLength="8" rows="3" value={term.reason} onChange={(e) => setTerm({ ...term, reason: e.target.value })} /></label>
            <button className="button button-primary" disabled={busy}><Plus size={14} /> Add terminology rule</button>
          </form>
        </section>
        <section className="panel admin-panel">
          <div className="panel-heading"><div><div className="eyebrow">SUBMISSIONS</div><h2>Recent content</h2></div><FileText size={18} /></div>
          <div className="admin-submissions">{(data.drafts || []).slice(0, 7).map((draft) => <button key={draft.id} onClick={() => onOpenDraft(draft.id)}><span><strong>{draft.title}</strong><small>{draft.author} · {draft.channel}</small></span><em className={'status-pill status-' + (draft.status === 'approved' ? 'approved' : draft.status === 'published' ? 'published' : 'review')}>{draft.status.replaceAll('_', ' ')}</em></button>)}</div>
        </section>
      </div>
    </div>
  );
}
