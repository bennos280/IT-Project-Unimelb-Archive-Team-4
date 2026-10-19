import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { createReviewer } from "../review-screen/api";

export type Reviewer = { id: number; name: string };

// Who saves: a new page type, each template version and each version of a series' checks record their reviewer; someone not
// listed adds their name here.
export default function ReviewerField({ reviewers, value, onChange, onAddReviewer }: {
  reviewers: Reviewer[]; value: string; onChange: (value: string) => void; onAddReviewer: (person: Reviewer) => void;
}) {
  const id = useId();
  const [adding, setAdding] = useState(!reviewers.length);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    setError("");
    try {
      const person = await createReviewer(name);
      onAddReviewer(person);
      onChange(String(person.id));
      setAdding(false);
      setName("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add the reviewer.");
    }
    setBusy(false);
  }

  return (
    <Field>
      <FieldLabel htmlFor={id}>Saved as</FieldLabel>
      <NativeSelect id={id} className="w-full" value={adding ? "add" : value} onChange={(e) => {
        setAdding(e.target.value === "add");
        onChange(e.target.value === "add" ? "" : e.target.value);
      }}>
        <option value="">Select reviewer</option>
        {reviewers.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        <option value="add">+ Add reviewer…</option>
      </NativeSelect>
      {adding && (
        <div className="flex gap-2">
          <Input aria-label="New reviewer name" placeholder="Enter reviewer name" value={name} onChange={(e) => setName(e.target.value)} />
          <Button variant="outline" disabled={busy || !name.trim()} onClick={add}>Add reviewer</Button>
        </div>
      )}
      {error && <FieldDescription className="text-destructive">{error}</FieldDescription>}
    </Field>
  );
}
