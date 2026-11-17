import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { Bell, CircleHelp, CircleUser, Menu, Search, Target } from "lucide-react";
import { createContext, useContext, useState, type FormEvent, type ReactNode } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const SearchContext = createContext("");

export function useCampaignSearch() {
  return useContext(SearchContext);
}

const hints = {
  help: "Здесь должна быть Справка",
  notifications: "Здесь должны быть Уведомления",
  profile: "Здесь должен быть Профиль",
} as const;

export function AppShell({ children }: { children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState("");
  const [hint, setHint] = useState<keyof typeof hints | null>(null);
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  function onSearch(e: FormEvent) {
    e.preventDefault();
    if (pathname !== "/") navigate({ to: "/" });
  }

  return (
    <SearchContext.Provider value={query}>
      <div className="flex min-h-screen flex-col bg-background text-foreground">
        <header className="sticky top-0 z-20 flex h-16 items-center gap-4 bg-sidebar px-5 shadow-elevation-2">
          <button
            type="button"
            aria-label={collapsed ? "Развернуть меню" : "Свернуть меню"}
            className="cursor-pointer rounded-full p-1 text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground"
            onClick={() => setCollapsed((v) => !v)}
          >
            <Menu className="h-6 w-6" />
          </button>
          <Link to="/" className="text-3xl font-bold tracking-tight text-primary">Keitaro</Link>
          <span className="text-xs uppercase tracking-wider text-muted-foreground">Adrobot T3</span>
          <form onSubmit={onSearch} className="mx-auto hidden w-full max-w-xl items-center gap-3 rounded-full bg-secondary px-4 py-2 md:flex">
            <Search className="h-5 w-5 shrink-0 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Поиск"
              aria-label="Поиск"
              className="w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
            />
          </form>
          <div className="ml-auto flex gap-3 text-muted-foreground md:ml-0">
            <HeaderIcon label="Справка" onClick={() => setHint("help")}><CircleHelp className="h-6 w-6" /></HeaderIcon>
            <HeaderIcon label="Уведомления" onClick={() => setHint("notifications")}><Bell className="h-6 w-6" /></HeaderIcon>
            <HeaderIcon label="Профиль" onClick={() => setHint("profile")}><CircleUser className="h-6 w-6" /></HeaderIcon>
          </div>
        </header>
        <div className="flex flex-1">
          <aside className={cn("hidden shrink-0 bg-sidebar py-3 transition-[width] duration-200 sm:block", collapsed ? "w-16" : "w-64")}>
            <Link to="/" activeOptions={{ exact: false }} title="Кампании"
              className={cn(
                "mx-3 flex items-center gap-4 rounded-full py-3 text-sidebar-foreground transition-colors hover:bg-sidebar-accent",
                collapsed ? "justify-center px-0" : "px-5",
              )}
              activeProps={{ className: "bg-primary/15 font-medium text-primary" }}>
              <Target className="h-5 w-5 shrink-0" />
              {!collapsed && "Кампании"}
            </Link>
          </aside>
          <main className="min-w-0 flex-1 overflow-x-auto p-6 md:p-8">{children}</main>
        </div>
      </div>
      <Dialog open={hint !== null} onOpenChange={(open) => !open && setHint(null)}>
        <DialogContent className="max-w-sm rounded-xl shadow-elevation-3">
          <DialogHeader>
            <DialogTitle>{hint ? hints[hint] : ""}</DialogTitle>
          </DialogHeader>
        </DialogContent>
      </Dialog>
    </SearchContext.Provider>
  );
}

function HeaderIcon({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={onClick}
      className="cursor-pointer rounded-full p-1.5 transition-colors hover:bg-sidebar-accent hover:text-foreground"
    >
      {children}
    </button>
  );
}
