"use client";

import { useState } from "react";

const requests = [
  { id: "REQ-0017", agent: "buyer-agent.demo", age: "Just now", summary: "Laptop under $1,600 · painless returns", status: "Ranking changed", tone: "success", title: "Laptop with painless returns", latency: "184 ms", quote: "A laptop under $1,600 — I’d rather pay a bit more if the returns are genuinely painless.", tags: ["Hard filter · ≤ $1,600", "Product · laptop", "Service · painless returns", "Preference · pay slightly more"], stages: [["01 · Intent", "4 constraints decoded"], ["02 · Exposure", "5 signed records served"], ["03 · Valuation", "$257.03 credited"], ["04 · Outcome", "Voltway ranked #1"]], products: ["Voltway Surface Laptop Go 3 · $1,142.96", "NorthGear Surface Laptop Go 3 · $1,099.00", "CityCircuit Surface Laptop Go 3 · $1,066.00"], reasons: ["Warranty credit capped at $74.50", "Unsigned claims were displayed but valued at $0", "CityCircuit lost $46.66 of unexpressed value"] },
  { id: "REQ-9238", agent: "travel-agent.ai", age: "24 min ago", summary: "Flight-safe power bank under $70", status: "Clarification needed", tone: "warning", title: "Flight-safe portable power", latency: "162 ms", quote: "Find a carry-on safe power bank below $70 with enough capacity for a full travel day.", tags: ["Hard filter · ≤ $70", "Product · power bank", "Safety · carry-on", "Capacity · 10,000 mAh"], stages: [["01 · Intent", "4 constraints decoded"], ["02 · Exposure", "3 records served"], ["03 · Valuation", "$0 credited"], ["04 · Outcome", "More data needed"]], products: ["Voltway Ridge 10K · $64.95", "NorthGear AirCell 10K · $59.00", "CityCircuit TravelPack · $67.50"], reasons: ["Battery energy in Wh is missing", "Capacity alone cannot prove flight safety", "Add a signed battery_energy_wh field"] },
  { id: "REQ-9229", agent: "buyer-agent.demo", age: "1 hr ago", summary: "Travel adapter for Europe and UK", status: "Incomplete match", tone: "danger", title: "Adapter for Europe and the UK", latency: "201 ms", quote: "I need one compact adapter that works in both Europe and the UK and includes USB-C charging.", tags: ["Region · Europe + UK", "Product · adapter", "Port · USB-C", "Preference · compact"], stages: [["01 · Intent", "4 constraints decoded"], ["02 · Exposure", "2 records served"], ["03 · Valuation", "$18 credited"], ["04 · Outcome", "Partial match"]], products: ["Voltway Universal Travel Adapter · $52.00", "NorthGear World Plug · $49.95"], reasons: ["Supported plug types are incomplete", "UK compatibility is not signed", "Map EU and UK plug standards explicitly"] },
];

export default function RequestsPage() {
  const [selectedId, setSelectedId] = useState(requests[0].id);
  const request = requests.find((item) => item.id === selectedId) ?? requests[0];

  return (
    <div className="content request-page">
      <div className="page-heading">
        <div><h1>Request console</h1><p>See why an agent selected, rejected or questioned an offer.</p></div>
        <div className="actions"><button type="button">Export log</button></div>
      </div>

      <div className="request-console">
        <aside className="request-inbox">
          <header><div><h2>Evaluation requests</h2><p>30 frozen scenarios · seeded state</p></div><span className="pill success">Run complete</span></header>
          <div className="request-items">
            {requests.map((item) => (
              <button className={item.id === selectedId ? "selected" : ""} key={item.id} onClick={() => setSelectedId(item.id)} type="button">
                <span className="request-row"><strong>{item.id}</strong><small>{item.age}</small></span>
                <span className="request-summary">{item.summary}</span>
                <span className={`pill ${item.tone}`}>{item.status}</span>
              </button>
            ))}
          </div>
        </aside>

        <section className="request-detail">
          <header><div><h2>Request explanation</h2><p>{request.id} · {request.agent} · verified</p></div><span className={`pill ${request.tone}`}>{request.status}</span></header>
          <div className="request-detail-body">
            <div className="request-title-row"><div><h3>{request.title}</h3><p>Completed in {request.latency}</p></div><code>UCP · Request-Id {request.id.toLowerCase()}</code></div>
            <blockquote>“{request.quote}”</blockquote>
            <div className="intent-tags">{request.tags.map((tag) => <span key={tag}>{tag}</span>)}</div>
            <div className="explanation-stages">
              {request.stages.map(([label, value]) => <article key={label}><small>{label}</small><strong>{value}</strong></article>)}
            </div>
            <div className="explanation-notes">
              <article><h3>Products considered</h3><ul>{request.products.map((product) => <li key={product}>{product}</li>)}</ul></article>
              <article><h3>What the console explains</h3><ul>{request.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul></article>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
