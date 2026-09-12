export default function SettingsPage() {
  return (
    <div className="content">
      <div className="page-heading">
        <div><h1>Settings</h1><p>Configure the merchant identity and agent access points.</p></div>
        <div className="actions"><button className="primary" type="button">Save changes</button></div>
      </div>

      <div className="settings-grid">
        <section className="panel">
          <div className="panel-heading"><div><h2>Merchant profile</h2><p>Shown in signed catalogue responses</p></div></div>
          <div className="setting-list">
            <label><span>Business name</span><input defaultValue="Voltway Australia" /></label>
            <label><span>Merchant ID</span><input defaultValue="merchant_voltway_au" readOnly /></label>
            <label><span>Catalogue URL</span><input defaultValue="https://voltway.example/catalogue.json" /></label>
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading"><div><h2>Agent access</h2><p>Public discovery and request endpoints</p></div><span className="pill success">Online</span></div>
          <div className="setting-list">
            <label><span>Agent discovery</span><input defaultValue="/.well-known/agent.json" readOnly /></label>
            <label><span>Request endpoint</span><input defaultValue="/api/v1/agent/request" readOnly /></label>
            <label><span>Log retention</span><input defaultValue="30 days" /></label>
          </div>
        </section>
      </div>
    </div>
  );
}
