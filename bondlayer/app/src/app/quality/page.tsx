import Image from "next/image";
import { products } from "@/lib/dashboard-data";

const issues = [
  { product: "Ridge 10K Power Bank", field: "battery_energy_wh", impact: "Agents cannot verify flight safety", fix: "Add the 37 Wh battery rating", priority: "High", tone: "danger" },
  { product: "Universal Travel Adapter", field: "supported_plug_types", impact: "Destination matching is incomplete", fix: "Map AU, EU, UK and US plugs", priority: "High", tone: "danger" },
  { product: "Braided USB-C Cable", field: "transfer_speed", impact: "Agents assume charging only", fix: "Add 5 Gbps transfer speed", priority: "Medium", tone: "warning" },
];

export default function QualityPage() {
  return (
    <div className="content">
      <div className="page-heading">
        <div><h1>Data quality</h1><p>Prioritised fixes that improve agent discovery and recommendation confidence.</p></div>
        <div className="actions"><button className="primary" type="button">Run audit</button></div>
      </div>

      <div className="metrics compact-metrics">
        <article className="metric"><p>Catalogue score</p><strong>80%</strong><span>+6 points this week</span></article>
        <article className="metric"><p>Agent-readable fields</p><strong className="fraction-value"><span className="metric-main">46</span><span className="metric-denominator">/ 52</span></strong><span>Across active products</span></article>
        <article className="metric"><p>Critical gaps</p><strong>2</strong><span>Resolve before next sync</span></article>
      </div>

      <section className="panel">
        <div className="panel-heading"><div><h2>Recommended fixes</h2><p>Ordered by expected agent impact</p></div></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Product</th><th>Missing field</th><th>Agent impact</th><th>Recommended fix</th><th>Priority</th></tr></thead>
            <tbody>
              {issues.map((issue) => (
                <tr key={issue.field}>
                  <td><div className="product-identity"><span className="product-thumb"><Image src={products.find((product) => product.name === issue.product)?.image ?? products[0].image} alt="" width={42} height={42} sizes="42px" /></span><span><strong>{issue.product}</strong></span></div></td>
                  <td><code>{issue.field}</code></td>
                  <td>{issue.impact}</td>
                  <td>{issue.fix}</td>
                  <td><span className={`pill ${issue.tone}`}>{issue.priority}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
