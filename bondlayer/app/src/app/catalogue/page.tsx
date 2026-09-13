"use client";

import { ChangeEvent, useState } from "react";
import { Failed, Loading } from "@/components/states";
import { humanise, severityTone, useReport, useSelectedMerchant } from "@/lib/api";

const FILTERS = ["all", "blocker", "degrades_match", "cosmetic", "info"] as const;

export default function CataloguePage() {
  const merchant = useSelectedMerchant();
  const { data: report, error } = useReport(merchant);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);

  const diagnostics =
    report?.diagnostics.filter((d) => filter === "all" || d.severity === filter) ?? [];

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setUploadMessage(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch("/onboard/catalog", { method: "POST", body: form });
      const body = (await response.json()) as { merchant?: string; detail?: string };
      if (!response.ok) throw new Error(body.detail ?? `Upload failed (${response.status})`);
      setUploadMessage(
        `Published ${file.name} for ${body.merchant}. Readiness and agent search are now using it.`,
      );
      window.location.reload();
    } catch (cause) {
      setUploadError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  return (
    <div className="content">
      <div className="page-heading">
        <div>
          <h1>Catalogue</h1>
          <p>
            The full remediation list for this merchant&rsquo;s export, worst first, as
            the server ordered it. The sentence in the last column is the
            merchant-facing message the server composed — it is not rewritten here.
          </p>
        </div>
        <label className="upload-button">
          <input type="file" accept=".csv,text/csv" onChange={upload} disabled={uploading} />
          {uploading ? "Processing…" : "Upload catalogue"}
        </label>
      </div>

      {uploadMessage && <p className="upload-success" role="status">{uploadMessage}</p>}
      {uploadError && <p className="upload-error" role="alert">{uploadError}</p>}
      {error && <Failed what="the merchant report" error={error} />}
      {!report && !error && <Loading what="the merchant report" />}

      {report && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Diagnostics</h2>
              <p>
                {diagnostics.length} of {report.diagnostics.length} shown ·{" "}
                {report.skus} SKUs from {report.rows_read} rows · readiness{" "}
                {report.readiness}%
              </p>
            </div>
            <div className="filter-row">
              {FILTERS.filter(
                (value) => value === "all" || value in report.by_severity,
              ).map((value) => (
                <button
                  className={`pill ${filter === value ? "success" : "neutral"}`}
                  key={value}
                  onClick={() => setFilter(value)}
                  type="button"
                >
                  {value === "all"
                    ? `All ${report.diagnostics.length}`
                    : `${humanise(value)} ${report.by_severity[value]}`}
                </button>
              ))}
            </div>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Row</th>
                  <th>SKU</th>
                  <th>Field</th>
                  <th>Rule</th>
                  <th>Found</th>
                  <th>Normalised</th>
                  <th>Severity</th>
                  <th>What an agent does with it</th>
                </tr>
              </thead>
              <tbody>
                {diagnostics.map((diagnostic, index) => (
                  <tr key={`${diagnostic.row}-${diagnostic.field}-${index}`}>
                    <td>{diagnostic.row}</td>
                    <td>
                      <code>{diagnostic.sku_id}</code>
                    </td>
                    <td>
                      <code>{diagnostic.field}</code>
                    </td>
                    <td>
                      <code>{diagnostic.rule}</code>
                    </td>
                    <td>{diagnostic.found || "—"}</td>
                    <td>
                      {diagnostic.normalised ? (
                        <span>
                          {diagnostic.normalised}
                          {diagnostic.autofixed && <b className="fixed-flag"> autofixed</b>}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      <span className={`pill ${severityTone(diagnostic.severity)}`}>
                        {humanise(diagnostic.severity)}
                      </span>
                    </td>
                    <td>{diagnostic.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
