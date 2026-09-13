"use client";

import Link from "next/link";
import { BannerCarousel } from "@/components/banner-carousel";
import { ComparisonStrip } from "@/components/merchant-switcher";
import { Failed, Loading } from "@/components/states";
import { humanise, severityTone, useReport, useSelectedMerchant } from "@/lib/api";

const SEVERITY_ORDER = ["blocker", "degrades_match", "cosmetic", "info"] as const;

export default function Home() {
  const merchant = useSelectedMerchant();
  const { data: report, error } = useReport(merchant);

  return (
    <div className="content">
      <BannerCarousel />

      <div className="page-heading">
        <div>
          <h1>Overview</h1>
          <p>Issues that stop AI shopping agents from finding your products.</p>
        </div>
      </div>

      <ComparisonStrip />

      {error && <Failed what="the merchant report" error={error} />}
      {!report && !error && <Loading what="the merchant report" />}

      {report && (
        <>
          <section className="stat-strip" aria-label="Readiness detail">
            <div className="stat" data-tour="readiness"><span>Agent readiness</span><strong>{report.readiness}%</strong></div>
            <div className="stat"><span>Rows rejected</span><strong>{report.rows_rejected}</strong></div>
            <div className="stat"><span>Auto-fixed</span><strong>{report.attributes_fixed}</strong></div>
            <div className="stat"><span>Issues</span><strong>{report.diagnostics.length}</strong></div>
          </section>

          <section className="dashboard-grid">
            <div className="dashboard-primary">
              <article className="panel" data-tour="worst-first">
                <div className="panel-heading">
                  <div>
                    <h2>Top issues</h2>
                    <p>Most severe first</p>
                  </div>
                  <Link className="pill neutral" href="/catalogue">
                    See all {report.diagnostics.length} →
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
                        <th>What to do</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.diagnostics.slice(0, 5).map((diagnostic, index) => (
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
                  <h2>By issue type</h2>
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
