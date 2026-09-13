"use client";

import { ComparisonStrip } from "@/components/merchant-switcher";
import { Failed, Loading } from "@/components/states";
import { humanise, severityTone, useReport, useSelectedMerchant } from "@/lib/api";

/**
 * The same diagnostics as /catalogue, rolled up by rule: which check fires
 * most, and the worst example the server recorded for it. Nothing is counted
 * here that the server did not count.
 */
export default function QualityPage() {
  const merchant = useSelectedMerchant();
  const { data: report, error } = useReport(merchant);

  const byRule = report
    ? Object.entries(report.by_rule)
        .filter(([, count]) => count > 0)
        .map(([rule, count]) => ({
          rule,
          count,
          worst: report.diagnostics.find((d) => d.rule === rule) ?? null,
        }))
        .sort((a, b) => b.count - a.count)
    : [];

  return (
    <div className="content">
      <div className="page-heading">
        <div>
          <h1>Data quality</h1>
          <p>Issues grouped by type. Fix one type to clear every row it affects.</p>
        </div>
      </div>

      <ComparisonStrip />

      {error && <Failed what="the merchant report" error={error} />}
      {!report && !error && <Loading what="the merchant report" />}

      {report && (
        <>
          <div className="metrics compact-metrics">
            <article className="metric">
              <p>Agent readiness</p>
              <strong>{report.readiness}%</strong>
            </article>
            <article className="metric">
              <p>Products live</p>
              <strong className="fraction-value">
                <span className="metric-main">{report.skus}</span>
                <span className="metric-denominator">/ {report.rows_read}</span>
              </strong>
              <span>of rows uploaded</span>
            </article>
            <article className="metric">
              <p>Blockers</p>
              <strong>{report.by_severity.blocker ?? 0}</strong>
              <span>Hidden from agent filters</span>
            </article>
            <article className="metric">
              <p>Auto-fixed</p>
              <strong>{report.attributes_fixed}</strong>
              <span>Values cleaned on upload</span>
            </article>
          </div>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>Issue types</h2>
                <p>Most rows first</p>
              </div>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Issue</th>
                    <th>Rows</th>
                    <th>Severity</th>
                    <th>Example</th>
                    <th>What to do</th>
                  </tr>
                </thead>
                <tbody>
                  {byRule.map(({ rule, count, worst }) => (
                    <tr key={rule}>
                      <td>
                        <code>{rule}</code>
                      </td>
                      <td>{count}</td>
                      <td>
                        {worst ? (
                          <span className={`pill ${severityTone(worst.severity)}`}>
                            {humanise(worst.severity)}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>
                        {worst ? (
                          <span>
                            <code>{worst.sku_id}</code> · {worst.field} ={" "}
                            {worst.found || "—"}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td>{worst ? worst.message : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
