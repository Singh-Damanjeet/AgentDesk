"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

import PageHeader from "@/components/dashboard/page-header";
import EmptyState from "@/components/ui/empty-state";
import ErrorState from "@/components/ui/error-state";
import LoadingState from "@/components/ui/loading-state";
import {
  deleteKnowledgeDocument,
  getKnowledgeDocument,
  listKnowledgeDocuments,
  reindexKnowledgeDocument,
  uploadKnowledgeDocument,
  type KnowledgeDocument,
  type KnowledgeDocumentDetail,
  type KnowledgeDocumentStatus,
} from "@/lib/api";

const MAX_DOCUMENT_SIZE_BYTES = 10 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = new Set([
  ".pdf",
  ".docx",
  ".txt",
  ".md",
  ".markdown",
]);

const buttonClassName =
  "rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-100 transition-colors hover:border-zinc-500 hover:bg-zinc-900 disabled:cursor-not-allowed disabled:opacity-50";

const primaryButtonClassName =
  "rounded-lg bg-white px-4 py-2 text-sm font-medium text-zinc-950 transition-colors hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-50";

const statusClasses: Record<KnowledgeDocumentStatus, string> = {
  uploaded: "border-zinc-700 bg-zinc-900 text-zinc-300",
  processing: "border-amber-900/70 bg-amber-950/30 text-amber-300",
  ready: "border-emerald-900/70 bg-emerald-950/30 text-emerald-300",
  failed: "border-red-900/70 bg-red-950/30 text-red-300",
};

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function getFileExtension(filename: string): string {
  const lastDot = filename.lastIndexOf(".");
  return lastDot >= 0 ? filename.slice(lastDot).toLowerCase() : "";
}

function validateSelectedFile(file: File): string | null {
  if (!file.name.trim()) {
    return "Choose a document with a valid filename.";
  }

  if (!ACCEPTED_EXTENSIONS.has(getFileExtension(file.name))) {
    return "Upload a PDF, DOCX, TXT, or Markdown file.";
  }

  if (file.size === 0) {
    return "The selected document is empty.";
  }

  if (file.size > MAX_DOCUMENT_SIZE_BYTES) {
    return "The document exceeds the 10 MB upload limit.";
  }

  return null;
}

function formatFileSize(size: number): string {
  if (size < 1024) {
    return `${size} B`;
  }

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function statusLabel(status: KnowledgeDocumentStatus): string {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function replaceDocument(
  documents: KnowledgeDocument[],
  updated: KnowledgeDocument,
): KnowledgeDocument[] {
  return documents.map((document) =>
    document.id === updated.id ? updated : document,
  );
}

function DocumentStatus({ status }: { status: KnowledgeDocumentStatus }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${statusClasses[status]}`}
    >
      {statusLabel(status)}
    </span>
  );
}

function DetailPanel({
  document,
  onClose,
}: {
  document: KnowledgeDocumentDetail;
  onClose: () => void;
}) {
  return (
    <section
      aria-label="Knowledge document details"
      className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-zinc-500">
            Document details
          </p>
          <h2 className="mt-2 break-all text-lg font-semibold text-white">
            {document.filename}
          </h2>
        </div>
        <button type="button" onClick={onClose} className={buttonClassName}>
          Close
        </button>
      </div>

      <dl className="mt-6 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-zinc-500">Type</dt>
          <dd className="mt-1 uppercase text-zinc-200">
            {document.file_type}
          </dd>
        </div>
        <div>
          <dt className="text-zinc-500">Size</dt>
          <dd className="mt-1 text-zinc-200">
            {formatFileSize(document.file_size)}
          </dd>
        </div>
        <div>
          <dt className="text-zinc-500">Chunks</dt>
          <dd className="mt-1 text-zinc-200">{document.chunk_count}</dd>
        </div>
        <div>
          <dt className="text-zinc-500">Created</dt>
          <dd className="mt-1 text-zinc-200">
            {formatDate(document.created_at)}
          </dd>
        </div>
      </dl>

      {document.error && (
        <p className="mt-5 rounded-lg border border-red-900/70 bg-red-950/20 px-4 py-3 text-sm text-red-300">
          {document.error}
        </p>
      )}

      {document.chunks.length > 0 && (
        <div className="mt-6 overflow-x-auto rounded-lg border border-zinc-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-zinc-950/70 text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-3 font-medium">Chunk</th>
                <th className="px-4 py-3 font-medium">Page</th>
                <th className="px-4 py-3 font-medium">Section</th>
                <th className="px-4 py-3 font-medium">Tokens</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {document.chunks.map((chunk) => (
                <tr key={chunk.id} className="text-zinc-300">
                  <td className="px-4 py-3">{chunk.chunk_index + 1}</td>
                  <td className="px-4 py-3">{chunk.page_number ?? "-"}</td>
                  <td className="max-w-xs truncate px-4 py-3">
                    {chunk.section ?? "-"}
                  </td>
                  <td className="px-4 py-3">{chunk.token_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export default function KnowledgeBase() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [selectedDocument, setSelectedDocument] =
    useState<KnowledgeDocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [uploadingName, setUploadingName] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const loadDocuments = useCallback(async () => {
    try {
      const result = await listKnowledgeDocuments();
      setDocuments(result);
      setLoadError(null);
    } catch (error) {
      setLoadError(
        getErrorMessage(error, "Unable to load knowledge documents."),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadDocuments();
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [loadDocuments]);

  useEffect(() => {
    if (!documents.some((document) => document.status === "processing")) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void loadDocuments();
    }, 2000);

    return () => window.clearInterval(intervalId);
  }, [documents, loadDocuments]);

  async function handleFile(file: File | undefined) {
    if (!file) {
      return;
    }

    const validationError = validateSelectedFile(file);
    if (validationError) {
      setActionError(validationError);
      return;
    }

    setActionError(null);
    setUploadingName(file.name);

    try {
      const uploaded = await uploadKnowledgeDocument(file);
      setDocuments((current) => [
        uploaded,
        ...current.filter((document) => document.id !== uploaded.id),
      ]);

      if (uploaded.status === "failed") {
        setActionError(
          uploaded.error ?? "The document could not be indexed.",
        );
      }
    } catch (error) {
      setActionError(
        getErrorMessage(error, "Unable to upload knowledge document."),
      );
    } finally {
      setUploadingName(null);
    }
  }

  async function handleView(documentId: string) {
    setActionError(null);
    setBusyAction(`${documentId}:view`);

    try {
      setSelectedDocument(await getKnowledgeDocument(documentId));
    } catch (error) {
      setActionError(
        getErrorMessage(error, "Unable to load document details."),
      );
    } finally {
      setBusyAction(null);
    }
  }

  async function handleReindex(document: KnowledgeDocument) {
    setActionError(null);
    setBusyAction(`${document.id}:reindex`);
    setDocuments((current) =>
      replaceDocument(current, {
        ...document,
        status: "processing",
        error: null,
      }),
    );

    try {
      const updated = await reindexKnowledgeDocument(document.id);
      setDocuments((current) => replaceDocument(current, updated));
      if (selectedDocument?.id === updated.id) {
        setSelectedDocument(null);
      }

      if (updated.status === "failed") {
        setActionError(
          updated.error ?? "The document could not be re-indexed.",
        );
      }
    } catch (error) {
      setActionError(
        getErrorMessage(error, "Unable to re-index knowledge document."),
      );
      await loadDocuments();
    } finally {
      setBusyAction(null);
    }
  }

  async function handleDelete(document: KnowledgeDocument) {
    if (!window.confirm(`Delete ${document.filename}?`)) {
      return;
    }

    setActionError(null);
    setBusyAction(`${document.id}:delete`);

    try {
      await deleteKnowledgeDocument(document.id);
      setDocuments((current) =>
        current.filter((currentDocument) => currentDocument.id !== document.id),
      );
      if (selectedDocument?.id === document.id) {
        setSelectedDocument(null);
      }
    } catch (error) {
      setActionError(
        getErrorMessage(error, "Unable to delete knowledge document."),
      );
    } finally {
      setBusyAction(null);
    }
  }

  const uploadButton = (
    <button
      type="button"
      onClick={() => fileInputRef.current?.click()}
      disabled={Boolean(uploadingName)}
      className={primaryButtonClassName}
    >
      Upload document
    </button>
  );

  return (
    <div>
      <PageHeader
        eyebrow="Support content"
        title="Knowledge Base"
        description="Upload and manage the documents AgentDesk will use for grounded answers."
        action={
          <div className="flex flex-wrap gap-3">
            <Link
              href="/dashboard/knowledge/test"
              className={buttonClassName}
            >
              Test knowledge
            </Link>
            {uploadButton}
          </div>
        }
      />

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.txt,.md,.markdown"
        className="sr-only"
        onChange={(event) => {
          void handleFile(event.target.files?.[0]);
          event.currentTarget.value = "";
        }}
      />

      <div className="mt-8 space-y-6">
        <section
          aria-label="Document upload"
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragActive(false);
            void handleFile(event.dataTransfer.files[0]);
          }}
          className={`rounded-xl border border-dashed px-6 py-8 transition-colors ${
            dragActive
              ? "border-zinc-400 bg-zinc-900"
              : "border-zinc-700 bg-zinc-900/30"
          }`}
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-base font-semibold text-zinc-100">
                Add company documentation
              </h2>
              <p className="mt-2 text-sm leading-6 text-zinc-500">
                PDF, DOCX, TXT, and Markdown files up to 10 MB. Files are
                parsed, chunked, embedded, and indexed before they become ready.
              </p>
            </div>
            <div className="shrink-0">{uploadButton}</div>
          </div>
        </section>

        {uploadingName && (
          <LoadingState label={`Uploading and indexing ${uploadingName}...`} />
        )}

        {actionError && (
          <ErrorState
            title="Knowledge action failed"
            description={actionError}
          />
        )}

        {loading && <LoadingState label="Loading knowledge documents..." />}

        {!loading && loadError && (
          <ErrorState
            title="Knowledge Base unavailable"
            description={loadError}
            action={
              <button
                type="button"
                onClick={() => {
                  setLoading(true);
                  void loadDocuments();
                }}
                className={buttonClassName}
              >
                Try again
              </button>
            }
          />
        )}

        {!loading && !loadError && documents.length === 0 && (
          <EmptyState
            title="No knowledge documents yet"
            description="Upload company documentation so AgentDesk can answer support questions using your own knowledge."
            action={uploadButton}
          />
        )}

        {!loading && !loadError && documents.length > 0 && (
          <section
            aria-label="Knowledge documents"
            className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50"
          >
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-zinc-800 bg-zinc-950/60 text-xs uppercase tracking-wide text-zinc-500">
                  <tr>
                    <th className="px-5 py-4 font-medium">Filename</th>
                    <th className="px-5 py-4 font-medium">Type</th>
                    <th className="px-5 py-4 font-medium">Size</th>
                    <th className="px-5 py-4 font-medium">Status</th>
                    <th className="px-5 py-4 font-medium">Chunks</th>
                    <th className="px-5 py-4 font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800">
                  {documents.map((document) => {
                    const viewBusy = busyAction === `${document.id}:view`;
                    const reindexBusy =
                      busyAction === `${document.id}:reindex`;
                    const deleteBusy = busyAction === `${document.id}:delete`;
                    const rowBusy = viewBusy || reindexBusy || deleteBusy;

                    return (
                      <tr key={document.id} className="text-zinc-300">
                        <td className="max-w-xs px-5 py-4">
                          <p className="truncate font-medium text-zinc-100">
                            {document.filename}
                          </p>
                          {document.error && (
                            <p className="mt-1 truncate text-xs text-red-300">
                              {document.error}
                            </p>
                          )}
                        </td>
                        <td className="px-5 py-4 uppercase text-zinc-400">
                          {document.file_type}
                        </td>
                        <td className="whitespace-nowrap px-5 py-4 text-zinc-400">
                          {formatFileSize(document.file_size)}
                        </td>
                        <td className="px-5 py-4">
                          <DocumentStatus status={document.status} />
                        </td>
                        <td className="px-5 py-4 text-zinc-400">
                          {document.chunk_count}
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => void handleView(document.id)}
                              disabled={rowBusy}
                              className={buttonClassName}
                            >
                              {viewBusy ? "Loading..." : "View"}
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleReindex(document)}
                              disabled={rowBusy || document.status === "processing"}
                              className={buttonClassName}
                            >
                              {reindexBusy ? "Re-indexing..." : "Re-index"}
                            </button>
                            <button
                              type="button"
                              onClick={() => void handleDelete(document)}
                              disabled={rowBusy}
                              className="rounded-lg border border-red-900/70 px-4 py-2 text-sm font-medium text-red-300 transition-colors hover:border-red-700 hover:bg-red-950/30 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {deleteBusy ? "Deleting..." : "Delete"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {selectedDocument && (
          <DetailPanel
            document={selectedDocument}
            onClose={() => setSelectedDocument(null)}
          />
        )}
      </div>
    </div>
  );
}
