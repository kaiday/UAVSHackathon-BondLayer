import { products } from "@/lib/dashboard-data";

export default function CataloguePage() {
  return (
    <div className="content">
      <div className="page-heading">
        <div>
          <h1>Product catalogue</h1>
          <p>See what shopping agents can understand and what to improve next.</p>
        </div>
        <div className="actions">
          <button type="button">Sync catalogue</button>
          <button className="primary" type="button">Add product</button>
        </div>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Agent-ready products</h2>
            <p>{products.length} products monitored</p>
          </div>
          <span className="pill success">Live</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th>Category</th>
                <th>Requests</th>
                <th>Data quality</th>
                <th>Next improvement</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {products.map((product) => (
                <tr key={product.sku}>
                  <td><strong>{product.name}</strong><small>{product.sku}</small></td>
                  <td>{product.category}</td>
                  <td>{product.requests}</td>
                  <td>
                    <div className="quality">
                      <span><i style={{ width: `${product.quality}%` }} /></span>
                      <strong>{product.quality}%</strong>
                    </div>
                  </td>
                  <td>{product.fix}</td>
                  <td><span className={`pill ${product.tone}`}>{product.status}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
