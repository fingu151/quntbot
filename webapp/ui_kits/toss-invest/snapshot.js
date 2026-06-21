/* ============================================================
   quntbot — live snapshot adapter.
   Fetches the engine's data/public_portfolio_snapshot.json and
   maps it onto window.QB_DATA (the shape the screens read).
   If no snapshot is reachable, the bundled mock data in data.js
   is kept untouched. Exposes window.QB_SNAPSHOT_READY (a promise
   the app awaits before mounting) and window.QB_DATA_SOURCE.

   Snapshot schema produced by scripts/generate_public_portfolio_snapshot.py.
   Fields the snapshot supplies: summary, market, positions(+rationale).
   Fields it does NOT carry (kept as mock): transactions, orders,
   dividends, reports, sectors, equityCurve, daily P/L.
   ============================================================ */
(function () {
  // Candidate URLs — works whether the static server roots at the repo
  // (app at /webapp/ui_kits/toss-invest/, data at /data) or elsewhere.
  const CANDIDATES = window.QB_SNAPSHOT_URLS || [
    '/data/public_portfolio_snapshot.json',
    '../../../data/public_portfolio_snapshot.json',
    './data/public_portfolio_snapshot.json',
  ];

  async function fetchFirst() {
    for (const url of CANDIDATES) {
      try {
        const res = await fetch(url, { cache: 'no-store' });
        if (res.ok) return await res.json();
      } catch (e) { /* try next */ }
    }
    return null;
  }

  // synthesize an 8-point sparkline from avg_price -> current_price
  function spark(avg, price) {
    const a = Number(avg) || 0, b = Number(price) || 0, out = [];
    for (let i = 0; i < 8; i++) out.push(a + (b - a) * (i / 7));
    return out;
  }

  function mapPosition(p, totalMarketValue) {
    const r = p.rationale || {};
    const f = r.factor_scores || {};
    return {
      ticker: String(p.ticker || ''),
      name: String(p.name || ''),
      qty: p.qty || 0,
      avg: p.avg_price || 0,
      price: p.current_price || 0,
      value: p.market_value || 0,
      cost: p.cost || 0,
      pl: p.profit_loss || 0,
      plRate: p.profit_loss_rate || 0,
      rank: r.rank != null ? r.rank : null,
      score: r.total_score != null ? r.total_score : null,
      weight: totalMarketValue ? (p.market_value / totalMarketValue) * 100 : 0,
      sector: '',
      factors: {
        value: f.value || 0,
        quality: f.quality || 0,
        momentum: f.momentum || 0,
        yield: f.yield || 0,
        technical: f.technical || 0,
        auxiliary: f.auxiliary || 0,
      },
      spark: spark(p.avg_price, p.current_price),
      status: r.execution_status === 'executed' ? 'executed' : undefined,
      orderReason: r.order_reason || '',
    };
  }

  function factorBudget(positions) {
    const keys = [
      ['value', '가치 Value', 25],
      ['quality', '퀄리티 Quality', 25],
      ['momentum', '모멘텀 Momentum', 20],
      ['yield', '배당 Yield', 5],
      ['technical', '기술적 Technical', 15],
      ['auxiliary', '보조 Auxiliary', 10],
    ];
    const n = positions.length || 1;
    return keys.map(([key, label, max]) => ({
      key, label, max,
      score: Math.round((positions.reduce((a, p) => a + (p.factors[key] || 0), 0) / n) * 10) / 10,
    }));
  }

  // Map a fetched snapshot onto window.QB_DATA. Returns true if applied,
  // false if the snapshot was empty/unusable (mock is kept). Safe to call
  // repeatedly — the app's poller calls it again when generated_at changes.
  function applySnapshot(snap) {
    if (!snap || !Array.isArray(snap.positions) || snap.positions.length === 0) {
      return false; // keep mock
    }
    const D = window.QB_DATA;
    const s = snap.summary || {};
    const m = snap.market || {};

    const totalMV = s.total_market_value || 0;
    const positions = snap.positions.map((p) => mapPosition(p, totalMV));

    D.summary = Object.assign({}, D.summary, {
      totalAsset: s.total_asset_value || 0,
      stockValue: s.stock_market_value || s.total_market_value || 0,
      cash: s.cash_balance || 0,
      totalCost: s.total_cost || 0,
      totalPL: s.total_profit_loss || 0,
      totalPLRate: s.total_profit_loss_rate || 0,
      holdingCount: s.holding_count || positions.length,
      dayPL: 0,          // snapshot has no intraday delta
      dayPLRate: 0,
      asOf: String(snap.generated_at || '').slice(0, 16).replace('T', ' '),
    });

    if (m.kospi || m.kosdaq || m.usdkrw) {
      const idx = (x, fb) => (x && x.value != null) ? { value: x.value, chg: x.chg_pct || 0 } : fb;
      D.market = {
        status: m.session_label || D.market.status,
        kospi: idx(m.kospi, D.market.kospi),
        kosdaq: idx(m.kosdaq, D.market.kosdaq),
        usdkrw: idx(m.usdkrw, D.market.usdkrw),
      };
    }

    D.positions = positions;
    D.factorBudget = factorBudget(positions);

    if (Array.isArray(snap.orders)) {
      D.orders = snap.orders.map((o) => ({
        date: String(o.date || '').replace(/-/g, '.'),
        ticker: String(o.ticker || ''),
        name: o.name || o.ticker || '',
        side: o.side === 'sell' ? 'sell' : 'buy',
        qty: o.qty || 0,
        price: o.price || 0,
        status: o.status || 'planned',
        reason: o.reason || '',
      }));
    }

    if (Array.isArray(snap.reports) && snap.reports.length) {
      D.reports = snap.reports.map((r) => ({
        date: String(r.date || '').replace(/-/g, '.'),
        name: r.name || r.ticker || '',
        ticker: String(r.ticker || ''),
        broker: r.broker || '',
        opinion: r.opinion || 'mixed',
        confidence: r.confidence != null ? r.confidence : 1,
        target: r.target || null,
        title: r.title || '',
        thesis: r.thesis || '',
        risk: r.risk || '',
        held: !!r.held,
      }));
    }

    window.QB_DATA_SOURCE = 'snapshot';
    window.QB_SNAPSHOT_GENERATED_AT = snap.generated_at || '';
    if (Array.isArray(snap.warnings) && snap.warnings.length) {
      console.warn('[quntbot] snapshot warnings:', snap.warnings);
    }
    console.info('[quntbot] live snapshot loaded:', positions.length, 'positions @', window.QB_SNAPSHOT_GENERATED_AT);
    return true;
  }

  // Exposed for the app's auto-refresh poller (see index.html).
  window.QB_fetchSnapshot = fetchFirst;
  window.QB_applySnapshot = applySnapshot;

  window.QB_DATA_SOURCE = 'mock';
  window.QB_SNAPSHOT_READY = (async function () {
    applySnapshot(await fetchFirst());
  })();
})();
