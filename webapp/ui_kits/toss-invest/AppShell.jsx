/* App shell: left sidebar + sticky top bar, Toss-web style. */
const QB_NAV = [
  { key:'asset', label:'자산', icon:'wallet' },
  { key:'analysis', label:'수익분석', icon:'pie' },
  { key:'transactions', label:'거래내역', icon:'receipt' },
  { key:'orders', label:'주문내역', icon:'list' },
  { key:'dividends', label:'예상 배당금', icon:'coins' },
  { key:'reports', label:'리포트', icon:'file' },
];

function Logo() {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:9 }}>
      <div style={{ width:30, height:30, borderRadius:9, background:'var(--blue-500)', display:'flex', alignItems:'center', justifyContent:'center', color:'#fff', fontWeight:800, fontSize:17, letterSpacing:'-.04em' }}>q</div>
      <span style={{ fontSize:19, fontWeight:800, color:'var(--grey-900)', letterSpacing:'-.03em' }}>quntbot</span>
    </div>
  );
}

function Sidebar({ active, onNav }) {
  const { QBIcon } = window;
  return (
    <aside style={{
      width:'var(--sidebar-w)', flex:'0 0 var(--sidebar-w)', height:'100vh', position:'sticky', top:0,
      background:'var(--surface-card)', borderRight:'1px solid var(--border-subtle)',
      display:'flex', flexDirection:'column', padding:'22px 14px',
    }}>
      <div style={{ padding:'0 10px 22px' }}><Logo/></div>
      <nav style={{ display:'flex', flexDirection:'column', gap:2 }}>
        {QB_NAV.map((n) => {
          const on = n.key === active;
          return (
            <button key={n.key} onClick={() => onNav(n.key)} style={{
              display:'flex', alignItems:'center', gap:12, padding:'11px 12px', border:'none',
              borderRadius:'var(--r-md)', cursor:'pointer', textAlign:'left',
              background:on ? 'var(--action-primary-soft)' : 'transparent',
              color:on ? 'var(--action-primary)' : 'var(--text-secondary)',
              fontFamily:'var(--font-sans)', fontSize:15, fontWeight:on ? 700 : 500,
              transition:'background var(--dur-fast) var(--ease-out)',
            }}
            onMouseEnter={(e)=>{ if(!on) e.currentTarget.style.background='var(--grey-50)'; }}
            onMouseLeave={(e)=>{ if(!on) e.currentTarget.style.background='transparent'; }}>
              <QBIcon name={n.icon} size={21} strokeWidth={on?2.4:2} />
              {n.label}
            </button>
          );
        })}
      </nav>
      <div style={{ marginTop:'auto', padding:'14px 12px', borderRadius:'var(--r-md)', background:'var(--grey-50)', display:'flex', gap:10, alignItems:'center' }}>
        <QBIcon name="shield" size={20} color="var(--green-500)" />
        <div style={{ fontSize:12.5, lineHeight:1.4, color:'var(--text-secondary)' }}>
          <b style={{ color:'var(--grey-800)' }}>PAPER 모드</b><br/>모의투자로 안전하게 운용 중
        </div>
      </div>
    </aside>
  );
}

function TopBar({ title }) {
  const { QBIcon } = window;
  const { market } = window.QB_DATA;
  const Idx = ({ label, v, chg }) => (
    <div style={{ display:'flex', alignItems:'baseline', gap:6, whiteSpace:'nowrap' }}>
      <span style={{ fontSize:12.5, color:'var(--text-tertiary)', fontWeight:600 }}>{label}</span>
      <span className="num" style={{ fontSize:13.5, fontWeight:700, color:'var(--grey-800)' }}>{v.toLocaleString('ko-KR',{minimumFractionDigits:2,maximumFractionDigits:2})}</span>
      <span className="num" style={{ fontSize:12.5, fontWeight:700, color: chg>=0?'var(--up)':'var(--down)' }}>{chg>=0?'+':''}{chg.toFixed(2)}%</span>
    </div>
  );
  return (
    <header style={{
      height:'var(--header-h)', position:'sticky', top:0, zIndex:10,
      background:'rgba(255,255,255,0.82)', backdropFilter:'saturate(180%) blur(12px)',
      borderBottom:'1px solid var(--border-subtle)',
      display:'flex', alignItems:'center', justifyContent:'space-between', gap:24, padding:'0 32px',
    }}>
      <h1 style={{ margin:0, fontSize:20, fontWeight:800, color:'var(--grey-900)', letterSpacing:'-.03em', whiteSpace:'nowrap' }}>{title}</h1>
      <div style={{ display:'flex', alignItems:'center', gap:22, flexShrink:0 }}>
        <div style={{ display:'flex', gap:18 }}>
          <Idx label="코스피" v={market.kospi.value} chg={market.kospi.chg} />
          <Idx label="코스닥" v={market.kosdaq.value} chg={market.kosdaq.chg} />
          <Idx label="환율" v={market.usdkrw.value} chg={market.usdkrw.chg} />
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:6 }}>
          <button style={iconBtn}><QBIcon name="search" size={20} color="var(--grey-600)"/></button>
          <button style={iconBtn}><QBIcon name="bell" size={20} color="var(--grey-600)"/></button>
        </div>
      </div>
    </header>
  );
}
const iconBtn = { width:38, height:38, borderRadius:'var(--r-md)', border:'none', background:'transparent', cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center' };

function AppShell({ active, onNav, title, children }) {
  return (
    <div style={{ display:'flex', minHeight:'100vh', background:'var(--bg-app)' }}>
      <Sidebar active={active} onNav={onNav} />
      <div style={{ flex:1, minWidth:0, display:'flex', flexDirection:'column' }}>
        <TopBar title={title} />
        <main style={{ flex:1, padding:'28px 32px 56px' }}>
          <div style={{ maxWidth:'var(--content-max)', margin:'0 auto' }}>{children}</div>
        </main>
      </div>
    </div>
  );
}
window.AppShell = AppShell;
window.QB_NAV = QB_NAV;
