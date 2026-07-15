import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FileText, Trash2, ArrowRight, Loader2, Info } from "lucide-react";
import Nav from "../components/Navbar";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import { deleteAnalysis, listAnalyses } from "../lib/api";
import { HISTORY } from "../constants/testIds";

const History = () => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      setLoading(true);
      const d = await listAnalyses();
      setItems(d);
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const remove = async (id) => {
    if (!confirm("Delete this analysis?")) return;
    try {
      await deleteAnalysis(id);
      setItems((it) => it.filter((x) => x.id !== id));
      toast.success("Deleted");
    } catch (e) {
      toast.error(e?.response?.data?.detail || e.message);
    }
  };

  return (
    <div className="min-h-screen bg-background" data-testid={HISTORY.page}>
      <Nav />

      <div className="max-w-[1440px] mx-auto px-6 py-12">
        <div className="overline">Archive</div>
        <h1 className="font-display font-bold text-3xl md:text-4xl mt-2 tracking-tight">
          Analysis history
        </h1>
        <p className="mt-2 text-sm text-muted-foreground max-w-xl">
          All plans processed on this device. Click any row to reopen its
          detailed report, or download a fresh PDF.
        </p>

        <div className="mt-8 rounded-md border border-border bg-card overflow-hidden">
          {loading && (
            <div className="p-10 flex items-center justify-center text-muted-foreground gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="font-mono-plex text-sm">Loading…</span>
            </div>
          )}

          {!loading && items.length === 0 && (
            <div className="p-14 text-center">
              <Info className="w-6 h-6 mx-auto text-muted-foreground" />
              <div className="mt-3 font-display font-bold text-lg">
                No analyses yet
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                Upload your first floor plan to see results here.
              </p>
              <Link to="/" className="inline-block mt-5">
                <Button className="rounded-full">Upload a plan</Button>
              </Link>
            </div>
          )}

          {!loading && items.length > 0 && (
            <table className="w-full text-sm">
              <thead className="text-left">
                <tr className="border-b border-border bg-secondary/40">
                  <th className="px-4 py-3 font-medium text-xs uppercase tracking-widest text-muted-foreground">File</th>
                  <th className="px-4 py-3 font-medium text-xs uppercase tracking-widest text-muted-foreground">Rooms</th>
                  <th className="px-4 py-3 font-medium text-xs uppercase tracking-widest text-muted-foreground">Doors</th>
                  <th className="px-4 py-3 font-medium text-xs uppercase tracking-widest text-muted-foreground">Windows</th>
                  <th className="px-4 py-3 font-medium text-xs uppercase tracking-widest text-muted-foreground">Walls (ft)</th>
                  <th className="px-4 py-3 font-medium text-xs uppercase tracking-widest text-muted-foreground">Confidence</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr
                    key={it.id}
                    data-testid={HISTORY.row(it.id)}
                    className="border-b border-border/70 last:border-none hover:bg-secondary/30 transition-colors"
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-primary" />
                        <div>
                          <div className="font-medium text-sm flex items-center gap-1.5">
                            {it.filename}
                            {it.page_count > 1 && (
                              <span className="text-[10px] font-mono-plex px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                                {it.page_count} pages
                              </span>
                            )}
                          </div>
                          <div className="text-xs text-muted-foreground font-mono-plex">
                            {new Date(it.created_at).toLocaleString()}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono-plex">{it.rooms}</td>
                    <td className="px-4 py-3 font-mono-plex">{it.doors}</td>
                    <td className="px-4 py-3 font-mono-plex">{it.windows}</td>
                    <td className="px-4 py-3 font-mono-plex">
                      {Number(it.wall_length).toFixed(1)}
                    </td>
                    <td className="px-4 py-3 font-mono-plex">
                      {Math.round(it.confidence)}%
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex gap-1">
                        <Link to={`/analysis/${it.id}`}>
                          <Button
                            variant="outline"
                            size="sm"
                            data-testid={HISTORY.openBtn(it.id)}
                            className="rounded-full gap-1"
                          >
                            Open <ArrowRight className="w-3 h-3" />
                          </Button>
                        </Link>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="rounded-full"
                          onClick={() => remove(it.id)}
                          aria-label="Delete"
                        >
                          <Trash2 className="w-4 h-4 text-muted-foreground hover:text-destructive" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};

export default History;
