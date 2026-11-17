import { useState } from "react";
import { ChevronRight, Loader2, Undo2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  addOffer, cancelStream, errText, pinOffer, publishStream, removeOffer, restoreOffer,
  type Offer, type Stream,
} from "@/lib/api";
import { OfferRow } from "./OfferRow";
import { AddOfferForm } from "./AddOfferForm";

export function StreamAccordion({ campaignId, stream, offers, onChanged }: {
  campaignId: number; stream: Stream; offers: Offer[]; onChanged: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const list = stream.offers ?? [];
  const hasOffers = list.length > 0 || stream.schema === "offers";
  const dirty = !!stream.is_dirty;

  async function run(key: string, fn: () => Promise<unknown>) {
    setBusy(key); setError(null);
    try { await fn(); await onChanged(); return true; }
    catch (e) { setError(errText(e)); return false; }
    finally { setBusy(null); }
  }

  return (
    <>
      <tr onClick={() => setOpen(!open)}
        className={cn("cursor-pointer border-t border-border transition-colors", dirty ? "bg-warning/15 hover:bg-warning/20" : "hover:bg-accent/60")}>
        <td className="px-3 py-3"><ChevronRight className={cn("h-4 w-4 text-muted-foreground transition-transform", open && "rotate-90")} /></td>
        <td className="px-3 py-3">{stream.id}</td>
        <td className="px-3 py-3 text-link">{stream.name}</td>
        <td className="px-3 py-3">{stream.type}</td>
        <td className="px-3 py-3 tabular-nums">{stream.weight}</td>
        <td className="px-3 py-3">{stream.schema ?? "—"}</td>
        <td className="px-3 py-3">{stream.action_type ?? "—"}</td>
        <td className="px-3 py-3">
          {dirty
            ? <span className="rounded-full bg-warning/25 px-2.5 py-0.5 text-xs font-medium text-warning">Не опубликован</span>
            : <span className="rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-medium text-primary">Синхронизирован</span>}
        </td>
        <td className="px-3 py-3 text-sm text-muted-foreground">{hasOffers ? `${list.filter((o) => o.status === "active").length} офф.` : "—"}</td>
      </tr>
      {open && (
        <tr className={cn(dirty && "bg-warning/5")}>
          <td colSpan={9} className="w-full max-w-0 px-4 pb-5 pt-2">
            <div className="ml-6 min-w-0 space-y-4 rounded-xl bg-background/60 p-4 shadow-elevation-1">
              {error && <div className="error rounded-lg bg-destructive/15 p-3 text-sm text-destructive">{error}</div>}
              <AddOfferForm offers={offers} busy={busy === "add"}
                onAdd={(oid) => run("add", () => addOffer(campaignId, stream.id, oid))} />
              <div>
                <div className="mb-1 text-sm font-medium text-muted-foreground">Офферы</div>
                {list.length === 0 ? (
                  <p className="px-3 py-2 text-sm text-muted-foreground">В потоке нет офферов</p>
                ) : list.map((o) => (
                  <OfferRow key={o.id} offer={o} busy={busy !== null}
                    onRemove={() => run(`o${o.id}`, () => removeOffer(campaignId, stream.id, o.id))}
                    onRestore={() => run(`o${o.id}`, () => restoreOffer(campaignId, stream.id, o.id))}
                    onPin={() => run(`o${o.id}`, () => pinOffer(campaignId, stream.id, o.id, !o.is_pinned))} />
                ))}
              </div>
              <div className="flex gap-2 border-t border-border pt-4">
                <Button disabled={busy !== null || !dirty} onClick={() => run("publish", () => publishStream(campaignId, stream.id))}>
                  {busy === "publish" ? <Loader2 className="animate-spin" /> : <Upload />} Push to Keitaro
                </Button>
                <Button variant="outline" disabled={busy !== null || !dirty} onClick={() => run("cancel", () => cancelStream(campaignId, stream.id))}>
                  {busy === "cancel" ? <Loader2 className="animate-spin" /> : <Undo2 />} Cancel
                </Button>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
