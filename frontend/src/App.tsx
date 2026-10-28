import {
  FormEvent,
  ReactNode,
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";
import { UseMutationResult, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import {
  ApiError,
  Catalog,
  Delivery,
  NamedItem,
  Page,
  Payment,
  PaymentDetail,
  RollTypeItem,
  TelegramStatus,
  User,
  UserRole,
  UnpaidPreview,
  api,
  displayDate,
  jsonBody,
  queryString,
  rememberCsrfToken,
  todayCambodia,
  userMessage,
} from "./api";
import { rollTypeLabel, rollTypeText, translate } from "./locales";

type Toast = { text: string; kind: "success" | "error" };
const ToastContext = createContext<(text: string, kind?: Toast["kind"]) => void>(() => {});

function useToast() {
  return useContext(ToastContext);
}

function Loading({ label = "កំពុងដំណើរការ..." }: { label?: string }) {
  return <div className="py-12 text-center text-sm text-slate-500" role="status">{label}</div>;
}

function Empty({ label = "មិនមានទិន្នន័យទេ។" }: { label?: string }) {
  return <div className="px-5 py-12 text-center text-sm text-slate-500">{label}</div>;
}

function PageTitle({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const dialog = useState<HTMLDialogElement | null>(null);
  const [element, setElement] = dialog;
  useEffect(() => {
    if (element && !element.open) element.showModal();
    return () => {
      if (element?.open) element.close();
    };
  }, [element]);
  return (
    <dialog
      ref={setElement}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      className="w-full"
    >
      <div className="max-h-[calc(100vh-2rem)] overflow-y-auto p-6">
        <div className="mb-5 flex items-start justify-between gap-4">
          <h2 className="text-lg font-bold text-ink">{title}</h2>
          <button className="rounded-lg px-2 py-1 text-slate-400 hover:bg-slate-100" onClick={onClose} aria-label="បិទ">
            ✕
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}

function Badge({ value }: { value: Delivery["status"] }) {
  const labels = {
    paid: ["បានបង់", "bg-emerald-50 text-emerald-700"],
    partial: ["បង់ខ្លះ", "bg-amber-50 text-amber-700"],
    unpaid: ["មិនទាន់បង់", "bg-rose-50 text-rose-700"],
  } as const;
  const [label, style] = labels[value];
  return <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${style}`}>{label}</span>;
}

function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="mt-2 text-sm text-rose-700" role="alert">{userMessage(error)}</p>;
}

function Field({
  label,
  children,
  className = "",
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return <label className={`block ${className}`}><span className="label">{label}</span>{children}</label>;
}

function App() {
  const [toast, setToast] = useState<Toast | null>(null);
  const me = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      try {
        const user = await api<User>("/auth/me");
        rememberCsrfToken(user.csrf_token);
        return user;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    retry: false,
  });

  const showToast = (text: string, kind: Toast["kind"] = "success") => {
    setToast({ text, kind });
    window.setTimeout(() => setToast(null), 4000);
  };

  if (me.isLoading) return <Loading label="កំពុងផ្ទៀងផ្ទាត់គណនី..." />;
  if (me.isError) {
    return (
      <main className="grid min-h-screen place-items-center p-5">
        <section className="card max-w-md text-center">
          <p className="font-semibold">មិនអាចភ្ជាប់ទៅប្រព័ន្ធបានទេ។</p>
          <p className="mt-2 text-sm text-slate-500">{userMessage(me.error)}</p>
          <button className="btn-primary mt-5" onClick={() => void me.refetch()}>ព្យាយាមម្ដងទៀត</button>
        </section>
      </main>
    );
  }

  return (
    <ToastContext.Provider value={showToast}>
      {toast && (
        <div
          className={`fixed right-4 top-4 z-50 max-w-sm rounded-xl px-4 py-3 text-sm text-white shadow-lg ${toast.kind === "error" ? "bg-rose-700" : "bg-emerald-700"}`}
          role="status"
        >
          {toast.text}
        </div>
      )}
      <Routes>
        <Route path="/login" element={me.data ? <Navigate to="/" replace /> : <LoginPage />} />
        {me.data ? (
          <Route element={<AppLayout user={me.data} />}>
            <Route index element={<DashboardPage />} />
            <Route path="deliveries" element={<DeliveriesPage user={me.data} />} />
            <Route path="unpaid" element={<UnpaidPage user={me.data} />} />
            <Route path="payments" element={<PaymentsPage user={me.data} />} />
            <Route path="account" element={<AccountPage user={me.data} />} />
            <Route path="users" element={me.data.permissions.can_manage_users ? <UsersPage /> : <ForbiddenPage />} />
            <Route path="catalog" element={me.data.permissions.can_manage_catalog ? <CatalogPage /> : <ForbiddenPage />} />
            <Route path="settings" element={me.data.permissions.can_manage_settings ? <SettingsPage /> : <ForbiddenPage />} />
            <Route path="audit" element={me.data.permissions.can_view_audit ? <AuditPage /> : <ForbiddenPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        ) : (
          <Route path="*" element={<Navigate to="/login" replace />} />
        )}
      </Routes>
    </ToastContext.Provider>
  );
}

function LoginPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const mutation = useMutation({
    mutationFn: () => api<User>("/auth/login", { method: "POST", body: jsonBody({ username, password }) }),
    onSuccess: (user) => {
      rememberCsrfToken(user.csrf_token);
      client.setQueryData(["me"], user);
      navigate("/", { replace: true });
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-teal-50 via-canvas to-slate-100 p-4">
      <section className="w-full max-w-md rounded-3xl border border-white bg-white p-8 shadow-panel sm:p-10">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-teal-700 text-2xl text-white">ឃ</div>
          <p className="text-sm font-semibold text-teal-700">ប្រព័ន្ធឃ្លាំង</p>
          <h1 className="mt-1 text-2xl font-bold text-ink">គ្រប់គ្រងកាវអ៊ុតក្រណាត់</h1>
          <p className="mt-2 text-sm text-slate-500">សូមចូលគណនីដើម្បីបន្ត</p>
        </div>
        <form className="space-y-5" onSubmit={submit}>
          <Field label="ឈ្មោះអ្នកប្រើប្រាស់">
            <input className="field" autoComplete="username" required maxLength={64} value={username} onChange={(event) => setUsername(event.target.value)} />
          </Field>
          <Field label="ពាក្យសម្ងាត់">
            <div className="relative">
              <input className="field pr-20" type={showPassword ? "text" : "password"} autoComplete="current-password" required maxLength={256} value={password} onChange={(event) => setPassword(event.target.value)} />
              <button type="button" className="absolute inset-y-0 right-3 text-xs font-semibold text-teal-700" onClick={() => setShowPassword((current) => !current)}>
                {showPassword ? "លាក់" : "បង្ហាញ"}
              </button>
            </div>
          </Field>
          <ErrorText error={mutation.error} />
          <button className="btn-primary w-full py-3" type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "កំពុងចូល..." : "ចូលប្រព័ន្ធ"}
          </button>
        </form>
      </section>
    </main>
  );
}

const navigation = [
  { to: "/", label: "ផ្ទាំងសង្ខេប", icon: "▦" },
  { to: "/deliveries", label: "កត់ត្រាការទទួល", icon: "＋" },
  { to: "/unpaid", label: "ចំនួនមិនទាន់បង់", icon: "◷" },
  { to: "/payments", label: "ប្រវត្តិការបង់", icon: "✓" },
];

function AppLayout({ user }: { user: User }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const logout = useMutation({
    mutationFn: () => api("/auth/logout", { method: "POST" }),
    onSuccess: () => {
      rememberCsrfToken(null);
      client.setQueryData(["me"], null);
      navigate("/login", { replace: true });
    },
    onError: (error) => toast(userMessage(error), "error"),
  });
  const links = [
    ...navigation,
    ...(user.permissions.can_manage_users ? [{ to: "/users", label: "គ្រប់គ្រងអ្នកប្រើ", icon: "♙" }] : []),
    ...(user.permissions.can_manage_catalog ? [{ to: "/catalog", label: "អ្នកផ្គត់ផ្គង់ និងប្រភេទ", icon: "◇" }] : []),
    ...(user.permissions.can_manage_settings ? [{ to: "/settings", label: "ការកំណត់សិទ្ធិ", icon: "⚙" }] : []),
    ...(user.permissions.can_view_audit ? [{ to: "/audit", label: "កំណត់ហេតុសកម្មភាព", icon: "≡" }] : []),
    { to: "/account", label: "គណនី និង Telegram", icon: "◎" },
  ];

  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-slate-200 bg-white md:fixed md:inset-y-0 md:flex md:w-64 md:flex-col md:border-b-0 md:border-r">
        <div className="flex items-center gap-3 px-5 py-5">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-teal-700 font-bold text-white">ឃ</div>
          <div><p className="font-bold leading-5">ឃ្លាំងកាវ</p><p className="text-xs text-slate-500">Inventory system</p></div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-1 md:flex-col md:overflow-y-auto md:pb-5" aria-label="ម៉ឺនុយចម្បង">
          {links.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.to === "/"} className={({ isActive }) => `flex shrink-0 items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition ${isActive ? "bg-teal-50 text-teal-800" : "text-slate-600 hover:bg-slate-50"}`}>
              <span className="w-5 text-center text-base">{item.icon}</span>{item.label}
            </NavLink>
          ))}
        </nav>
        <div className="hidden border-t border-slate-100 p-4 md:block">
          <p className="truncate text-sm font-semibold">{user.username}</p>
          <p className="mt-0.5 text-xs text-slate-500">{user.role === "admin" ? "អ្នកគ្រប់គ្រង" : "បុគ្គលិកឃ្លាំង"}</p>
          <button className="btn-secondary mt-3 w-full" onClick={() => logout.mutate()} disabled={logout.isPending}>ចាកចេញ</button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8 md:ml-64">
        <div className="mb-6 flex items-center justify-between md:hidden">
          <span className="truncate text-sm font-semibold">{user.username}</span>
          <button className="btn-secondary px-3 py-2" onClick={() => logout.mutate()} disabled={logout.isPending}>ចាកចេញ</button>
        </div>
        <Outlet />
      </main>
    </div>
  );
}

interface DashboardData {
  summary: {
    total_received: number;
    total_paid: number;
    total_unpaid: number;
    received_today: number;
    currently_unpaid: number;
    delivery_count: number;
  };
  by_supplier: { supplier_name: string; received: number; unpaid: number }[];
  by_roll_type: { roll_type_id: number; roll_type_code: string; roll_type_name: string; roll_type_name_en: string; received: number; paid: number; unpaid: number }[];
  by_supplier_and_roll_type: { supplier_id: number; supplier_name: string; roll_type_id: number; roll_type_code: string; roll_type_name: string; roll_type_name_en: string; received: number; paid: number; unpaid: number }[];
  recent_deliveries: Delivery[];
  recent_payments: Payment[];
}

function DashboardPage() {
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard", start, end],
    queryFn: () => api<DashboardData>(`/dashboard${queryString({ start_date: start, end_date: end })}`),
  });
  if (isLoading) return <Loading />;
  if (error || !data) return <ErrorText error={error} />;
  const cards = [
    ["ទទួលសរុប", data.summary.total_received, "ប្រវត្តិទទួលទំនិញទាំងអស់"],
    ["បានបង់", data.summary.total_paid, "បរិមាណដែលបានបង់ឱ្យអ្នកផ្គត់ផ្គង់"],
    ["មិនទាន់បង់", data.summary.currently_unpaid, "បរិមាណដែលនៅសល់ត្រូវបង់"],
    ["ទទួលថ្ងៃនេះ", data.summary.received_today, "តាមម៉ោងកម្ពុជា"],
  ];
  return (
    <>
      <PageTitle title="ផ្ទាំងសង្ខេប" subtitle="ស្ថានភាពទទួលទំនិញ និងការបង់ប្រាក់" />
      <section className="card mb-5 grid gap-3 sm:grid-cols-2">
        <Field label="ចាប់ពីថ្ងៃទទួល"><input className="field" type="date" value={start} onChange={(event) => setStart(event.target.value)} /></Field>
        <Field label="ដល់ថ្ងៃទទួល"><input className="field" type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></Field>
        <p className="text-xs text-slate-500 sm:col-span-2">ចំនួនមិនទាន់បង់នៅតែបង្ហាញជាចំនួនបច្ចុប្បន្នទាំងអស់ ទោះបីបានជ្រើសកាលបរិច្ឆេទក៏ដោយ។</p>
      </section>
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(([title, value, caption]) => (
          <section className="card" key={String(title)}>
            <p className="text-sm font-medium text-slate-500">{title}</p>
            <p className="mt-3 text-3xl font-bold tracking-tight">{Number(value).toLocaleString()} <span className="text-sm font-medium text-slate-500">កី</span></p>
            <p className="mt-2 text-xs text-slate-400">{caption}</p>
          </section>
        ))}
      </div>
      <div className="mt-6 grid gap-5 xl:grid-cols-2">
        <section className="card">
          <h2 className="mb-4 font-bold">បរិមាណតាមអ្នកផ្គត់ផ្គង់</h2>
          {data.by_supplier.length === 0 ? <Empty /> : <div className="space-y-4">{data.by_supplier.map((row) => <div key={row.supplier_name} className="flex items-center justify-between gap-3 border-b border-slate-100 pb-3 last:border-0"><span className="font-medium">{row.supplier_name}</span><span className="text-right text-sm text-slate-600">ទទួល {row.received.toLocaleString()} · នៅសល់ {row.unpaid.toLocaleString()}</span></div>)}</div>}
        </section>
        <section className="card">
          <h2 className="mb-4 font-bold">បរិមាណតាមប្រភេទកាវ</h2>
          {data.by_roll_type.length === 0 ? <Empty /> : <div className="space-y-4">{data.by_roll_type.map((row) => <div key={row.roll_type_code} className="flex items-center justify-between gap-3 border-b border-slate-100 pb-3 last:border-0"><span className="font-medium">{rollTypeText({ roll_type_code: row.roll_type_code, roll_type_name: row.roll_type_name, roll_type_name_en: row.roll_type_name_en })}</span><span className="text-right text-sm text-slate-600">ទទួល {row.received.toLocaleString()} · បានបង់ {row.paid.toLocaleString()} · មិនទាន់បង់ {row.unpaid.toLocaleString()}</span></div>)}</div>}
        </section>
      </div>
      <section className="card mt-6">
        <h2 className="mb-4 font-bold">បរិមាណតាមអ្នកផ្គត់ផ្គង់ និងប្រភេទកាវ</h2>
        {data.by_supplier_and_roll_type.length === 0 ? <Empty /> : <div className="space-y-3">{data.by_supplier_and_roll_type.map((row) => <div key={`${row.supplier_id}-${row.roll_type_code}`} className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3 last:border-0"><span className="font-medium">{row.supplier_name} · {rollTypeText({ roll_type_code: row.roll_type_code, roll_type_name: row.roll_type_name, roll_type_name_en: row.roll_type_name_en })}</span><span className="text-sm text-slate-600">ទទួល {row.received.toLocaleString()} · បានបង់ {row.paid.toLocaleString()} · មិនទាន់បង់ {row.unpaid.toLocaleString()}</span></div>)}</div>}
      </section>
      <section className="mt-6">
        <div className="mb-3 flex items-center justify-between"><h2 className="font-bold">ការទទួលថ្មីៗ</h2><Link className="text-sm font-semibold text-teal-700" to="/deliveries">មើលទាំងអស់ →</Link></div>
        <div className="table-wrap"><table><thead><tr><th>ថ្ងៃទទួល</th><th>អ្នកផ្គត់ផ្គង់</th><th>ប្រភេទកាវ</th><th>ទទួល</th><th>ស្ថានភាព</th></tr></thead><tbody>
          {data.recent_deliveries.length === 0 ? <tr><td colSpan={5}><Empty /></td></tr> : data.recent_deliveries.map((row) => <tr key={row.id}><td>{displayDate(row.delivery_date)}</td><td>{row.supplier_name}</td><td>{rollTypeText(row)}</td><td>{row.quantity_received.toLocaleString()}</td><td><Badge value={row.status} /></td></tr>)}
        </tbody></table></div>
      </section>
      <section className="mt-6">
        <div className="mb-3 flex items-center justify-between"><h2 className="font-bold">ប្រវត្តិបង់ថ្មីៗ</h2><Link className="text-sm font-semibold text-teal-700" to="/payments">មើលទាំងអស់ →</Link></div>
        <div className="table-wrap"><table><thead><tr><th>លេខយោង</th><th>អ្នកផ្គត់ផ្គង់</th><th>ថ្ងៃបង់</th><th>បរិមាណ</th><th>បញ្ជាក់ដោយ</th></tr></thead><tbody>
          {data.recent_payments.length === 0 ? <tr><td colSpan={5}><Empty label="មិនទាន់មានប្រវត្តិការបង់ទេ។" /></td></tr> : data.recent_payments.map((item) => <tr key={item.id}><td className="font-semibold">{item.reference}</td><td>{item.supplier_name}</td><td>{displayDate(item.payment_date)}</td><td>{item.total_quantity.toLocaleString()}</td><td>{item.created_by_username ?? "—"}</td></tr>)}
        </tbody></table></div>
      </section>
    </>
  );
}

function DeliveriesPage({ user }: { user: User }) {
  const client = useQueryClient();
  const toast = useToast();
  const [supplier, setSupplier] = useState("");
  const [rollType, setRollType] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Delivery | null>(null);
  const [adding, setAdding] = useState(false);
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: () => api<Catalog>("/catalog") });
  const filters = { supplier_id: supplier, roll_type_id: rollType, start_date: start, end_date: end, page, page_size: 25 };
  const deliveries = useQuery({
    queryKey: ["deliveries", filters],
    queryFn: () => api<Page<Delivery>>(`/deliveries${queryString(filters)}`),
  });
  const summary = useQuery({
    queryKey: ["delivery-summary", supplier, rollType, start, end],
    queryFn: () => api<{ totals: { received: number; paid: number; unpaid: number }; delivery_count: number }>(`/deliveries/summary${queryString({ supplier_id: supplier, roll_type_id: rollType, start_date: start, end_date: end })}`),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api(`/deliveries/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["deliveries"] });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      toast("បានលុបកំណត់ត្រាដោយជោគជ័យ។");
    },
    onError: (error) => toast(userMessage(error), "error"),
  });
  const canEdit = user.permissions.can_edit_deliveries;

  return (
    <>
      <PageTitle title="ការទទួលទំនិញប្រចាំថ្ងៃ" subtitle="កំណត់ត្រាទាំងនេះនៅតែរក្សាទុកក្រោយពេលបង់" action={<button className="btn-primary" onClick={() => setAdding(true)}>＋ កត់ត្រាការទទួល</button>} />
      <section className="card mb-5">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Field label="អ្នកផ្គត់ផ្គង់"><select className="field" value={supplier} onChange={(event) => { setSupplier(event.target.value); setPage(1); }}><option value="">ទាំងអស់</option>{catalog.data?.suppliers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
          <Field label={translate("rollType")}><select className="field" value={rollType} onChange={(event) => { setRollType(event.target.value); setPage(1); }}><option value="">ទាំងអស់</option>{catalog.data?.roll_types.map((item) => <option key={item.id} value={item.id}>{rollTypeLabel(item)}</option>)}</select></Field>
          <Field label="ចាប់ពីថ្ងៃ"><input className="field" type="date" value={start} onChange={(event) => { setStart(event.target.value); setPage(1); }} /></Field>
          <Field label="ដល់ថ្ងៃ"><input className="field" type="date" value={end} onChange={(event) => { setEnd(event.target.value); setPage(1); }} /></Field>
        </div>
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-600">
          <span>ចំនួនកំណត់ត្រា៖ <b>{summary.data?.delivery_count ?? "—"}</b></span>
          <span>ទទួលសរុប៖ <b>{summary.data?.totals.received.toLocaleString() ?? "—"}</b> កី</span>
          <span>បានបង់៖ <b>{summary.data?.totals.paid.toLocaleString() ?? "—"}</b></span>
          <span>នៅសល់៖ <b>{summary.data?.totals.unpaid.toLocaleString() ?? "—"}</b></span>
        </div>
      </section>
      {deliveries.isLoading ? <Loading /> : deliveries.error ? <ErrorText error={deliveries.error} /> : (
        <div className="table-wrap"><table><thead><tr><th>ថ្ងៃទទួល</th><th>អ្នកផ្គត់ផ្គង់</th><th>ប្រភេទកាវ</th><th>ទទួល</th><th>បានបង់</th><th>នៅសល់</th><th>ស្ថានភាព</th><th>កត់ត្រាដោយ</th><th>សកម្មភាព</th></tr></thead>
          <tbody>{deliveries.data?.items.length ? deliveries.data.items.map((row) => <tr key={row.id}>
            <td>{displayDate(row.delivery_date)}</td><td>{row.supplier_name}</td><td>{rollTypeText(row)}</td><td>{row.quantity_received.toLocaleString()}</td><td>{row.quantity_paid.toLocaleString()}</td><td>{row.quantity_unpaid.toLocaleString()}</td><td><Badge value={row.status} /></td><td>{row.created_by_username ?? "—"}</td>
            <td><div className="flex gap-2">{canEdit && <button className="text-sm font-semibold text-teal-700" onClick={() => setEditing(row)}>កែ</button>}{user.permissions.can_delete_deliveries && <button className="text-sm font-semibold text-rose-700" onClick={() => { if (window.confirm("តើអ្នកប្រាកដថាចង់លុបកំណត់ត្រានេះទេ?")) remove.mutate(row.id); }}>លុប</button>}</div></td>
          </tr>) : <tr><td colSpan={9}><Empty label="មិនមានការទទួលក្នុងលក្ខខណ្ឌនេះទេ។" /></td></tr>}</tbody>
        </table></div>
      )}
      <Pagination page={page} pages={deliveries.data?.pages ?? 0} onChange={setPage} />
      {adding && <DeliveryDialog catalog={catalog.data} onClose={() => setAdding(false)} />}
      {editing && <DeliveryDialog catalog={catalog.data} delivery={editing} onClose={() => setEditing(null)} />}
    </>
  );
}

function DeliveryDialog({ catalog, delivery, onClose }: { catalog?: Catalog; delivery?: Delivery; onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const [supplier, setSupplier] = useState(String(delivery?.supplier_id ?? ""));
  const [rollType, setRollType] = useState(String(delivery?.roll_type_id ?? ""));
  const [quantity, setQuantity] = useState(String(delivery?.quantity_received ?? ""));
  const [date, setDate] = useState(delivery?.delivery_date ?? todayCambodia());
  const [note, setNote] = useState(delivery?.note ?? "");
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const mutation = useMutation({
    mutationFn: () => delivery
      ? api<Delivery>(`/deliveries/${delivery.id}`, { method: "PATCH", body: jsonBody({ supplier_id: Number(supplier), roll_type_id: Number(rollType), quantity_received: Number(quantity), delivery_date: date, note }) })
      : api<Delivery>("/deliveries", { method: "POST", body: jsonBody({ supplier_id: Number(supplier), roll_type_id: Number(rollType), quantity_received: Number(quantity), delivery_date: date, note, idempotency_key: idempotencyKey }) }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["deliveries"] });
      void client.invalidateQueries({ queryKey: ["delivery-summary"] });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      toast(delivery ? "បានកែប្រែកំណត់ត្រា។" : "បានកត់ត្រាការទទួល។");
      onClose();
    },
  });
  return (
    <Dialog title={delivery ? "កែតម្រូវការទទួល" : "កត់ត្រាការទទួលថ្មី"} onClose={onClose}>
      <form className="space-y-4" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
        <Field label="អ្នកផ្គត់ផ្គង់"><select className="field" required value={supplier} onChange={(event) => setSupplier(event.target.value)}><option value="">ជ្រើសរើស</option>{catalog?.suppliers.filter((item) => item.is_active || item.id === delivery?.supplier_id).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
        <Field label={translate("rollType")}><select className="field" required value={rollType} onChange={(event) => setRollType(event.target.value)}><option value="">ជ្រើសរើស</option>{catalog?.roll_types.filter((item) => item.is_active || item.id === delivery?.roll_type_id).map((item) => <option key={item.id} value={item.id}>{rollTypeLabel(item)}</option>)}</select></Field>
        <Field label="ចំនួនកី"><input className="field" type="number" min="1" max="1000000" step="1" required value={quantity} onChange={(event) => setQuantity(event.target.value)} /></Field>
        <Field label="ថ្ងៃទទួល"><input className="field" type="date" required value={date} onChange={(event) => setDate(event.target.value)} /></Field>
        <Field label="កំណត់ចំណាំ (ស្រេចចិត្ត)"><textarea className="field min-h-20" maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)} /></Field>
        <ErrorText error={mutation.error} />
        <div className="flex justify-end gap-2 pt-2"><button type="button" className="btn-secondary" onClick={onClose}>បោះបង់</button><button className="btn-primary" disabled={mutation.isPending}>{mutation.isPending ? "កំពុងរក្សាទុក..." : "រក្សាទុក"}</button></div>
      </form>
    </Dialog>
  );
}

function UnpaidPage({ user }: { user: User }) {
  const client = useQueryClient();
  const toast = useToast();
  const [supplier, setSupplier] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [rollType, setRollType] = useState("");
  const [quantities, setQuantities] = useState<Record<number, number>>({});
  const [paymentDate, setPaymentDate] = useState(todayCambodia());
  const [paymentKey, setPaymentKey] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: () => api<Catalog>("/catalog") });
  useEffect(() => {
    if (!supplier && catalog.data?.suppliers[0]) setSupplier(String(catalog.data.suppliers[0].id));
  }, [catalog.data, supplier]);
  const filters = { supplier_id: supplier, start_date: start, end_date: end, roll_type_id: rollType };
  const preview = useQuery({
    queryKey: ["unpaid", filters],
    queryFn: () => api<UnpaidPreview>(`/payments/unpaid${queryString(filters)}`),
    enabled: Boolean(supplier),
  });
  useEffect(() => {
    if (preview.data) {
      setQuantities(Object.fromEntries(preview.data.deliveries.map((delivery) => [delivery.id, delivery.quantity_unpaid])));
    }
  }, [preview.data]);
  const selected = preview.data?.deliveries.filter((delivery) => (quantities[delivery.id] ?? 0) > 0) ?? [];
  const totalSelected = selected.reduce((sum, delivery) => sum + Math.min(quantities[delivery.id] ?? 0, delivery.quantity_unpaid), 0);
  const payment = useMutation({
    mutationFn: () => api<PaymentDetail>("/payments/confirm", {
      method: "POST",
      body: jsonBody({
        supplier_id: Number(supplier),
        roll_type_id: Number(rollType),
        start_date: start || null,
        end_date: end || null,
        payment_date: paymentDate,
        allocations: selected.map((delivery) => ({ delivery_id: delivery.id, quantity: Math.min(quantities[delivery.id], delivery.quantity_unpaid) })),
        idempotency_key: paymentKey,
      }),
    }),
    onSuccess: (result) => {
      setConfirm(false);
      setPaymentKey(null);
      setQuantities({});
      void client.invalidateQueries({ queryKey: ["unpaid"] });
      void client.invalidateQueries({ queryKey: ["payments"] });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      void client.invalidateQueries({ queryKey: ["deliveries"] });
      toast(`បានកត់ត្រាការបង់ ${result.total_quantity.toLocaleString()} កី (${result.reference})។`);
    },
    onError: (error) => toast(userMessage(error), "error"),
  });
  const canPay = Boolean(rollType) && Boolean(totalSelected) && selected.length > 0
    && selected.every((delivery) => String(delivery.roll_type_id) === rollType);

  return (
    <>
      <PageTitle title="ចំនួនមិនទាន់បង់" subtitle="ជ្រើសរើសកំណត់ត្រាដែលត្រូវបង់។ ការបង់ខ្លះអាចទុកចំនួននៅសល់បាន។" />
      <section className="card mb-5">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Field label="អ្នកផ្គត់ផ្គង់"><select className="field" required value={supplier} onChange={(event) => setSupplier(event.target.value)}><option value="">ជ្រើសរើស</option>{catalog.data?.suppliers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
          <Field label="ចាប់ពីថ្ងៃទទួល"><input className="field" type="date" value={start} onChange={(event) => setStart(event.target.value)} /></Field>
          <Field label="ដល់ថ្ងៃទទួល"><input className="field" type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></Field>
          <Field label={translate("rollType")}><select className="field" value={rollType} onChange={(event) => { setRollType(event.target.value); setQuantities({}); }}><option value="">ជ្រើសប្រភេទកាវដើម្បីបង់</option>{catalog.data?.roll_types.map((item) => <option key={item.id} value={item.id}>{rollTypeLabel(item)}</option>)}</select></Field>
        </div>
      </section>
      {preview.isLoading ? <Loading /> : preview.error ? <ErrorText error={preview.error} /> : preview.data && (
        <>
          <div className="mb-4 grid gap-3 sm:grid-cols-3">
            <SummaryTile label="អ្នកផ្គត់ផ្គង់" value={preview.data.supplier.name} />
            <SummaryTile label="ចំនួនមិនទាន់បង់ក្នុងជម្រើស" value={`${preview.data.totals.unpaid.toLocaleString()} កី`} />
            <SummaryTile label="ចំនួនដែលបានជ្រើសសម្រាប់បង់" value={`${totalSelected.toLocaleString()} កី`} />
          </div>
          <div className="table-wrap mb-4"><table><thead><tr><th>{translate("rollType")}</th><th>{translate("received")}</th><th>{translate("paid")}</th><th>{translate("unpaid")}</th></tr></thead><tbody>{preview.data.by_roll_type.map((item) => <tr key={item.roll_type_code}><td>{rollTypeText({ roll_type_code: item.roll_type_code, roll_type_name: item.roll_type_name, roll_type_name_en: item.roll_type_name_en })}</td><td>{item.received.toLocaleString()}</td><td>{item.paid.toLocaleString()}</td><td>{item.unpaid.toLocaleString()}</td></tr>)}</tbody></table></div>
          <div className="table-wrap"><table><thead><tr><th>ជ្រើស</th><th>ថ្ងៃទទួល</th><th>ប្រភេទកាវ</th><th>ទទួល</th><th>បានបង់</th><th>នៅសល់</th><th>បង់ចំនួន</th></tr></thead><tbody>
            {preview.data.deliveries.length ? preview.data.deliveries.map((row) => <tr key={row.id}>
              <td><input aria-label={`ជ្រើសរើសកំណត់ត្រា ${row.id}`} type="checkbox" checked={(quantities[row.id] ?? 0) > 0} onChange={(event) => setQuantities((old) => ({ ...old, [row.id]: event.target.checked ? row.quantity_unpaid : 0 }))} /></td>
              <td>{displayDate(row.delivery_date)}</td><td>{rollTypeText(row)}</td><td>{row.quantity_received.toLocaleString()}</td><td>{row.quantity_paid.toLocaleString()}</td><td>{row.quantity_unpaid.toLocaleString()}</td>
              <td><input className="field w-28" aria-label={`ចំនួនកីដែលត្រូវបង់ ${row.id}`} type="number" min="0" max={row.quantity_unpaid} step="1" value={quantities[row.id] ?? 0} onChange={(event) => setQuantities((old) => ({ ...old, [row.id]: Math.min(Number(event.target.value) || 0, row.quantity_unpaid) }))} /></td>
            </tr>) : <tr><td colSpan={7}><Empty label="មិនមានចំនួនមិនទាន់បង់ក្នុងលក្ខខណ្ឌនេះទេ។" /></td></tr>}
          </tbody></table></div>
          <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
            <Field label="ថ្ងៃបង់"><input className="field" type="date" required value={paymentDate} onChange={(event) => setPaymentDate(event.target.value)} /></Field>
            {user.permissions.can_confirm_payments && <button className="btn-primary" disabled={!canPay} onClick={() => { setPaymentKey(crypto.randomUUID()); setConfirm(true); }}>ពិនិត្យ និងបញ្ជាក់ការបង់ ({totalSelected.toLocaleString()})</button>}
          </div>
        </>
      )}
      {confirm && preview.data && (
        <Dialog title="ពិនិត្យការបង់មុនរក្សាទុក" onClose={() => setConfirm(false)}>
          <p className="mb-3 text-sm text-slate-600">អ្នកផ្គត់ផ្គង់៖ <b>{preview.data.supplier.name}</b><br />ថ្ងៃទទួល៖ {start ? displayDate(start) : "ទាំងអស់"} ដល់ {end ? displayDate(end) : "ទាំងអស់"}<br />ថ្ងៃបង់៖ {displayDate(paymentDate)}</p>
          <div className="table-wrap"><table><thead><tr><th>ថ្ងៃទទួល</th><th>{translate("rollType")}</th><th>ចំនួនត្រូវបង់</th></tr></thead><tbody>{selected.map((row) => <tr key={row.id}><td>{displayDate(row.delivery_date)}</td><td>{rollTypeText(row)}</td><td>{quantities[row.id].toLocaleString()}</td></tr>)}</tbody></table></div>
          <p className="mt-4 rounded-xl bg-teal-50 p-4 font-bold text-teal-900">សរុប៖ {totalSelected.toLocaleString()} កី</p>
          <ErrorText error={payment.error} />
          <div className="mt-5 flex justify-end gap-2"><button className="btn-secondary" onClick={() => setConfirm(false)}>ត្រឡប់ទៅកែ</button><button className="btn-primary" disabled={payment.isPending} onClick={() => payment.mutate()}>{payment.isPending ? "កំពុងរក្សាទុក..." : "បញ្ជាក់ការបង់"}</button></div>
        </Dialog>
      )}
    </>
  );
}

function SummaryTile({ label, value }: { label: string; value: string }) {
  return <section className="card"><p className="text-xs text-slate-500">{label}</p><p className="mt-2 font-bold">{value}</p></section>;
}

function PaymentsPage({ user }: { user: User }) {
  const [supplier, setSupplier] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [deliveryStart, setDeliveryStart] = useState("");
  const [deliveryEnd, setDeliveryEnd] = useState("");
  const [rollType, setRollType] = useState("");
  const [page, setPage] = useState(1);
  const [selectedPayment, setSelectedPayment] = useState<number | null>(null);
  const [reverseReason, setReverseReason] = useState("");
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: () => api<Catalog>("/catalog") });
  const filters = { supplier_id: supplier, start_date: start, end_date: end, delivery_start_date: deliveryStart, delivery_end_date: deliveryEnd, roll_type_id: rollType, page, page_size: 25 };
  const payments = useQuery({ queryKey: ["payments", filters], queryFn: () => api<Page<Payment>>(`/payments${queryString(filters)}`) });
  const detail = useQuery({ queryKey: ["payment", selectedPayment], queryFn: () => api<PaymentDetail>(`/payments/${selectedPayment}`), enabled: selectedPayment !== null });
  const client = useQueryClient();
  const toast = useToast();
  const reverse = useMutation({
    mutationFn: () => api<PaymentDetail>(`/payments/${selectedPayment}/reverse`, { method: "POST", body: jsonBody({ reason: reverseReason }) }),
    onSuccess: () => {
      setReverseReason("");
      void client.invalidateQueries({ queryKey: ["payment", selectedPayment] });
      void client.invalidateQueries({ queryKey: ["payments"] });
      void client.invalidateQueries({ queryKey: ["unpaid"] });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
      toast("បានកែតម្រូវការបង់ ហើយបរិមាណត្រូវបានត្រឡប់ទៅមិនទាន់បង់។");
    },
    onError: (error) => toast(userMessage(error), "error"),
  });
  return (
    <>
      <PageTitle title="ប្រវត្តិការបង់" subtitle="មើលប្រតិបត្តិការបង់ និងកំណត់ត្រាការទទួលដែលបានគ្របដណ្ដប់" />
      <section className="card mb-5">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Field label="អ្នកផ្គត់ផ្គង់"><select className="field" value={supplier} onChange={(event) => { setSupplier(event.target.value); setPage(1); }}><option value="">ទាំងអស់</option>{catalog.data?.suppliers.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></Field>
          <Field label="ថ្ងៃបង់ចាប់ពី"><input className="field" type="date" value={start} onChange={(event) => setStart(event.target.value)} /></Field>
          <Field label="ថ្ងៃបង់ដល់"><input className="field" type="date" value={end} onChange={(event) => setEnd(event.target.value)} /></Field>
          <Field label="ថ្ងៃទទួលចាប់ពី"><input className="field" type="date" value={deliveryStart} onChange={(event) => setDeliveryStart(event.target.value)} /></Field>
          <Field label="ថ្ងៃទទួលដល់"><input className="field" type="date" value={deliveryEnd} onChange={(event) => setDeliveryEnd(event.target.value)} /></Field>
          <Field label={translate("rollType")}><select className="field" value={rollType} onChange={(event) => setRollType(event.target.value)}><option value="">ទាំងអស់</option>{catalog.data?.roll_types.map((item) => <option key={item.id} value={item.id}>{rollTypeLabel(item)}</option>)}</select></Field>
        </div>
      </section>
      {payments.isLoading ? <Loading /> : payments.error ? <ErrorText error={payments.error} /> : (
        <div className="table-wrap"><table><thead><tr><th>លេខយោង</th><th>អ្នកផ្គត់ផ្គង់</th><th>ថ្ងៃបង់</th><th>ថ្ងៃទទួលដែលគ្របដណ្ដប់</th><th>បរិមាណ</th><th>ប្រភេទកាវ</th><th>បញ្ជាក់ដោយ</th><th>ស្ថានភាព</th><th>លម្អិត</th></tr></thead><tbody>
          {payments.data?.items.length ? payments.data.items.map((payment) => <tr key={payment.id}>
            <td className="font-semibold">{payment.reference}</td><td>{payment.supplier_name}</td><td>{displayDate(payment.payment_date)}</td><td>{payment.delivery_date_from ? `${displayDate(payment.delivery_date_from)} – ${displayDate(payment.delivery_date_to)}` : "—"}</td><td>{payment.total_quantity.toLocaleString()}</td><td>{payment.roll_type_breakdown.map((item) => `${rollTypeText({ roll_type_code: item.roll_type_code, roll_type_name: item.roll_type_name, roll_type_name_km: item.roll_type_name_km, roll_type_name_en: item.roll_type_name_en })}: ${item.quantity}`).join(" · ") || "—"}</td><td>{payment.created_by_username ?? "—"}</td><td>{payment.is_reversed ? <span className="text-rose-700">បានកែតម្រូវ</span> : <span className="text-emerald-700">បានបង់</span>}</td><td><button className="font-semibold text-teal-700" onClick={() => setSelectedPayment(payment.id)}>បើក</button></td>
          </tr>) : <tr><td colSpan={9}><Empty label="មិនមានប្រវត្តិការបង់ទេ។" /></td></tr>}
        </tbody></table></div>
      )}
      <Pagination page={page} pages={payments.data?.pages ?? 0} onChange={setPage} />
      {selectedPayment !== null && <Dialog title={`ការបង់ ${detail.data?.reference ?? ""}`} onClose={() => setSelectedPayment(null)}>
        {detail.isLoading ? <Loading /> : detail.error ? <ErrorText error={detail.error} /> : detail.data && <>
          <p className="mb-4 text-sm text-slate-600">អ្នកផ្គត់ផ្គង់៖ <b>{detail.data.supplier_name}</b> · ថ្ងៃបង់៖ {displayDate(detail.data.payment_date)}<br />សរុប៖ <b>{detail.data.total_quantity.toLocaleString()} កី</b>{detail.data.note ? <><br />កំណត់ចំណាំ៖ {detail.data.note}</> : null}</p>
          <div className="table-wrap"><table><thead><tr><th>ថ្ងៃទទួល</th><th>{translate("rollType")}</th><th>បានបង់</th><th>ទទួលសរុប</th></tr></thead><tbody>{detail.data.allocations.map((allocation) => <tr key={allocation.allocation_id}><td>{displayDate(allocation.delivery_date)}</td><td>{rollTypeText({ roll_type_code: allocation.roll_type_code, roll_type_name: allocation.roll_type_name, roll_type_name_km: allocation.roll_type_name_km, roll_type_name_en: allocation.roll_type_name_en })}</td><td>{allocation.quantity_paid.toLocaleString()}</td><td>{allocation.quantity_received.toLocaleString()}</td></tr>)}</tbody></table></div>
          {detail.data.is_reversed && <p className="mt-4 rounded-xl bg-rose-50 p-3 text-sm text-rose-800">ការបង់នេះត្រូវបានកែតម្រូវ ហើយបរិមាណត្រូវបានត្រឡប់ទៅចំនួនមិនទាន់បង់។ {detail.data.reversal_reason ?? ""}</p>}
          {user.permissions.can_reverse_payments && !detail.data.is_reversed && <form className="mt-5 border-t border-slate-100 pt-4" onSubmit={(event) => { event.preventDefault(); if (window.confirm("ការកែតម្រូវនឹងរក្សាប្រវត្តិដើម ហើយត្រឡប់ចំនួននេះទៅមិនទាន់បង់។ បន្តទេ?")) reverse.mutate(); }}>
            <Field label="មូលហេតុត្រូវកែតម្រូវ"><textarea className="field min-h-20" minLength={3} maxLength={1000} required value={reverseReason} onChange={(event) => setReverseReason(event.target.value)} /></Field>
            <ErrorText error={reverse.error} /><button className="btn-danger mt-3" disabled={reverse.isPending}>កែតម្រូវការបង់</button>
          </form>}
        </>}
      </Dialog>}
    </>
  );
}

interface UserUpdatePayload {
  id: number;
  role?: UserRole;
  is_active?: boolean;
}

function UsersPage() {
  const client = useQueryClient();
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<UserRole>("warehouse_user");
  const [resetUser, setResetUser] = useState<number | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const users = useQuery({ queryKey: ["users"], queryFn: () => api<ManagedUser[]>("/users") });
  const create = useMutation({
    mutationFn: () => api("/users", { method: "POST", body: jsonBody({ username: newUsername, password: newPassword, role: newRole }) }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["users"] }); setAdding(false); setNewUsername(""); setNewPassword(""); toast("បានបង្កើតគណនីអ្នកប្រើប្រាស់។"); },
    onError: (error) => toast(userMessage(error), "error"),
  });
  const update = useMutation({
    mutationFn: ({ id, ...changes }: UserUpdatePayload) => api(`/users/${id}`, { method: "PATCH", body: jsonBody(changes) }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["users"] }); toast("បានកែប្រែស្ថានភាពគណនី។"); },
    onError: (error) => toast(userMessage(error), "error"),
  });
  const revokeTelegram = useMutation({
    mutationFn: (userId: number) => api(`/users/${userId}/telegram`, { method: "DELETE" }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ["users"] });
      toast("បានដកការភ្ជាប់ Telegram របស់អ្នកប្រើ។");
    },
    onError: (error) => toast(userMessage(error), "error"),
  });
  const reset = useMutation({
    mutationFn: () => api(`/users/${resetUser}/password`, { method: "POST", body: jsonBody({ new_password: resetPassword }) }),
    onSuccess: () => { setResetUser(null); setResetPassword(""); toast("បានកំណត់ពាក្យសម្ងាត់ថ្មី។"); },
    onError: (error) => toast(userMessage(error), "error"),
  });
  return (
    <>
      <PageTitle title="គ្រប់គ្រងអ្នកប្រើ" subtitle="បង្កើតគណនី កំណត់តួនាទី និងបិទគណនីដែលមិនប្រើ" action={<button className="btn-primary" onClick={() => setAdding(true)}>＋ បង្កើតអ្នកប្រើ</button>} />
      {users.isLoading ? <Loading /> : users.error ? <ErrorText error={users.error} /> : (
        <div className="table-wrap"><table><thead><tr><th>ឈ្មោះអ្នកប្រើ</th><th>តួនាទី</th><th>ស្ថានភាព</th><th>Telegram</th><th>បង្កើតនៅ</th><th>សកម្មភាព</th></tr></thead><tbody>{users.data?.map((user) => <tr key={user.id}>
          <td className="font-semibold">{user.username}</td><td><select aria-label={`តួនាទី ${user.username}`} className="field min-w-40" value={user.role} disabled={update.isPending} onChange={(event) => update.mutate({ id: user.id, role: event.target.value as UserRole })}><option value="warehouse_user">បុគ្គលិកឃ្លាំង</option><option value="admin">អ្នកគ្រប់គ្រង</option></select></td><td>{user.is_active ? "សកម្ម" : "បានបិទ"}</td><td>{user.telegram_linked ? "បានភ្ជាប់" : "មិនទាន់ភ្ជាប់"}</td><td>{displayDate(user.created_at)}</td><td><div className="flex flex-wrap gap-3"><button className="text-sm font-semibold text-teal-700" onClick={() => setResetUser(user.id)}>កំណត់ពាក្យសម្ងាត់</button>{user.telegram_linked && <button className="text-sm font-semibold text-amber-700" disabled={revokeTelegram.isPending} onClick={() => { if (window.confirm(`ដកការភ្ជាប់ Telegram របស់ ${user.username}?`)) revokeTelegram.mutate(user.id); }}>ដក Telegram</button>}<button className="text-sm font-semibold text-rose-700" disabled={update.isPending} onClick={() => update.mutate({ id: user.id, is_active: !user.is_active })}>{user.is_active ? "បិទគណនី" : "បើកគណនីឡើងវិញ"}</button></div></td>
        </tr>)}</tbody></table></div>
      )}
      {adding && <Dialog title="បង្កើតគណនី" onClose={() => setAdding(false)}><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
        <Field label="ឈ្មោះអ្នកប្រើ"><input className="field" required minLength={3} maxLength={64} value={newUsername} onChange={(event) => setNewUsername(event.target.value)} /></Field>
        <Field label="ពាក្យសម្ងាត់បណ្ដោះអាសន្ន (យ៉ាងតិច ៨ តួ)"><input className="field" type="password" required minLength={8} maxLength={256} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></Field>
        <Field label="តួនាទី"><select className="field" value={newRole} onChange={(event) => setNewRole(event.target.value as UserRole)}><option value="warehouse_user">បុគ្គលិកឃ្លាំង</option><option value="admin">អ្នកគ្រប់គ្រង</option></select></Field>
        <ErrorText error={create.error} /><div className="flex justify-end gap-2"><button className="btn-secondary" type="button" onClick={() => setAdding(false)}>បោះបង់</button><button className="btn-primary" disabled={create.isPending}>បង្កើតគណនី</button></div>
      </form></Dialog>}
      {resetUser !== null && <Dialog title="កំណត់ពាក្យសម្ងាត់ថ្មី" onClose={() => setResetUser(null)}><form className="space-y-4" onSubmit={(event) => { event.preventDefault(); reset.mutate(); }}>
        <Field label="ពាក្យសម្ងាត់ថ្មី"><input className="field" type="password" required minLength={8} maxLength={256} value={resetPassword} onChange={(event) => setResetPassword(event.target.value)} /></Field><ErrorText error={reset.error} />
        <div className="flex justify-end gap-2"><button type="button" className="btn-secondary" onClick={() => setResetUser(null)}>បោះបង់</button><button className="btn-primary" disabled={reset.isPending}>រក្សាទុក</button></div>
      </form></Dialog>}
    </>
  );
}

interface ManagedUser {
  id: number;
  username: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  telegram_linked: boolean;
}

function CatalogPage() {
  const client = useQueryClient();
  const toast = useToast();
  const catalog = useQuery({ queryKey: ["catalog-all"], queryFn: () => api<Catalog>("/catalog?only_active=false") });
  const [supplierName, setSupplierName] = useState("");
  const [rollCode, setRollCode] = useState("");
  const [rollNameKm, setRollNameKm] = useState("");
  const [rollNameEn, setRollNameEn] = useState("");
  const createSupplier = useMutation({
    mutationFn: () => api("/suppliers", { method: "POST", body: jsonBody({ name: supplierName }) }),
    onSuccess: () => { setSupplierName(""); void client.invalidateQueries({ queryKey: ["catalog-all"] }); void client.invalidateQueries({ queryKey: ["catalog"] }); toast("បានបង្កើតអ្នកផ្គត់ផ្គង់។"); },
    onError: (error) => toast(userMessage(error), "error"),
  });
  const createRoll = useMutation({
    mutationFn: () => api("/roll-types", { method: "POST", body: jsonBody({ code: rollCode, name_km: rollNameKm, name_en: rollNameEn }) }),
    onSuccess: () => { setRollCode(""); setRollNameKm(""); setRollNameEn(""); void client.invalidateQueries({ queryKey: ["catalog-all"] }); void client.invalidateQueries({ queryKey: ["catalog"] }); toast("បានបង្កើតប្រភេទកាវ។"); },
    onError: (error) => toast(userMessage(error), "error"),
  });
  const update = useMutation({
    mutationFn: ({ kind, item, name, name_km, name_en, is_active }: CatalogUpdateInput) => api(`/${kind}/${item.id}`, { method: "PATCH", body: jsonBody(kind === "suppliers" ? { name, is_active } : { name_km, name_en, is_active }) }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["catalog-all"] }); void client.invalidateQueries({ queryKey: ["catalog"] }); toast("បានកែប្រែកាតាឡុក។"); },
    onError: (error) => toast(userMessage(error), "error"),
  });
  return (
    <>
      <PageTitle title="អ្នកផ្គត់ផ្គង់ និងប្រភេទកាវ" subtitle="អសកម្មជាជម្រើសល្អជាងការលុប ដើម្បីរក្សាប្រវត្តិចាស់" />
      <div className="grid gap-5 xl:grid-cols-2">
        <CatalogList title="អ្នកផ្គត់ផ្គង់" kind="suppliers" items={catalog.data?.suppliers ?? []} name={supplierName} setName={setSupplierName} create={createSupplier} update={update} />
        <RollTypeCatalogList items={catalog.data?.roll_types ?? []} code={rollCode} setCode={setRollCode} nameKm={rollNameKm} setNameKm={setRollNameKm} nameEn={rollNameEn} setNameEn={setRollNameEn} create={createRoll} update={update} />
      </div>
      {catalog.isLoading && <Loading />}
      {catalog.error && <ErrorText error={catalog.error} />}
    </>
  );
}

function CatalogList({
  title,
  kind,
  items,
  name,
  setName,
  create,
  update,
}: {
  title: string;
  kind: "suppliers";
  items: NamedItem[];
  name: string;
  setName: (value: string) => void;
  create: Pick<UseMutationResult<unknown, Error, void>, "mutate" | "isPending">;
  update: Pick<UseMutationResult<unknown, Error, CatalogUpdateInput>, "mutate" | "isPending">;
}) {
  return (
    <section className="card">
      <h2 className="mb-4 font-bold">{title}</h2>
      <form className="mb-5 flex gap-2" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
        <input className="field" required maxLength={120} aria-label={`ឈ្មោះ${title}`} placeholder={`បញ្ចូលឈ្មោះ${title}`} value={name} onChange={(event) => setName(event.target.value)} />
        <button className="btn-primary shrink-0" disabled={create.isPending}>បន្ថែម</button>
      </form>
      <div className="space-y-3">{items.map((item) => <CatalogRow key={item.id} item={item} kind={kind} update={update} />)}{items.length === 0 && <Empty />}</div>
    </section>
  );
}

interface CatalogUpdateInput {
  kind: "suppliers" | "roll-types";
  item: NamedItem | RollTypeItem;
  name?: string;
  name_km?: string;
  name_en?: string;
  is_active?: boolean;
}

function CatalogRow({ item, kind, update }: { item: NamedItem; kind: "suppliers"; update: Pick<UseMutationResult<unknown, Error, CatalogUpdateInput>, "mutate" | "isPending"> }) {
  const [name, setName] = useState(item.name);
  useEffect(() => setName(item.name), [item.name]);
  return <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-100 p-3">
    <input className="field min-w-40 flex-1" aria-label={`ឈ្មោះ ${item.name}`} maxLength={120} value={name} onChange={(event) => setName(event.target.value)} />
    <button className="btn-secondary px-3" disabled={name.trim() === item.name || update.isPending} onClick={() => update.mutate({ kind, item, name: name.trim() })}>រក្សាឈ្មោះ</button>
    <button className={item.is_active ? "btn-danger px-3" : "btn-secondary px-3"} disabled={update.isPending} onClick={() => update.mutate({ kind, item, is_active: !item.is_active })}>{item.is_active ? "បិទ" : "បើក"}</button>
  </div>;
}

function RollTypeCatalogList({
  items,
  code,
  setCode,
  nameKm,
  setNameKm,
  nameEn,
  setNameEn,
  create,
  update,
}: {
  items: RollTypeItem[];
  code: string;
  setCode: (value: string) => void;
  nameKm: string;
  setNameKm: (value: string) => void;
  nameEn: string;
  setNameEn: (value: string) => void;
  create: Pick<UseMutationResult<unknown, Error, void>, "mutate" | "isPending">;
  update: Pick<UseMutationResult<unknown, Error, CatalogUpdateInput>, "mutate" | "isPending">;
}) {
  return (
    <section className="card">
      <h2 className="mb-4 font-bold">ប្រភេទកាវ</h2>
      <p className="mb-4 text-sm text-slate-500">ប្រភេទដើមមានកូដថេរ ហើយឈ្មោះខ្មែរនិងអង់គ្លេសអាចកែប្រែដោយឡែកពីគ្នា។</p>
      <form className="mb-5 grid gap-3" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
        <Field label="កូដប្រភេទ (អក្សរធំ និងសញ្ញា _)"><input className="field" required minLength={2} maxLength={40} pattern="[A-Z][A-Z0-9_]*" value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} /></Field>
        <Field label="ឈ្មោះជាភាសាខ្មែរ"><input className="field" required maxLength={120} value={nameKm} onChange={(event) => setNameKm(event.target.value)} /></Field>
        <Field label="ឈ្មោះជាភាសាអង់គ្លេស"><input className="field" required maxLength={120} value={nameEn} onChange={(event) => setNameEn(event.target.value)} /></Field>
        <button className="btn-primary justify-self-start" disabled={create.isPending}>បន្ថែមប្រភេទកាវ</button>
      </form>
      <div className="space-y-3">{items.map((item) => <RollTypeCatalogRow key={item.id} item={item} update={update} />)}{items.length === 0 && <Empty />}</div>
    </section>
  );
}

function RollTypeCatalogRow({ item, update }: { item: RollTypeItem; update: Pick<UseMutationResult<unknown, Error, CatalogUpdateInput>, "mutate" | "isPending"> }) {
  const [nameKm, setNameKm] = useState(item.name_km);
  const [nameEn, setNameEn] = useState(item.name_en);
  useEffect(() => { setNameKm(item.name_km); setNameEn(item.name_en); }, [item.name_km, item.name_en]);
  return (
    <div className="space-y-2 rounded-xl border border-slate-100 p-3">
      <div className="flex items-center justify-between gap-2"><strong>{item.code}</strong><button className={item.is_active ? "btn-danger px-3" : "btn-secondary px-3"} disabled={update.isPending} onClick={() => update.mutate({ kind: "roll-types", item, is_active: !item.is_active })}>{item.is_active ? "បិទ" : "បើក"}</button></div>
      <label className="block text-xs font-medium text-slate-600">ភាសាខ្មែរ<input className="field mt-1" maxLength={120} value={nameKm} onChange={(event) => setNameKm(event.target.value)} /></label>
      <label className="block text-xs font-medium text-slate-600">English<input className="field mt-1" maxLength={120} value={nameEn} onChange={(event) => setNameEn(event.target.value)} /></label>
      <button className="btn-secondary px-3" disabled={(nameKm === item.name_km && nameEn === item.name_en) || update.isPending} onClick={() => update.mutate({ kind: "roll-types", item, name_km: nameKm.trim(), name_en: nameEn.trim() })}>រក្សាឈ្មោះ</button>
    </div>
  );
}

function SettingsPage() {
  const client = useQueryClient();
  const toast = useToast();
  const settings = useQuery({
    queryKey: ["settings"],
    queryFn: () => api<{ settings: Record<string, string[]>; roles: UserRole[] }>("/settings"),
  });
  const save = useMutation({
    mutationFn: ({ key, value }: { key: string; value: string[] }) => api(`/settings/${key}`, { method: "PUT", body: jsonBody({ value }) }),
    onSuccess: () => { void client.invalidateQueries({ queryKey: ["settings"] }); void client.invalidateQueries({ queryKey: ["me"] }); toast("បានរក្សាទុកសិទ្ធិ។"); },
    onError: (error) => toast(userMessage(error), "error"),
  });
  const items = [
    ["payment_confirmer_roles", "តួនាទីដែលអាចបញ្ជាក់ការបង់"],
    ["delivery_editor_roles", "តួនាទីដែលអាចកែការទទួល"],
    ["delivery_deleter_roles", "តួនាទីដែលអាចលុបការទទួលដែលមិនទាន់បង់"],
  ];
  return (
    <>
      <PageTitle title="ការកំណត់សិទ្ធិ" subtitle="សិទ្ធិត្រូវបានផ្ទៀងផ្ទាត់នៅលើ API មិនមែនត្រឹមតែលាក់ប៊ូតុងទេ" />
      {settings.isLoading ? <Loading /> : settings.error ? <ErrorText error={settings.error} /> : (
        <div className="space-y-4">{items.map(([key, label]) => <PermissionSetting key={key} settingKey={key} label={label} selected={settings.data?.settings[key] ?? ["admin"]} roles={settings.data?.roles ?? []} onSave={(value) => save.mutate({ key, value })} saving={save.isPending} />)}</div>
      )}
    </>
  );
}

function PermissionSetting({ settingKey, label, selected, roles, onSave, saving }: { settingKey: string; label: string; selected: string[]; roles: UserRole[]; onSave: (value: string[]) => void; saving: boolean }) {
  const [value, setValue] = useState(selected);
  useEffect(() => setValue(selected), [selected]);
  return <section className="card" aria-labelledby={`setting-${settingKey}`}>
    <h2 id={`setting-${settingKey}`} className="font-bold">{label}</h2>
    <div className="my-4 flex flex-wrap gap-5">{roles.map((role) => <label key={role} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.includes(role)} onChange={(event) => setValue((old) => event.target.checked ? [...old, role] : old.filter((item) => item !== role))} />{role === "admin" ? "អ្នកគ្រប់គ្រង" : "បុគ្គលិកឃ្លាំង"}</label>)}</div>
    <button className="btn-primary" disabled={saving || value.length === 0} onClick={() => onSave(value)}>រក្សាទុកសិទ្ធិ</button>
  </section>;
}

function AccountPage({ user }: { user: User }) {
  const client = useQueryClient();
  const toast = useToast();
  const [link, setLink] = useState<{ deep_link: string; expires_at: string; instructions_km: string } | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const status = useQuery({
    queryKey: ["telegram-status"],
    queryFn: () => api<TelegramStatus>("/telegram/status"),
    refetchInterval: 10_000,
  });
  const createLink = useMutation({
    mutationFn: () => api<{ deep_link: string; expires_at: string; instructions_km: string }>("/telegram/link", { method: "POST" }),
    onSuccess: setLink,
    onError: (error) => toast(userMessage(error), "error"),
  });
  const unlink = useMutation({
    mutationFn: () => api("/telegram/link", { method: "DELETE" }),
    onSuccess: () => { setLink(null); void client.invalidateQueries({ queryKey: ["telegram-status"] }); void client.invalidateQueries({ queryKey: ["me"] }); toast("បានដកការភ្ជាប់ Telegram។"); },
    onError: (error) => toast(userMessage(error), "error"),
  });
  const password = useMutation({
    mutationFn: () => api("/auth/password", { method: "POST", body: jsonBody({ current_password: currentPassword, new_password: newPassword }) }),
    onSuccess: () => { setCurrentPassword(""); setNewPassword(""); toast("បានប្ដូរពាក្យសម្ងាត់។"); },
    onError: (error) => toast(userMessage(error), "error"),
  });
  return (
    <>
      <PageTitle title="គណនី និង Telegram" subtitle={`បានចូលជាអ្នកប្រើ ${user.username}`} />
      <div className="grid gap-5 xl:grid-cols-2">
        <section className="card">
          <h2 className="font-bold">គណនី Telegram</h2>
          {status.isLoading ? <Loading /> : status.error ? <ErrorText error={status.error} /> : <>
            <p className="mt-3 text-sm text-slate-600">{status.data?.is_linked ? `បានភ្ជាប់${status.data.telegram_username ? ` ជា @${status.data.telegram_username}` : ""}។` : "មិនទាន់ភ្ជាប់គណនី Telegram ទេ។"}</p>
            <div className="mt-4 flex flex-wrap gap-2">{!status.data?.is_linked && <button className="btn-primary" onClick={() => createLink.mutate()} disabled={createLink.isPending}>{createLink.isPending ? "កំពុងបង្កើត..." : "ភ្ជាប់ Telegram"}</button>}{status.data?.is_linked && <button className="btn-danger" onClick={() => { if (window.confirm("តើអ្នកចង់ដកការភ្ជាប់ Telegram មែនទេ?")) unlink.mutate(); }} disabled={unlink.isPending}>ដកការភ្ជាប់</button>}</div>
          </>}
          {link && <div className="mt-5 rounded-xl border border-teal-100 bg-teal-50 p-4">
            <p className="whitespace-pre-line text-sm">{link.instructions_km}</p>
            {link.deep_link ? <a className="btn-primary mt-4" href={link.deep_link} target="_blank" rel="noreferrer">បើក Telegram</a> : <p className="mt-3 text-sm text-rose-700">មិនទាន់កំណត់ឈ្មោះ Telegram bot នៅលើ server ទេ។</p>}
            <p className="mt-2 text-xs text-slate-500">ផុតកំណត់៖ {new Date(link.expires_at).toLocaleString("km-KH")}</p>
          </div>}
        </section>
        <section className="card">
          <h2 className="font-bold">ប្ដូរពាក្យសម្ងាត់</h2>
          <form className="mt-4 space-y-4" onSubmit={(event) => { event.preventDefault(); password.mutate(); }}>
            <Field label="ពាក្យសម្ងាត់បច្ចុប្បន្ន"><input className="field" type="password" required maxLength={256} value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></Field>
            <Field label="ពាក្យសម្ងាត់ថ្មី (យ៉ាងតិច ៨ តួ)"><input className="field" type="password" required minLength={8} maxLength={256} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /></Field>
            <ErrorText error={password.error} /><button className="btn-primary" disabled={password.isPending}>ប្ដូរពាក្យសម្ងាត់</button>
          </form>
        </section>
      </div>
    </>
  );
}

function Pagination({ page, pages, onChange }: { page: number; pages: number; onChange: (page: number) => void }) {
  if (pages < 2) return null;
  return <nav className="mt-5 flex items-center justify-center gap-3" aria-label="ទំព័រ">
    <button className="btn-secondary px-3" disabled={page <= 1} onClick={() => onChange(page - 1)}>មុន</button>
    <span className="text-sm text-slate-500">ទំព័រ {page} / {pages}</span>
    <button className="btn-secondary px-3" disabled={page >= pages} onClick={() => onChange(page + 1)}>បន្ទាប់</button>
  </nav>;
}

function ForbiddenPage() {
  return <section className="card"><h1 className="text-xl font-bold">គ្មានសិទ្ធិចូលប្រើ</h1><p className="mt-2 text-slate-500">សូមទាក់ទងអ្នកគ្រប់គ្រង ប្រសិនបើអ្នកត្រូវការសិទ្ធិនេះ។</p></section>;
}

interface AuditItem {
  id: number;
  action: string;
  actor_username: string | null;
  entity_type: string | null;
  entity_id: number | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

function AuditPage() {
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [page, setPage] = useState(1);
  const filters = { action, entity_type: entityType, page, page_size: 50 };
  const audit = useQuery({
    queryKey: ["audit", filters],
    queryFn: () => api<Page<AuditItem>>(`/audit${queryString(filters)}`),
  });
  return <>
    <PageTitle title="កំណត់ហេតុសកម្មភាព" subtitle="ប្រវត្តិសកម្មភាពសំខាន់ៗ និងការកែតម្រូវក្នុងប្រព័ន្ធ" />
    <section className="card mb-5 grid gap-3 sm:grid-cols-2">
      <Field label="ប្រភេទសកម្មភាព"><input className="field" value={action} maxLength={64} onChange={(event) => { setAction(event.target.value); setPage(1); }} placeholder="ឧ. payment.confirm" /></Field>
      <Field label="ប្រភេទទិន្នន័យ"><input className="field" value={entityType} maxLength={64} onChange={(event) => { setEntityType(event.target.value); setPage(1); }} placeholder="ឧ. delivery" /></Field>
    </section>
    {audit.isLoading ? <Loading /> : audit.error ? <ErrorText error={audit.error} /> : <div className="table-wrap">
      <table><thead><tr><th>ពេលវេលា</th><th>អ្នកប្រើ</th><th>សកម្មភាព</th><th>ប្រភេទ</th><th>លេខសម្គាល់</th><th>ព័ត៌មានបន្ថែម</th></tr></thead><tbody>
        {audit.data?.items.length ? audit.data.items.map((item) => <tr key={item.id}>
          <td>{new Date(item.created_at).toLocaleString("km-KH")}</td><td>{item.actor_username ?? "ប្រព័ន្ធ"}</td><td className="font-mono text-xs">{item.action}</td><td>{item.entity_type ?? "—"}</td><td>{item.entity_id ?? "—"}</td><td className="max-w-sm truncate text-xs">{item.details ? JSON.stringify(item.details) : "—"}</td>
        </tr>) : <tr><td colSpan={6}><Empty label="មិនមានកំណត់ហេតុក្នុងលក្ខខណ្ឌនេះទេ។" /></td></tr>}
      </tbody></table>
    </div>}
    <Pagination page={page} pages={audit.data?.pages ?? 0} onChange={setPage} />
  </>;
}

export default App;
