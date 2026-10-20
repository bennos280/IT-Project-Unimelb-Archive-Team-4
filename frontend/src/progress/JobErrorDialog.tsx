import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

// Displays the backend error for one item, named as on screen; the parent controls whether this dialog exists.
export default function JobErrorDialog({ item, message, onClose }: { item: string; message: string; onClose: () => void }) {
  // Escape calls onClose too, keeping the parent state in sync with the visible dialog.
  return (
    <Dialog open onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        showCloseButton={false}
        onInteractOutside={(event) => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Transcription error</DialogTitle>
          <DialogDescription>{item}</DialogDescription>
        </DialogHeader>
        {/* Preserve error line breaks and allow long messages to wrap and scroll. */}
        <pre className="max-h-[50vh] overflow-y-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap [overflow-wrap:anywhere]">{message}</pre>
        <DialogFooter>
          <Button onClick={onClose}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
