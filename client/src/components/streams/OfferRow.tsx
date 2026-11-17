import { Pin, PinOff, RotateCcw, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { StreamOffer } from "@/lib/api";

export function OfferRow({ offer, busy, onRemove, onRestore, onPin }: {
  offer: StreamOffer; busy: boolean; onRemove: () => void; onRestore: () => void; onPin: () => void;
}) {
  const removed = offer.status === "removed";
  return (
    <div className={cn("flex items-center gap-3 rounded-lg px-3 py-2 transition-colors hover:bg-accent/60", removed && "text-muted-foreground opacity-60")}>
      <span className="w-20 shrink-0 text-xs text-muted-foreground">[{offer.id}]</span>
      <span className={cn("flex-1 truncate", removed && "line-through")}>{offer.name}</span>
      <span className={cn("w-14 text-right font-medium tabular-nums", removed ? "text-muted-foreground" : "text-primary")}>{removed ? 0 : offer.weight}%</span>
      {removed ? (
        <Button size="sm" variant="outline" disabled={busy} onClick={onRestore}><RotateCcw /> Bring Back</Button>
      ) : (
        <>
          <Button size="icon" variant="ghost" disabled={busy} onClick={onPin} aria-label={offer.is_pinned ? "Unpin" : "Pin"}
            className={offer.is_pinned ? "text-warning" : "text-muted-foreground"}>
            {offer.is_pinned ? <Pin className="fill-current" /> : <PinOff />}
          </Button>
          <Button size="sm" variant="ghost" disabled={busy} onClick={onRemove} className="text-destructive"><X /> Remove</Button>
        </>
      )}
    </div>
  );
}
