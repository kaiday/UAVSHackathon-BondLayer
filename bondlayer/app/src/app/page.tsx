import { activity, products } from "@/lib/dashboard-data";

const metrics = [
  { label: "Avg. requests / product", value: "20.1", note: "Across 62 products" },
  { label: "Agent-ready", value: "48", note: "14 need fixes" },
  { label: "Visitor → lead/member", value: "18.6%", note: "+3.2 points this week" },
  { label: "Agent requests", value: "1,248", note: "Last 7 days" },
];

export default function Home() {
  return (
    <div className="content">
      <div className="page-heading">
        <div><h1>Catalogue health</h1><p>Make every product easy for agents to find and compare.</p></div>
        <div className="actions"><button>Export</button><button className="primary">Run test</button></div>
      </div>

      <section className="metrics" aria-label="Key metrics">
        {metrics.map((metric) => <article className="metric" key={metric.label}><p>{metric.label}</p><strong>{metric.value}</strong><span>{metric.note}</span></article>)}
      </section>

      <section className="dashboard-grid">
        <div className="dashboard-primary">
          <article className="panel catalogue-panel">
            <div className="panel-heading"><div><h2>Product catalogue</h2><p>Agent-facing fields and recommended fixes</p></div><span className="pill success">Live</span></div>
            <div className="table-wrap"><table><thead><tr><th>Product</th><th>Category</th><th>Requests</th><th>Data quality</th><th>Next fix</th><th>Status</th></tr></thead><tbody>
              {products.map((product) => (
                <tr key={product.sku}>
                  <td><strong>{product.name}</strong><small>{product.sku}</small></td>
                  <td>{product.category}</td><td>{product.requests}</td>
                  <td><div className="quality"><span><i style={{ width: `${product.quality}%` }} /></span><strong>{product.quality}%</strong></div></td>
                  <td><code>{product.fix}</code></td>
                  <td><span className={`pill ${product.tone}`}>{product.status}</span></td>
                </tr>
              ))}
            </tbody></table></div>
          </article>

          <section className="panel activity">
            <div className="panel-heading"><div><h2>Agent traffic</h2><p>HTTP events · last hour</p></div><span className="pill">42 events</span></div>
            <div className="bars" aria-label="Agent request activity">
              {activity.map((height, index) => {
                const timestamp = `08:${String(index + 8).padStart(2, "0")}`;
                const requests = Math.max(1, Math.round(height / 14));
                return (
                  <span className="bar-point" key={timestamp} tabIndex={0} aria-label={`${timestamp}, ${requests} requests`}>
                    <i style={{ height: `${height}%` }} />
                    <span className="bar-tooltip"><strong>{timestamp}</strong><small>{requests} {requests === 1 ? "request" : "requests"}</small></span>
                  </span>
                );
              })}
            </div>
          </section>
        </div>

        <article className="panel reasons">
          <div className="panel-heading"><div><h2>Improve discovery</h2><p>Highest-impact actions</p></div><span className="pill warning">3 fixes</span></div>
          <div className="reason-list">
            <div><span>1</span><p><strong>Stable identifiers</strong><small>Publish GTIN, MPN and canonical URL.</small></p></div>
            <div><span>2</span><p><strong>Structured specifications</strong><small>Use typed values, units and availability.</small></p></div>
            <div><span>3</span><p><strong>Verifiable benefits</strong><small>Sign returns, warranty and member value.</small></p></div>
            <aside><strong>Best next fix</strong><p>Add <code>battery_energy_wh</code> so agents can verify flight eligibility.</p></aside>
          </div>
        </article>
      </section>
    </div>
  );
}
