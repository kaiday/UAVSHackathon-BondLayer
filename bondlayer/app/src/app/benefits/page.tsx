export default function BenefitsPage() {
  return (
    <div className="content">
      <div className="page-heading">
        <div><h1>Benefit records</h1><p>Signed offers agents can verify, compare and include in a recommendation.</p></div>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div><h2>Where the records are shown</h2><p>This console does not list records yet: the onboarding API does not return them.</p></div>
          <span className="pill neutral">Not in this prototype</span>
        </div>
        <div className="setting-list">
          <p>
            Catalogue onboarding publishes your products and prices. No benefit records are created automatically.
          </p>
          <p>
            Publishing and managing your own signed benefit records is a separate integration. New catalogues are served as plain UCP until that integration is configured.
          </p>
        </div>
      </section>
    </div>
  );
}
