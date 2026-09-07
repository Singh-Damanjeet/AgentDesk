"use client";

import type { FormEvent } from "react";
import { useState } from "react";
import Link from "next/link";

import PageHeader from "@/components/dashboard/page-header";
import ErrorState from "@/components/ui/error-state";
import LoadingState from "@/components/ui/loading-state";
import {
  queryRAG,
  type RAGResponse,
  type RAGSource,
} from "@/lib/api";

const MAX_QUESTION_LENGTH = 2000;

const secondaryButtonClassName =
  "rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-100 transition-colors hover:border-zinc-500 hover:bg-zinc-900 disabled:cursor-not-allowed disabled:opacity-50";

const primaryButtonClassName =
  "rounded-lg bg-white px-5 py-2.5 text-sm font-medium text-zinc-950 transition-colors hover:bg-zinc-200 disabled:cursor-not-allowed disabled:opacity-50";

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function formatSourceLocation(source: RAGSource): string {
  const location =
    source.page !== null
      ? `Page ${source.page}`
      : source.section
        ? source.section
        : "Location unavailable";

  return `${source.document_name} · ${location} · ${source.score.toFixed(2)}`;
}

function formatChunkLocation(
  page: number | null,
  section: string | null,
): string {
  if (page !== null) {
    return `Page ${page}`;
  }

  return section ?? "Location unavailable";
}

function AnswerPanel({ result }: { result: RAGResponse }) {
  return (
    <section
      aria-label="RAG answer"
      aria-live="polite"
      className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-zinc-100">Answer</h2>
        <span className="text-sm text-zinc-500">{result.latency_ms} ms</span>
      </div>

      <p
        className={`mt-5 whitespace-pre-wrap text-sm leading-7 ${
          result.insufficient_evidence
            ? "text-amber-200"
            : "text-zinc-200"
        }`}
      >
        {result.answer}
      </p>

      <p className="mt-5 text-xs text-zinc-600">Trace ID: {result.trace_id}</p>
    </section>
  );
}

function SourcesPanel({ result }: { result: RAGResponse }) {
  return (
    <section
      aria-label="Retrieved sources"
      className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6"
    >
      <h2 className="text-lg font-semibold text-zinc-100">Sources</h2>

      {result.sources.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">
          No sufficiently relevant sources were found.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {result.sources.map((source) => (
            <li
              key={source.chunk_id}
              className="rounded-lg border border-zinc-800 bg-zinc-950/60 px-4 py-3"
            >
              <p className="text-sm font-medium text-zinc-200">
                {formatSourceLocation(source)}
              </p>
              <p className="mt-1 text-xs text-zinc-600">
                Chunk {source.chunk_id}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function RetrievedChunksPanel({ result }: { result: RAGResponse }) {
  return (
    <section
      aria-label="Retrieved chunks"
      className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-zinc-100">
            Retrieved chunks
          </h2>
          <p className="mt-1 text-sm text-zinc-500">
            Raw evidence used for this test query.
          </p>
        </div>
        <span className="text-sm text-zinc-500">
          {result.retrieved_chunks.length} chunks
        </span>
      </div>

      {result.retrieved_chunks.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500">
          No chunks were included in the answer context.
        </p>
      ) : (
        <div className="mt-5 space-y-4">
          {result.retrieved_chunks.map((chunk) => (
            <article
              key={chunk.chunk_id}
              className="rounded-lg border border-zinc-800 bg-zinc-950/60 p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-zinc-500">
                <span className="font-medium text-zinc-300">
                  {chunk.document_name}
                </span>
                <span>Score: {chunk.score.toFixed(2)}</span>
              </div>
              <p className="mt-2 text-xs text-zinc-600">
                Chunk {chunk.chunk_id} ·{" "}
                {formatChunkLocation(chunk.page, chunk.section)}
              </p>
              <p className="mt-4 whitespace-pre-wrap text-sm leading-6 text-zinc-300">
                {chunk.content}
              </p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

export default function RAGTestConsole() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<RAGResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuestion = question.trim();

    if (!normalizedQuestion) {
      setError("Enter a question before asking AgentDesk.");
      setResult(null);
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      setResult(await queryRAG({ question: normalizedQuestion }));
    } catch (requestError) {
      setError(
        getErrorMessage(requestError, "Unable to query the knowledge base."),
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Knowledge Base"
        title="Test Knowledge"
        description="Ask a single grounded question and inspect the answer, citations, and retrieved evidence."
        action={
          <Link
            href="/dashboard/knowledge"
            className={secondaryButtonClassName}
          >
            Back to Knowledge Base
          </Link>
        }
      />

      <div className="mt-8 space-y-6">
        <form
          onSubmit={handleSubmit}
          aria-busy={loading}
          className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-6"
        >
          <label
            htmlFor="rag-question"
            className="text-sm font-medium text-zinc-200"
          >
            Ask AgentDesk a question
          </label>
          <textarea
            id="rag-question"
            name="question"
            value={question}
            onChange={(event) => {
              setQuestion(event.target.value);
              setError(null);
            }}
            maxLength={MAX_QUESTION_LENGTH}
            rows={4}
            placeholder="How long do customers have to request a refund?"
            className="mt-3 w-full resize-y rounded-lg border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm leading-6 text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-zinc-500"
          />
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-zinc-600">
              {question.length}/{MAX_QUESTION_LENGTH} characters
            </p>
            <button
              type="submit"
              disabled={loading}
              className={primaryButtonClassName}
            >
              {loading ? "Asking..." : "Ask"}
            </button>
          </div>
        </form>

        {loading && (
          <LoadingState label="Retrieving evidence and generating an answer..." />
        )}

        {error && (
          <ErrorState title="RAG query failed" description={error} />
        )}

        {result && (
          <div className="space-y-6">
            <AnswerPanel result={result} />
            <SourcesPanel result={result} />
            <RetrievedChunksPanel result={result} />
          </div>
        )}
      </div>
    </div>
  );
}
