const cards = [
  {
    title: 'Raw Telemetry',
    detail: 'Migrate fetch flow with pagination, filters, and cached queries.',
  },
  {
    title: 'DTC Analytics',
    detail: 'Migrate DTC fetch and severity/frequency dashboards.',
  },
  {
    title: 'Visualization',
    detail: 'Move chart builder into reusable chart blocks with saved presets.',
  },
  {
    title: 'KPI Dashboard',
    detail: 'Port KPI cards and export flows with improved UX performance.',
  },
]

export function OverviewPage() {
  return (
    <section className="page">
      <header className="page-head">
        <h2>Migration Control Center</h2>
        <p>Fast React frontend baseline for phased replacement of Streamlit screens.</p>
      </header>

      <div className="cards-grid">
        {cards.map((card) => (
          <article key={card.title} className="card">
            <h3>{card.title}</h3>
            <p>{card.detail}</p>
          </article>
        ))}
      </div>
    </section>
  )
}
