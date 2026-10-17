import PageHistory from "./PageHistory";
import { createPortal } from "react-dom";
import { ModelFields, ModelTable, type ModelChoice, type ModelData } from "../progress/ModelControls";
import { useCallback, useEffect, useRef, useState } from 'react';
import type { useReviewSession } from './useReviewSession';
import './page-actions.css';

type Job = { id: number; status: string; pageType?: string; step?: string | null; error: string | null };
const typeLabel = (value?: string) => ({ main: "Main page", notes: "Notes", coded: "Coded", other: "Other" }[value ?? ""] ?? value ?? "the selected page type");
type Context = { bundleId: string; surveyId: string; category: string; needsTranscription?: boolean; revision: number; hasReviews: boolean; job: Job | null; surveys: { id: string; pages: { id: string; type: string }[] }[] };
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail || `Request failed (${response.status}).`);
  if (!body) throw new Error('The backend did not return JSON.');
  return body;
}

// Acts on the selected page, using backend checks rather than changing local sample data.
export default function PageActions({ session, toolbar }: { session: ReturnType<typeof useReviewSession>; toolbar: HTMLDivElement | null }) {
  const { page, reviewer, reviewers, reviews, saving, setAttempt } = session;
  const pageId = page?.id;
  const menu = useRef<HTMLDetailsElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const [context, setContext] = useState<Context | null>(null);
  const [mode, setMode] = useState<'move' | 'type' | 'transcribe'>('move');
  const [modelData, setModelData] = useState<ModelData | null>(null);
  const [choice, setChoice] = useState<ModelChoice>({model:'',provider:'claude',effort:''});
  const [showModels, setShowModels] = useState(false);
  const [target, setTarget] = useState('');
  const [type, setType] = useState('main');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [job, setJob] = useState<Job | null>(null);
  const pendingJob = useRef<number | null>(null);
  const [loading, setLoading] = useState(false);
  const reviewerId = reviewers.find(person => person.name === reviewer)?.id;
  const dirty = Object.values(reviews).some(fields => Object.values(fields).some(value => !value.savedAt));
  const dirtyRef = useRef(dirty);
  useEffect(() => { dirtyRef.current = dirty; }, [dirty]);
  const running = job?.status === 'waiting' || job?.status === 'running';

  function reloadPage() {
    const url = new URL(window.location.href);
    if (pageId) url.searchParams.set('page', pageId);
    window.history.replaceState(null, '', url);
    setAttempt(n => n + 1);
  }

  // Discover an existing job on reload; stop polling when this page leaves the screen.
  useEffect(() => {
    if (!pageId) return;
    let active = true;
    let wasRunning = false;
    async function refresh() {
      try {
        const next = await request<Context>(`/page-actions/${encodeURIComponent(pageId!)}`);
        if (!active) return;
        setContext(next); setJob(next.job);
        const pending = next.job?.status === 'waiting' || next.job?.status === 'running';
        if ((wasRunning || pendingJob.current === next.job?.id) && !pending) {
          if (next.job?.status === 'done' && dirtyRef.current) {
            // Do not overwrite drafts made while the worker was running.
            pendingJob.current = next.job.id;
            setNotice('Retranscription finished. Pending edits are still visible; discard them before loading the new fields.');
            return;
          }
          pendingJob.current = null;
          if (next.job?.status === 'done') { setNotice('Transcription complete. Review the new data.'); const url = new URL(window.location.href); url.searchParams.set('page', pageId!); window.history.replaceState(null, '', url); setAttempt(n=>n+1); }
          else setError(next.job?.error || 'Retranscription failed. You can retry Change page type.');
        }
        wasRunning = pending;
      } catch (cause) { if (active) setError(cause instanceof Error ? cause.message : 'Could not load page actions.'); }
    }
    void refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => { active = false; window.clearInterval(timer); };
  }, [pageId, setAttempt]);

  const open = useCallback(async (action: 'move' | 'type' | 'transcribe') => {
    if (menu.current) menu.current.open = false;
    setMode(action); setShowModels(false); setModelData(null); setChoice({model:'',provider:'claude',effort:''}); setTarget(''); setReason(''); setError(''); setLoading(true); setContext(null);
    dialog.current?.showModal();
    try { const next = await request<Context>(`/page-actions/${encodeURIComponent(pageId!)}`); setContext(next); setJob(next.job); setType(next.category);
      if (action === 'transcribe') {
        const data = await request<ModelData>('/transcription-models');
        setModelData(data); setChoice(data.configured);
      }
    }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not load page actions.'); }
    finally { setLoading(false); }
  }, [pageId]);
  // A Transcribe action from the page list opens this page's model dialog once.
  useEffect(() => {
    const url = new URL(window.location.href);
    if (url.searchParams.get('action') !== 'transcribe' || url.searchParams.get('page') !== pageId) return;
    const timer = window.setTimeout(() => {
      url.searchParams.delete('action');
      window.history.replaceState(null, '', url);
      void open('transcribe');
    }, 0);
    return () => window.clearTimeout(timer);
  }, [pageId, open]);
  async function submit() {
    if (!context || !page || !reviewerId || dirty || busy || running) return;
    setBusy(true); setError('');
    try {
      if (mode === 'move') {
        const result = await request<{surveyId:string;pageId:string}>(`/page-moves/${encodeURIComponent(page.id)}`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({surveyId:target,sourceSurveyId:context.surveyId,revision:context.revision,reviewerId,reason})});
        window.location.assign(`/?survey=${encodeURIComponent(result.surveyId)}&page=${encodeURIComponent(result.pageId)}`);
      } else if (mode === 'type') {
        await request(`/page-classification/${encodeURIComponent(page.id)}`, {method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({pageType:type,reviewerId,revision:context.revision})});
        setNotice(''); dialog.current?.close(); reloadPage();
      } else {
        if (!modelData || !choice.model.trim() || !choice.effort.trim()) return;
        const result = await request<{job:Job}>(`/page-transcription/${encodeURIComponent(page.id)}`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reviewerId,revision:context.revision,...choice})});
        pendingJob.current = result.job.id; setJob({...result.job,pageType:result.job.pageType ?? context.category}); setNotice('');
        dialog.current?.close();
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Page action failed.'); }
    finally { setBusy(false); }
  }
  if (!page) return null;
  const destination = context?.surveys.find(s=>s.id===target);
  return <div className="page-actions">
    {toolbar && createPortal(<div className="page-actions page-toolbar-actions"><button type="button" disabled={busy||saving||running} onClick={()=>void open('transcribe')}>Transcribe</button>{!running && <details ref={menu}><summary>Page actions</summary><div className="page-actions-menu"><button disabled={busy||saving||running} onClick={()=>void open('type')}>Change page type</button><button disabled={busy||saving||running} onClick={()=>void open('move')}>Move to another survey</button></div></details>}<PageHistory pageId={page.id} /></div>, toolbar)}
    {page.needsTranscription && !running && <p role="status" className="page-action-warning">Page has been changed to a different page type. Click the Transcribe button.</p>}

    {running && <div className="page-action-progress" role="status" aria-live="polite">
      <strong>Transcribing this page as {typeLabel(job.pageType)}.</strong>
      <p>{job.status === 'waiting'
        ? 'Queued for retranscription. The worker has not started this job yet.'
        : 'The worker is processing this page for retranscription.'}</p>
      {job.status === 'running' && <progress aria-label="Retranscription in progress" />}
      <p>Existing data remains visible until the new transcription succeeds.</p>
    </div>}
    {notice && !running && <p role="status">{notice}</p>}
    {error && <p role="alert">{error}</p>}
    <dialog className={showModels ? "page-action-model-table" : undefined} ref={dialog} aria-label={showModels ? "Transcription models" : mode === "move" ? "Move to another survey" : mode === "type" ? "Change page type" : "Transcribe page"} onCancel={e=>{if(busy)e.preventDefault();}}>
      <h2 id="page-action-title">{showModels ? 'Transcription models' : mode==='move'?'Move to another survey':mode==='type'?'Change page type':'Transcribe page'}</h2>
      <p>Page {page.id}{context && ` · Bundle ${context.bundleId} · Survey ${context.surveyId}`}</p>
      {loading && <p role="status">Loading…</p>}
      {error && <p role="alert">{error}</p>}
      {(dirty||(!reviewerId && mode!=='transcribe'))&&<p className="page-action-warning">{dirty?'Save or discard your pending reviews before changing this page.':'Select a reviewer in the review screen first.'}</p>}
      {showModels && modelData ? <ModelTable data={modelData} /> : <>
      {context && (mode==='move'?<>
        <label>Destination survey<select value={target} onChange={e=>setTarget(e.target.value)}><option value="">Select a survey</option>{context.surveys.filter(s=>s.id!==context.surveyId).map(s=><option key={s.id} value={s.id}>{s.id}</option>)}</select></label>
        <p>Only surveys in the same bundle are available. The image, extracted data and saved reviews stay with this page.</p>
        {context.surveys.length<2&&<p>No other surveys exist in this bundle.</p>}
        {destination&&<div className="page-action-preview"><strong>Destination pages</strong>{destination.pages.map(p=><p key={p.id}>{p.id} · {p.type}</p>)}{destination.pages.some(p=>p.type===context.category)&&<p>Another page of this type already exists. Multiple pages of the same type are allowed; check the destination.</p>}</div>}
        <label>Reason (optional)<textarea rows={3} value={reason} onChange={e=>setReason(e.target.value)}/></label>
      </>:mode==='type'?<>
        <label>Correct page type<select value={type} onChange={e=>setType(e.target.value)}>{['main','notes','coded','other'].map(t=><option key={t} value={t}>{t}</option>)}</select></label>
      </>:<>
        <label>Reviewer<select aria-label="Reviewer" value={reviewer} onChange={e=>session.setReviewer(e.target.value)}><option value="">Select reviewer</option>{reviewers.map(person=><option key={person.id} value={person.name}>{person.name}</option>)}</select></label>
        {modelData && <ModelFields data={modelData} choice={choice} setChoice={setChoice} busy={busy} onViewTable={()=>setShowModels(true)} />}
        {context.hasReviews && <p className="page-action-warning">Successful transcription replaces the current fields and resets their review status. Your previous data and saved reviews will be retained in history.</p>}
      </>)}
      <footer><button disabled={busy} onClick={()=>dialog.current?.close()}>Cancel</button><button disabled={loading||!context||busy||saving||dirty||!reviewerId||running||(mode==='move'?!target:mode==='type'?type===context.category:!modelData||!choice.model.trim()||!choice.effort.trim())} onClick={()=>void submit()}>{busy?'Saving…':mode==='move'?'Move page':mode==='type'?'Change page type':'Transcribe'}</button></footer>
      </>}
      {showModels && <button onClick={()=>setShowModels(false)}>Back to transcription</button>}
    </dialog>
  </div>;
}
