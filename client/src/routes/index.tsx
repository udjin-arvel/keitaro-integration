import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { GitBranch, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useCampaignSearch } from "@/components/AppShell";
import { CampaignDialog } from "@/components/CampaignDialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { deleteCampaign, errText, getCampaigns, keitaroId, type Campaign } from "@/lib/api";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Кампании — Adrobot T3" },
      { name: "description", content: "Кампании Keitaro: создание, редактирование, удаление и управление потоками." },
      { property: "og:title", content: "Кампании — Adrobot T3" },
      { property: "og:description", content: "Управление кампаниями и потоками Keitaro." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: CampaignList,
});

function CampaignList() {
  const [items, setItems] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Campaign | null | undefined>(undefined);
  const [pendingDelete, setPendingDelete] = useState<Campaign | null>(null);
  const [deleting, setDeleting] = useState(false);
  const query = useCampaignSearch().trim().toLowerCase();

  async function load() {
    setLoading(true);
    try { setItems(await getCampaigns()); setError(null); }
    catch (e) { setError(errText(e)); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await deleteCampaign(pendingDelete.id);
      setPendingDelete(null);
      await load();
    } catch (e) { setError(errText(e)); }
    finally { setDeleting(false); }
  }

  const visible = query
    ? items.filter((c) => [c.name, c.geo, c.id, c.offer_id, keitaroId(c) ?? ""].join(" ").toLowerCase().includes(query))
    : items;

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-medium">Кампании</h1>
        <Button onClick={() => setDialog(null)}><Plus /> Создать кампанию</Button>
      </div>
      {error && <div className="error mb-4 rounded-lg bg-destructive/15 p-3 text-sm text-destructive">{error}</div>}
      <div className="overflow-hidden rounded-xl bg-card shadow-elevation-1">
        <table className="w-full text-left text-sm">
          <thead className="text-muted-foreground">
            <tr>{["ID", "Name", "Geo", "Offer ID", "Keitaro ID", "Actions"].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-muted-foreground"><Loader2 className="mx-auto h-5 w-5 animate-spin" /></td></tr>
            ) : visible.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">{items.length === 0 ? "Кампаний пока нет" : "Ничего не найдено"}</td></tr>
            ) : visible.map((c) => (
              <tr key={c.id} className="border-t border-border transition-colors hover:bg-accent/60">
                <td className="px-4 py-3">{c.id}</td>
                <td className="px-4 py-3">
                  <Link to="/campaigns/$id/streams" params={{ id: String(c.id) }} className="text-link hover:underline">{c.name}</Link>
                </td>
                <td className="px-4 py-3"><span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs">{c.geo}</span></td>
                <td className="px-4 py-3">{c.offer_id}</td>
                <td className="px-4 py-3">{keitaroId(c) ?? "—"}</td>
                <td className="px-4 py-2">
                  <div className="flex h-8 items-center gap-1">
                    <Button asChild variant="ghost" size="sm" className="h-8 text-link">
                      <Link to="/campaigns/$id/streams" params={{ id: String(c.id) }}><GitBranch /> Streams</Link>
                    </Button>
                    <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Edit" onClick={() => setDialog(c)}><Pencil className="text-link" /></Button>
                    <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Delete" onClick={() => setPendingDelete(c)}><Trash2 className="text-destructive" /></Button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CampaignDialog campaign={dialog} onClose={() => setDialog(undefined)} onSaved={() => { setDialog(undefined); load(); }} />
      <Dialog open={pendingDelete !== null} onOpenChange={(open) => !open && !deleting && setPendingDelete(null)}>
        <DialogContent className="max-w-sm rounded-xl shadow-elevation-3">
          <DialogHeader>
            <DialogTitle>Удалить кампанию «{pendingDelete?.name}»?</DialogTitle>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" disabled={deleting} onClick={() => setPendingDelete(null)}>Отмена</Button>
            <Button type="button" variant="destructive" disabled={deleting} onClick={confirmDelete}>Да</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
