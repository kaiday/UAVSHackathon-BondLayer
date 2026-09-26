"use client";

import { ChangeEvent, useState } from "react";
import { Failed, Loading } from "@/components/states";
import { humanise, refreshMerchants, severityTone, uploadCatalogue, useReport, useSelectedMerchant } from "@/lib/api";

const FILTERS = ["all", "blocker", "degrades_match", "cosmetic", "info"] as const;

export default function CataloguePage() {
  const merchant = useSelectedMerchant();
  const { data: report, error, reload } = useReport(merchant);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);

  const diagnostics =
    report?.diagnostics.filter((d) => filter === "all" || d.severity === filter) ?? [];

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.target;
    const file = input.files?.[0];
    if (!file || !merchant) return;
    setUploading(true);
    setUploadError(null);
    setUploadMessage(null);
    try {
      await uploadCatalogue(file, { merchant });
      setUploadMessage(
        `Catalogue updated from ${file.name}.`,
      );
      reload();
      refreshMerchants();
    } catch (cause) {
      setUploadError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setUploading(false);
      input.value = "";
    }
  }

  return (
    <div className="content">
      <div className="page-heading">
        <div>
          <h1>Catalogue</h1>
          <p>Every issue in your catalogue. Fix blockers first.</p>
        </div>
        <label className="upload-button">
          <input type="file" aria-label="Replace catalogue" accept=".csv,text/csv" onChange={upload} disabled={uploading || !merchant} />
          {uploading ? "Processing…" : "Replace catalogue"}
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
              <h2>Issues</h2>
              <p>
                Showing {diagnostics.length} of {report.diagnostics.length}
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
                  <th>Issue</th>
                  <th>Current</th>
                  <th>Fixed to</th>
                  <th>Severity</th>
                  <th>What to do</th>
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
                          {diagnostic.autofixed && <b className="fixed-flag"> auto</b>}
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
