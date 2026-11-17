import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StreamAccordion } from "@/components/streams/StreamAccordion";
import {
  errText, getCampaigns, getOffers, getStreams, keitaroId, ktStreamsUrl, syncStreams,
  type Campaign, type Offer, type Stream, type StreamsResponse,
} from "@/lib/api";

export const Route = createFileRoute("/campaigns/$id/streams")({
  head: () => ({
    meta: [
      { title: "Потоки кампании — Adrobot T3" },
      { name: "description", content: "Потоки кампании Keitaro: офферы, веса, публикация изменений." },
      { property: "og:title", content: "Потоки кампании — Adrobot T3" },
      { property: "og:description", content: "Управление потоками и офферами кампании Keitaro." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: StreamsPage,
});

function unpack(r: StreamsResponse): { streams: Stream[]; campaign?: Campaign | undefined; url?: string | undefined } {
  if (Array.isArray(r)) return { streams: r };
  return { streams: r.streams ?? [], campaign: r.campaign, url: r.view_in_kt_url ?? r.keitaro_url };
}

function StreamsPage() {
  const id = Number(Route.useParams().id);
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [ktUrl, setKtUrl] = useState<string | null>(null);
  const [streams, setStreams] = useState<Stream[]>([]);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = (r: StreamsResponse) => {
    const u = unpack(r);
    setStreams(u.streams);
    if (u.campaign) setCampaign(u.campaign);
    if (u.url) setKtUrl(u.url);
  };
  const reload = useCallback(async () => { apply(await getStreams(id)); }, [id]);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      reload(),
      getCampaigns().then((l) => { const c = l.find((x) => x.id === id); if (c) setCampaign((p) => p ?? c); }),
      getOffers().then(setOffers),
    ]).then((rs) => {
      const failed = rs.find((r) => r.status === "rejected") as PromiseRejectedResult | undefined;
      setError(failed ? errText(failed.reason) : null);
      setLoading(false);
    });
  }, [id, reload]);

  async function onSync() {
    setSyncing(true); setError(null);
    try { apply(await syncStreams(id)); } catch (e) { setError(errText(e)); }
    finally { setSyncing(false); }
  }

  const viewUrl = ktUrl ?? ktStreamsUrl(campaign);

  return (
    <>
      <Link to="/" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" /> Кампании</Link>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h1 className="text-3xl font-medium">{campaign?.name ?? `Кампания #${id}`}</h1>
          <p className="text-sm text-muted-foreground">
            {campaign ? <>Geo {campaign.geo} · Offer {campaign.offer_id} · Keitaro ID {keitaroId(campaign) ?? "—"}</> : "Потоки кампании"}
          </p>
        </div>
        <Button onClick={onSync} disabled={syncing}>{syncing ? <Loader2 className="animate-spin" /> : <RefreshCw />} Fetch Streams From KT</Button>
        {viewUrl ? (
          <Button asChild variant="outline"><a href={viewUrl} target="_blank" rel="noreferrer"><ExternalLink /> View In KT</a></Button>
        ) : (
          <Button variant="outline" disabled><ExternalLink /> View In KT</Button>
        )}
      </div>
      {error && <div className="error mb-4 rounded-lg bg-destructive/15 p-3 text-sm text-destructive">{error}</div>}
      <div className="overflow-hidden rounded-xl bg-card shadow-elevation-1">
        <table className="w-full text-left text-sm">
          <thead className="text-muted-foreground">
            <tr>{["", "ID", "Name", "Type", "Weight", "Schema", "Action", "Status", "Actions"].map((h, i) => <th key={i} className="px-3 py-3 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={9} className="py-10 text-center text-muted-foreground"><Loader2 className="mx-auto h-5 w-5 animate-spin" /></td></tr>
            ) : streams.length === 0 ? (
              <tr><td colSpan={9} className="py-10 text-center text-muted-foreground">Потоков нет</td></tr>
            ) : streams.map((s) => (
              <StreamAccordion key={s.id} campaignId={id} stream={s} offers={offers} onChanged={reload} />
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
