import { useCallback, useEffect, useState } from "react";
import { Copy, ExternalLink, FolderOpen, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { backendRequest } from "../progress/backend";

type Version = {
  current: string | null; latest: string | null; releases: string; error: string | null; updatable: boolean;
  checkedAt: string; system: { os: string; python: string; pytorch: boolean };
};
type Folders = { data: string; output: string };

const REPO = "https://github.com/bennos280/IT-Project-Unimelb-Archive-Team-4";

// What a problem report needs: this copy's version and the computer it runs on.
function versionInfo(version: Version) {
  return [
    `PrestCribe ${version.current ?? "(not installed from a release)"}`,
    version.system.os,
    `Python ${version.system.python}`,
    `Page sorting on this computer: ${version.system.pytorch ? "available" : "not available"}`,
  ].join("\n");
}

function Link({ href, children }: { href: string; children: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline">
      {children} <ExternalLink aria-hidden="true" className="size-3.5" />
    </a>
  );
}

// The About tab: PrestCribe and its version, whether it's up to date (an installed copy can update itself: the installer runs
// again in its own window and opens PrestCribe once it's done; a git copy is updated with git), a link to the latest release's notes on GitHub,
// its version info to copy for a problem report, where its files are, and help.
export default function About() {
  const [version, setVersion] = useState<Version | null>(null);
  const [state, setState] = useState<"checking" | "" | "unreachable" | "updating" | "stalled" | "failed">("checking");
  const [updateError, setUpdateError] = useState("");
  const [copied, setCopied] = useState("");
  const load = useCallback(() => {
    backendRequest<Version>("/version").then((v) => { setVersion(v); setState(""); }).catch(() => setState("unreachable"));
  }, []);
  useEffect(load, [load]);

  // While updating, PrestCribe is asked for its version every 5 s: once it answers again after being gone (or as a new version), the page reloads.
  const current = version?.current;
  useEffect(() => {
    if (state !== "updating") return;
    let gone = false;
    const poll = setInterval(() => {
      backendRequest<Version>("/version").then((v) => { if (gone || v.current !== current) location.reload(); }).catch(() => { gone = true; });
    }, 5000);
    const giveUp = setTimeout(() => setState("stalled"), 3 * 60 * 1000);
    return () => { clearInterval(poll); clearTimeout(giveUp); };
  }, [state, current]);

  function checkAgain() {
    setState("checking");
    setCopied("");
    load();
  }

  async function update() {
    if (!window.confirm(`Update to ${version?.latest}? PrestCribe closes, updates in a new window, then opens again.`)) return;
    try {
      await backendRequest("/update", { method: "POST" });
      setState("updating");
    } catch (e) {
      setUpdateError(e instanceof Error ? e.message : "The update couldn't start.");
      setState("failed");
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(versionInfo(version!));
      setCopied("Copied.");
    } catch {
      setCopied("Couldn't copy it.");
    }
  }

  const checked = version && new Date(version.checkedAt).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  const status = state === "checking" ? "Checking for updates…"
    : state === "unreachable" ? "Couldn't check for updates."
    : state === "updating" ? "Updating: PrestCribe closes now, updates in a new window, then opens again."
    : state === "stalled" ? "The update didn't finish. Running the install line from the README again fixes it."
    : !version ? ""
    : version.error ? version.error
    : version.updatable ? `${version.latest} is available.`
    : version.current ? `Up to date · checked at ${checked}.`
    : `Latest release: ${version.latest}. A copy not installed from a release is updated with git.`;
  const report = version ? `${REPO}/issues/new?body=${encodeURIComponent(`\n\n---\n${versionInfo(version)}`)}` : `${REPO}/issues/new`;

  return (
    <>
      <section id="updates" aria-labelledby="about-title">
        <Card>
          <CardContent className="flex flex-wrap items-start gap-4">
            <img src="/favicon.svg" alt="" className="size-14" />
            <div className="min-w-0 flex-1 space-y-3">
              <div>
                <h2 id="about-title" className="text-xl font-semibold tracking-tight">
                  PrestCribe {version?.current && <span className="font-normal text-muted-foreground">{version.current}</span>}
                </h2>
                <p className="text-sm text-muted-foreground">
                  Made by IT Project Team 4 at the University of Melbourne, for the University of Melbourne Archives.
                </p>
              </div>
              <p role="status" className="text-sm">
                {status}
                {state === "failed" && ` ${updateError}`}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                {version?.updatable && state !== "updating" && <Button size="sm" onClick={update}><RefreshCw /> Update now</Button>}
                {state !== "updating" && (
                  <Button size="sm" variant="outline" disabled={state === "checking"} onClick={checkAgain}>Check again</Button>
                )}
                {version && <Button size="sm" variant="outline" onClick={copy}><Copy /> Copy version info</Button>}
                <span role="status" className="text-sm text-muted-foreground">{copied}</span>
              </div>
              {version && (
                <p className="text-sm">
                  <Link href={version.latest ? `${version.releases}/tag/${version.latest}` : version.releases}>
                    {version.latest ? `What's new in ${version.latest}` : "What's new"}
                  </Link>
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      </section>
      <FilesHere />
      <section id="help" className="space-y-3">
        <h2 className="text-xl font-semibold tracking-tight">Help</h2>
        <div className="flex flex-wrap gap-6 text-sm">
          <Link href={`${REPO}#readme`}>How PrestCribe works</Link>
          <Link href={report}>Report a problem</Link>
        </div>
      </section>
    </>
  );
}

// Where this copy keeps its scans and results, each opened in Explorer or Finder by its button.
function FilesHere() {
  const [folders, setFolders] = useState<Folders | null | "failed">(null);
  const [error, setError] = useState("");
  useEffect(() => {
    backendRequest<Folders>("/folders").then(setFolders).catch(() => setFolders("failed"));
  }, []);

  async function open(which: keyof Folders) {
    setError("");
    try {
      await backendRequest(`/folders/${which}/open`, { method: "POST" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "The folder couldn't be opened.");
    }
  }

  return (
    <section id="folders" className="space-y-3">
      <h2 className="text-xl font-semibold tracking-tight">Where your files are</h2>
      <Card>
        <CardContent className="space-y-3 text-sm">
          {folders === "failed" ? <p className="text-destructive">The folders couldn't be loaded.</p>
            : folders && ([["data", "Scans"], ["output", "Results"]] as const).map(([which, name]) => (
              <div key={which} className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="w-16 font-medium">{name}</span>
                <code className="min-w-0 flex-1 rounded bg-muted px-1 py-0.5 font-mono break-all">{folders[which]}</code>
                <Button size="sm" variant="outline" aria-label={`Open folder: ${name.toLowerCase()}`} onClick={() => open(which)}>
                  <FolderOpen /> Open folder
                </Button>
              </div>
            ))}
          {error && <p className="text-destructive">{error}</p>}
          <p className="text-muted-foreground">Your work itself is in PrestCribe's database: save it as a PrestCribe file from the home page.</p>
        </CardContent>
      </Card>
    </section>
  );
}
