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
            The value each merchant&apos;s verified records credited, and the value an agent withheld, are on the{" "}
            <a href="/console/requests/">Requests</a> page for every evaluation request.
          </p>
          <p>
            The records themselves, with their signatures checked, are rendered by the buyer-agent chat page
            (port 8001 by default) and by the <a href="/dashboard/">merchant dashboard</a>.
          </p>
        </div>
      </section>
    </div>
  );
}
