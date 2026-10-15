import { StrictMode, useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Building2,
  Check,
  CheckCheck,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  Clock3,
  Code2,
  ExternalLink,
  FileCheck2,
  FilePlus2,
  Files,
  FileText,
  Fingerprint,
  FlaskConical,
  GitBranch,
  Layers3,
  ListChecks,
  LoaderCircle,
  LogOut,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
  X,
} from "lucide-react";
import {
  api,
  ApiError,
  type Application,
  type Audit,
  date,
  download,
  type Integration,
  labels,
  type Monitor,
  roleLabels,
  setToken,
  type User,
} from "./api";
import "./style.css";
import "@fontsource/golos-text/cyrillic-400.css";
import "@fontsource/golos-text/cyrillic-500.css";
import "@fontsource/golos-text/cyrillic-600.css";
import "@fontsource/golos-text/latin-400.css";
import "@fontsource/golos-text/latin-500.css";
import "@fontsource/golos-text/latin-600.css";

type View = "applications" | "review" | "monitor";
type Notice = {
  text: string;
  error?: boolean;
  code?: string;
  correlation?: string;
};
const editable = ["DRAFT", "NEEDS_CORRECTION", "AWAITING_APPLICANT_SIGNATURE"];

function Badge({ status }: { status: string }) {
  const color =
    status === "COMPLETED"
      ? "green"
      : ["REJECTED", "CANCELLED"].includes(status)
        ? "gray"
        : status === "DRAFT"
          ? "gray"
          : status === "NEEDS_CORRECTION"
            ? "orange"
            : "blue";
  return (
    <span className={`badge ${color}`}>
      <span />
      {labels[status] || status}
    </span>
  );
}

function Portal() {
  const [user, setUser] = useState<User | null>(null);
  const [loginOpen, setLoginOpen] = useState(true);
  const [view, setView] = useState<View>("applications");
  const [items, setItems] = useState<Application[]>([]);
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [selected, setSelected] = useState<Application | null>(null);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [tab, setTab] = useState<"document" | "audit" | "integration">(
    "document",
  );
  const [username, setUsername] = useState("applicant.a");
  const [password, setPassword] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState("PERMIT");
  const [reason, setReason] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const submitKeys = useRef(new Map<string, string>());
  const fail = useCallback((error: unknown) => {
    setNotice({
      text: error instanceof Error ? error.message : "Сеть недоступна",
      error: true,
      code: error instanceof ApiError ? error.code : "NETWORK_ERROR",
      correlation: error instanceof ApiError ? error.correlation : undefined,
    });
    if (error instanceof ApiError && error.code === "UNAUTHORIZED")
      setLoginOpen(true);
  }, []);

  const refresh = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      if (user.role !== "qa_observer") {
        const result = await api<{ items: Application[] }>(
          "/applications?limit=100",
        );
        setItems(result.items);
      } else setItems([]);
      if (user.role !== "applicant") setMonitor(await api<Monitor>("/monitor"));
    } catch (error) {
      fail(error);
    } finally {
      setLoading(false);
    }
  }, [user, fail]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const hasSelection = selected !== null;
  useEffect(() => {
    if (!loginOpen && !createOpen && !guideOpen && !hasSelection) return;
    const previous = document.activeElement as HTMLElement | null;
    const layers = document.querySelectorAll<HTMLElement>(
      ".overlay, .drawer-overlay",
    );
    const layer = layers[layers.length - 1];
    const focusable = () =>
      layer
        ? Array.from(
            layer.querySelectorAll<HTMLElement>(
              "button:not(:disabled), input:not([hidden]), select, textarea, a[href]",
            ),
          ).filter((el) => el.getClientRects().length > 0)
        : [];
    focusable()[0]?.focus();
    const handle = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) {
        if (guideOpen) setGuideOpen(false);
        else if (createOpen) setCreateOpen(false);
        else if (loginOpen && user) setLoginOpen(false);
        else if (!loginOpen) setSelected(null);
      }
      if (e.key === "Tab") {
        const nodes = focusable();
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", handle);
    return () => {
      document.removeEventListener("keydown", handle);
      previous?.focus();
    };
  }, [loginOpen, createOpen, guideOpen, hasSelection, busy, user]);
  // Poll only while an accepted local task is still processing.
  useEffect(() => {
    if (
      !items.some((a) =>
        ["SUBMITTED", "VALIDATING"].includes(a.business_status),
      )
    )
      return;
    const timer = setTimeout(() => void refresh(), 1200);
    return () => clearTimeout(timer);
  }, [items, refresh]);

  const open = async (id: string) => {
    try {
      const [app, events, checks] = await Promise.all([
        api<Application>(`/applications/${id}`),
        api<Audit[]>(`/applications/${id}/audit`),
        api<Integration[]>(`/applications/${id}/integrations`),
      ]);
      setSelected(app);
      setAudit(events);
      setIntegrations(checks);
      setTitle(app.title);
      setDescription(app.description);
      setType(app.type);
      setReason("");
    } catch (error) {
      fail(error);
    }
  };

  const act = async (action: string, extra: Record<string, unknown> = {}) => {
    if (!selected) return;
    setBusy(true);
    try {
      const command = { expected_version: selected.version, ...extra };
      const headers: Record<string, string> = {};
      if (action === "submit") {
        const slot = `${selected.id}:${selected.version}`;
        if (!submitKeys.current.has(slot))
          submitKeys.current.set(slot, crypto.randomUUID());
        headers["Idempotency-Key"] = submitKeys.current.get(slot)!;
      }
      await api(`/applications/${selected.id}/${action}`, {
        method: "POST",
        headers,
        body: JSON.stringify(command),
      });
      setNotice({
        text:
          action === "submit"
            ? "Заявление отправлено на локальную проверку"
            : "Изменения сохранены",
      });
      await open(selected.id);
      await refresh();
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  };

  const signIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const result = await api<{ access_token: string; user: User }>(
        "/auth/login",
        {
          method: "POST",
          body: JSON.stringify({ username, password }),
        },
      );
      setToken(result.access_token);
      setUser(result.user);
      setLoginOpen(false);
      setSelected(null);
      setItems([]);
      setMonitor(null);
      setNotice(null);
      setFilter("all");
      setSearch("");
      setView(
        result.user.role === "applicant"
          ? "applications"
          : result.user.role === "qa_observer"
            ? "monitor"
            : "review",
      );
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const result = await api<Application>(
        selected ? `/applications/${selected.id}` : "/applications",
        {
          method: selected ? "PATCH" : "POST",
          body: JSON.stringify({
            title,
            description,
            type,
            ...(selected ? { expected_version: selected.version } : {}),
          }),
        },
      );
      setCreateOpen(false);
      setNotice({
        text: selected
          ? "Новая ревизия сохранена. Подпишите её заново."
          : "Черновик создан. Добавьте тестовый документ.",
      });
      await refresh();
      await open(result.id);
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  };

  const attach = async (file?: File) => {
    if (!file || !selected) return;
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("expected_version", String(selected.version));
      await api(`/applications/${selected.id}/attachments`, {
        method: "POST",
        body: form,
      });
      await open(selected.id);
      await refresh();
      setNotice({ text: "Документ загружен. Хеш и ревизия обновлены." });
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const navigate = (next: View) => {
    setView(next);
    setSelected(null);
    setFilter("all");
    setSearch("");
  };
  const total = items.length;
  const done = items.filter((a) => a.business_status === "COMPLETED").length;
  const pending = items.filter(
    (a) =>
      !["DRAFT", "COMPLETED", "CANCELLED", "REJECTED"].includes(
        a.business_status,
      ),
  ).length;
  const visible = items.filter(
    (a) =>
      (filter === "all" || a.business_status === filter) &&
      `${a.title} ${a.id}`.toLowerCase().includes(search.toLowerCase()),
  );
  const canEdit =
    user?.role === "applicant" &&
    selected &&
    editable.includes(selected.business_status);

  return (
    <div className="shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="GovFlow — главная">
          <span className="brand-icon">
            <Layers3 size={24} />
          </span>
          <span>
            GovFlow<small>by ADLabs</small>
          </span>
        </a>
        <div className="workspace">
          <div className="workspace-symbol">
            <Building2 size={17} />
          </div>
          <span>
            CivicTech Solutions<small>Учебное пространство</small>
          </span>
          <ChevronDown size={15} />
        </div>
        <div className="nav-label">РАБОЧАЯ ОБЛАСТЬ</div>
        <nav>
          <button
            className={view === "applications" ? "active" : ""}
            onClick={() => navigate("applications")}
            disabled={user?.role === "qa_observer"}
          >
            <Files size={19} />
            Мои заявления
            {user?.role === "applicant" && (
              <span className="nav-count">{total}</span>
            )}
          </button>
          <button
            className={view === "review" ? "active" : ""}
            onClick={() => navigate("review")}
            disabled={!user || ["applicant", "qa_observer"].includes(user.role)}
          >
            <ListChecks size={19} />
            Очередь рассмотрения
          </button>
          <button
            className={view === "monitor" ? "active" : ""}
            onClick={() => navigate("monitor")}
            disabled={!user || user.role === "applicant"}
          >
            <Activity size={19} />
            QA Monitor
            <span className="live-dot" />
          </button>
        </nav>
        <div className="nav-label resources">РЕСУРСЫ ПРОЕКТА</div>
        <a className="resource" href="/docs" target="_blank" rel="noreferrer">
          <Code2 size={18} />
          Swagger API
          <ArrowUpRight size={14} />
        </a>
        <button className="resource" onClick={() => setGuideOpen(true)}>
          <BookOpen size={18} />
          Как устроен стенд
          <ArrowUpRight size={14} />
        </button>
        <div className="sidebar-bottom">
          <div className="reference-card">
            <FlaskConical size={19} />
            <strong>Reference environment</strong>
            <p>
              Детерминированный baseline.
              <br />
              Только синтетические данные.
            </p>
            <span>
              <span className="live-dot" />
              Stage 1 · v0.1.0
            </span>
          </div>
          <button className="profile" onClick={() => setLoginOpen(true)}>
            <span className="avatar">
              {user?.username.slice(0, 2).toUpperCase() || "QA"}
            </span>
            <span>
              {user?.username || "Учебный аккаунт"}
              <small>
                {user ? roleLabels[user.role] : "Войдите для начала"}
              </small>
            </span>
            <LogOut size={16} />
          </button>
        </div>
      </aside>

      <main>
        <header className="topbar">
          <div className="breadcrumbs">
            Рабочая область
            <ChevronRight size={14} />
            <strong>
              {view === "applications"
                ? "Мои заявления"
                : view === "review"
                  ? "Очередь рассмотрения"
                  : "QA Monitor"}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="env-tag">
              <span className="live-dot" />
              Локальный стенд
            </span>
            <span className="tenant-label">
              <Building2 size={15} />
              {user?.tenant_name || "CivicTech"}
            </span>
          </div>
        </header>
        <div className="page">
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                <span />
                GOVFLOW CORE · RELEASE R-1.4
              </div>
              <h1>
                {view === "monitor"
                  ? "Качество под наблюдением"
                  : view === "review"
                    ? "Очередь рассмотрения"
                    : "Мои заявления"}
              </h1>
              <p>
                {view === "monitor"
                  ? "Состояние системы и факты для вашего QA-расследования."
                  : view === "review"
                    ? "Проверяйте сведения и принимайте обоснованные решения."
                    : "Весь путь заявления: от первого черновика до подписанного решения."}
              </p>
            </div>
            {user?.role === "applicant" ? (
              <button
                className="primary"
                onClick={() => {
                  setSelected(null);
                  setTitle("");
                  setDescription("");
                  setType("PERMIT");
                  setCreateOpen(true);
                }}
              >
                <Plus size={18} />
                Создать заявление
              </button>
            ) : (
              <button
                className="secondary"
                disabled={loading}
                onClick={() => void refresh()}
              >
                <RefreshCw size={16} className={loading ? "spin" : ""} />
                Обновить данные
              </button>
            )}
          </div>

          {notice && (
            <div
              role={notice.error ? "alert" : "status"}
              className={`notice ${notice.error ? "error" : ""}`}
            >
              <div>
                {notice.error ? (
                  <ShieldCheck size={18} />
                ) : (
                  <CheckCircle2 size={18} />
                )}
                <span>
                  {notice.text}
                  {notice.code && (
                    <small>
                      {notice.code} · correlation: {notice.correlation}
                    </small>
                  )}
                </span>
              </div>
              <button
                aria-label="Закрыть уведомление"
                onClick={() => setNotice(null)}
              >
                <X size={16} />
              </button>
            </div>
          )}

          {view !== "monitor" ? (
            <>
              <section className="stats" aria-label="Показатели заявлений">
                {[
                  {
                    label: "Всего заявлений",
                    value: total,
                    icon: Files,
                    note: "В текущей выборке",
                    color: "slate",
                  },
                  {
                    label: "В обработке",
                    value: pending,
                    icon: Clock3,
                    note: "Проверка и рассмотрение",
                    color: "amber",
                  },
                  {
                    label: "Завершено",
                    value: done,
                    icon: FileCheck2,
                    note: "Обе подписи проверены",
                    color: "teal",
                  },
                  {
                    label: "Черновики",
                    value: items.filter((a) => a.business_status === "DRAFT")
                      .length,
                    icon: FileText,
                    note: "Готовы к вашему следующему шагу",
                    color: "violet",
                  },
                ].map((s) => (
                  <div className="stat" key={s.label}>
                    <div className="stat-top">
                      <span>{s.label}</span>
                      <span className={`stat-icon ${s.color}`}>
                        <s.icon size={19} />
                      </span>
                    </div>
                    <strong>{s.value.toString().padStart(2, "0")}</strong>
                    <small>{s.note}</small>
                  </div>
                ))}
              </section>

              <div className="content-grid">
                <section className="panel applications-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>
                        {view === "review"
                          ? "Заявления организации"
                          : user?.role === "applicant"
                            ? "Ваши заявления"
                            : "Заявления организации"}
                        <span className="count-pill">{total}</span>
                      </h2>
                      <p>Актуальные статусы и история каждого обращения</p>
                    </div>
                    <button
                      className="icon-button"
                      aria-label="Обновить список"
                      disabled={loading}
                      onClick={() => void refresh()}
                    >
                      <RefreshCw size={16} className={loading ? "spin" : ""} />
                    </button>
                  </div>
                  <div className="table-toolbar">
                    <label className="search">
                      <Search size={17} />
                      <input
                        placeholder="Найти по названию или ID…"
                        aria-label="Поиск заявлений"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                      />
                    </label>
                    <select
                      aria-label="Фильтр статуса"
                      value={filter}
                      onChange={(e) => setFilter(e.target.value)}
                    >
                      <option value="all">Все статусы</option>
                      {Object.entries(labels).map(([s, label]) => (
                        <option value={s} key={s}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>ЗАЯВЛЕНИЕ</th>
                          <th>СТАТУС</th>
                          <th>ОБНОВЛЕНО</th>
                          <th aria-label="Открыть" />
                        </tr>
                      </thead>
                      <tbody>
                        {visible.map((a) => (
                          <tr
                            key={a.id}
                            onClick={() => {
                              setTab("document");
                              void open(a.id);
                            }}
                          >
                            <td>
                              <button className="table-title">
                                <span className="document-icon">
                                  <FileText size={19} />
                                </span>
                                <span>
                                  <strong>{a.title}</strong>
                                  <small>
                                    {a.id.slice(0, 8).toUpperCase()}
                                    <span>·</span>
                                    {a.type === "PERMIT"
                                      ? "Разрешение"
                                      : "Продление"}
                                  </small>
                                </span>
                              </button>
                            </td>
                            <td>
                              <Badge status={a.business_status} />
                            </td>
                            <td className="date-cell">
                              {date(a.updated_at)}
                              <small>
                                v{a.version} · rev {a.document_version}
                              </small>
                            </td>
                            <td>
                              <ChevronRight size={16} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {loading && !items.length ? (
                    <div className="empty">
                      <LoaderCircle className="spin" />
                      <h3>Загружаем заявления…</h3>
                    </div>
                  ) : (
                    !visible.length && (
                      <div className="empty">
                        <span>
                          <FilePlus2 size={29} />
                        </span>
                        <h3>
                          {search || filter !== "all"
                            ? "Ничего не найдено"
                            : "Здесь начинается ваш процесс"}
                        </h3>
                        <p>
                          {search || filter !== "all"
                            ? "Попробуйте изменить поисковый запрос или фильтр."
                            : "Создайте первое заявление и пройдите его путь до решения."}
                        </p>
                        {user?.role === "applicant" &&
                          !search &&
                          filter === "all" && (
                            <button
                              className="text-button"
                              onClick={() => {
                                setSelected(null);
                                setTitle("");
                                setDescription("");
                                setCreateOpen(true);
                              }}
                            >
                              Создать черновик
                              <ArrowRight size={15} />
                            </button>
                          )}
                      </div>
                    )
                  )}
                  <div className="table-footer">
                    <span>
                      Показано {visible.length} из {total} в выборке · до 100
                      записей
                    </span>
                    <span>
                      <ShieldCheck size={14} />
                      Tenant isolation
                    </span>
                  </div>
                </section>
                <aside className="right-column">
                  <section className="guide-card">
                    <div className="guide-top">
                      <span className="mini-label">СКВОЗНОЙ СЦЕНАРИЙ</span>
                      <GitBranch size={18} />
                    </div>
                    <h2>
                      Одно заявление.
                      <br />
                      Весь рабочий процесс.
                    </h2>
                    <p>
                      Пройдите путь в ролях заявителя, специалиста и
                      уполномоченного.
                    </p>
                    <ol>
                      {[
                        "Создайте и подпишите заявление",
                        "Проверьте и согласуйте сведения",
                        "Подпишите итоговое решение",
                      ].map((s, i) => (
                        <li key={s}>
                          <span>{i + 1}</span>
                          {s}
                        </li>
                      ))}
                    </ol>
                    <button onClick={() => setGuideOpen(true)}>
                      Открыть руководство
                      <ArrowUpRight size={16} />
                    </button>
                  </section>
                  <section className="integrity-card">
                    <div className="integrity-icon">
                      <Fingerprint size={25} />
                    </div>
                    <h3>Целостность — в деталях</h3>
                    <p>
                      Каждое изменение создаёт ревизию. Каждая подпись привязана
                      к хешу документа.
                    </p>
                    <div>
                      <Check size={14} />
                      SHA-256 + учебный HMAC
                    </div>
                    <div>
                      <Check size={14} />
                      Контроль версий и аудит
                    </div>
                    <small>Учебная симуляция. Не юридическая ЭЦП.</small>
                  </section>
                </aside>
              </div>
              <section className="principles">
                <div>
                  <ShieldCheck size={21} />
                  <span>
                    <strong>Изоляция организаций</strong>
                    <small>Доступ проверяется на сервере</small>
                  </span>
                </div>
                <div>
                  <GitBranch size={21} />
                  <span>
                    <strong>Прозрачные переходы</strong>
                    <small>Каждый шаг виден в аудите</small>
                  </span>
                </div>
                <div>
                  <FlaskConical size={21} />
                  <span>
                    <strong>Воспроизводимая среда</strong>
                    <small>Baseline · seed 42 по умолчанию</small>
                  </span>
                </div>
              </section>
            </>
          ) : (
            <>
              {!monitor ? (
                <div className="empty">
                  <Activity />
                  <h3>
                    {loading ? "Получаем показатели…" : "Показатели недоступны"}
                  </h3>
                  <button className="secondary" onClick={() => void refresh()}>
                    Повторить
                  </button>
                </div>
              ) : (
                <>
                  <div className="monitor-banner">
                    <span className="monitor-symbol">
                      <Activity size={27} />
                    </span>
                    <div>
                      <h2>
                        Reference baseline{" "}
                        <span className="badge green">
                          <span />
                          Подключён
                        </span>
                      </h2>
                      <p>
                        {monitor.tenant} · build {monitor.build} · seed{" "}
                        {monitor.seed}
                      </p>
                    </div>
                    <span className="mono">{monitor.scenario}</span>
                  </div>
                  <section className="stats">
                    {[
                      {
                        label: "Заявлений в tenant",
                        value: Object.values(monitor.statuses).reduce(
                          (a, b) => a + b,
                          0,
                        ),
                        icon: Files,
                      },
                      {
                        label: "Успешных проверок",
                        value: monitor.checks.VALID || 0,
                        icon: CheckCheck,
                      },
                      {
                        label: "Ожидают проверки",
                        value:
                          (monitor.statuses.SUBMITTED || 0) +
                          (monitor.statuses.VALIDATING || 0),
                        icon: Clock3,
                      },
                      {
                        label: "Завершено",
                        value: monitor.statuses.COMPLETED || 0,
                        icon: FileCheck2,
                      },
                    ].map((s) => (
                      <div className="stat" key={s.label}>
                        <div className="stat-top">
                          <span>{s.label}</span>
                          <span className="stat-icon teal">
                            <s.icon size={18} />
                          </span>
                        </div>
                        <strong>{s.value.toString().padStart(2, "0")}</strong>
                        <small>Обезличенные факты из PostgreSQL</small>
                      </div>
                    ))}
                  </section>
                  <div className="monitor-grid">
                    <section className="panel">
                      <div className="panel-heading">
                        <h2>Состояния процесса</h2>
                        <GitBranch size={18} />
                      </div>
                      <div className="status-breakdown">
                        {Object.keys(monitor.statuses).length ? (
                          Object.entries(monitor.statuses).map(([s, n]) => (
                            <div key={s}>
                              <Badge status={s} />
                              <strong>{n}</strong>
                            </div>
                          ))
                        ) : (
                          <p>
                            Заявлений пока нет. Пройдите сценарий заявителя.
                          </p>
                        )}
                      </div>
                    </section>
                    <section className="panel">
                      <div className="panel-heading">
                        <h2>Контур исполнения</h2>
                        <Code2 size={18} />
                      </div>
                      <dl className="runtime-list">
                        <dt>Внешняя проверка</dt>
                        <dd>{monitor.registry}</dd>
                        <dt>Обработка</dt>
                        <dd>{monitor.queue}</dd>
                        <dt>DLQ</dt>
                        <dd>{monitor.dlq}</dd>
                        <dt>Подписи</dt>
                        <dd>{monitor.signature}</dd>
                      </dl>
                      <div className="stage-note">
                        Stage 1: локальная проверка без HTTP Registry и брокера.
                        Надёжная доставка и retry/DLQ запланированы на Stage 2.
                      </div>
                    </section>
                  </div>
                </>
              )}
            </>
          )}
          <footer>
            <span>
              ADLabs <b>GovFlow</b> QA Simulator
            </span>
            <span>
              Синтетические данные · Учебная среда{" "}
              <span className="footer-dot">•</span> v0.1.0
            </span>
          </footer>
        </div>
      </main>

      {loginOpen && (
        <div className="overlay login-overlay">
          <form
            className="modal login-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Вход в лабораторию"
            onSubmit={signIn}
          >
            <div className="login-mark">
              <Layers3 size={30} />
            </div>
            <div className="eyebrow">ADLABS · GOVFLOW</div>
            <h2>
              {user ? "Сменить учебную роль" : "Добро пожаловать в лабораторию"}
            </h2>
            <p>
              Исследуйте процесс электронных заявлений.
              <br />
              Все организации и документы — учебные.
            </p>
            <label>
              Учётная запись
              <select
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              >
                {["a", "b"].map((t) => (
                  <optgroup key={t} label={`Организация ${t.toUpperCase()}`}>
                    {[
                      "applicant",
                      "applicant2",
                      "reviewer",
                      "officer",
                      "tenant_admin",
                      "qa_observer",
                    ].map((r) => (
                      <option key={`${r}.${t}`} value={`${r}.${t}`}>
                        {r}.{t} · {roleLabels[r] || "Второй заявитель"}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </label>
            <label>
              Пароль локального стенда
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="DEMO_PASSWORD из файла .env"
              />
            </label>
            {notice?.error && (
              <div className="login-error" role="alert">
                {notice.text}
              </div>
            )}
            <button className="primary full" disabled={busy}>
              {busy ? (
                <LoaderCircle className="spin" size={17} />
              ) : (
                <ArrowRight size={17} />
              )}
              Войти в пространство
            </button>
            <small className="login-hint">
              Первый запуск: <code>python scripts/configure.py</code>
              <br />
              Пароль создан локально и сохранён в <code>.env</code>.
            </small>
            {user && (
              <div className="login-actions">
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setLoginOpen(false)}
                >
                  Вернуться
                </button>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => {
                    setToken("");
                    setUser(null);
                    setPassword("");
                    setItems([]);
                    setMonitor(null);
                    setSelected(null);
                  }}
                >
                  Выйти из аккаунта
                </button>
              </div>
            )}
          </form>
        </div>
      )}

      {createOpen && (
        <div
          className="overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget && !busy) setCreateOpen(false);
          }}
        >
          <form
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Создание заявления"
            onSubmit={save}
          >
            <div className="modal-header">
              <div>
                <div className="eyebrow">НОВЫЙ ПРОЦЕСС</div>
                <h2>Создать заявление</h2>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label="Закрыть"
                onClick={() => setCreateOpen(false)}
              >
                <X size={20} />
              </button>
            </div>
            <label>
              Тип услуги
              <select value={type} onChange={(e) => setType(e.target.value)}>
                <option value="PERMIT">Разрешение</option>
                <option value="RENEWAL">Продление разрешения</option>
              </select>
            </label>
            <label>
              Название
              <input
                autoFocus
                required
                minLength={3}
                maxLength={150}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Например, разрешение на учебный объект"
              />
            </label>
            <label>
              Описание
              <textarea
                required
                minLength={10}
                maxLength={4000}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={4}
                placeholder="Опишите запрос. Используйте только синтетические данные."
              />
            </label>
            <div className="form-note">
              <ShieldCheck size={16} />
              После создания добавьте тестовый PDF или PNG.
            </div>
            <button className="primary full" disabled={busy}>
              <FilePlus2 size={17} />
              {busy ? "Сохраняем…" : "Создать черновик"}
            </button>
          </form>
        </div>
      )}

      {selected && !createOpen && !loginOpen && (
        <div
          className="drawer-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget && !busy) setSelected(null);
          }}
        >
          <section
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-label="Карточка заявления"
          >
            <div className="drawer-heading">
              <span className="eyebrow">
                ЗАЯВЛЕНИЕ · {selected.id.slice(0, 8).toUpperCase()}
              </span>
              <button
                className="icon-button"
                aria-label="Закрыть карточку"
                onClick={() => setSelected(null)}
              >
                <X size={20} />
              </button>
            </div>
            <h2>{selected.title}</h2>
            <div className="drawer-meta">
              <Badge status={selected.business_status} />
              <span>
                v{selected.version} · документ rev {selected.document_version}
              </span>
              <button
                className="icon-button"
                aria-label="Обновить карточку"
                onClick={() => void open(selected.id)}
              >
                <RefreshCw size={15} />
              </button>
            </div>
            <div className="detail-tabs">
              {(
                [
                  { id: "document", label: "Документ", icon: FileText },
                  { id: "audit", label: "Аудит", icon: GitBranch },
                  { id: "integration", label: "Проверки", icon: Activity },
                ] as const
              ).map((t) => (
                <button
                  key={t.id}
                  className={tab === t.id ? "active" : ""}
                  onClick={() => setTab(t.id)}
                >
                  <t.icon size={16} />
                  {t.label}
                  {t.id === "audit" && <span>{audit.length}</span>}
                </button>
              ))}
            </div>
            {notice?.error && (
              <div className="notice error drawer-error" role="alert">
                <div>
                  <ShieldCheck size={18} />
                  <span>
                    {notice.text}
                    <small>
                      {notice.code} · {notice.correlation}
                    </small>
                  </span>
                </div>
                <button
                  aria-label="Закрыть ошибку"
                  onClick={() => setNotice(null)}
                >
                  <X size={16} />
                </button>
              </div>
            )}
            {tab === "document" && (
              <>
                {canEdit ? (
                  <form className="edit-form" onSubmit={save}>
                    <label>
                      Название
                      <input
                        required
                        minLength={3}
                        maxLength={150}
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                      />
                    </label>
                    <label>
                      Тип услуги
                      <select
                        value={type}
                        onChange={(e) => setType(e.target.value)}
                      >
                        <option value="PERMIT">Разрешение</option>
                        <option value="RENEWAL">Продление разрешения</option>
                      </select>
                    </label>
                    <label>
                      Описание
                      <textarea
                        required
                        rows={3}
                        minLength={10}
                        maxLength={4000}
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                      />
                    </label>
                    <button className="secondary" disabled={busy}>
                      Сохранить изменения
                    </button>
                  </form>
                ) : (
                  <div className="document-description">
                    <h3>
                      {selected.type === "PERMIT"
                        ? "Разрешение"
                        : "Продление разрешения"}
                    </h3>
                    <p>{selected.description}</p>
                  </div>
                )}
                <section className="detail-section">
                  <div className="section-title">
                    <h3>
                      Вложения <span>{selected.attachments.length}</span>
                    </h3>
                    {canEdit && (
                      <button
                        className="text-button"
                        disabled={busy}
                        onClick={() => fileInput.current?.click()}
                      >
                        <Upload size={15} />
                        Загрузить
                      </button>
                    )}
                  </div>
                  <input
                    type="file"
                    ref={fileInput}
                    accept="application/pdf,image/png"
                    hidden
                    onChange={(e) => void attach(e.target.files?.[0])}
                  />
                  {selected.attachments.length ? (
                    selected.attachments.map((f) => (
                      <button
                        className="attachment"
                        key={f.id}
                        onClick={() => void download(selected, f).catch(fail)}
                      >
                        <span className="document-icon">
                          <FileText size={19} />
                        </span>
                        <span>
                          <strong>{f.filename}</strong>
                          <small>
                            {(f.size / 1024).toFixed(1)} KB · SHA-256{" "}
                            {f.sha256.slice(0, 12)}…
                          </small>
                        </span>
                        <ArrowDownToLine size={17} />
                      </button>
                    ))
                  ) : (
                    <div
                      className="upload-empty"
                      onClick={() => canEdit && fileInput.current?.click()}
                    >
                      <Upload size={22} />
                      <span>Добавьте синтетический документ</span>
                      <small>PDF или PNG, до 5 MiB</small>
                    </div>
                  )}
                </section>
                <section className="detail-section">
                  <h3>Целостность документа</h3>
                  <div className="hash-box">
                    <Fingerprint size={18} />
                    <code>{selected.document_hash}</code>
                  </div>
                  <div className="signature-row">
                    <span>
                      {selected.applicant_signed ? (
                        <CheckCircle2 size={17} />
                      ) : (
                        <Circle size={17} />
                      )}
                      Подпись заявителя
                    </span>
                    <b>
                      {selected.applicant_signed ? "Проверена" : "Не подписано"}
                    </b>
                  </div>
                  <div className="signature-row">
                    <span>
                      {selected.officer_signed ? (
                        <CheckCircle2 size={17} />
                      ) : (
                        <Circle size={17} />
                      )}
                      Подпись уполномоченного
                    </span>
                    <b>
                      {selected.officer_signed ? "Проверена" : "Не подписано"}
                    </b>
                  </div>
                  <small className="muted">
                    Учебный HMAC. Не юридически значимая ЭЦП.
                  </small>
                </section>
                {selected.reviews.length > 0 && (
                  <section className="detail-section">
                    <h3>Решения специалиста</h3>
                    {selected.reviews.map((r, i) => (
                      <div className="review-note" key={i}>
                        <Badge status={r.decision} />
                        <p>{r.reason}</p>
                      </div>
                    ))}
                  </section>
                )}
                {selected.decision_document && (
                  <section className="detail-section">
                    <h3>Документ решения</h3>
                    <pre>
                      {JSON.stringify(selected.decision_document, null, 2)}
                    </pre>
                    <div className="hash-box">
                      <Fingerprint size={18} />
                      <code>{selected.decision_hash}</code>
                    </div>
                  </section>
                )}
                <div className="action-area">
                  {user?.role === "applicant" &&
                    ["DRAFT", "NEEDS_CORRECTION"].includes(
                      selected.business_status,
                    ) && (
                      <button
                        className="primary full"
                        disabled={busy}
                        onClick={() => void act("prepare-signature")}
                      >
                        <Fingerprint size={17} />
                        Подготовить к подписанию
                      </button>
                    )}
                  {user?.role === "applicant" &&
                    selected.business_status ===
                      "AWAITING_APPLICANT_SIGNATURE" &&
                    (!selected.applicant_signed ? (
                      <button
                        className="primary full"
                        disabled={busy}
                        onClick={() =>
                          void act("sign", {
                            document_hash: selected.document_hash,
                          })
                        }
                      >
                        <Fingerprint size={17} />
                        Подписать учебной подписью
                      </button>
                    ) : (
                      <button
                        className="primary full"
                        disabled={busy}
                        onClick={() => void act("submit")}
                      >
                        <ArrowRight size={17} />
                        Отправить заявление
                      </button>
                    ))}
                  {user?.role === "reviewer" &&
                    selected.business_status === "UNDER_REVIEW" && (
                      <>
                        <label>
                          Основание решения
                          <textarea
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            rows={3}
                            minLength={5}
                            placeholder="Результат проверки и обоснование (от 5 символов)"
                          />
                        </label>
                        <button
                          className="primary full"
                          disabled={busy || reason.trim().length < 5}
                          onClick={() =>
                            void act("review", { decision: "APPROVED", reason })
                          }
                        >
                          <Check size={17} />
                          Одобрить заявление
                        </button>
                        <div className="split-buttons">
                          <button
                            className="secondary"
                            disabled={busy || reason.trim().length < 5}
                            onClick={() =>
                              void act("review", {
                                decision: "NEEDS_CORRECTION",
                                reason,
                              })
                            }
                          >
                            На доработку
                          </button>
                          <button
                            className="secondary danger"
                            disabled={busy || reason.trim().length < 5}
                            onClick={() =>
                              void act("review", {
                                decision: "REJECTED",
                                reason,
                              })
                            }
                          >
                            Отклонить
                          </button>
                        </div>
                      </>
                    )}
                  {user?.role === "officer" &&
                    selected.business_status ===
                      "AWAITING_OFFICER_SIGNATURE" && (
                      <button
                        className="primary full"
                        disabled={busy}
                        onClick={() =>
                          void act("sign-decision", {
                            document_hash: selected.decision_hash,
                          })
                        }
                      >
                        <Fingerprint size={17} />
                        Подписать итоговое решение
                      </button>
                    )}
                  {user?.role === "applicant" &&
                    ["DRAFT", "NEEDS_CORRECTION"].includes(
                      selected.business_status,
                    ) && (
                      <button
                        className="text-button danger cancel-action"
                        disabled={busy}
                        onClick={() => void act("cancel")}
                      >
                        Отменить заявление
                      </button>
                    )}
                  {selected.business_status === "COMPLETED" && (
                    <div className="completion">
                      <CheckCircle2 size={24} />
                      <strong>Процесс успешно завершён</strong>
                      <p>Две подписи, решение и аудит сохранены в базе.</p>
                    </div>
                  )}
                  {busy && (
                    <div className="busy-status" role="status">
                      <LoaderCircle size={16} className="spin" />
                      Выполняем команду…
                    </div>
                  )}
                </div>
              </>
            )}
            {tab === "audit" && (
              <div className="timeline">
                {audit.map((e) => (
                  <div className="timeline-event" key={e.id}>
                    <span className="timeline-dot">
                      <Check size={12} />
                    </span>
                    <div>
                      <span className="timeline-version">v{e.version}</span>
                      <h3>
                        {labels[e.action] ||
                          {
                            CREATED: "Заявление создано",
                            ATTACHMENT_ADDED: "Документ приложен",
                            DOCUMENT_UPDATED: "Документ изменён",
                            APPLICANT_SIGNED: "Заявитель подписал",
                          }[e.action] ||
                          e.action}
                      </h3>
                      <small>
                        {new Date(e.timestamp).toLocaleString("ru-RU")}
                      </small>
                      <code>{e.correlation_id}</code>
                    </div>
                  </div>
                ))}
              </div>
            )}
            {tab === "integration" && (
              <div className="detail-section">
                <h3>Проверка сведений</h3>
                <p className="muted">
                  Техническое состояние: {selected.processing_status}
                </p>
                {integrations.length ? (
                  integrations.map((c) => (
                    <div className="integration-result" key={c.id}>
                      <CheckCircle2 size={23} />
                      <div>
                        <strong>{c.outcome}</strong>
                        <p>
                          {c.provider} · попытка {c.attempt}
                        </p>
                        <code>{c.correlation_id}</code>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="empty">
                    <Clock3 />
                    <p>Проверка начнётся после отправки заявления.</p>
                  </div>
                )}
                <div className="stage-note">
                  Локальный детерминированный адаптер Stage 1. Внешних
                  HTTP-запросов нет.
                </div>
              </div>
            )}
            <div className="drawer-id">
              Application UUID <code>{selected.id}</code>
            </div>
          </section>
        </div>
      )}

      {guideOpen && (
        <div className="overlay">
          <section
            className="modal guide-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Руководство"
          >
            <div className="modal-header">
              <div>
                <div className="eyebrow">REFERENCE FLOW</div>
                <h2>От черновика до решения</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Закрыть руководство"
                onClick={() => setGuideOpen(false)}
              >
                <X size={20} />
              </button>
            </div>
            <p>
              Войдите с паролем из <code>.env</code>. Менять роль можно через
              профиль внизу боковой панели.
            </p>
            <ol className="guide-steps">
              <li>
                <strong>applicant.a · Заявитель</strong>
                <p>
                  Создайте заявление, загрузите тестовый PDF/PNG, подготовьте
                  документ, подпишите и отправьте.
                </p>
              </li>
              <li>
                <strong>reviewer.a · Специалист</strong>
                <p>
                  В очереди откройте заявление «На рассмотрении». Проверьте
                  вкладки «Проверки» и «Аудит», укажите основание и одобрите.
                </p>
              </li>
              <li>
                <strong>officer.a · Уполномоченный</strong>
                <p>
                  Откройте ожидающее подписи решение и подпишите. Заявление
                  станет завершённым.
                </p>
              </li>
              <li>
                <strong>qa_observer.a · Наблюдатель</strong>
                <p>
                  Изучите реальные агрегированные показатели в QA Monitor.
                  Tenant B не имеет доступа к заявлению tenant A.
                </p>
              </li>
            </ol>
            <div className="stage-note">
              Реализованы Stage 0 + Stage 1. Registry/worker, fault profiles,
              mutants, LMS и WorkLab — следующие этапы. Подписи — учебная
              HMAC-симуляция.
            </div>
            <a
              className="primary full"
              href="/docs"
              target="_blank"
              rel="noreferrer"
            >
              <Code2 size={17} />
              Исследовать API в Swagger
              <ExternalLink size={15} />
            </a>
          </section>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Portal />
  </StrictMode>,
);
