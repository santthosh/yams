export default function Home() {
  return (
    <main>
      <header>
        <span className="wordmark">YAMS</span>
        <span className="badge">Paper only</span>
      </header>
      <section aria-labelledby="workspace-heading">
        <p className="eyebrow">Your local research workspace</p>
        <h1 id="workspace-heading">A clear starting point.</h1>
        <p>
          Explore market ideas with synthetic capital and inspectable evidence.
          No real brokerage or real-money trading.
        </p>
        <div className="notice">
          <h2>Foundation in progress</h2>
          <p>
            This shell contains no market data, portfolios, or calculated
            investment results. Offline fixture setup and workspace persistence
            are being built next.
          </p>
        </div>
      </section>
      <footer>Yet Another Market Simulator · Local and single-user</footer>
    </main>
  );
}
