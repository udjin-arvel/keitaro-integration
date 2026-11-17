import { useState, type FormEvent } from "react";
import { Loader2, Plus } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { fieldClass, type Offer } from "@/lib/api";

export function AddOfferForm({ offers, busy, onAdd }: { offers: Offer[]; busy: boolean; onAdd: (id: number) => Promise<boolean> }) {
  const [value, setValue] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    const id = Number(value);
    if (!Number.isInteger(id) || id <= 0) return;
    if (await onAdd(id)) setValue("");
  }
  return (
    <form onSubmit={submit} className="flex w-full min-w-0 max-w-full items-center gap-2">
      <input type="number" min={1} placeholder="ID оффера" className={cn(fieldClass, "w-36 shrink-0")} value={value} onChange={(e) => setValue(e.target.value)} />
      <select className={cn(fieldClass, "w-0 min-w-0 flex-1 basis-0")} value={offers.some((o) => String(o.id) === value) ? value : ""} onChange={(e) => setValue(e.target.value)}>
        <option value="">Выберите оффер…</option>
        {offers.map((o) => <option key={o.id} value={o.id}>[{o.id}] {o.name}</option>)}
      </select>
      <Button type="submit" className="shrink-0" disabled={busy || !value}>{busy ? <Loader2 className="animate-spin" /> : <Plus />} Add</Button>
    </form>
  );
}
