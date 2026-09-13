"use client";

import { useState } from "react";
import { ClipboardList } from "lucide-react";
import { Failed, Loading } from "@/components/states";
import {
  humanise,
  money,
  percent,
  useRequestReport,
  useRequests,
  type MerchantRow,
} from "@/lib/api";

/**
 * "Why we lost", per merchant, per request — a projection of the RequestReport
 * the server returns from /onboard/requests and /onboard/requests/{id}. The
 * four figures and the sentence are the server's; this page lays them out.
 */
function MerchantCard({ row }: { row: MerchantRow }) {
  return (
    <article className={`merchant-card ${row.won ? "won" : ""}`}>
      <header>
        <div>
          <strong>{humanise(row.merchant)}</strong>
          {row.control_merchant && <span className="pill neutral">control</span>}
        </div>
        <span className={`pill ${row.won ? "success" : "danger"}`}>
          {row.won ? "won" : "lost"}
        </span>
      </header>

      <dl className="figure-grid">
        <div>
          <dt>Fields exposed</dt>
          <dd>{row.fields_exposed}</dd>
        </div>
        <div>
          <dt>Legible share</dt>
          <dd>{percent(row.legible_share)}</dd>
        </div>
        <div>
          <dt>Verified value credited</dt>
          <dd className="money-pill">{money(row.value_credited_aud)}</dd>
        </div>
        <div>
          <dt>Value withheld</dt>
          <dd className="money-pill withheld">{money(row.value_withheld_aud)}</dd>
        </div>
      </dl>

      {row.sku_id && (
        <p className="offer-line">
          <code>{row.sku_id}</code> shelf {money(row.shelf_price)} → effective{" "}
          <b className="money-pill">{money(row.effective_cost)}</b>
        </p>
      )}

      {row.lost_because && <p className="lost-because">{row.lost_because}</p>}

      {row.unsatisfied.length > 0 && (
        <ul className="unsatisfied">
          {row.unsatisfied.map((clause) => (
            <li key={clause}>
              {clause} <span>← no catalogue attribute answers this</span>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export default function RequestsPage() {
  const { data: requests, error: listError } = useRequests();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const activeId = selectedId ?? requests?.[0]?.request_id ?? null;
  const { data: report, error: reportError } = useRequestReport(activeId);

  return (
    <div className="content request-page">
      <div className="page-heading">
        <div>
          <h1>Request console</h1>
          <p>
            Available request reports from <code>GET /onboard/requests</code> and{" "}
            <code>GET /onboard/requests/{"{id}"}</code>.
          </p>
        </div>
      </div>

      {listError && <Failed what="the request list" error={listError} />}
      {!requests && !listError && <Loading what="the request list" />}

      {requests?.length === 0 && <section className="panel"><div className="panel-heading"><div><h2>No request history</h2><p>This workspace has no saved request reports. The buyer-agent page shows live comparisons; recording them here is not yet connected.</p></div></div></section>}

      {requests && requests.length > 0 && (
        <div className="request-console">
          <aside className="request-inbox">
            <header>
              <div>
                <h2 className="request-heading-title">
                  <span className="section-icon">
                    <ClipboardList size={17} strokeWidth={2.2} />
                  </span>
                  Request reports
                </h2>
                <p>{requests.length} reports</p>
              </div>
            </header>
            <div className="request-items">
              {requests.map((request) => {
                const winner = request.merchants.find((m) => m.won);
                return (
                  <button
                    className={request.request_id === activeId ? "selected" : ""}
                    key={request.request_id}
                    onClick={() => setSelectedId(request.request_id)}
                    type="button"
                  >
                    <span className="request-row">
                      <strong>{request.request_id}</strong>
                    </span>
                    <span className="request-summary">{request.utterance}</span>
                    <span className={`pill ${winner ? "success" : "neutral"}`}>
                      {winner ? `${humanise(winner.merchant)} won` : "no winner"}
                    </span>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="request-detail">
            <header>
              <div>
                <h2>Request explanation</h2>
                <p>{activeId}</p>
              </div>
            </header>

            {reportError && <Failed what="this request" error={reportError} />}
            {!report && !reportError && <Loading what="this request" />}

            {report && (
              <div className="request-detail-body" key={report.request_id}>
                <blockquote>&ldquo;{report.utterance}&rdquo;</blockquote>

                <div className="intent-tags">
                  {report.constraints.map((constraint, index) => (
                    <span key={`${constraint.text}-${index}`}>
                      {humanise(constraint.kind)} · {constraint.text}
                    </span>
                  ))}
                </div>

                <h3 className="section-title">With BondLayer records</h3>
                <div className="merchant-cards">
                  {report.merchants.map((row) => (
                    <MerchantCard key={`bond-${row.merchant}`} row={row} />
                  ))}
                </div>

                <h3 className="section-title">
                  Control — same catalogue, no verified records
                </h3>
                <div className="merchant-cards">
                  {report.control.map((row) => (
                    <MerchantCard key={`control-${row.merchant}`} row={row} />
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
