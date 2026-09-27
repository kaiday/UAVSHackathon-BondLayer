"use client";

import { ChangeEvent, useState } from "react";
import { Download } from "lucide-react";
import { Failed, Loading } from "@/components/states";
import { CurrentMerchant } from "@/components/merchant-switcher";
import { humanise, refreshMerchants, severityTone, uploadCatalogue, useReport, useSelectedMerchant, type CatalogueUpload } from "@/lib/api";

const FILTERS = ["all", "blocker", "degrades_match", "cosmetic", "info"] as const;

export default function CataloguePage() {
  const merchant = useSelectedMerchant();
  const { data: report, error, reload } = useReport(merchant);
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("all");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [addition, setAddition] = useState<{ file: File; merchant: string; preview: CatalogueUpload } | null>(null);

  async function addProducts(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !merchant) return;
    setUploading(true);
    setAddition(null);
    setUploadError(null);
    setUploadMessage(null);
    try {
      const preview = await uploadCatalogue(file, { merchant, append: true, preview: true });
      setAddition({ file, merchant, preview });
    } catch (cause) {
      setUploadError(cause instanceof Error ? cause.message : String(cause));
    } finally { setUploading(false); }
  }

  async function publishAddition() {
    if (!addition || addition.merchant !== merchant) return;
    setUploading(true);
    setUploadError(null);
    try {
      const result = await uploadCatalogue(addition.file, { merchant: addition.merchant, append: true, revision: addition.preview.revision });
      setUploadMessage(`${result.added_rows} products added. Your existing products are retained.`);
      setAddition(null);
      reload();
      refreshMerchants();
    } catch (cause) {
      setAddition(null);
      setUploadError(cause instanceof Error ? cause.message : String(cause));
    } finally { setUploading(false); }
  }

  const diagnostics =
    report?.diagnostics.filter((d) => filter === "all" || d.severity === filter) ?? [];

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.target;
    const file = input.files?.[0];
    if (!file || !merchant) return;
    setUploading(true);
    setAddition(null);
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
      <div className="page-action-row catalogue-actions">
        <div className="catalogue-merchant-heading"><CurrentMerchant /></div>
        <a className="upload-button secondary-action catalogue-download" href="/onboard/catalog/template" download aria-label="Download CSV template" title="Download CSV template"><Download size={18} aria-hidden="true" /></a>
        <label className="upload-button secondary-action">
          <input type="file" aria-label="Replace catalogue" accept=".csv,text/csv" onChange={upload} disabled={uploading || !merchant} />
          {uploading ? "Processing…" : "Replace catalogue"}
        </label>
        <label className={`upload-button ${addition && addition.merchant === merchant ? "secondary-action" : ""}`}>
          <input type="file" aria-label="Add products CSV" accept=".csv,text/csv" onChange={addProducts} disabled={uploading || !merchant} />
          {uploading ? "Processing…" : "Add products"}
        </label>
      </div>

      {addition && addition.merchant === merchant && <section className="panel" aria-label="Review added products">
        <div className="panel-heading"><div><h2>Review added products</h2><p>{addition.file.name} · {addition.preview.added_rows} new products · {addition.preview.report.skus} total products · {addition.preview.report.readiness}% ready</p><p>Existing products are retained. No missing or duplicate SKUs found.</p></div></div>
        {addition.preview.report.diagnostics.length > 0 && <div className="table-wrap"><table><thead><tr><th>SKU</th><th>Severity</th><th>What to do</th></tr></thead><tbody>{addition.preview.report.diagnostics.slice(0, 12).map((d, i) => <tr key={i}><td>{d.sku_id}</td><td>{humanise(d.severity)}</td><td>{d.message}</td></tr>)}</tbody></table></div>}
        <div className="page-action-row catalogue-actions catalogue-review-actions"><button type="button" className="upload-button secondary-action" disabled={uploading} onClick={() => setAddition(null)}>Cancel</button><button type="button" className="upload-button" disabled={uploading} onClick={publishAddition}>{uploading ? "Publishing…" : "Publish changes"}</button></div>
      </section>}

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
                  className={`filter-pill ${filter === value ? "active" : ""}`}
                  key={value}
                  onClick={() => setFilter(value)}
                  type="button"
                  aria-pressed={filter === value}
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
