export function KpiPage() {
  return (
    <section className="page">
      <header className="page-head">
        <h2>KPI Dashboard</h2>
        <p>Migrate KPI metrics, trend cards, and report export actions in this module.</p>
      </header>

      <div className="cards-grid">
        <article className="metric-card">
          <span>Running %</span>
          <strong>--</strong>
        </article>
        <article className="metric-card">
          <span>Idle %</span>
          <strong>--</strong>
        </article>
        <article className="metric-card">
          <span>Stopped %</span>
          <strong>--</strong>
        </article>
        <article className="metric-card">
          <span>Total Distance</span>
          <strong>--</strong>
        </article>
      </div>
    </section>
  )
}
