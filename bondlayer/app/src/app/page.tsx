"use client";

import Link from "next/link";
import { ComparisonStrip } from "@/components/merchant-switcher";
import { Failed, Loading } from "@/components/states";
import { humanise, severityTone, useReport, useSelectedMerchant } from "@/lib/api";

const SEVERITY_ORDER = ["blocker", "degrades_match", "cosmetic", "info"] as const;

export default function Home() {
  const merchant = useSelectedMerchant();
  const { data: report, error } = useReport(merchant);

  return (
    <div className="content">
      <div className="page-heading">
        <div>
          <h1>Catalogue readiness</h1>
          <p>
            What a shopping agent can read in this merchant&rsquo;s export, and what it
            cannot. Every figure on this page comes from{" "}
            <code>GET /onboard/report/{merchant ?? "…"}</code>.
          </p>
        </div>
      </div>

      <ComparisonStrip />

      {error && <Failed what="the merchant report" error={error} />}
      {!report && !error && <Loading what="the merchant report" />}

      {report && (
        <>
          <section className="metrics" aria-label="Readiness detail">
            <article className="metric">
              <p>Agent readiness</p>
              <strong>{report.readiness}%</strong>
              <div className="metric-trend">
                <small>{report.skus} SKUs from {report.rows_read} rows</small>
              </div>
            </article>
            <article className="metric">
              <p>Rows rejected</p>
              <strong>{report.rows_rejected}</strong>
              <div className="metric-trend">
                <small>Unparseable, never served to an agent</small>
              </div>
            </article>
            <article className="metric">
              <p>Attributes normalised</p>
              <strong>{report.attributes_fixed}</strong>
              <div className="metric-trend">
                <small>Repaired on read, provenance kept</small>
              </div>
            </article>
            <article className="metric">
              <p>Diagnostics</p>
              <strong>{report.diagnostics.length}</strong>
              <div className="metric-trend">
                <small>{report.by_severity.blocker ?? 0} of them blockers</small>
              </div>
            </article>
          </section>

          <section className="dashboard-grid">
            <div className="dashboard-primary">
              <article className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Worst first</h2>
                    <p>
                      Blocker → degrades match → cosmetic → info, then by row. The
                      server sorts this; the console does not reorder it.
                    </p>
                  </div>
                  <Link className="pill neutral" href="/catalogue">
                    All {report.diagnostics.length} →
                  </Link>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Row</th>
                        <th>SKU</th>
                        <th>Field</th>
                        <th>Severity</th>
                        <th>What an agent does with it</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.diagnostics.slice(0, 12).map((diagnostic, index) => (
                        <tr key={`${diagnostic.row}-${diagnostic.field}-${index}`}>
                          <td>{diagnostic.row}</td>
                          <td>
                            <code>{diagnostic.sku_id}</code>
                          </td>
                          <td>
                            <code>{diagnostic.field}</code>
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
              </article>
            </div>

            <article className="panel reasons">
              <div className="panel-heading">
                <div>
                  <h2>By severity</h2>
                  <p>Every diagnostic this export produced</p>
                </div>
              </div>
              <div className="reason-list">
                {SEVERITY_ORDER.filter((severity) => severity in report.by_severity).map(
                  (severity) => (
                    <div key={severity}>
                      <span>{report.by_severity[severity]}</span>
                      <p>
                        <strong>{humanise(severity)}</strong>
                      </p>
                    </div>
                  ),
                )}
              </div>

              <div className="panel-heading secondary-heading">
                <div>
                  <h2>By rule</h2>
                  <p>Which check fired, and how often</p>
                </div>
              </div>
              <div className="rule-list">
                {Object.entries(report.by_rule)
                  .sort((a, b) => b[1] - a[1])
                  .map(([rule, count]) => (
                    <div key={rule}>
                      <code>{rule}</code>
                      <b>{count}</b>
                    </div>
                  ))}
              </div>
            </article>
          </section>
        </>
      )}
    </div>
  );
}
