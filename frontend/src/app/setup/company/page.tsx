"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import {
  getCompanySettings,
  updateCompanySettings,
} from "@/lib/api";


export default function CompanySetupPage() {
  const router = useRouter();

  const [name, setName] = useState("");
  const [website, setWebsite] = useState("");
  const [industry, setIndustry] = useState("");
  const [supportName, setSupportName] = useState("");
  const [defaultLanguage, setDefaultLanguage] = useState("en");
  const [timezone, setTimezone] = useState("UTC");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);


  useEffect(() => {
    async function loadCompany() {
      try {
        const company = await getCompanySettings();

        if (company) {
          setName(company.name);
          setWebsite(company.website ?? "");
          setIndustry(company.industry ?? "");
          setSupportName(company.support_name ?? "");
          setDefaultLanguage(company.default_language);
          setTimezone(company.timezone);
        }
      } catch {
        setError("Unable to load existing company settings.");
      } finally {
        setLoading(false);
      }
    }

    loadCompany();
  }, []);


  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setSaving(true);
    setError(null);

    try {
      await updateCompanySettings({
        name,
        website: website || null,
        industry: industry || null,
        support_name: supportName || null,
        default_language: defaultLanguage,
        timezone,
      });

      router.push("/setup/ai-provider");
    } catch {
      setError("Unable to save company settings.");
    } finally {
      setSaving(false);
    }
  }


  if (loading) {
    return (
      <main className="min-h-screen bg-zinc-950 text-white">
        <div className="mx-auto max-w-3xl px-6 py-20">
          <p className="text-zinc-400">Loading company settings...</p>
        </div>
      </main>
    );
  }


  return (
    <main className="min-h-screen bg-zinc-950 text-white">
      <div className="mx-auto max-w-3xl px-6 py-20">
        <p className="text-sm text-zinc-500">
          Step 2 of 5
        </p>

        <h1 className="mt-3 text-3xl font-semibold">
          Company
        </h1>

        <p className="mt-3 text-zinc-400">
          Tell AgentDesk who it will be supporting.
        </p>

        <form
          onSubmit={handleSubmit}
          className="mt-10 space-y-6"
        >
          <div>
            <label className="text-sm text-zinc-300">
              Company name *
            </label>

            <input
              required
              value={name}
              onChange={(event) => setName(event.target.value)}
              className="mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 outline-none focus:border-zinc-600"
              placeholder="Acme Inc."
            />
          </div>

          <div>
            <label className="text-sm text-zinc-300">
              Website
            </label>

            <input
              value={website}
              onChange={(event) => setWebsite(event.target.value)}
              className="mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 outline-none focus:border-zinc-600"
              placeholder="https://example.com"
            />
          </div>

          <div>
            <label className="text-sm text-zinc-300">
              Industry
            </label>

            <input
              value={industry}
              onChange={(event) => setIndustry(event.target.value)}
              className="mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 outline-none focus:border-zinc-600"
              placeholder="Software"
            />
          </div>

          <div>
            <label className="text-sm text-zinc-300">
              Support name
            </label>

            <input
              value={supportName}
              onChange={(event) => setSupportName(event.target.value)}
              className="mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 outline-none focus:border-zinc-600"
              placeholder="Acme Support"
            />
          </div>

          <div className="grid gap-6 sm:grid-cols-2">
            <div>
              <label className="text-sm text-zinc-300">
                Default language
              </label>

              <input
                value={defaultLanguage}
                onChange={(event) =>
                  setDefaultLanguage(event.target.value)
                }
                className="mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 outline-none focus:border-zinc-600"
              />
            </div>

            <div>
              <label className="text-sm text-zinc-300">
                Timezone
              </label>

              <input
                value={timezone}
                onChange={(event) =>
                  setTimezone(event.target.value)
                }
                className="mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-3 outline-none focus:border-zinc-600"
              />
            </div>
          </div>

          {error && (
            <div className="rounded-lg border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
              {error}
            </div>
          )}

          <div className="flex items-center justify-between pt-4">
            <button
              type="button"
              onClick={() => router.push("/setup")}
              className="rounded-lg border border-zinc-700 px-5 py-3 text-zinc-300"
            >
              Back
            </button>

            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-white px-5 py-3 font-medium text-black disabled:opacity-50"
            >
              {saving ? "Saving..." : "Continue"}
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}