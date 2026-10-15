export type User = {
  id: string;
  username: string;
  role: string;
  tenant_id: string;
  tenant_name: string;
};
export type Attachment = {
  id: string;
  filename: string;
  size: number;
  mime: string;
  sha256: string;
};
export type Application = {
  id: string;
  title: string;
  description: string;
  type: string;
  business_status: string;
  processing_status: string;
  version: number;
  document_version: number;
  document_hash: string;
  applicant_signed: boolean;
  officer_signed: boolean;
  created_at: string;
  updated_at: string;
  attachments: Attachment[];
  decision_hash: string | null;
  decision_document: Record<string, unknown> | null;
  reviews: { decision: string; reason: string; created_at: string }[];
};
export type Audit = {
  id: string;
  version: number;
  action: string;
  before: string;
  after: string;
  correlation_id: string;
  timestamp: string;
};
export type Integration = {
  id: string;
  outcome: string;
  provider: string;
  attempt: number;
  correlation_id: string;
};
export type Monitor = {
  build: string;
  stage: string;
  profile: string;
  scenario: string;
  seed: number;
  tenant: string;
  statuses: Record<string, number>;
  checks: Record<string, number>;
  registry: string;
  queue: string;
  dlq: string;
  signature: string;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public code: string,
    public correlation: string,
  ) {
    super(message);
  }
}

let token = "";
export function setToken(value: string) {
  token = value;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  headers.set("X-Correlation-ID", crypto.randomUUID());
  const response = await fetch(`/api/v1${path}`, { ...options, headers });
  const result = await response.json();
  if (!response.ok)
    throw new ApiError(
      result.message || "Не удалось выполнить запрос",
      result.code || "HTTP_ERROR",
      result.correlation_id || "",
    );
  return result as T;
}
export async function download(application: Application, file: Attachment) {
  const response = await fetch(
    `/api/v1/applications/${application.id}/attachments/${file.id}`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok) throw new Error("Не удалось скачать файл");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = file.filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const labels: Record<string, string> = {
  DRAFT: "Черновик",
  AWAITING_APPLICANT_SIGNATURE: "Ожидает подписи",
  SUBMITTED: "Отправлено",
  VALIDATING: "Проверяется",
  UNDER_REVIEW: "На рассмотрении",
  NEEDS_CORRECTION: "На доработке",
  APPROVED: "Одобрено",
  AWAITING_OFFICER_SIGNATURE: "Подпись решения",
  COMPLETED: "Завершено",
  REJECTED: "Отклонено",
  CANCELLED: "Отменено",
};
export const roleLabels: Record<string, string> = {
  applicant: "Заявитель",
  reviewer: "Специалист",
  officer: "Уполномоченный",
  tenant_admin: "Администратор",
  qa_observer: "QA-наблюдатель",
};
export const date = (s: string) =>
  new Date(s).toLocaleDateString("ru-RU", { day: "numeric", month: "short" });
