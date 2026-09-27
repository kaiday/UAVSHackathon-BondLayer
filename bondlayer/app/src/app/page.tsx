"use client";

import Link from "next/link";
import { BarList, ChartCard, Donut, SERIES } from "@/components/charts";
import { ComparisonStrip } from "@/components/merchant-switcher";
import { Failed, Loading } from "@/components/states";
import { humanise, severityTone, useReport, useSelectedMerchant } from "@/lib/api";
import { useShoppingInsights, type ShoppingInsights } from "@/lib/insights";

const SEVERITY_ORDER = ["blocker", "degrades_match", "cosmetic", "info"] as const;

function ShoppingSummary({ data }: { data: ShoppingInsights }) {
  const metrics = data.metrics;
  const total = metrics.requests;
  const checkout = Math.min(metrics.checkout_confirmations, total);
  const selectedOnly = Math.max(0, Math.min(metrics.selected, total) - checkout);
  const competitor = Math.max(0, Math.min(metrics.selection_known - metrics.selected, total - checkout - selectedOnly));
  const unknown = Math.max(0, total - checkout - selectedOnly - competitor);
  const share = (value: number) => total ? Math.round((value / total) * 100) : 0;
  const funnel = [
    { label: "Requests", value: total, color: SERIES[0] },
    { label: "Offer shown", value: metrics.with_offers, color: SERIES[1] },
    { label: "Agent selected", value: metrics.selected, color: SERIES[2] },
    { label: "Checkout confirmed", value: metrics.checkout_confirmations, color: SERIES[3] },
  ];
  const outcomes = [
    { label: "Checked out", value: checkout, color: SERIES[0] },
    { label: "Selected only", value: selectedOnly, color: SERIES[1] },
    { label: "Competitor chosen", value: competitor, color: SERIES[2] },
    { label: "Unknown / no offer", value: unknown, color: SERIES[3] },
  ];
  const opportunities = data.opportunities.slice(0, 3).map((item) => ({
    label: item.title,
    value: item.requests,
  }));

  return (
    <section className="overview-insights" aria-labelledby="shopping-summary-title">
      <div className="overview-insights-heading">
        <div>
          <h2 id="shopping-summary-title">Shopping summary</h2>
          <p>Last 30 days · with published benefits{data.coverage.demo_requests ? " · demo activity (simulated dates)" : ""}</p>
        </div>
        <Link href="/requests">View shopping insights →</Link>
      </div>
      <div className="overview-insights-grid">
        <ChartCard className="overview-insight-card" title="Shopping funnel" subtitle="Where requests progress or drop away"
          table={{ columns: ["Stage", "Requests", "Share"], rows: funnel.map((item) => [item.label, item.value, `${share(item.value)}%`]) }}>
          <ol className="overview-funnel">
            {funnel.map((item) => (
              <li key={item.label}>
                <div><span>{item.label}</span><strong>{item.value}</strong></div>
                <span className="overview-funnel-track"><i style={{ width: `${share(item.value)}%`, background: item.color }} /></span>
              </li>
            ))}
          </ol>
        </ChartCard>

        <ChartCard className="overview-insight-card" title="Request outcomes" subtitle="What agents did after comparing"
          table={{ columns: ["Outcome", "Requests", "Share"], rows: outcomes.map((item) => [item.label, item.value, `${share(item.value)}%`]) }}>
          <Donut slices={outcomes} centerLabel="requests" />
        </ChartCard>

        <ChartCard className="overview-insight-card" title="Top missed opportunities" subtitle="Issues ranked by requests affected"
          table={{ columns: ["Opportunity", "Requests"], rows: opportunities.map((item) => [item.label, item.value]) }}>
          <BarList items={opportunities} limit={3} color={SERIES[1]} />
        </ChartCard>
      </div>
    </section>
  );
}

export default function Home() {
  const merchant = useSelectedMerchant();
  const { data: report, error } = useReport(merchant);
  const { data: insights } = useShoppingInsights(merchant, 30, "enabled");

  return (
    <div className="content">
      <ComparisonStrip report={report} />

      {error && <Failed what="the merchant report" error={error} />}
      {!report && !error && <Loading what="the merchant report" />}

      {report && (
        <>
          {insights && <ShoppingSummary data={insights} />}

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
