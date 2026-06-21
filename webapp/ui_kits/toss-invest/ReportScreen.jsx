/* 리포트 — broker research summaries (research-report overlay). */
function ReportScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const { Card, Badge, TickerBadge, StatTile, Tabs } = NS;
  const { QBIcon } = window;
  const { reports, won } = window.QB_DATA;
  const [tab, setTab] = React.useState('all');

  const filtered = reports.filter(r => tab==='all' || (tab==='held'&&r.held) || (tab==='positive'&&r.opinion==='positive'));
  const opinionMap = { positive:['buy','매수'], mixed:['hold','중립'], negative:['sell','매도'] };

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
      {/* Summary banner */}
      <Card padding={26} style={{ display:'flex', alignItems:'center', gap:28 }}>
        <div style={{ display:'flex', alignItems:'center', gap:13, flex:'0 0 auto' }}>
          <div style={{ width:46, height:46, borderRadius:13, background:'var(--purple-50)', display:'flex', alignItems:'center', justifyContent:'center' }}><QBIcon name="sparkles" size={24} color="var(--purple-500)"/></div>
          <div>
            <div style={{ fontSize:16.5, fontWeight:800, color:'var(--grey-900)' }}>리서치 요약</div>
            <div style={{ fontSize:12.5, color:'var(--text-tertiary)' }}>한경·미래에셋 컨센서스 1,000건 자동 분석</div>
          </div>
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:24, flex:1, paddingLeft:28, borderLeft:'1px solid var(--border-subtle)' }}>
          <StatTile label="분석 리포트" value="996" sub="본문 추출" />
          <StatTile label="매수 의견" value="175" sub="positive" />
          <StatTile label="중립 의견" value="810" sub="mixed" />
          <StatTile label="보유 종목 관련" value="42" sub="포트폴리오" />
        </div>
      </Card>

      <Tabs value={tab} onChange={setTab} items={[{key:'all',label:'전체'},{key:'held',label:'보유 종목'},{key:'positive',label:'매수 의견'}]} />

      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
        {filtered.map((r,i)=>{
          const [tone,label] = opinionMap[r.opinion] || ['hold','중립'];
          return (
            <Card key={i} padding={22} interactive shadow="sm" style={{ display:'flex', flexDirection:'column', gap:13 }}>
              <div style={{ display:'flex', alignItems:'center', gap:11 }}>
                <TickerBadge name={r.name} ticker={r.ticker} size={42} />
                <div style={{ flex:1, minWidth:0 }}>
                  <div style={{ display:'flex', alignItems:'center', gap:7 }}>
                    <span style={{ fontSize:15.5, fontWeight:800, color:'var(--grey-900)' }}>{r.name}</span>
                    {r.held && <Badge tone="info" size="sm">보유</Badge>}
                  </div>
                  <div style={{ fontSize:12.5, color:'var(--text-tertiary)' }}>{r.broker} · {r.date}</div>
                </div>
                <Badge tone={tone} solid>{label}</Badge>
              </div>
              <div style={{ fontSize:15, fontWeight:700, color:'var(--grey-900)', lineHeight:1.35, letterSpacing:'-.01em' }}>{r.title}</div>
              <div style={{ fontSize:13.5, color:'var(--text-body)', lineHeight:1.5, textWrap:'pretty' }}>{r.thesis}</div>
              <div style={{ display:'flex', alignItems:'flex-start', gap:7, padding:'10px 12px', background:'var(--grey-50)', borderRadius:'var(--r-md)' }}>
                <QBIcon name="shield" size={16} color="var(--amber-500)" style={{ flex:'0 0 16px', marginTop:1 }} />
                <span style={{ fontSize:12.5, color:'var(--text-secondary)', lineHeight:1.45 }}><b style={{ color:'var(--grey-700)' }}>리스크</b> · {r.risk}</span>
              </div>
              <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', paddingTop:2 }}>
                <span style={{ fontSize:12.5, color:'var(--text-tertiary)' }}>신뢰도 {(r.confidence*100).toFixed(0)}%</span>
                {r.target && <span className="num" style={{ fontSize:13.5, fontWeight:700, color:'var(--up)' }}>목표가 {won(r.target)}</span>}
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
window.ReportScreen = ReportScreen;
