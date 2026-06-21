/* 주문내역 — most recent rebalance plan + execution. */
function OrderScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const { Card, Badge, TickerBadge, DeltaValue } = NS;
  const { QBIcon } = window;
  const { orders, won } = window.QB_DATA;
  const buys = orders.filter(o=>o.side==='buy'), sells = orders.filter(o=>o.side==='sell');

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
      <Card padding={24} style={{ display:'flex', alignItems:'center', gap:20 }}>
        <div style={{ width:48, height:48, borderRadius:14, background:'var(--action-primary-soft)', display:'flex', alignItems:'center', justifyContent:'center' }}>
          <QBIcon name="refresh" size={26} color="var(--blue-500)" />
        </div>
        <div style={{ flex:1 }}>
          <div style={{ display:'flex', alignItems:'center', gap:8 }}>
            <span style={{ fontSize:16.5, fontWeight:800, color:'var(--grey-900)' }}>주간 리밸런싱</span>
            <Badge tone="success" size="sm">실행 완료</Badge>
            <Badge tone="info" size="sm">PAPER</Badge>
          </div>
          <div style={{ fontSize:13, color:'var(--text-tertiary)', marginTop:3 }}>2026.06.16 11:19 · 매수 {buys.length} · 매도 {sells.length} · 실패 0 · 계획 일치</div>
        </div>
        <div style={{ textAlign:'right' }}>
          <div style={{ fontSize:12.5, color:'var(--text-tertiary)' }}>다음 예정</div>
          <div style={{ fontSize:14.5, fontWeight:700, color:'var(--grey-800)' }}>2026.06.23 (월)</div>
        </div>
      </Card>

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        {[['매수 주문', buys, 'buy'], ['매도 주문', sells, 'sell']].map(([title, list, side]) => (
          <Card key={side} padding={0}>
            <div style={{ padding:'18px 24px 12px', display:'flex', alignItems:'center', gap:8 }}>
              <Badge tone={side} solid>{side==='buy'?'매수':'매도'}</Badge>
              <span style={{ fontSize:15.5, fontWeight:800, color:'var(--grey-900)' }}>{title}</span>
              <span className="num" style={{ fontSize:14, color:'var(--text-tertiary)', marginLeft:'auto' }}>{list.length}건</span>
            </div>
            {list.map((o,i)=>(
              <div key={i} style={{ display:'flex', alignItems:'center', gap:12, padding:'13px 24px', borderTop:'1px solid var(--grey-50)' }}>
                <TickerBadge name={o.name} ticker={o.ticker} size={38} />
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ fontSize:14.5, fontWeight:700, color:'var(--grey-900)' }}>{o.name}</div>
                  <div style={{ fontSize:12, color:'var(--text-tertiary)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>{o.reason}</div>
                </div>
                <div style={{ textAlign:'right' }}>
                  <div className="num" style={{ fontSize:14, fontWeight:700, color:'var(--grey-900)' }}>{o.qty}주</div>
                  {o.price ? <div className="num" style={{ fontSize:12, color:'var(--text-tertiary)' }}>{won(o.price)}</div> : null}
                </div>
              </div>
            ))}
          </Card>
        ))}
      </div>
    </div>
  );
}
window.OrderScreen = OrderScreen;
