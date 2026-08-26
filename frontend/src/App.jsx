import { useEffect, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Cloud,
  Cpu,
  CreditCard,
  Database,
  Ellipsis,
  ExternalLink,
  HardDrive,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  MapPin,
  Menu,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const initialDatabases = [
  {
    id: 1,
    name: "production-db",
    engine: "PostgreSQL",
    version: "16.4",
    mode: "cluster",
    status: "running",
    cpu: 8,
    ram: 32,
    storage: 250,
    datacenter: "Paris · DC1",
    usage: 64,
    plan: "payg",
  },
  {
    id: 2,
    name: "analytics-warehouse",
    engine: "PostgreSQL",
    version: "16.4",
    mode: "single",
    status: "running",
    cpu: 4,
    ram: 16,
    storage: 100,
    datacenter: "Lyon · DC2",
    usage: 38,
    plan: "3",
  },
  {
    id: 3,
    name: "app-staging",
    engine: "MySQL",
    version: "8.4",
    mode: "single",
    status: "running",
    cpu: 2,
    ram: 8,
    storage: 50,
    datacenter: "Paris · DC1",
    usage: 22,
    plan: "1",
  },
  {
    id: 4,
    name: "redis-cache",
    engine: "Redis",
    version: "7.4",
    mode: "cluster",
    status: "running",
    cpu: 2,
    ram: 8,
    storage: 20,
    datacenter: "Marseille · DC3",
    usage: 45,
    plan: "payg",
  },
];
const nav = [
  ["Vue d’ensemble", LayoutDashboard],
  ["Bases de données", Database],
  ["Sauvegardes", HardDrive],
  ["Réplication", RefreshCw],
  ["Demandes de ressources", Cpu],
  ["Facturation", CreditCard],
  ["Sécurité & accès", ShieldCheck],
];
const chartData = Array.from({ length: 25 }, (_, i) => ({
  hour: `${String(i).padStart(2, "0")}:00`,
  cpu: [
    27, 25, 29, 24, 26, 25, 33, 30, 29, 34, 32, 42, 39, 44, 37, 41, 35, 32, 39,
    35, 37, 33, 40, 38, 42,
  ][i],
  ram: [
    44, 45, 44, 43, 45, 44, 47, 46, 47, 48, 48, 51, 50, 53, 51, 53, 51, 50, 53,
    52, 52, 51, 54, 53, 55,
  ][i],
}));
const euro = (n) =>
  new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(
    n,
  );
const price = (db) =>
  (db.cpu * 8 + db.ram * 2 + db.storage * 0.1) *
  (db.mode === "cluster" ? 3 : 1) *
  (1 - ({ 3: 0.05, 6: 0.1, 12: 0.15 }[db.plan] || 0));
const statusLabel = {
  running: "Disponible",
  pending: "En attente",
  provisioning: "Provisionnement",
  failed: "Échec",
};
const stored = (key, fallback, storage = localStorage) => {
  try {
    return JSON.parse(storage.getItem(key)) ?? fallback;
  } catch {
    return fallback;
  }
};

export default function App() {
  const [page, setPage] = useState("Vue d’ensemble"),
    [dbs, setDbs] = useState(() => stored("sc-dbs", initialDatabases)),
    [requests, setRequests] = useState(() => stored("sc-requests", [])),
    [backups, setBackups] = useState(() =>
      stored("sc-backups", [
        {
          id: 1,
          name: "production-db",
          date: "Aujourd’hui, 03:00",
          size: "18,4 Go",
          site: "Lyon · DC2",
          status: "Terminée",
        },
        {
          id: 2,
          name: "analytics-warehouse",
          date: "Aujourd’hui, 03:15",
          size: "7,2 Go",
          site: "Marseille · DC3",
          status: "Terminée",
        },
      ]),
    );
  const [modal, setModal] = useState(null),
    [toast, setToast] = useState(""),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [period, setPeriod] = useState("24 dernières heures"),
    [admin, setAdmin] = useState(
      () => stored("sc-user", null, sessionStorage)?.user?.role === "admin",
    ),
    [mobile, setMobile] = useState(false),
    [user, setUser] = useState(() => stored("sc-user", null, sessionStorage)),
    [api, setApi] = useState(false),
    [notifications, setNotifications] = useState(false);
  const [form, setForm] = useState({
    name: "",
    engine: "PostgreSQL",
    mode: "single",
    cpu: 2,
    ram: 8,
    storage: 50,
    datacenter: "Paris · DC1",
    plan: "payg",
  });
  const [auth, setAuth] = useState({
      name: "",
      email: "",
      password: "",
      code: "",
      channel: "email",
      phone: "",
    }),
    [challenge, setChallenge] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const notify = (t) => {
    setToast(t);
    setTimeout(() => setToast(""), 4500);
  };
  async function call(path, options = {}) {
    const r = await fetch("/api" + path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(user?.token ? { Authorization: `Bearer ${user.token}` } : {}),
        ...options.headers,
      },
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.message || "Une erreur est survenue");
    return data;
  }
  useEffect(() => {
    fetch("/api/health")
      .then((r) => r.ok && setApi(true))
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!user) localStorage.setItem("sc-dbs", JSON.stringify(dbs));
  }, [dbs, user]);
  useEffect(() => {
    if (!user) localStorage.setItem("sc-requests", JSON.stringify(requests));
  }, [requests, user]);
  useEffect(() => {
    if (!user) localStorage.setItem("sc-backups", JSON.stringify(backups));
  }, [backups, user]);
  useEffect(() => {
    if (user) {
      sessionStorage.setItem("sc-user", JSON.stringify(user));
      setDbs([]);
      setRequests([]);
      setBackups([]);
      Promise.all([
        call("/databases"),
        call("/resource-requests"),
        call("/backups"),
      ])
        .then(([d, r, b]) => {
          setDbs(d);
          setRequests(r);
          setBackups(b);
        })
        .catch((e) => notify(e.message));
    } else sessionStorage.removeItem("sc-user");
  }, [user]);
  useEffect(() => {
    if (!modal) return;
    const previous = document.activeElement;
    document.body.style.overflow = "hidden";
    const dialog = document.querySelector('[role="dialog"]');
    const focusable = () => [
      ...dialog.querySelectorAll(
        "button:not(:disabled),input:not(:disabled),select:not(:disabled),a[href]",
      ),
    ];
    focusable()[0]?.focus();
    const keys = (e) => {
      if (e.key === "Escape") {
        setModal(null);
        setChallenge(null);
      }
      if (e.key === "Tab") {
        const items = focusable(),
          first = items[0],
          last = items.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", keys);
    return () => {
      document.body.style.overflow = "";
      document.removeEventListener("keydown", keys);
      previous?.focus();
    };
  }, [modal]);
  const go = (p) => {
    setPage(p);
    setQuery("");
    setMobile(false);
  };
  const open = (type, db = null) => {
    setError("");
    setModal({ type, db });
    if (type === "create")
      setForm({
        name: "",
        engine: "PostgreSQL",
        mode: "single",
        cpu: 2,
        ram: 8,
        storage: 50,
        datacenter: "Paris · DC1",
        plan: "payg",
      });
    if (type === "extend") setForm({ ...db });
  };
  const saveRequest = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = {
        ...form,
        cpu: Number(form.cpu),
        ram: Number(form.ram),
        storage: Number(form.storage),
      };
      if (modal.type === "create") {
        if (user) {
          const d = await call("/databases", {
            method: "POST",
            body: JSON.stringify(payload),
          });
          setDbs([...dbs, d]);
          setRequests(await call("/resource-requests"));
        } else {
          const id = Date.now();
          setDbs([
            ...dbs,
            {
              ...payload,
              id,
              status: "pending",
              version:
                form.engine === "MySQL"
                  ? "8.4"
                  : form.engine === "Redis"
                    ? "7.4"
                    : "16.4",
              usage: 0,
            },
          ]);
          setRequests([
            ...requests,
            {
              id,
              database_id: id,
              name: form.name,
              type: "Création",
              status: "pending",
              ...payload,
            },
          ]);
        }
      } else {
        const req = user
          ? await call("/resource-requests", {
              method: "POST",
              body: JSON.stringify({ ...payload, database_id: modal.db.id }),
            })
          : {
              id: Date.now(),
              database_id: modal.db.id,
              name: modal.db.name,
              type: "Extension",
              status: "pending",
              ...payload,
            };
        setRequests([...requests, req]);
      }
      setModal(null);
      notify("Demande envoyée. La validation administrateur est nécessaire.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const approve = async (req, decision) => {
    try {
      if (user) {
        await call(`/resource-requests/${req.id}`, {
          method: "PATCH",
          body: JSON.stringify({ status: decision }),
        });
        const d = await call("/databases");
        setDbs(d);
      } else if (decision === "approved") {
        setDbs(
          dbs.map((d) =>
            d.id === req.database_id
              ? {
                  ...d,
                  cpu: req.cpu,
                  ram: req.ram,
                  storage: req.storage,
                  status: "running",
                }
              : d,
          ),
        );
      } else if (req.type === "Création") {
        setDbs(
          dbs.map((d) =>
            d.id === req.database_id ? { ...d, status: "failed" } : d,
          ),
        );
      }
      setRequests(
        requests.map((r) => (r.id === req.id ? { ...r, status: decision } : r)),
      );
      notify(
        decision === "approved"
          ? "Demande approuvée · provisionnement simulé"
          : "Demande refusée",
      );
    } catch (e) {
      notify(e.message);
    }
  };
  const backup = async (db) => {
    try {
      const b = user
        ? await call(`/databases/${db.id}/backups`, { method: "POST" })
        : {
            id: Date.now(),
            name: db.name,
            date: new Date().toLocaleString("fr-FR"),
            size: "Simulation",
            site: db.datacenter.includes("DC2")
              ? "Marseille · DC3"
              : "Lyon · DC2",
            status: "Simulée",
          };
      setBackups([b, ...backups]);
      notify("Sauvegarde simulée enregistrée");
    } catch (e) {
      notify(e.message);
    }
  };
  const login = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (modal.type === "register") {
        const r = await call("/register", {
          method: "POST",
          body: JSON.stringify(auth),
        });
        notify(r.message);
        setModal(null);
      } else if (challenge) {
        const r = await call("/mfa/verify", {
          method: "POST",
          body: JSON.stringify({ challenge_id: challenge, code: auth.code }),
        });
        setUser(r);
        setAdmin(r.user.role === "admin");
        setChallenge(null);
        setModal(null);
      } else {
        const r = await call("/login", {
          method: "POST",
          body: JSON.stringify(auth),
        });
        setChallenge(r.challenge_id);
        notify("Code de vérification envoyé");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const download = async () => {
    if (!user) {
      notify("Connectez-vous à l’API pour générer une facture PDF.");
      return;
    }
    try {
      const r = await fetch("/api/invoices/current/pdf", {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (!r.ok) throw new Error("Impossible de générer la facture");
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = "estimation-souverain-cloud.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      notify(e.message);
    }
  };
  const visible = dbs.filter(
    (d) =>
      (filter === "all" || d.engine === filter) &&
      `${d.name} ${d.engine} ${d.datacenter}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const pending = requests.filter((r) => r.status === "pending");
  const allocated = dbs.filter((d) => d.status === "running");
  const nodes = (d) => (d.mode === "cluster" ? 3 : 1);
  const totals = {
    cpu: allocated.reduce((a, d) => a + d.cpu * nodes(d), 0),
    ram: allocated.reduce((a, d) => a + d.ram * nodes(d), 0),
    storage: allocated.reduce((a, d) => a + d.storage * nodes(d), 0),
  };
  const monthly = dbs
    .filter((d) => d.status === "running")
    .reduce((a, d) => a + price(d), 0);
  const databaseTable = () => (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Nom / Moteur</th>
            <th>Statut</th>
            <th>Configuration</th>
            <th>Datacenter</th>
            <th>Stockage utilisé</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {visible.map((d) => (
            <tr key={d.id}>
              <td>
                <div className="db-name">
                  <span className={`engine ${d.engine.toLowerCase()}`}>
                    <Database size={19} />
                  </span>
                  <div>
                    <button
                      className="text-link"
                      onClick={() => open("detail", d)}
                    >
                      {d.name}
                    </button>
                    <small>
                      {d.engine} {d.version} <span className="dot-sep">·</span>{" "}
                      {d.mode === "cluster"
                        ? "Cluster · 3 nœuds"
                        : "Instance simple"}
                    </small>
                  </div>
                </div>
              </td>
              <td>
                <span
                  className={`badge ${d.status === "running" ? "green" : "amber"}`}
                >
                  <i />
                  {statusLabel[d.status]}
                </span>
              </td>
              <td>
                <span className="config">
                  {d.cpu} vCPU <span> / </span> {d.ram} Go RAM
                </span>
                <small>{d.storage} Go SSD NVMe</small>
              </td>
              <td>
                <span className="dc">
                  <MapPin size={13} />
                  {d.datacenter}
                </span>
                <small className="country">France</small>
              </td>
              <td>
                <div className="storage-top">
                  <span>
                    {Math.round((d.storage * d.usage) / 100)} / {d.storage} Go
                  </span>
                  <span>{d.usage}%</span>
                </div>
                <div className="progress">
                  <i style={{ width: `${d.usage}%` }} />
                </div>
              </td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`Gérer ${d.name}`}
                  onClick={() => open("detail", d)}
                >
                  <Ellipsis size={18} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!visible.length && (
        <div className="empty">
          Aucune base de données ne correspond à votre recherche.
        </div>
      )}
    </div>
  );
  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            go("Vue d’ensemble");
          }}
        >
          <span className="brand-mark">
            <Cloud size={26} />
          </span>
          <span>
            souverain<span className="brand-cloud">cloud</span>
          </span>
        </a>
        <div className="workspace">
          <span className="workspace-icon">A</span>
          <div>
            Acme Technologies
            <small>Espace {admin ? "administrateur" : "client"}</small>
          </div>
          <ChevronDown size={15} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {nav.map(([label, Icon]) => (
            <button
              key={label}
              onClick={() => go(label)}
              className={page === label ? "active" : ""}
            >
              <Icon size={18} />
              <span>{label}</span>
              {label === "Demandes de ressources" && pending.length > 0 && (
                <b>{pending.length}</b>
              )}
            </button>
          ))}
          {admin && (
            <button
              className={page === "Administration" ? "active" : ""}
              onClick={() => go("Administration")}
            >
              <Users size={18} />
              Administration
            </button>
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="sovereignty">
            <ShieldCheck size={22} />
            <strong>Vos données, en France.</strong>
            <p>
              Hébergement souverain.
              <br />
              Contrôle total sur vos données.
            </p>
            <span>
              <i />3 datacenters opérationnels
            </span>
          </div>
          <button className="help" onClick={() => open("help")}>
            <CircleHelp size={18} />
            Aide & documentation
            <ExternalLink size={13} />
          </button>
          <button
            className="profile"
            onClick={() => (user ? open("account") : open("login"))}
          >
            <span className="avatar">
              {user?.user?.name?.slice(0, 2).toUpperCase() || "AM"}
            </span>
            <div>
              {user?.user?.name || "Alex Martin"}
              <small>{user?.user?.email || "Mode démonstration"}</small>
            </div>
            <Settings size={16} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="icon-button mobile-menu"
              onClick={() => setMobile(!mobile)}
              aria-label="Menu"
            >
              <Menu size={19} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>{page}</strong>
          </div>
          <div className="top-actions">
            <span className="environment">
              <i />
              {user ? "API connectée" : "Environnement démo"}
            </span>
            <button
              className="icon-button notification"
              onClick={() => setNotifications(!notifications)}
              aria-label="Notifications"
            >
              <Bell size={19} />
              {pending.length > 0 && <i />}
            </button>
            <div className="header-divider" />
            <button
              className="avatar small-avatar"
              onClick={() => open(user ? "account" : "login")}
            >
              {user?.user?.name?.slice(0, 2).toUpperCase() || "AM"}
            </button>
          </div>
          {notifications && (
            <div className="notification-panel">
              <strong>Notifications</strong>
              <p>
                {pending.length
                  ? `${pending.length} demande(s) en attente de validation.`
                  : "Vous êtes à jour."}
              </p>
              <button
                className="text-link"
                onClick={() => {
                  go("Demandes de ressources");
                  setNotifications(false);
                }}
              >
                Voir les demandes <ArrowRight size={14} />
              </button>
            </div>
          )}
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">VOTRE CLOUD, EN TOUTE CONFIANCE</div>
              <h1>{page}</h1>
              <p>
                {page === "Vue d’ensemble"
                  ? "Pilotez vos bases de données. Nous prenons soin du reste."
                  : {
                      "Bases de données":
                        "Déployez et gérez vos instances et clusters en un seul endroit.",
                      Sauvegardes:
                        "Protégez vos données avec des sauvegardes répliquées sur un autre site.",
                      Réplication:
                        "Une infrastructure résiliente, répartie sur trois datacenters français.",
                      "Demandes de ressources":
                        "Suivez vos demandes de création et d’extension de ressources.",
                      Facturation:
                        "Une vision claire de votre consommation et de vos dépenses.",
                      "Sécurité & accès":
                        "Gardez le contrôle de votre compte et de vos accès.",
                      Administration:
                        "Validez les comptes clients et les demandes de ressources.",
                    }[page]}
              </p>
            </div>
            <div className="heading-actions">
              {page === "Vue d’ensemble" && (
                <button
                  className="button secondary"
                  onClick={() => open("help")}
                >
                  <BookOpen size={16} />
                  Documentation
                  <ArrowUpRight size={14} />
                </button>
              )}
              <button className="button primary" onClick={() => open("create")}>
                <Plus size={17} />
                Créer une base de données
              </button>
            </div>
          </div>
          {page === "Vue d’ensemble" && (
            <>
              <div className="sovereign-banner">
                <span className="banner-icon">
                  <ShieldCheck size={23} />
                </span>
                <div>
                  <strong>
                    La performance du cloud. La confiance du souverain.
                  </strong>
                  <p>
                    Vos données sont hébergées et répliquées exclusivement en
                    France.
                  </p>
                </div>
                <span className="france">
                  <i />
                  Infrastructure 100% française
                </span>
              </div>
              <div className="stats-grid">
                {[
                  [
                    Database,
                    "Bases de données",
                    dbs.length,
                    "instances et clusters",
                    `${dbs.filter((d) => d.status === "running").length} disponibles`,
                  ],
                  [
                    Cpu,
                    "vCPU alloués",
                    totals.cpu,
                    "vCPU au total",
                    "Ressources dédiées",
                  ],
                  [
                    HardDrive,
                    "Stockage provisionné",
                    totals.storage,
                    "Go SSD NVMe",
                    `${Math.round(allocated.reduce((a, d) => a + (d.storage * nodes(d) * d.usage) / 100, 0))} Go utilisés`,
                  ],
                  [
                    CreditCard,
                    "Coût mensuel estimé",
                    euro(monthly),
                    "HT · mois en cours",
                    "Voir ma facturation",
                  ],
                ].map(([Icon, label, value, unit, foot], i) => (
                  <div className="stat-card" key={label}>
                    <div className="stat-label">
                      {label}
                      <Icon size={18} />
                    </div>
                    <div className="stat-value">
                      {value}
                      {i === 1 && <span>vCPU</span>}
                      {i === 2 && <span>Go</span>}
                    </div>
                    <div className="stat-footer">
                      {i === 0 ? (
                        <>
                          <i className="status-dot" />
                          {foot}
                        </>
                      ) : i === 3 ? (
                        <button onClick={() => go("Facturation")}>
                          {foot}
                          <ArrowRight size={13} />
                        </button>
                      ) : (
                        <>
                          <span className="stat-unit">{unit}</span>
                          <span>{foot}</span>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <div className="charts-grid">
                <section className="panel consumption">
                  <div className="panel-header">
                    <div>
                      <h2>Consommation des ressources</h2>
                      <p>Utilisation moyenne sur l’ensemble de vos bases</p>
                    </div>
                    <select
                      aria-label="Période"
                      value={period}
                      onChange={(e) => setPeriod(e.target.value)}
                    >
                      <option>24 dernières heures</option>
                      <option>7 derniers jours</option>
                      <option>30 derniers jours</option>
                    </select>
                  </div>
                  <div className="chart-legend">
                    <span>
                      <i className="legend-cpu" />
                      CPU <strong>42 %</strong>
                    </span>
                    <span>
                      <i className="legend-ram" />
                      Mémoire <strong>55 %</strong>
                    </span>
                    <small>
                      {user
                        ? "Métriques simulées · télémétrie à connecter"
                        : "Données de démonstration"}
                    </small>
                  </div>
                  <div className="resource-chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart
                        data={chartData.map((d, i) => ({
                          ...d,
                          hour: period.startsWith("7")
                            ? `J${Math.floor(i / 4) + 1}`
                            : period.startsWith("30")
                              ? `${i + 1} oct.`
                              : d.hour,
                        }))}
                        margin={{ top: 8, right: 12, bottom: 0, left: -20 }}
                      >
                        <defs>
                          <linearGradient id="cpu" x1="0" y1="0" x2="0" y2="1">
                            <stop
                              offset="0%"
                              stopColor="#49876c"
                              stopOpacity={0.2}
                            />
                            <stop
                              offset="100%"
                              stopColor="#49876c"
                              stopOpacity={0}
                            />
                          </linearGradient>
                          <linearGradient id="ram" x1="0" y1="0" x2="0" y2="1">
                            <stop
                              offset="0%"
                              stopColor="#9ab5da"
                              stopOpacity={0.1}
                            />
                            <stop
                              offset="100%"
                              stopColor="#9ab5da"
                              stopOpacity={0}
                            />
                          </linearGradient>
                        </defs>
                        <CartesianGrid
                          strokeDasharray="3 4"
                          vertical={false}
                          stroke="#edf0ef"
                        />
                        <XAxis
                          dataKey="hour"
                          tick={{
                            fontSize: 10,
                            fill: "#9a a5a0".replace(" ", ""),
                          }}
                          tickLine={false}
                          axisLine={false}
                          interval={3}
                        />
                        <YAxis
                          domain={[0, 100]}
                          ticks={[0, 25, 50, 75, 100]}
                          tickFormatter={(v) => `${v}%`}
                          tick={{ fontSize: 10, fill: "#98a39e" }}
                          axisLine={false}
                          tickLine={false}
                        />
                        <Tooltip
                          formatter={(v, n) => [
                            `${v}%`,
                            n === "cpu" ? "CPU" : "Mémoire",
                          ]}
                          contentStyle={{
                            borderRadius: 9,
                            border: "1px solid #e2e8e4",
                            fontSize: 12,
                          }}
                        />
                        <Area
                          type="monotone"
                          dataKey="ram"
                          stroke="#8eabd0"
                          strokeWidth={2}
                          fill="url(#ram)"
                        />
                        <Area
                          type="monotone"
                          dataKey="cpu"
                          stroke="#397b5d"
                          strokeWidth={2.2}
                          fill="url(#cpu)"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </section>
                <section className="panel datacenters">
                  <div className="panel-header">
                    <div>
                      <h2>Vos datacenters</h2>
                      <p>Une présence locale, une résilience nationale</p>
                    </div>
                    <span className="live-dot" />
                  </div>
                  <div className="france-map">
                    <svg
                      viewBox="0 0 290 177"
                      aria-label="Carte des datacenters en France"
                    >
                      <defs>
                        <pattern
                          id="dots"
                          width="7"
                          height="7"
                          patternUnits="userSpaceOnUse"
                        >
                          <circle cx="2" cy="2" r="1.1" fill="#d7e0da" />
                        </pattern>
                      </defs>
                      <path
                        d="M121 10 142 22 165 19 175 35 204 41 218 58 206 76 213 94 199 113 209 136 193 146 175 143 160 163 135 160 118 143 102 143 98 126 79 116 76 96 50 81 45 65 26 61 32 49 59 48 70 33 90 36 102 25Z"
                        fill="url(#dots)"
                      />
                      <path
                        d="M141 52 Q191 73 174 102 M174 102 178 137 M141 52 Q120 106 178 137"
                        fill="none"
                        stroke="#74a489"
                        strokeWidth="1.2"
                        strokeDasharray="4 4"
                      />
                      <circle cx="141" cy="52" r="11" fill="#e4eee7" />
                      <circle cx="141" cy="52" r="4.5" fill="#367757" />
                      <circle cx="174" cy="102" r="9" fill="#e4eee7" />
                      <circle cx="174" cy="102" r="4" fill="#367757" />
                      <circle cx="178" cy="137" r="9" fill="#e4eee7" />
                      <circle cx="178" cy="137" r="4" fill="#367757" />
                      <text x="156" y="49">
                        Paris
                      </text>
                      <text x="190" y="103">
                        Lyon
                      </text>
                      <text x="193" y="140">
                        Marseille
                      </text>
                    </svg>
                  </div>
                  <div className="dc-list">
                    {["Paris · DC1", "Lyon · DC2", "Marseille · DC3"].map(
                      (dc) => (
                        <div key={dc}>
                          <span>
                            <i />
                            {dc}
                          </span>
                          <span>Opérationnel</span>
                        </div>
                      ),
                    )}
                  </div>
                  <button
                    className="panel-link"
                    onClick={() => go("Réplication")}
                  >
                    Voir la réplication inter-sites
                    <ArrowRight size={14} />
                  </button>
                </section>
              </div>
              <section className="panel database-panel">
                <div className="panel-header">
                  <div className="title-inline">
                    <h2>Vos bases de données</h2>
                    <span className="count">{dbs.length}</span>
                  </div>
                  <button
                    className="text-link muted"
                    onClick={() => go("Bases de données")}
                  >
                    Tout voir
                    <ArrowRight size={15} />
                  </button>
                </div>
                {databaseTable()}
              </section>
              <div className="bottom-grid">
                <section className="panel activity-panel">
                  <div className="panel-header">
                    <h2>Activité récente</h2>
                    <span className="muted-small">Aujourd’hui</span>
                  </div>
                  <div className="activity-row">
                    <span className="activity-icon">
                      <CheckCheck size={17} />
                    </span>
                    <div>
                      <strong>
                        {backups[0]?.status === "Simulée"
                          ? "Sauvegarde simulée enregistrée"
                          : "Sauvegarde automatique terminée"}
                      </strong>
                      <p>
                        {backups[0]?.name || "Aucune sauvegarde"}{" "}
                        <span>· {backups[0]?.site}</span>
                      </p>
                    </div>
                    <time>03:00</time>
                  </div>
                  <div className="activity-row">
                    <span className="activity-icon blue">
                      <RefreshCw size={16} />
                    </span>
                    <div>
                      <strong>Réplication inter-sites active</strong>
                      <p>
                        Paris → Lyon → Marseille <span>· Démonstration</span>
                      </p>
                    </div>
                    <time>02:45</time>
                  </div>
                </section>
                <section className="support-card">
                  <span className="support-icon">
                    <ShieldCheck size={27} />
                  </span>
                  <div>
                    <h3>Une infrastructure qui vous accompagne.</h3>
                    <p>
                      Un besoin d’évolution ? Nos équipes sont à vos côtés
                      <br className="desktop-break" /> pour dimensionner votre
                      prochain projet.
                    </p>
                    <button onClick={() => open("help")}>
                      Contacter un expert
                      <ArrowUpRight size={14} />
                    </button>
                  </div>
                </section>
              </div>
            </>
          )}
          {page === "Bases de données" && (
            <section className="panel">
              <div className="panel-header">
                <div className="search-box">
                  <Search size={16} />
                  <input
                    placeholder="Rechercher une base de données…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </div>
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  aria-label="Filtrer par moteur"
                >
                  <option value="all">Tous les moteurs</option>
                  {["PostgreSQL", "MySQL", "Redis"].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </div>
              {databaseTable()}
            </section>
          )}
          {page === "Sauvegardes" && (
            <>
              <div className="notice">
                <ShieldCheck size={19} />
                Les opérations sont simulées. La rétention cible est de 30
                jours, avec copie sur un datacenter distinct.
              </div>
              <section className="panel">
                <div className="panel-header">
                  <h2>Points de restauration</h2>
                  <button
                    className="button secondary"
                    onClick={() => open("backup")}
                  >
                    <Plus size={16} />
                    Nouvelle sauvegarde
                  </button>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Base de données</th>
                        <th>Date</th>
                        <th>Taille</th>
                        <th>Site de réplication</th>
                        <th>Statut</th>
                      </tr>
                    </thead>
                    <tbody>
                      {backups.map((b) => (
                        <tr key={b.id}>
                          <td>
                            <strong>{b.name}</strong>
                          </td>
                          <td>{b.date}</td>
                          <td>{b.size}</td>
                          <td>{b.site}</td>
                          <td>
                            <span className="badge green">
                              <Check size={12} />
                              {b.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
          {page === "Réplication" && (
            <>
              <div className="notice">
                <RefreshCw size={18} />
                Topologie cible · Réplication asynchrone chiffrée ·
                Provisionnement cloud simulé
              </div>
              <div className="replication-grid">
                {["Paris · DC1", "Lyon · DC2", "Marseille · DC3"].map(
                  (dc, i) => (
                    <section className="panel site-card" key={dc}>
                      <span className="site-icon">
                        <Server size={30} />
                      </span>
                      <span className="badge green">
                        <i />
                        Site disponible · démo
                      </span>
                      <h2>{dc}</h2>
                      <p>{i === 0 ? "Site primaire" : "Site de réplication"}</p>
                      <div>
                        <span>Instances hébergées</span>
                        <strong>
                          {dbs.filter((d) => d.datacenter === dc).length}
                        </strong>
                      </div>
                      <div>
                        <span>Localisation</span>
                        <strong>France</strong>
                      </div>
                      <div>
                        <span>Chiffrement cible</span>
                        <strong>TLS 1.3</strong>
                      </div>
                    </section>
                  ),
                )}
              </div>
              <section className="panel">
                <div className="panel-header">
                  <h2>Politique de continuité</h2>
                  <ShieldCheck size={20} />
                </div>
                <div className="policy-grid">
                  <div>
                    <small>RÉPLICATION</small>
                    <h3>Inter-datacenters</h3>
                    <p>
                      Chaque sauvegarde est affectée à un site distinct du site
                      primaire.
                    </p>
                  </div>
                  <div>
                    <small>OBJECTIFS À VALIDER</small>
                    <h3>RPO & RTO contractuels</h3>
                    <p>
                      À définir selon le moteur et les capacités de votre
                      infrastructure.
                    </p>
                  </div>
                  <div>
                    <small>SOUVERAINETÉ</small>
                    <h3>Trois sites français</h3>
                    <p>
                      Aucun transfert de données en dehors des datacenters
                      autorisés.
                    </p>
                  </div>
                </div>
              </section>
            </>
          )}
          {(page === "Demandes de ressources" || page === "Administration") && (
            <>
              <div className="section-toolbar">
                <div className="tabs">
                  <button className="selected">
                    Toutes les demandes <span>{requests.length}</span>
                  </button>
                </div>
                {!user && (
                  <button
                    className="button secondary"
                    onClick={() => setAdmin(!admin)}
                  >
                    <Users size={15} />
                    {admin
                      ? "Quitter la vue admin démo"
                      : "Vue administrateur démo"}
                  </button>
                )}
              </div>
              <section className="panel">
                <div className="panel-header">
                  <h2>Demandes de ressources</h2>
                  <span className="badge amber">
                    {pending.length} en attente
                  </span>
                </div>
                {!requests.length ? (
                  <div className="empty">
                    <Cpu size={32} />
                    <h3>Aucune demande pour le moment</h3>
                    <p>
                      Créez une base ou demandez une extension depuis une
                      instance existante.
                    </p>
                    <button
                      className="button primary"
                      onClick={() => open("create")}
                    >
                      <Plus size={16} />
                      Créer une base de données
                    </button>
                  </div>
                ) : (
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Base</th>
                          <th>Demande</th>
                          <th>Ressources souhaitées</th>
                          <th>Statut</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {requests.map((r) => (
                          <tr key={r.id}>
                            <td>
                              <strong>{r.name}</strong>
                            </td>
                            <td>{r.type}</td>
                            <td>
                              {r.cpu} vCPU · {r.ram} Go · {r.storage} Go
                            </td>
                            <td>
                              <span
                                className={`badge ${r.status === "approved" ? "green" : "amber"}`}
                              >
                                {r.status === "pending"
                                  ? "En attente"
                                  : r.status === "approved"
                                    ? "Approuvée"
                                    : "Refusée"}
                              </span>
                            </td>
                            <td>
                              {admin && r.status === "pending" ? (
                                <div className="row-actions">
                                  <button
                                    className="button primary compact"
                                    onClick={() => approve(r, "approved")}
                                  >
                                    <Check size={14} />
                                    Approuver
                                  </button>
                                  <button
                                    className="button secondary compact"
                                    onClick={() => approve(r, "rejected")}
                                  >
                                    Refuser
                                  </button>
                                </div>
                              ) : (
                                <span className="muted-small">
                                  {r.status === "pending"
                                    ? "Validation administrateur requise"
                                    : "Traitée"}
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
              {page === "Administration" && (
                <AdminUsers call={call} notify={notify} />
              )}
            </>
          )}
          {page === "Facturation" && (
            <>
              <div className="billing-grid">
                <section className="panel billing-summary">
                  <span className="eyebrow">ESTIMATION MENSUELLE</span>
                  <h2>
                    {euro(monthly)}
                    <small> HT / mois</small>
                  </h2>
                  <p>
                    Estimation selon les ressources actuellement disponibles.
                  </p>
                  <button className="button primary" onClick={download}>
                    <ArrowDownToLine size={16} />
                    Estimation PDF du mois
                  </button>
                </section>
                <section className="panel">
                  <div className="panel-header">
                    <h2>Une facturation à votre rythme</h2>
                    <CreditCard size={20} />
                  </div>
                  <div className="billing-info">
                    <p>
                      Choisissez votre formule lors de la création d’une base de
                      données.
                    </p>
                    <div className="plan-tags">
                      {[
                        "Pay-as-you-Go",
                        "1 mois",
                        "3 mois · −5 %",
                        "6 mois · −10 %",
                        "1 an · −15 %",
                      ].map((p) => (
                        <span key={p}>{p}</span>
                      ))}
                    </div>
                    <small>
                      Les factures sont envoyées par email le premier jour du
                      mois lorsque le planificateur est actif.
                    </small>
                  </div>
                </section>
              </div>
              <section className="panel">
                <div className="panel-header">
                  <h2>Détail des coûts estimés</h2>
                  <span className="muted-small">
                    Tarifs de démonstration · hors taxes
                  </span>
                </div>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Base de données</th>
                        <th>Formule</th>
                        <th>Ressources</th>
                        <th>Estimation mensuelle</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dbs
                        .filter((d) => d.status === "running")
                        .map((d) => (
                          <tr key={d.id}>
                            <td>
                              <strong>{d.name}</strong>
                            </td>
                            <td>
                              {d.plan === "payg"
                                ? "Pay-as-you-Go"
                                : `${d.plan} mois`}
                            </td>
                            <td>
                              {d.cpu} vCPU · {d.ram} Go · {d.storage} Go SSD
                              {d.mode === "cluster" ? " × 3 nœuds" : ""}
                            </td>
                            <td>{euro(price(d))}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
          {page === "Sécurité & accès" && (
            <div className="security-grid">
              <section className="panel">
                <div className="panel-header">
                  <h2>Authentification multifacteur</h2>
                  <LockKeyhole size={20} />
                </div>
                <div className="security-body">
                  <p>
                    Chaque connexion nécessite un code à usage unique, valable 5
                    minutes.
                  </p>
                  {[
                    [
                      "email",
                      "Code par email",
                      "Envoyé à votre adresse de connexion",
                    ],
                    [
                      "whatsapp",
                      "Code par WhatsApp",
                      "Nécessite un numéro vérifié et un fournisseur configuré",
                    ],
                  ].map(([key, label, desc]) => (
                    <div className="setting-row" key={key}>
                      <div>
                        <strong>{label}</strong>
                        <small>{desc}</small>
                      </div>
                      <span
                        className={`badge ${key === "email" ? "green" : "amber"}`}
                      >
                        {key === "email"
                          ? "Obligatoire"
                          : user?.user?.phone_verified_at
                            ? "Numéro vérifié"
                            : "À configurer"}
                      </span>
                    </div>
                  ))}
                  <div className="notice small-notice">
                    Les préférences de sécurité réelles sont contrôlées par le
                    serveur.
                  </div>
                </div>
              </section>
              <section className="panel">
                <div className="panel-header">
                  <h2>Protection de l’infrastructure</h2>
                  <ShieldCheck size={20} />
                </div>
                <div className="security-body">
                  {[
                    "Isolation des comptes clients",
                    "Validation administrative des ressources",
                    "Journalisation des opérations sensibles",
                    "Mots de passe hachés et codes MFA à durée limitée",
                  ].map((v) => (
                    <div className="check-row" key={v}>
                      <Check size={17} />
                      {v}
                    </div>
                  ))}
                </div>
              </section>
            </div>
          )}
          {page === "Sécurité & accès" && user && (
            <PhoneEnrollment
              call={call}
              user={user}
              setUser={setUser}
              notify={notify}
            />
          )}
          {page === "Facturation" && user && (
            <InvoiceHistory call={call} user={user} notify={notify} />
          )}
          <footer>
            <span>
              <ShieldCheck size={13} />
              Souverain Cloud · Vos données restent chez vous.
            </span>
            <span>
              <i className="status-dot" />
              {user
                ? "API connectée · cloud simulé"
                : "Console de démonstration"}
              <span className="footer-version">v1.0</span>
            </span>
          </footer>
        </main>
      </div>
      {toast && (
        <div className="toast" role="status">
          <Check size={18} />
          {toast}
          <button onClick={() => setToast("")} aria-label="Fermer">
            <X size={15} />
          </button>
        </div>
      )}
      {modal && (
        <div
          className="modal-overlay"
          onClick={() => {
            setModal(null);
            setChallenge(null);
          }}
        >
          <section
            className={`modal ${["create", "extend"].includes(modal.type) ? "wide-modal" : ""}`}
            role="dialog"
            aria-modal="true"
            aria-label="Fenêtre de gestion"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <div>
                <span className="eyebrow">SOUVERAIN CLOUD</span>
                <h2>
                  {
                    {
                      create: "Créer une base de données",
                      extend: "Étendre les ressources",
                      detail: modal.db?.name,
                      help: "Votre centre de ressources",
                      login: challenge
                        ? "Vérification en deux étapes"
                        : "Connexion à votre espace",
                      register: "Créer un compte client",
                      backup: "Nouvelle sauvegarde",
                      account: "Votre compte",
                    }[modal.type]
                  }
                </h2>
              </div>
              <button
                className="icon-button"
                onClick={() => {
                  setModal(null);
                  setChallenge(null);
                }}
                aria-label="Fermer"
              >
                <X size={21} />
              </button>
            </div>
            {["create", "extend"].includes(modal.type) && (
              <form onSubmit={saveRequest}>
                <div className="notice small-notice">
                  <Clock3 size={17} />
                  Les ressources seront provisionnées après validation
                  administrateur.
                </div>
                <div className="form-grid">
                  <label className="full">
                    Nom de la base
                    <input
                      required
                      pattern="[a-z][a-z0-9-]{2,39}"
                      title="3 à 40 caractères : lettres minuscules, chiffres et tirets"
                      placeholder="ex. production-db"
                      value={form.name}
                      disabled={modal.type === "extend"}
                      onChange={(e) =>
                        setForm({ ...form, name: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Moteur
                    <select
                      value={form.engine}
                      disabled={modal.type === "extend"}
                      onChange={(e) =>
                        setForm({ ...form, engine: e.target.value })
                      }
                    >
                      {["PostgreSQL", "MySQL", "Redis"].map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Datacenter
                    <select
                      value={form.datacenter}
                      disabled={modal.type === "extend"}
                      onChange={(e) =>
                        setForm({ ...form, datacenter: e.target.value })
                      }
                    >
                      {["Paris · DC1", "Lyon · DC2", "Marseille · DC3"].map(
                        (v) => (
                          <option key={v}>{v}</option>
                        ),
                      )}
                    </select>
                  </label>
                  <div className="full">
                    <span className="field-label">Architecture</span>
                    <div className="architecture-options">
                      {[
                        ["single", "Instance simple", "Un nœud dédié"],
                        [
                          "cluster",
                          "Cluster haute disponibilité",
                          "3 nœuds dédiés",
                        ],
                      ].map(([v, title, desc]) => (
                        <button
                          disabled={modal.type === "extend"}
                          type="button"
                          key={v}
                          onClick={() => setForm({ ...form, mode: v })}
                          className={form.mode === v ? "chosen" : ""}
                        >
                          <Server size={20} />
                          <strong>{title}</strong>
                          <small>{desc}</small>
                          {form.mode === v && <Check size={15} />}
                        </button>
                      ))}
                    </div>
                  </div>
                  <label>
                    CPU (vCPU)
                    <select
                      value={form.cpu}
                      onChange={(e) =>
                        setForm({ ...form, cpu: +e.target.value })
                      }
                    >
                      {[2, 4, 8, 16, 32, 64]
                        .filter(
                          (n) => modal.type !== "extend" || n >= modal.db.cpu,
                        )
                        .map((n) => (
                          <option key={n} value={n}>
                            {n} vCPU
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Mémoire (Go)
                    <select
                      value={form.ram}
                      onChange={(e) =>
                        setForm({ ...form, ram: +e.target.value })
                      }
                    >
                      {[8, 16, 32, 64, 128, 256]
                        .filter(
                          (n) => modal.type !== "extend" || n >= modal.db.ram,
                        )
                        .map((n) => (
                          <option key={n} value={n}>
                            {n} Go RAM
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Stockage SSD (Go)
                    <input
                      type="number"
                      min={modal.type === "extend" ? modal.db.storage : 20}
                      max="10000"
                      required
                      value={form.storage}
                      onChange={(e) =>
                        setForm({ ...form, storage: +e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Formule
                    <select
                      value={form.plan}
                      disabled={modal.type === "extend"}
                      onChange={(e) =>
                        setForm({ ...form, plan: e.target.value })
                      }
                    >
                      <option value="payg">Pay-as-you-Go</option>
                      <option value="1">Pack 1 mois</option>
                      <option value="3">Pack 3 mois · −5 %</option>
                      <option value="6">Pack 6 mois · −10 %</option>
                      <option value="12">Pack 1 an · −15 %</option>
                    </select>
                  </label>
                </div>
                <div className="estimate">
                  <span>Estimation mensuelle HT</span>
                  <strong>{euro(price(form))}</strong>
                </div>
                {error && <p className="error">{error}</p>}
                <div className="modal-footer">
                  <button
                    type="button"
                    className="button secondary"
                    onClick={() => setModal(null)}
                  >
                    Annuler
                  </button>
                  <button disabled={busy} className="button primary">
                    {busy ? "Envoi…" : "Envoyer la demande"}
                    <ArrowRight size={15} />
                  </button>
                </div>
              </form>
            )}
            {modal.type === "detail" && (
              <>
                <span
                  className={`badge ${modal.db.status === "running" ? "green" : "amber"}`}
                >
                  <i />
                  {statusLabel[modal.db.status]}
                </span>
                <div className="detail-grid">
                  {[
                    ["Moteur", `${modal.db.engine} ${modal.db.version}`],
                    [
                      "Architecture",
                      modal.db.mode === "cluster"
                        ? "Cluster · 3 nœuds"
                        : "Instance simple",
                    ],
                    ["CPU", `${modal.db.cpu} vCPU`],
                    ["Mémoire", `${modal.db.ram} Go`],
                    ["Stockage", `${modal.db.storage} Go SSD`],
                    ["Datacenter", modal.db.datacenter],
                  ].map(([k, v]) => (
                    <div key={k}>
                      <small>{k}</small>
                      <strong>{v}</strong>
                    </div>
                  ))}
                </div>
                <div className="notice small-notice">
                  Les identifiants et endpoints seront disponibles après
                  raccordement au fournisseur cloud.
                </div>
                <div className="modal-footer">
                  <button
                    className="button secondary"
                    onClick={() => backup(modal.db)}
                  >
                    <HardDrive size={16} />
                    Sauvegarder
                  </button>
                  <button
                    className="button primary"
                    onClick={() => open("extend", modal.db)}
                  >
                    <Cpu size={16} />
                    Étendre les ressources
                  </button>
                </div>
              </>
            )}
            {modal.type === "help" && (
              <div className="help-content">
                <p>Gérez vos bases de données en trois étapes.</p>
                {[
                  [
                    "01",
                    "Configurez votre base",
                    "Choisissez un moteur, un site, des ressources et une formule de facturation.",
                  ],
                  [
                    "02",
                    "Obtenez la validation",
                    "Un administrateur examine votre demande avant toute allocation.",
                  ],
                  [
                    "03",
                    "Pilotez votre infrastructure",
                    "Suivez vos ressources, sauvegardes et factures depuis cette console.",
                  ],
                ].map(([n, t, d]) => (
                  <div className="help-step" key={n}>
                    <b>{n}</b>
                    <div>
                      <strong>{t}</strong>
                      <p>{d}</p>
                    </div>
                  </div>
                ))}
                <div className="notice small-notice">
                  Pour contacter un expert, configurez l’adresse de support de
                  votre fournisseur dans le déploiement.
                </div>
                <button
                  className="button primary"
                  onClick={() => {
                    setModal(null);
                    go("Demandes de ressources");
                  }}
                >
                  Voir mes demandes
                  <ArrowRight size={15} />
                </button>
              </div>
            )}
            {["login", "register"].includes(modal.type) && (
              <form onSubmit={login}>
                {!api && (
                  <div className="notice small-notice">
                    Démarrez l’API Laravel pour utiliser les comptes sécurisés.
                  </div>
                )}
                {challenge ? (
                  <label>
                    Code de vérification
                    <input
                      autoFocus
                      required
                      inputMode="numeric"
                      pattern="[0-9]{6}"
                      maxLength={6}
                      value={auth.code}
                      onChange={(e) =>
                        setAuth({ ...auth, code: e.target.value })
                      }
                    />
                  </label>
                ) : (
                  <div className="auth-fields">
                    {modal.type === "register" && (
                      <label>
                        Nom complet
                        <input
                          required
                          value={auth.name}
                          onChange={(e) =>
                            setAuth({ ...auth, name: e.target.value })
                          }
                        />
                      </label>
                    )}
                    <label>
                      Adresse email
                      <input
                        type="email"
                        required
                        value={auth.email}
                        onChange={(e) =>
                          setAuth({ ...auth, email: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Mot de passe
                      <input
                        type="password"
                        minLength={12}
                        required
                        value={auth.password}
                        onChange={(e) =>
                          setAuth({ ...auth, password: e.target.value })
                        }
                      />
                    </label>
                    {modal.type === "register" ? (
                      <>
                        <label>
                          WhatsApp (format international, facultatif)
                          <input
                            placeholder="+33612345678"
                            value={auth.phone}
                            onChange={(e) =>
                              setAuth({ ...auth, phone: e.target.value })
                            }
                          />
                        </label>
                        <p className="muted-small">
                          Votre compte sera activé après validation par un
                          administrateur.
                        </p>
                      </>
                    ) : (
                      <label>
                        Canal de vérification
                        <select
                          value={auth.channel}
                          onChange={(e) =>
                            setAuth({ ...auth, channel: e.target.value })
                          }
                        >
                          <option value="email">Email</option>
                          <option value="whatsapp">
                            WhatsApp (si configuré)
                          </option>
                        </select>
                      </label>
                    )}
                  </div>
                )}
                {error && <p className="error">{error}</p>}
                <div className="modal-footer">
                  <button
                    type="button"
                    className="text-link"
                    onClick={() => {
                      setChallenge(null);
                      open(modal.type === "login" ? "register" : "login");
                    }}
                  >
                    {modal.type === "login"
                      ? "Créer un compte"
                      : "Se connecter"}
                  </button>
                  <button className="button primary" disabled={busy || !api}>
                    {busy
                      ? "Patientez…"
                      : challenge
                        ? "Vérifier"
                        : modal.type === "register"
                          ? "Créer mon compte"
                          : "Se connecter"}
                    <ArrowRight size={15} />
                  </button>
                </div>
              </form>
            )}
            {modal.type === "backup" && (
              <div className="backup-choices">
                {dbs
                  .filter((d) => d.status === "running")
                  .map((d) => (
                    <button
                      key={d.id}
                      onClick={() => {
                        backup(d);
                        setModal(null);
                      }}
                    >
                      <Database size={19} />
                      <span>
                        {d.name}
                        <small>{d.datacenter}</small>
                      </span>
                      <Plus size={16} />
                    </button>
                  ))}
                {!dbs.some((d) => d.status === "running") && (
                  <p>Aucune base disponible.</p>
                )}
              </div>
            )}
            {modal.type === "account" && (
              <div>
                <p>
                  {user?.user?.name}
                  <br />
                  {user?.user?.email}
                </p>
                <span className="badge green">
                  {user?.user?.role === "admin" ? "Administrateur" : "Client"}
                </span>
                <div className="modal-footer">
                  <button
                    className="button secondary"
                    onClick={async () => {
                      try {
                        await call("/logout", { method: "POST" });
                      } catch {}
                      setUser(null);
                      setAdmin(false);
                      setDbs(initialDatabases);
                      setRequests([]);
                      setBackups([]);
                      setModal(null);
                      notify("Déconnexion effectuée");
                    }}
                  >
                    <LogOut size={16} />
                    Se déconnecter
                  </button>
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

function AdminUsers({ call, notify }) {
  const [users, setUsers] = useState([]);
  useEffect(() => {
    call("/admin/users")
      .then(setUsers)
      .catch((e) => notify(e.message));
  }, []);
  return (
    <section className="panel admin-users">
      <div className="panel-header">
        <h2>Activation des comptes clients</h2>
        <Users size={19} />
      </div>
      {!users.length ? (
        <div className="empty">
          Aucun compte à afficher. Connectez-vous avec un compte administrateur.
        </div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Client</th>
                <th>Email</th>
                <th>Statut</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.name}</td>
                  <td>{u.email}</td>
                  <td>{u.status === "active" ? "Actif" : "En attente"}</td>
                  <td>
                    {u.status === "pending" && (
                      <button
                        className="button primary compact"
                        onClick={async () => {
                          try {
                            await call(`/admin/users/${u.id}/approve`, {
                              method: "POST",
                            });
                            setUsers(
                              users.map((x) =>
                                x.id === u.id ? { ...x, status: "active" } : x,
                              ),
                            );
                            notify("Compte activé");
                          } catch (e) {
                            notify(e.message);
                          }
                        }}
                      >
                        Activer le compte
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function PhoneEnrollment({ call, user, setUser, notify }) {
  const [phone, setPhone] = useState(user.user.phone || ""),
    [code, setCode] = useState(""),
    [challenge, setChallenge] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (challenge) {
        const data = await call("/mfa/whatsapp/verify", {
          method: "POST",
          body: JSON.stringify({ challenge_id: challenge, code }),
        });
        setUser({ ...user, user: data.user });
        setChallenge(null);
        notify(data.message);
      } else {
        const data = await call("/mfa/whatsapp/enroll", {
          method: "POST",
          body: JSON.stringify({ phone }),
        });
        setChallenge(data.challenge_id);
        notify("Code envoyé à votre numéro WhatsApp.");
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="panel admin-users">
      <div className="panel-header">
        <h2>Vérifier votre numéro WhatsApp</h2>
        {user.user.phone_verified_at && (
          <span className="badge green">
            <Check size={12} />
            Numéro vérifié
          </span>
        )}
      </div>
      <form className="phone-form" onSubmit={submit}>
        <p>
          Connectez votre numéro pour recevoir vos codes de connexion via
          WhatsApp.
        </p>
        {challenge ? (
          <label>
            Code à six chiffres
            <input
              required
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength="6"
              value={code}
              onChange={(e) => setCode(e.target.value)}
            />
          </label>
        ) : (
          <label>
            Numéro international
            <input
              required
              pattern="\+[1-9][0-9]{7,14}"
              placeholder="+33612345678"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
            />
          </label>
        )}
        {error && <div className="error">{error}</div>}
        <button className="button primary" disabled={busy}>
          {busy
            ? "Patientez…"
            : challenge
              ? "Vérifier le code"
              : "Envoyer un code WhatsApp"}
          <ArrowRight size={14} />
        </button>
      </form>
    </section>
  );
}

function InvoiceHistory({ call, user, notify }) {
  const [invoices, setInvoices] = useState([]);
  useEffect(() => {
    call("/invoices")
      .then(setInvoices)
      .catch((e) => notify(e.message));
  }, []);
  const download = async (invoice) => {
    try {
      const r = await fetch(`/api/invoices/${invoice.id}/pdf`, {
        headers: { Authorization: `Bearer ${user.token}` },
      });
      if (!r.ok) throw new Error("Téléchargement impossible.");
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `${invoice.number}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      notify(e.message);
    }
  };
  return (
    <section className="panel admin-users">
      <div className="panel-header">
        <h2>Factures mensuelles</h2>
        <span className="muted-small">Périodes clôturées</span>
      </div>
      {!invoices.length ? (
        <div className="empty">
          Vos factures apparaîtront après la première clôture mensuelle.
        </div>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Numéro</th>
                <th>Période</th>
                <th>Montant HT</th>
                <th>Envoi email</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {invoices.map((i) => (
                <tr key={i.id}>
                  <td>
                    <strong>{i.number}</strong>
                  </td>
                  <td>{i.period}</td>
                  <td>{euro(i.total)}</td>
                  <td>{i.emailed_at ? "Envoyée" : "À envoyer"}</td>
                  <td>
                    <button
                      className="button secondary compact"
                      onClick={() => download(i)}
                    >
                      <ArrowDownToLine size={13} />
                      PDF
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
