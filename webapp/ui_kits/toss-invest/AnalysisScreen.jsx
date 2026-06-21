/* 수익분석 — performance analysis. */
function AreaChart({ data, labels, height=240 }) {
  const NS = window.QuntbotDesignSystem_ce5871;
  const w = 760, pad = 8;
  const min = Math.min(...data) * 0.985, max = Math.max(...data) * 1.01;
  const span = max - min || 1;
  const stepX = (w - pad*2) / (data.length - 1);
  const pts = data.map((v,i)=>[pad + i*stepX, height - 28 - ((v-min)/span)*(height-50)]);
  const line = pts.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  const area = `${line} L${pts[pts.length-1][0]} ${height-28} L${pts[0][0]} ${height-28} Z`;
  const up = data[data.length-1] >= data[0];
  const c = up ? 'var(--up)' : 'var(--down)';
  return (
    <svg viewBox={`0 0 ${w} ${height}`} width="100%" style={{ display:'block' }} preserveAspectRatio="none">
      <defs><linearGradient id="ac" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={c} stopOpacity="0.16"/><stop offset="100%" stopColor={c} stopOpacity="0"/></linearGradient></defs>
      {[0,0.5,1].map((g,i)=>(<line key={i} x1={pad} x2={w-pad} y1={28+g*(height-56)} y2={28+g*(height-56)} stroke="var(--grey-100)" strokeWidth="1"/>))}
      <path d={area} fill="url(#ac)"/>
      <path d={line} fill="none" stroke={c} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round"/>
      <circle cx={pts[pts.length-1][0]} cy={pts[pts.length-1][1]} r="4.5" fill={c}/>
      {labels.map((l,i)=> i%2===0 && (<text key={i} x={pad + i*stepX} y={height-8} fontSize="11" fill="var(--text-tertiary)" textAnchor="middle" fontFamily="var(--font-sans)">{l}</text>))}
    </svg>
  );
}

function AnalysisScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const { Card, StatTile, DeltaValue, FactorBar, SegmentedControl, TickerBadge, Badge } = NS;
  const { summary, equityCurve, equityLabels, factorBudget, positions, won } = window.QB_DATA;
  const [period, setPeriod] = React.useState('1Y');

  const gainers = [...positions].sort((a,b)=>b.plRate-a.plRate).slice(0,3);
  const losers = [...positions].sort((a,b)=>a.plRate-b.plRate).slice(0,3);
  const Mini = ({p}) => (
    <div style={{ display:'flex', alignItems:'center', gap:10, padding:'9px 0' }}>
      <TickerBadge name={p.name} ticker={p.ticker} size={34} />
      <div style={{ flex:1 }}>
        <div style={{ fontSize:14, fontWeight:600, color:'var(--grey-900)' }}>{p.name}</div>
        <div style={{ fontSize:12, color:'var(--text-tertiary)' }}>{won(p.value)}</div>
      </div>
      <DeltaValue value={p.plRate} percent size={14.5} />
    </div>
  );

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:16 }}>
        <Card padding={22}><StatTile label="총 평가손익" value={won(summary.totalPL)} delta={summary.totalPLRate} deltaPercent /></Card>
        <Card padding={22}><StatTile label="누적 수익률" value="+9.50%" sub="2024.07 운용 개시" /></Card>
        <Card padding={22}><StatTile label="실현손익" value="₩0" sub="이번 분기" /></Card>
        <Card padding={22}><StatTile label="추정 MDD" value="−12.4%" sub="백테스트 기준" /></Card>
      </div>

      <Card padding={24}>
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:8 }}>
          <div>
            <div style={{ fontSize:16, fontWeight:800, color:'var(--grey-900)' }}>평가금액 추이</div>
            <div style={{ display:'flex', alignItems:'baseline', gap:10, marginTop:6 }}>
              <span className="num" style={{ fontSize:26, fontWeight:800, color:'var(--grey-900)', letterSpacing:'-.03em' }}>{won(summary.totalAsset)}</span>
              <DeltaValue value={21.5} percent size={15} />
            </div>
          </div>
          <SegmentedControl size="sm" value={period} onChange={setPeriod} items={['3M','6M','1Y','전체']} />
        </div>
        <AreaChart data={equityCurve} labels={equityLabels} />
      </Card>

      <div style={{ display:'grid', gridTemplateColumns:'1.1fr 1fr', gap:16 }}>
        <Card padding={24}>
          <div style={{ fontSize:16, fontWeight:800, color:'var(--grey-900)', marginBottom:4 }}>팩터 배분</div>
          <div style={{ fontSize:13, color:'var(--text-tertiary)', marginBottom:18 }}>100점 팩터 예산 · 포트폴리오 평균</div>
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            {factorBudget.map((f)=>(<FactorBar key={f.key} label={f.label} score={f.score} max={f.max} factor={f.key} />))}
          </div>
        </Card>
        <div style={{ display:'grid', gridTemplateRows:'1fr 1fr', gap:16 }}>
          <Card padding={'18px 24px'}>
            <div style={{ display:'flex', alignItems:'center', gap:7, marginBottom:2 }}>
              <span style={{ fontSize:14.5, fontWeight:800, color:'var(--grey-900)' }}>수익 상위</span><Badge tone="buy" size="sm">TOP 3</Badge>
            </div>
            {gainers.map(p=><Mini key={p.ticker} p={p}/>)}
          </Card>
          <Card padding={'18px 24px'}>
            <div style={{ display:'flex', alignItems:'center', gap:7, marginBottom:2 }}>
              <span style={{ fontSize:14.5, fontWeight:800, color:'var(--grey-900)' }}>수익 하위</span><Badge tone="sell" size="sm">BOTTOM 3</Badge>
            </div>
            {losers.map(p=><Mini key={p.ticker} p={p}/>)}
          </Card>
        </div>
      </div>
    </div>
  );
}
window.AnalysisScreen = AnalysisScreen;
