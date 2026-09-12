import Image from "next/image";
import { products } from "@/lib/dashboard-data";

const metrics = [
  { label: "Avg. requests / product", value: "20.1", trend: "12.4%", direction: "up", note: "vs. previous 7 days" },
  { label: "Agent-ready", value: "48", trend: "8.7%", direction: "up", note: "vs. previous 7 days" },
  { label: "Visitor → lead/member", value: "18.6%", trend: "3.2 pts", direction: "up", note: "vs. previous week" },
  { label: "Agent requests", value: "1,248", trend: "4.6%", direction: "down", note: "vs. previous 7 days" },
];

const requestTrend = [28, 33, 31, 38, 36, 43, 47, 42, 49, 54, 51, 58, 62, 56, 65, 70, 64, 72, 76, 69, 74, 81, 78, 86, 83, 91, 88, 96, 102, 108];
const trendMaximum = Math.max(...requestTrend);
const trendMinimum = Math.min(...requestTrend);
const trendPoints = requestTrend.map((value, index) => {
  const x = (index / (requestTrend.length - 1)) * 600;
  const y = 150 - ((value - trendMinimum) / (trendMaximum - trendMinimum)) * 120;
  return `${x.toFixed(1)},${y.toFixed(1)}`;
}).join(" ");
const trendDates = requestTrend.map((_, index) => {
  const date = new Date(Date.UTC(2026, 8, 12 - (requestTrend.length - 1 - index)));
  return date.toLocaleDateString("en-AU", { day: "2-digit", month: "short", timeZone: "UTC" });
});

export default function Home() {
  return (
    <div className="content">
      <div className="page-heading">
        <div><h1>Good morning, Merchant</h1><p>Make every product easy for agents to find and compare.</p></div>
        <div className="actions"><button>Export</button><button className="primary">Run test</button></div>
      </div>

      <section className="metrics" aria-label="Key metrics">
        {metrics.map((metric) => <article className="metric" key={metric.label}><p>{metric.label}</p><strong>{metric.value}</strong><div className="metric-trend"><span className={metric.direction}><b aria-hidden="true">{metric.direction === "up" ? "↑" : "↓"}</b> {metric.trend}</span><small>{metric.note}</small></div></article>)}
      </section>

      <section className="dashboard-grid">
        <div className="dashboard-primary">
          <article className="panel catalogue-panel">
            <div className="panel-heading"><div><h2>Product catalogue</h2><p>Agent-facing fields and recommended fixes</p></div><span className="pill success">Live</span></div>
            <div className="table-wrap"><table><thead><tr><th>Product</th><th>Category</th><th>Requests</th><th>Data quality</th><th>Next fix</th><th>Status</th></tr></thead><tbody>
              {products.map((product) => (
                <tr key={product.sku}>
                  <td><div className="product-identity"><span className="product-thumb"><Image src={product.image} alt="" width={42} height={42} sizes="42px" /></span><span><strong>{product.name}</strong><small>{product.sku}</small></span></div></td>
                  <td>{product.category}</td><td>{product.requests}</td>
                  <td><div className="quality"><span><i style={{ width: `${product.quality}%` }} /></span><strong>{product.quality}%</strong></div></td>
                  <td><code>{product.fix}</code></td>
                  <td><span className={`pill ${product.tone}`}>{product.status}</span></td>
                </tr>
              ))}
            </tbody></table></div>
          </article>

          <section className="panel request-trend">
            <div className="panel-heading"><div><h2>Agent requests over time</h2><p>Daily requests · last 30 days</p></div><span className="pill success">↑ 12.4%</span></div>
            <div className="line-chart" role="img" aria-label="Agent requests rose from 28 to 108 per day over the last 30 days, up 12.4 percent from the preceding period.">
              <svg viewBox="0 0 600 170" preserveAspectRatio="none" aria-hidden="true">
                <defs><linearGradient id="request-area" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#159a8c" stopOpacity=".24" /><stop offset="1" stopColor="#159a8c" stopOpacity="0" /></linearGradient></defs>
                <path className="chart-grid" d="M0 30H600M0 90H600M0 150H600" />
                <polygon points={`0,150 ${trendPoints} 600,150`} fill="url(#request-area)" />
                <polyline points={trendPoints} className="chart-line" />
                {requestTrend.map((value, index) => {
                  const [x, y] = trendPoints.split(" ")[index].split(",");
                  return <circle key={trendDates[index]} cx={x} cy={y} r="7" className="chart-point" tabIndex={0}><title>{trendDates[index]} · {value} agent requests</title></circle>;
                })}
              </svg>
              <div className="chart-axis"><span>30 days ago</span><span>Today</span></div>
            </div>
          </section>
        </div>

        <article className="panel reasons">
          <div className="panel-heading"><div><h2>Catalogue readiness</h2><p>62 products by agent readiness</p></div><span className="pill success">77% ready</span></div>
          <div className="readiness-chart" aria-label="48 products ready, 6 missing product data, 5 missing availability, and 3 incomplete policies.">
            <div className="readiness-stack"><i className="ready" style={{ width: "77.4%" }} /><i className="product-data" style={{ width: "9.7%" }} /><i className="availability" style={{ width: "8.1%" }} /><i className="policies" style={{ width: "4.8%" }} /></div>
            <ul><li><i className="ready" />48 ready</li><li><i className="product-data" />6 missing data</li><li><i className="availability" />5 availability</li><li><i className="policies" />3 policy gaps</li></ul>
          </div>
          <div className="panel-heading secondary-heading"><div><h2>Improve discovery</h2><p>Highest-impact actions</p></div><span className="pill warning">3 fixes</span></div>
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
