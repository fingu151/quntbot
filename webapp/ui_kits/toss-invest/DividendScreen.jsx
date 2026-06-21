/* 예상 배당금 — dividend forecast. */
function DividendScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const { Card, StatTile, TickerBadge, Badge } = NS;
  const { QBIcon } = window;
  const { dividends, won } = window.QB_DATA;

  const total = dividends.reduce((a,d)=>a+d.total,0);
  const byMonth = dividends.reduce((acc,d)=>{ acc[d.payMonth]=(acc[d.payMonth]||0)+d.total; return acc; }, {});
  const months = ['4월','8월'];
  const maxMonth = Math.max(...Object.values(byMonth));
  const sorted = [...dividends].sort((a,b)=>b.total-a.total);

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:20 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1.3fr 1fr', gap:16 }}>
        <Card padding={28}>
          <div style={{ fontSize:14, color:'var(--text-secondary)', fontWeight:600, marginBottom:8 }}>올해 예상 배당금</div>
          <div className="num" style={{ fontSize:36, fontWeight:800, color:'var(--grey-900)', letterSpacing:'-.03em' }}>{won(total)}</div>
          <div style={{ fontSize:13.5, color:'var(--text-tertiary)', marginTop:8 }}>세전 기준 · 평균 배당수익률 <b style={{ color:'var(--up)' }}>2.4%</b> · {dividends.length}개 종목</div>
          <div style={{ display:'flex', gap:14, marginTop:22, alignItems:'flex-end', height:90 }}>
            {months.map(m=>(
              <div key={m} style={{ flex:1, display:'flex', flexDirection:'column', alignItems:'center', gap:8 }}>
                <span className="num" style={{ fontSize:13, fontWeight:700, color:'var(--grey-800)' }}>{won(byMonth[m]||0)}</span>
                <div style={{ width:'100%', maxWidth:120, height:(byMonth[m]/maxMonth)*60+8, background:'var(--blue-500)', borderRadius:8 }} />
                <span style={{ fontSize:12.5, color:'var(--text-tertiary)' }}>{m}</span>
              </div>
            ))}
            <div style={{ flex:2 }} />
          </div>
        </Card>
        <Card padding={24} style={{ display:'flex', flexDirection:'column', justifyContent:'center', gap:18 }}>
          <div style={{ display:'flex', alignItems:'center', gap:12 }}>
            <div style={{ width:44, height:44, borderRadius:12, background:'var(--amber-50)', display:'flex', alignItems:'center', justifyContent:'center' }}><QBIcon name="coins" size={24} color="var(--amber-500)"/></div>
            <StatTile label="다가오는 배당락" value="6월 30일" sub="KT&G 중간배당 · 2개 종목" />
          </div>
          <div style={{ height:1, background:'var(--border-subtle)' }} />
          <div style={{ display:'flex', alignItems:'center', gap:12 }}>
            <div style={{ width:44, height:44, borderRadius:12, background:'var(--green-50)', display:'flex', alignItems:'center', justifyContent:'center' }}><QBIcon name="calendar" size={24} color="var(--green-500)"/></div>
            <StatTile label="연 환산 수익 기여" value="+0.36%p" sub="포트폴리오 대비" />
          </div>
        </Card>
      </div>

      <Card padding={0}>
        <div style={{ padding:'18px 24px 14px', fontSize:16, fontWeight:800, color:'var(--grey-900)' }}>종목별 예상 배당</div>
        <div style={{ display:'grid', gridTemplateColumns:'1fr 90px 110px 90px', padding:'0 24px 10px', fontSize:12.5, color:'var(--text-tertiary)', fontWeight:600, borderBottom:'1px solid var(--border-subtle)' }}>
          <span>종목</span><span style={{textAlign:'right'}}>주당 배당</span><span style={{textAlign:'right'}}>예상 배당금</span><span style={{textAlign:'right'}}>수익률</span>
        </div>
        {sorted.map((d,i)=>(
          <div key={i} style={{ display:'grid', gridTemplateColumns:'1fr 90px 110px 90px', alignItems:'center', padding:'13px 24px', borderBottom: i<sorted.length-1?'1px solid var(--grey-50)':'none' }}>
            <div style={{ display:'flex', alignItems:'center', gap:12 }}>
              <TickerBadge name={d.name} ticker={d.ticker} size={38} />
              <div>
                <div style={{ fontSize:14.5, fontWeight:700, color:'var(--grey-900)' }}>{d.name}</div>
                <div style={{ fontSize:12, color:'var(--text-tertiary)' }}>{d.qty}주 · {d.payMonth} 지급 · 배당락 {d.exDate}</div>
              </div>
            </div>
            <span className="num" style={{ textAlign:'right', fontSize:14, color:'var(--text-body)' }}>{won(d.dps)}</span>
            <span className="num" style={{ textAlign:'right', fontSize:15, fontWeight:700, color:'var(--grey-900)' }}>{won(d.total)}</span>
            <span className="num" style={{ textAlign:'right', fontSize:14, fontWeight:700, color:'var(--up)' }}>{d.yield.toFixed(2)}%</span>
          </div>
        ))}
      </Card>
    </div>
  );
}
window.DividendScreen = DividendScreen;
