/* 거래내역 — filled trades, grouped by date. */
function TransactionScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const { Card, Badge, TickerBadge, SegmentedControl } = NS;
  const { transactions, won } = window.QB_DATA;
  const [filter, setFilter] = React.useState('all');

  const rows = transactions.filter(t => filter==='all' || t.side===filter);
  const groups = rows.reduce((acc,t)=>{ (acc[t.date]=acc[t.date]||[]).push(t); return acc; }, {});

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center' }}>
        <div style={{ fontSize:14, color:'var(--text-secondary)' }}>최근 30일 체결된 거래입니다. 모든 주문은 PAPER 모드로 실행됩니다.</div>
        <SegmentedControl size="sm" value={filter} onChange={setFilter} items={[{key:'all',label:'전체'},{key:'buy',label:'매수'},{key:'sell',label:'매도'}]} />
      </div>
      {Object.entries(groups).map(([date, list]) => (
        <Card key={date} padding={0}>
          <div style={{ padding:'14px 24px', fontSize:13.5, fontWeight:700, color:'var(--text-secondary)', borderBottom:'1px solid var(--border-subtle)' }}>{date}</div>
          {list.map((t,i)=>(
            <div key={i} style={{ display:'flex', alignItems:'center', gap:14, padding:'14px 24px', borderBottom: i<list.length-1?'1px solid var(--grey-50)':'none' }}>
              <TickerBadge name={t.name} ticker={t.ticker} size={40} />
              <div style={{ flex:1 }}>
                <div style={{ display:'flex', alignItems:'center', gap:7 }}>
                  <Badge tone={t.side==='buy'?'buy':'sell'} solid size="sm">{t.side==='buy'?'매수':'매도'}</Badge>
                  <span style={{ fontSize:15, fontWeight:700, color:'var(--grey-900)' }}>{t.name}</span>
                </div>
                <div style={{ fontSize:12.5, color:'var(--text-tertiary)', marginTop:2 }}>{t.time} · {t.qty}주 · {won(t.price)}</div>
              </div>
              <div style={{ textAlign:'right' }}>
                <div className="num" style={{ fontSize:15.5, fontWeight:700, color: t.side==='buy'?'var(--up)':'var(--down)' }}>{t.side==='buy'?'-':'+'}{won(t.amount)}</div>
                <div style={{ fontSize:12, color:'var(--text-tertiary)' }}>체결 완료</div>
              </div>
            </div>
          ))}
        </Card>
      ))}
    </div>
  );
}
window.TransactionScreen = TransactionScreen;
