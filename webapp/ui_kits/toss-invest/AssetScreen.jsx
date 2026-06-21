/* 자산 — portfolio overview (hero). */
function AssetScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const { StatTile, DeltaValue, Donut, Sparkline, TickerBadge, Badge, FactorBar, SegmentedControl, Card } = NS;
  const { QBIcon } = window;
  const { summary, positions, sectors, won } = window.QB_DATA;
  const [sort, setSort] = React.useState('plRate');
  const [open, setOpen] = React.useState(null);

  const sorted = [...positions].sort((a,b) => (b[sort]||0) - (a[sort]||0));
  const SortLabels = { plRate:'수익률', value:'평가금액', weight:'비중' };

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
      {/* Hero */}
      <div style={{ display:'grid', gridTemplateColumns:'1.55fr 1fr', gap:16 }}>
        <Card padding={28} style={{ display:'flex', flexDirection:'column', justifyContent:'space-between' }}>
          <div>
            <div style={{ fontSize:14, color:'var(--text-secondary)', fontWeight:600, marginBottom:8 }}>내 투자 자산</div>
            <div className="num" style={{ fontSize:38, fontWeight:800, color:'var(--grey-900)', letterSpacing:'-.03em', lineHeight:1.05 }}>{won(summary.totalAsset)}</div>
            <div style={{ display:'flex', gap:16, marginTop:12, alignItems:'baseline' }}>
              <span style={{ display:'inline-flex', gap:6, alignItems:'baseline' }}>
                <span style={{ fontSize:13.5, color:'var(--text-tertiary)' }}>평가손익</span>
                <DeltaValue value={summary.totalPL} prefix="₩" showArrow={false} size={16} />
                <DeltaValue value={summary.totalPLRate} percent size={15} />
              </span>
              <span style={{ display:'inline-flex', gap:6, alignItems:'baseline' }}>
                <span style={{ fontSize:13.5, color:'var(--text-tertiary)' }}>오늘</span>
                <DeltaValue value={summary.dayPL} prefix="₩" showArrow={false} size={15} />
                <DeltaValue value={summary.dayPLRate} percent size={14} />
              </span>
            </div>
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:16, marginTop:24, paddingTop:20, borderTop:'1px solid var(--border-subtle)' }}>
            <StatTile label="주식 평가금액" value={won(summary.stockValue)} />
            <StatTile label="예수금" value={won(summary.cash)} />
            <StatTile label="매입금액" value={won(summary.totalCost)} />
            <StatTile label="보유 종목" value={summary.holdingCount + '개'} />
          </div>
        </Card>

        <Card padding={24}>
          <div style={{ fontSize:15, fontWeight:700, color:'var(--grey-900)', marginBottom:4 }}>자산 비중</div>
          <div style={{ display:'flex', alignItems:'center', gap:18 }}>
            <Donut size={132} thickness={20} centerSub="주식" centerLabel="66%"
              segments={[{label:'주식',value:summary.stockValue,color:'var(--blue-500)'},{label:'현금',value:summary.cash,color:'var(--grey-200)'}]} />
            <div style={{ display:'flex', flexDirection:'column', gap:10, flex:1 }}>
              {sectors.slice(0,5).map((s) => (
                <div key={s.label} style={{ display:'flex', alignItems:'center', gap:8 }}>
                  <span style={{ width:9, height:9, borderRadius:3, background:s.color }} />
                  <span style={{ fontSize:13, color:'var(--text-body)', flex:1 }}>{s.label}</span>
                  <span className="num" style={{ fontSize:13, fontWeight:600, color:'var(--grey-800)' }}>{s.value.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      {/* Holdings */}
      <Card padding={0}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'20px 24px 16px' }}>
          <div style={{ fontSize:17, fontWeight:800, color:'var(--grey-900)' }}>보유 종목 <span className="num" style={{ color:'var(--text-tertiary)' }}>{positions.length}</span></div>
          <SegmentedControl size="sm" value={sort} onChange={setSort} items={Object.keys(SortLabels).map(k=>({key:k,label:SortLabels[k]}))} />
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 96px 150px 96px', padding:'0 24px 10px', fontSize:12.5, color:'var(--text-tertiary)', fontWeight:600, borderBottom:'1px solid var(--border-subtle)' }}>
          <span>종목</span><span style={{ textAlign:'right' }}>추세</span><span style={{ textAlign:'right' }}>평가금액</span><span style={{ textAlign:'right' }}>수익률</span>
        </div>
        {sorted.map((p) => {
          const on = open === p.ticker;
          return (
            <div key={p.ticker} style={{ borderBottom:'1px solid var(--grey-50)' }}>
              <div onClick={() => setOpen(on ? null : p.ticker)} style={{ display:'grid', gridTemplateColumns:'1fr 96px 150px 96px', alignItems:'center', padding:'14px 24px', cursor:'pointer' }}
                onMouseEnter={(e)=>e.currentTarget.style.background='var(--grey-50)'}
                onMouseLeave={(e)=>e.currentTarget.style.background='transparent'}>
                <div style={{ display:'flex', alignItems:'center', gap:12 }}>
                  <TickerBadge name={p.name} ticker={p.ticker} size={40} />
                  <div>
                    <div style={{ display:'flex', alignItems:'center', gap:7 }}>
                      <span style={{ fontSize:15, fontWeight:700, color:'var(--grey-900)' }}>{p.name}</span>
                      {p.rank && <Badge tone="hold" size="sm">랭크 {p.rank}</Badge>}
                      {p.status==='executed' && <Badge tone="success" size="sm">신규</Badge>}
                    </div>
                    <div style={{ fontSize:12.5, color:'var(--text-tertiary)' }}>{p.ticker} · {p.qty}주 · 비중 {p.weight.toFixed(1)}%</div>
                  </div>
                </div>
                <div style={{ display:'flex', justifyContent:'flex-end' }}><Sparkline data={p.spark} width={84} height={32} /></div>
                <div style={{ textAlign:'right' }}>
                  <div className="num" style={{ fontSize:15, fontWeight:700, color:'var(--grey-900)' }}>{won(p.value)}</div>
                  <div className="num" style={{ fontSize:12.5, color:'var(--text-tertiary)' }}>{won(p.price)}</div>
                </div>
                <div style={{ display:'flex', flexDirection:'column', alignItems:'flex-end', gap:1 }}>
                  <DeltaValue value={p.plRate} percent size={15} />
                  <DeltaValue value={p.pl} prefix="₩" showArrow={false} size={12.5} />
                </div>
              </div>
              {on && (
                <div style={{ padding:'4px 24px 22px 76px', background:'var(--grey-50)' }}>
                  <div style={{ fontSize:13, fontWeight:700, color:'var(--grey-800)', margin:'14px 0 12px' }}>팩터 점수 · 종합 {p.score ? p.score.toFixed(1) : '—'}/100</div>
                  <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:'14px 28px' }}>
                    <FactorBar label="가치 Value" score={p.factors.value} max={25} factor="value" />
                    <FactorBar label="퀄리티 Quality" score={p.factors.quality} max={25} factor="quality" />
                    <FactorBar label="모멘텀 Momentum" score={p.factors.momentum} max={20} factor="momentum" />
                    <FactorBar label="배당 Yield" score={p.factors.yield} max={5} factor="yield" />
                    <FactorBar label="기술적 Technical" score={p.factors.technical} max={15} factor="technical" />
                    <FactorBar label="보조 Auxiliary" score={p.factors.auxiliary} max={10} factor="auxiliary" />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </Card>
    </div>
  );
}
window.AssetScreen = AssetScreen;
