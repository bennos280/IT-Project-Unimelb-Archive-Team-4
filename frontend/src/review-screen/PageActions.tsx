import PageHistory from "./PageHistory";
import { createPortal } from "react-dom";
import { ModelFields, ModelTable, type ModelChoice, type ModelData } from "../progress/ModelControls";
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { useReviewSession } from './useReviewSession';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field';
import { NativeSelect } from '@/components/ui/native-select';
import { Progress } from '@/components/ui/progress';
import { Spinner } from '@/components/ui/spinner';
import { Textarea } from '@/components/ui/textarea';
import { recordWords } from '../progress/backend';

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

const NO_CHOICE: ModelChoice = {model:'',provider:'',effort:''}; // nothing prefilled

// Acts on the selected page, using backend checks rather than changing local sample data.
export default function PageActions({ session, toolbar }: { session: ReturnType<typeof useReviewSession>; toolbar: HTMLDivElement | null }) {
  const { page, reviewerId, reviews, saving, setAttempt } = session;
  const words = recordWords(session.survey?.recordName);
  const pageId = page?.id;
  const uid = useId();
  const [menuOpen, setMenuOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [context, setContext] = useState<Context | null>(null);
  const [mode, setMode] = useState<'move' | 'type' | 'transcribe'>('move');
  const [modelData, setModelData] = useState<ModelData | null>(null);
  const [choice, setChoice] = useState<ModelChoice>(NO_CHOICE);
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
    setMenuOpen(false);
    setMode(action); setShowModels(false); setModelData(null); setChoice({model:'',provider:'claude',effort:''}); setTarget(''); setReason(''); setError(''); setLoading(true); setContext(null);
    setDialogOpen(true);
    try { const next = await request<Context>(`/page-actions/${encodeURIComponent(pageId!)}`); setContext(next); setJob(next.job); setType(next.category);
      if (action === 'transcribe') {
        const data = await request<ModelData>('/transcription-models');
        setModelData(data); setChoice(data.configured ?? NO_CHOICE);
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
        setNotice(''); setDialogOpen(false); reloadPage();
      } else {
        if (!modelData || !choice.provider || !choice.model.trim() || !choice.effort.trim()) return;
        const result = await request<{job:Job}>(`/page-transcription/${encodeURIComponent(page.id)}`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reviewerId,revision:context.revision,...choice})});
        pendingJob.current = result.job.id; setJob({...result.job,pageType:result.job.pageType ?? context.category}); setNotice('');
        setDialogOpen(false);
      }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Page action failed.'); }
    finally { setBusy(false); }
  }
  if (!page) return null;
  const destination = context?.surveys.find(s=>s.id===target);
  const title = showModels ? 'Transcription models' : mode==='move'?`Move to another ${words.one}`:mode==='type'?'Change page type':'Transcribe page';
  return <div className="space-y-3 text-sm">
    {toolbar && createPortal(<div data-testid="page-toolbar" className="flex flex-wrap items-center gap-2">
      <Button type="button" variant="outline" size="sm" disabled={busy||saving||running} onClick={()=>void open('transcribe')}>Transcribe</Button>
      {!running && <Collapsible open={menuOpen} onOpenChange={setMenuOpen} className="relative">
        <CollapsibleTrigger asChild><Button type="button" variant="outline" size="sm">{menuOpen ? <ChevronDown /> : <ChevronRight />}Page actions</Button></CollapsibleTrigger>
        <CollapsibleContent className="absolute right-0 z-20 mt-1 flex min-w-56 flex-col gap-1 rounded-lg bg-popover p-2 text-popover-foreground shadow-md ring-1 ring-foreground/10">
          <Button variant="ghost" size="sm" className="justify-start" disabled={busy||saving||running} onClick={()=>void open('type')}>Change page type</Button>
          {session.survey?.grouped&&<Button variant="ghost" size="sm" className="justify-start" disabled={busy||saving||running} onClick={()=>void open('move')}>Move to another {words.one}</Button>}
        </CollapsibleContent>
      </Collapsible>}
      <PageHistory pageId={page.id} />
    </div>, toolbar)}
    {page.needsTranscription && !running && <Alert role="status"><AlertDescription>Page has been changed to a different page type. Click the Transcribe button.</AlertDescription></Alert>}

    {running && <Alert role="status" aria-live="polite">
      <AlertTitle>Transcribing this page as {typeLabel(job.pageType)}.</AlertTitle>
      <AlertDescription className="space-y-2">
        <p>{job.status === 'waiting'
          ? 'Queued for retranscription. The worker has not started this job yet.'
          : 'The worker is processing this page for retranscription.'}</p>
        {job.status === 'running' && <Progress aria-label="Retranscription in progress" className="[&>[data-slot=progress-indicator]]:transform-none! [&>[data-slot=progress-indicator]]:animate-pulse" />}
        <p>Existing data remains visible until the new transcription succeeds.</p>
      </AlertDescription>
    </Alert>}
    {notice && !running && <Alert role="status"><AlertDescription>{notice}</AlertDescription></Alert>}
    {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
    <Dialog open={dialogOpen} onOpenChange={next => { if (!next && busy) return; setDialogOpen(next); }}>
      <DialogContent showCloseButton={false} onInteractOutside={e=>e.preventDefault()} className={`max-h-[90vh] overflow-y-auto ${showModels ? 'sm:max-w-[1000px]' : 'sm:max-w-[540px]'}`}>
        <DialogHeader>
          <DialogTitle className="text-lg">{title}</DialogTitle>
          <DialogDescription>Page {page.id}{context && ` · Item ${context.bundleId} · ${words.One} ${context.surveyId}`}</DialogDescription>
        </DialogHeader>
        {loading && <p role="status" className="flex items-center gap-2 text-muted-foreground"><Spinner role={undefined} aria-hidden="true" />Loading…</p>}
        {error && <Alert variant="destructive"><AlertDescription>{error}</AlertDescription></Alert>}
        {dirty&&<Alert role={undefined}><AlertDescription>Save or discard your pending reviews before changing this page.</AlertDescription></Alert>}
        {showModels && modelData ? <ModelTable data={modelData} /> : <>
        {context && (mode==='move'?<FieldGroup className="gap-4">
          <Field>
            <FieldLabel htmlFor={`${uid}-target`}>Destination {words.one}</FieldLabel>
            <NativeSelect id={`${uid}-target`} className="w-full" value={target} onChange={e=>setTarget(e.target.value)}><option value="">Select {words.a}</option>{context.surveys.filter(s=>s.id!==context.surveyId).map(s=><option key={s.id} value={s.id}>{s.id}</option>)}</NativeSelect>
          </Field>
          <FieldDescription>Only {words.many} in the same item are available. The image, extracted data and saved reviews stay with this page.</FieldDescription>
          {context.surveys.length<2&&<FieldDescription>No other {words.many} exist in this item.</FieldDescription>}
          {destination&&<Card size="sm">
            <CardHeader><CardTitle>Destination pages</CardTitle></CardHeader>
            <CardContent className="space-y-1">{destination.pages.map(p=><p key={p.id}>{p.id} · {p.type}</p>)}{destination.pages.some(p=>p.type===context.category)&&<p className="font-medium">Another page of this type already exists. Multiple pages of the same type are allowed; check the destination.</p>}</CardContent>
          </Card>}
          <Field>
            <FieldLabel htmlFor={`${uid}-reason`}>Reason (optional)</FieldLabel>
            <Textarea id={`${uid}-reason`} rows={3} value={reason} onChange={e=>setReason(e.target.value)}/>
          </Field>
        </FieldGroup>:mode==='type'?<FieldGroup className="gap-4">
          <Field>
            <FieldLabel htmlFor={`${uid}-type`}>Correct page type</FieldLabel>
            <NativeSelect id={`${uid}-type`} className="w-full" value={type} onChange={e=>setType(e.target.value)}>{['main','notes','coded','other'].map(t=><option key={t} value={t}>{t}</option>)}</NativeSelect>
          </Field>
        </FieldGroup>:<FieldGroup className="gap-4">
          {modelData && <ModelFields data={modelData} choice={choice} setChoice={setChoice} busy={busy} onViewTable={()=>setShowModels(true)} />}
          {context.hasReviews && <Alert role={undefined}><AlertDescription>Successful transcription replaces the current fields and resets their review status. Your previous data and saved reviews will be retained in history.</AlertDescription></Alert>}
        </FieldGroup>)}
        <DialogFooter>
          <Button variant="outline" disabled={busy} onClick={()=>setDialogOpen(false)}>Cancel</Button>
          <Button disabled={loading||!context||busy||saving||dirty||running||(mode==='move'?!target:mode==='type'?type===context.category:!modelData||!choice.provider||!choice.model.trim()||!choice.effort.trim())} onClick={()=>void submit()}>{busy?'Saving…':mode==='move'?'Move page':mode==='type'?'Change page type':'Transcribe'}</Button>
        </DialogFooter>
        </>}
        {showModels && <Button variant="outline" className="justify-self-start" onClick={()=>setShowModels(false)}>Back to transcription</Button>}
      </DialogContent>
    </Dialog>
  </div>;
}
