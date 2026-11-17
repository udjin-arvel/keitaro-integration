import { useEffect, useState, type FormEvent } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { GEOS, createCampaign, errText, fieldClass, updateCampaign, type Campaign, type CampaignInput } from "@/lib/api";

// campaign === undefined → closed; null → create; Campaign → edit
export function CampaignDialog({ campaign, onClose, onSaved }: { campaign: Campaign | null | undefined; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ name: "", geo: "", offer_id: "" });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setForm(campaign ? { name: campaign.name, geo: campaign.geo, offer_id: String(campaign.offer_id) } : { name: "", geo: "", offer_id: "" });
    setError(null);
  }, [campaign]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const offer = Number(form.offer_id);
    if (!form.name.trim() || !form.geo || !Number.isInteger(offer) || offer <= 0) { setError("Заполните все поля. Offer ID — целое положительное число."); return; }
    setSaving(true); setError(null);
    try {
      if (campaign) {
        const patch: Partial<CampaignInput> = {};
        if (form.name.trim() !== campaign.name) patch.name = form.name.trim();
        if (form.geo !== campaign.geo) patch.geo = form.geo;
        if (offer !== campaign.offer_id) patch.offer_id = offer;
        if (Object.keys(patch).length) await updateCampaign(campaign.id, patch);
      } else {
        await createCampaign({ name: form.name.trim(), geo: form.geo, offer_id: offer });
      }
      onSaved();
    } catch (err) { setError(errText(err)); }
    finally { setSaving(false); }
  }

  return (
    <Dialog open={campaign !== undefined} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="rounded-xl shadow-elevation-3">
        <DialogHeader><DialogTitle>{campaign ? "Редактировать кампанию" : "Новая кампания"}</DialogTitle></DialogHeader>
        {!campaign && <p className="-mt-2 text-sm text-muted-foreground">Будут созданы потоки White и Offer с весом 50/50.</p>}
        <form onSubmit={onSubmit} className="space-y-4">
          {error && <div className="error rounded-lg bg-destructive/15 p-3 text-sm text-destructive">{error}</div>}
          <Field label="Name"><input className={fieldClass} value={form.name} maxLength={200} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Geo">
            <select className={fieldClass} value={form.geo} onChange={(e) => setForm({ ...form, geo: e.target.value })}>
              <option value="">Выберите страну</option>
              {!GEOS.some(([c]) => c === form.geo) && form.geo && <option value={form.geo}>{form.geo}</option>}
              {GEOS.map(([c, n]) => <option key={c} value={c}>{c} — {n}</option>)}
            </select>
          </Field>
          <Field label="Offer ID"><input type="number" min={1} className={fieldClass} value={form.offer_id} onChange={(e) => setForm({ ...form, offer_id: e.target.value })} /></Field>
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={onClose}>Отмена</Button>
            <Button type="submit" disabled={saving}>{saving && <Loader2 className="animate-spin" />}{campaign ? "Сохранить" : "Создать"}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="block space-y-1.5"><span className="text-sm font-medium text-muted-foreground">{label}</span>{children}</label>;
}
