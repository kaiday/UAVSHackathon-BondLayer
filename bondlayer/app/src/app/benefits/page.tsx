const benefits = [
  { name: "Free returns", scope: "All products", conditions: "30 days, unused", ceiling: "$45", signature: "Verified", expiry: "No expiry", tone: "success" },
  { name: "Extended warranty", scope: "Laptops", conditions: "BondLayer members", ceiling: "$129", signature: "Verified", expiry: "31 Dec 2026", tone: "success" },
  { name: "Trade-in credit", scope: "Selected devices", conditions: "Eligible serial number", ceiling: "$300", signature: "Review", expiry: "30 Sep 2026", tone: "warning" },
  { name: "Member pricing", scope: "Accessories", conditions: "Signed member ID", ceiling: "12%", signature: "Verified", expiry: "No expiry", tone: "success" },
];

export default function BenefitsPage() {
  return (
    <div className="content">
      <div className="page-heading">
        <div><h1>Benefit records</h1><p>Signed offers agents can verify, compare and include in a recommendation.</p></div>
        <div className="actions"><button className="primary" type="button">Create benefit</button></div>
      </div>

      <section className="panel">
        <div className="panel-heading"><div><h2>Published benefits</h2><p>{benefits.length} active records</p></div><span className="pill success">Verified</span></div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Benefit</th><th>Scope</th><th>Conditions</th><th>Value ceiling</th><th>Signature</th><th>Expiry</th></tr></thead>
            <tbody>
              {benefits.map((benefit) => (
                <tr key={benefit.name}>
                  <td><strong>{benefit.name}</strong></td>
                  <td>{benefit.scope}</td>
                  <td>{benefit.conditions}</td>
                  <td>{benefit.ceiling}</td>
                  <td><span className={`pill ${benefit.tone}`}>{benefit.signature}</span></td>
                  <td>{benefit.expiry}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
