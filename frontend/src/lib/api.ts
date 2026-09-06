export type HealthResponse = {
  status: string;
  service: string;
};

export type ConfigStatusResponse = {
  configured: boolean;
  installation_id: string;
};

export type CompanySettings = {
  id: string;
  name: string;
  website: string | null;
  industry: string | null;
  support_name: string | null;
  default_language: string;
  timezone: string;
};

export type CompanyUpdate = {
  name: string;
  website: string | null;
  industry: string | null;
  support_name: string | null;
  default_language: string;
  timezone: string;
};

export type AIProviderSettings = {
  id: string;
  provider: string;
  model: string;
  embedding_provider: string | null;
  embedding_model: string | null;
  enabled: boolean;
  api_key_configured: boolean;
};

export type AIConnectionTestRequest = {
  provider: string;
  model: string;
  api_key: string;
};

export type AIConnectionTestResponse = {
  success: boolean;
  message: string;
};

export type AIProviderUpdate = {
  provider: string;
  model: string;
  api_key?: string;
  embedding_provider?: string | null;
  embedding_model?: string | null;
  enabled: boolean;
};

export type DashboardOverview = {
  ai_provider: {
    configured: boolean;
    provider: string | null;
    model: string | null;
  };
  storage: {
    type: "sqlite";
    status: "ready" | "unavailable";
  };
  knowledge: {
    document_count: number;
  };
  tickets: {
    open_count: number;
  };
  widget: {
    configured: boolean;
  };
  system: {
    status: "healthy" | "unavailable";
  };
};

export type KnowledgeDocumentStatus =
  | "uploaded"
  | "processing"
  | "ready"
  | "failed";

export type KnowledgeDocument = {
  id: string;
  filename: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  status: KnowledgeDocumentStatus;
  chunk_count: number;
  created_at: string;
  updated_at: string;
  error: string | null;
};

export type KnowledgeChunk = {
  id: string;
  chunk_index: number;
  page_number: number | null;
  section: string | null;
  token_count: number;
  char_start: number;
  char_end: number;
};

export type KnowledgeDocumentDetail = KnowledgeDocument & {
  chunks: KnowledgeChunk[];
};

export type RAGQueryRequest = {
  question: string;
};

export type RAGSource = {
  document_id: string;
  document_name: string;
  chunk_id: string;
  page: number | null;
  section: string | null;
  score: number;
};

export type RAGRetrievedChunk = RAGSource & {
  content: string;
};

export type RAGResponse = {
  answer: string;
  sources: RAGSource[];
  retrieved_chunks: RAGRetrievedChunk[];
  insufficient_evidence: boolean;
  latency_ms: number;
  trace_id: string;
};

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

async function getErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const payload: unknown = await response.json();

    if (isRecord(payload) && typeof payload.detail === "string") {
      return payload.detail;
    }
  } catch {
    // Use the operation-specific fallback when the API did not return JSON.
  }

  return fallback;
}

async function requestJson<T>(
  input: string,
  init: RequestInit,
  fallback: string,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${input}`, init);

  if (!response.ok) {
    throw new Error(await getErrorMessage(response, fallback));
  }

  return (await response.json()) as T;
}

export async function getBackendHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>(
    "/api/health",
    {
      cache: "no-store",
    },
    "Backend health check failed",
  );
}

export async function getDashboardOverview(): Promise<DashboardOverview> {
  return requestJson<DashboardOverview>(
    "/api/dashboard/overview",
    {
      cache: "no-store",
    },
    "Unable to load dashboard overview",
  );
}

export async function getConfigStatus(): Promise<ConfigStatusResponse> {
  return requestJson<ConfigStatusResponse>(
    "/api/config/status",
    {
      cache: "no-store",
    },
    "Unable to read AgentDesk configuration status",
  );
}

export async function getCompanySettings(): Promise<CompanySettings | null> {
  const response = await fetch(`${API_BASE_URL}/api/settings/company`, {
    cache: "no-store",
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(response, "Unable to load company settings"),
    );
  }

  return (await response.json()) as CompanySettings | null;
}

export async function updateCompanySettings(
  data: CompanyUpdate,
): Promise<CompanySettings> {
  return requestJson<CompanySettings>(
    "/api/settings/company",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    },
    "Unable to save company settings",
  );
}

export async function getAISettings(): Promise<AIProviderSettings | null> {
  const response = await fetch(`${API_BASE_URL}/api/settings/ai`, {
    cache: "no-store",
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(response, "Unable to load AI settings"),
    );
  }

  return (await response.json()) as AIProviderSettings | null;
}

export async function testAIConnection(
  data: AIConnectionTestRequest,
): Promise<AIConnectionTestResponse> {
  return requestJson<AIConnectionTestResponse>(
    "/api/settings/ai/test",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    },
    "Unable to test AI connection",
  );
}

export async function updateAISettings(
  data: AIProviderUpdate,
): Promise<AIProviderSettings> {
  return requestJson<AIProviderSettings>(
    "/api/settings/ai",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    },
    "Unable to save AI settings",
  );
}

export async function completeSetup(): Promise<ConfigStatusResponse> {
  return requestJson<ConfigStatusResponse>(
    "/api/config/complete",
    {
      method: "POST",
    },
    "Unable to complete AgentDesk setup",
  );
}

export async function uploadKnowledgeDocument(
  file: File,
): Promise<KnowledgeDocument> {
  const formData = new FormData();
  formData.append("file", file);

  return requestJson<KnowledgeDocument>(
    "/api/knowledge/documents",
    {
      method: "POST",
      body: formData,
    },
    "Unable to upload knowledge document",
  );
}

export async function listKnowledgeDocuments(): Promise<KnowledgeDocument[]> {
  return requestJson<KnowledgeDocument[]>(
    "/api/knowledge/documents",
    {
      cache: "no-store",
    },
    "Unable to load knowledge documents",
  );
}

export async function getKnowledgeDocument(
  documentId: string,
): Promise<KnowledgeDocumentDetail> {
  return requestJson<KnowledgeDocumentDetail>(
    `/api/knowledge/documents/${encodeURIComponent(documentId)}`,
    {
      cache: "no-store",
    },
    "Unable to load knowledge document details",
  );
}

export async function reindexKnowledgeDocument(
  documentId: string,
): Promise<KnowledgeDocument> {
  return requestJson<KnowledgeDocument>(
    `/api/knowledge/documents/${encodeURIComponent(documentId)}/reindex`,
    {
      method: "POST",
    },
    "Unable to re-index knowledge document",
  );
}

export async function deleteKnowledgeDocument(
  documentId: string,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/knowledge/documents/${encodeURIComponent(documentId)}`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    throw new Error(
      await getErrorMessage(response, "Unable to delete knowledge document"),
    );
  }
}

export async function queryRAG(
  data: RAGQueryRequest,
): Promise<RAGResponse> {
  return requestJson<RAGResponse>(
    "/api/rag/query",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    },
    "Unable to query the knowledge base",
  );
}
