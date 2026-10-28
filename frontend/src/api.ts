export type UserRole = "admin" | "warehouse_user";

export interface User {
  id: number;
  username: string;
  role: UserRole;
  is_active: boolean;
  permissions: Record<string, boolean>;
  csrf_token: string | null;
  telegram?: TelegramStatus;
}

export interface TelegramStatus {
  is_linked: boolean;
  bot_username: string | null;
  telegram_username: string | null;
  linked_at: string | null;
}

export interface NamedItem {
  id: number;
  name: string;
  is_active: boolean;
}

export interface RollTypeItem {
  id: number;
  code: string;
  name: string;
  name_km: string;
  name_en: string;
  is_active: boolean;
}

export interface Catalog {
  suppliers: NamedItem[];
  roll_types: RollTypeItem[];
}

export interface Delivery {
  id: number;
  delivery_date: string;
  supplier_id: number;
  supplier_name: string;
  roll_type_id: number;
  roll_type_name: string;
  roll_type_name_km: string | null;
  roll_type_name_en: string | null;
  roll_type_code: string | null;
  quantity_received: number;
  quantity_paid: number;
  quantity_unpaid: number;
  status: "unpaid" | "partial" | "paid";
  note: string | null;
  created_by_username: string | null;
  created_at: string;
  updated_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface Payment {
  id: number;
  reference: string;
  supplier_id: number;
  supplier_name: string;
  payment_date: string;
  total_quantity: number;
  note: string | null;
  created_by: number;
  created_by_username: string | null;
  is_reversed: boolean;
  reversal_reason?: string | null;
  delivery_date_from: string | null;
  delivery_date_to: string | null;
  roll_type_breakdown: { roll_type_id: number; roll_type_name: string; roll_type_name_km?: string; roll_type_name_en?: string; roll_type_code?: string; quantity: number }[];
}

export interface PaymentDetail extends Payment {
  allocations: {
    allocation_id: number;
    delivery_id: number;
    delivery_date: string;
    roll_type_id: number;
    roll_type_name: string | null;
    roll_type_name_km: string | null;
    roll_type_name_en: string | null;
    roll_type_code: string | null;
    quantity_paid: number;
    quantity_received: number;
  }[];
}

export interface UnpaidPreview {
  supplier: { id: number; name: string };
  start_date: string | null;
  end_date: string | null;
  deliveries: Delivery[];
  totals: { received: number; paid: number; unpaid: number };
  by_roll_type: {
    roll_type_id: number;
    roll_type_code: string;
    roll_type_name: string;
    roll_type_name_en: string;
    received: number;
    paid: number;
    unpaid: number;
    quantity_unpaid: number;
    delivery_count: number;
  }[];
  delivery_count: number;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
  ) {
    super(message);
  }
}

let csrfToken: string | null = null;

export function rememberCsrfToken(token: string | null): void {
  csrfToken = token;
}

const apiBase = (import.meta.env.VITE_API_BASE_URL as string | undefined) || "/api";

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (csrfToken && ["POST", "PUT", "PATCH", "DELETE"].includes((options.method ?? "GET").toUpperCase())) {
    headers.set("X-CSRF-Token", csrfToken);
  }
  const response = await fetch(`${apiBase}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });
  if (response.status === 204) return undefined as T;
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const errorPayload =
      typeof body === "object" && body !== null && "error" in body
        ? (body as { error?: { code?: string; message?: string } }).error
        : undefined;
    throw new ApiError(
      errorPayload?.message ?? "សំណើមិនអាចបំពេញបានទេ។ សូមព្យាយាមម្ដងទៀត។",
      response.status,
      errorPayload?.code ?? "request_failed",
    );
  }
  return body as T;
}

export function queryString(values: Record<string, string | number | null | undefined>): string {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") query.set(key, String(value));
  });
  const rendered = query.toString();
  return rendered ? `?${rendered}` : "";
}

export function userMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "មានបញ្ហាក្នុងការតភ្ជាប់។ សូមពិនិត្យការតភ្ជាប់របស់អ្នក។";
  const messages: Record<string, string> = {
    unauthenticated: "សូមចូលគណនីម្ដងទៀត។",
    forbidden: "អ្នកមិនមានសិទ្ធិធ្វើសកម្មភាពនេះទេ។",
    csrf_invalid: "វគ្គចូលគណនីផុតកំណត់។ សូមផ្ទុកទំព័រឡើងវិញ។",
    invalid_date_range: "កាលបរិច្ឆេទចាប់ផ្ដើមត្រូវតែមុនកាលបរិច្ឆេទបញ្ចប់។",
    nothing_to_pay: "មិនមានចំនួនដែលមិនទាន់បង់ក្នុងជម្រើសនេះទេ។",
    exceeds_unpaid_quantity: "ចំនួននេះលើសពីចំនួនដែលមិនទាន់បង់។",
    allocation_conflict: "ទិន្នន័យបានផ្លាស់ប្ដូរ។ សូមផ្ទុកឡើងវិញហើយពិនិត្យម្ដងទៀត។",
    idempotency_key_reused: "សំណើនេះត្រូវបានប្រើរួចហើយ។ សូមព្យាយាមម្ដងទៀត។",
    username_taken: "ឈ្មោះអ្នកប្រើប្រាស់នេះមានរួចហើយ។",
  };
  return messages[error.code] ?? error.message;
}

export function todayCambodia(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Phnom_Penh",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function displayDate(value: string | null | undefined): string {
  if (!value) return "—";
  const [year, month, day] = value.slice(0, 10).split("-");
  return `${day}-${month}-${year}`;
}

export function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}
