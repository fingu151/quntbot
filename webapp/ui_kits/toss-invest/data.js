/* ============================================================
   quntbot — shared mock data for the Toss-style UI kit.
   Sourced from the real public_portfolio_snapshot + research
   summaries (anonymized values). Exposes window.QB_DATA.
   ============================================================ */
(function () {
  const won = (n) => '₩' + Math.round(n).toLocaleString('ko-KR');

  const summary = {
    totalAsset: 98668267,
    stockValue: 65070670,
    cash: 33585877,
    totalCost: 59425267,
    totalPL: 5644629,
    totalPLRate: 9.5,
    dayPL: 1842300,
    dayPLRate: 1.91,
    holdingCount: 34,
    asOf: '2026.06.16 13:03',
  };

  const market = {
    status: '정규장',
    kospi: { value: 8751.45, chg: 8.08 },
    kosdaq: { value: 1019.06, chg: 5.30 },
    usdkrw: { value: 1513.18, chg: -0.83 },
  };

  // equity-curve-ish series for the analysis chart (월별 평가금액, 만원)
  const equityCurve = [8120, 8240, 8050, 8390, 8610, 8470, 8720, 8980, 8830, 9150, 9420, 9867];
  const equityLabels = ['7월','8월','9월','10월','11월','12월','1월','2월','3월','4월','5월','6월'];

  const positions = [
    { ticker:'028050', name:'삼성E&A', qty:24, avg:43651, price:56800, value:1363200, cost:1047624, pl:315572, plRate:30.12, rank:6, score:66.7, weight:2.10, sector:'건설', factors:{value:14.9,quality:13.6,momentum:16.7,yield:3.4,technical:15.0,auxiliary:3.1}, spark:[44,46,45,49,52,50,54,57] },
    { ticker:'005850', name:'에스엘', qty:18, avg:60558, price:77400, value:1393200, cost:1090044, pl:303154, plRate:27.81, rank:16, score:63.3, weight:2.14, sector:'자동차부품', factors:{value:19.4,quality:13.5,momentum:14.9,yield:4.6,technical:10.0,auxiliary:1.0}, spark:[61,63,62,66,70,72,75,77] },
    { ticker:'028260', name:'삼성물산', qty:3, avg:407250, price:493000, value:1479000, cost:1221750, pl:257250, plRate:21.06, rank:27, score:59.4, weight:2.27, sector:'지주', factors:{value:13.1,quality:14.7,momentum:16.4,yield:2.3,technical:10.0,auxiliary:2.8}, spark:[407,420,415,450,470,460,485,493] },
    { ticker:'034730', name:'SK', qty:2, avg:566000, price:670000, value:1340000, cost:1132000, pl:208000, plRate:18.37, rank:23, score:60.1, weight:2.06, sector:'지주', factors:{value:15.7,quality:7.5,momentum:17.8,yield:3.3,technical:12.5,auxiliary:3.3}, spark:[566,580,575,610,640,630,660,670] },
    { ticker:'033100', name:'제룡전기', qty:60, avg:48855, price:55400, value:3324000, cost:2931300, pl:392650, plRate:13.39, rank:22, score:60.1, weight:5.11, sector:'전기장비', factors:{value:14.0,quality:22.5,momentum:13.2,yield:3.8,technical:10.0,auxiliary:-3.3}, spark:[48,50,49,52,54,53,55,55] },
    { ticker:'004800', name:'효성', qty:10, avg:175840, price:199300, value:1993000, cost:1758400, pl:234600, plRate:13.34, rank:11, score:65.0, weight:3.06, sector:'지주', factors:{value:20.1,quality:15.0,momentum:12.3,yield:4.1,technical:12.5,auxiliary:1.0}, spark:[176,180,178,188,195,192,197,199] },
    { ticker:'062040', name:'산일전기', qty:5, avg:225500, price:254000, value:1270000, cost:1127500, pl:142500, plRate:12.64, rank:28, score:59.0, weight:1.95, sector:'전기장비', factors:{value:4.1,quality:23.7,momentum:14.8,yield:2.1,technical:10.0,auxiliary:4.3}, spark:[225,235,230,245,250,248,252,254] },
    { ticker:'000270', name:'기아', qty:15, avg:151306, price:170300, value:2554500, cost:2269590, pl:284910, plRate:12.55, rank:9, score:66.1, weight:3.93, sector:'자동차', factors:{value:21.5,quality:16.3,momentum:11.6,yield:4.8,technical:10.0,auxiliary:2.0}, spark:[151,158,154,163,168,165,169,170] },
    { ticker:'002380', name:'KCC', qty:3, avg:505000, price:565000, value:1695000, cost:1515000, pl:180000, plRate:11.88, rank:25, score:59.8, weight:2.61, sector:'화학', factors:{value:24.3,quality:12.2,momentum:10.5,yield:4.2,technical:7.5,auxiliary:1.0}, spark:[505,520,515,540,555,550,562,565] },
    { ticker:'007340', name:'DN오토모티브', qty:50, avg:41168, price:45500, value:2275000, cost:2058400, pl:216600, plRate:10.52, rank:7, score:66.5, weight:3.50, sector:'자동차부품', factors:{value:21.4,quality:13.6,momentum:14.1,yield:4.0,technical:12.5,auxiliary:1.0}, spark:[41,43,42,44,45,44,45,45] },
    { ticker:'011200', name:'HMM', qty:67, avg:19930, price:21700, value:1453900, cost:1335310, pl:118590, plRate:8.88, rank:null, score:null, weight:2.24, sector:'해운', factors:{value:21.3,quality:16.0,momentum:5.7,yield:4.5,technical:7.5,auxiliary:2.0}, spark:[19,20,20,21,21,21,21,21] },
    { ticker:'028670', name:'팬오션', qty:477, avg:5057, price:5460, value:2604420, cost:2412189, pl:191850, plRate:7.95, rank:19, score:61.1, weight:4.00, sector:'해운', factors:{value:23.3,quality:9.8,momentum:9.2,yield:4.3,technical:12.5,auxiliary:2.0}, spark:[5.0,5.2,5.1,5.3,5.4,5.3,5.4,5.4] },
    { ticker:'033780', name:'KT&G', qty:13, avg:177400, price:187700, value:2440100, cost:2306200, pl:133900, plRate:5.81, rank:20, score:60.7, weight:3.75, sector:'필수소비재', factors:{value:15.1,quality:16.8,momentum:10.8,yield:4.4,technical:12.5,auxiliary:1.0}, spark:[177,180,178,185,187,186,188,187] },
    { ticker:'012330', name:'현대모비스', qty:2, avg:625000, price:657500, value:1315000, cost:1250000, pl:65000, plRate:5.20, rank:10, score:65.3, weight:2.02, sector:'자동차부품', factors:{value:18.5,quality:14.3,momentum:15.5,yield:3.0,technical:10.0,auxiliary:3.9}, spark:[625,640,632,650,658,655,660,657] },
    { ticker:'001800', name:'오리온홀딩스', qty:67, avg:27200, price:27750, value:1859250, cost:1822400, pl:36850, plRate:2.02, rank:2, score:71.3, weight:2.86, sector:'지주', factors:{value:21.0,quality:16.3,momentum:15.7,yield:4.7,technical:12.5,auxiliary:1.0}, spark:[27,27.5,27.2,27.8,27.7,27.6,27.8,27.7] },
    { ticker:'003690', name:'코리안리', qty:92, avg:13902, price:14060, value:1293520, cost:1278984, pl:14536, plRate:1.13, rank:12, score:64.6, weight:1.99, sector:'보험', factors:{value:22.8,quality:5.5,momentum:18.0,yield:4.8,technical:12.5,auxiliary:1.0}, spark:[13.9,14.0,13.9,14.1,14.0,14.0,14.1,14.0] },
    { ticker:'017550', name:'수산세보틱스', qty:474, avg:2709, price:2720, value:1289280, cost:1284066, pl:5214, plRate:0.40, rank:26, score:59.6, weight:1.98, sector:'기계', factors:{value:21.2,quality:13.7,momentum:12.8,yield:1.7,technical:12.5,auxiliary:-2.3}, spark:[2.7,2.71,2.70,2.72,2.72,2.71,2.72,2.72], status:'executed' },
    { ticker:'023160', name:'태광', qty:40, avg:31032, price:31000, value:1240000, cost:1241280, pl:-1280, plRate:-0.10, rank:29, score:58.8, weight:1.91, sector:'기계', factors:{value:19.5,quality:17.6,momentum:9.7,yield:3.7,technical:5.0,auxiliary:3.3}, spark:[31,31.2,31.1,31.0,31.0,31.1,31.0,31.0] },
    { ticker:'000240', name:'한국앤컴퍼니', qty:87, avg:30750, price:28850, value:2509950, cost:2675250, pl:-165300, plRate:-6.18, rank:1, score:77.3, weight:3.86, sector:'지주', factors:{value:23.6,quality:18.2,momentum:17.3,yield:4.7,technical:12.5,auxiliary:1.0}, spark:[30.7,30.0,30.4,29.2,28.8,29.0,28.9,28.8] },
  ];

  // 거래내역 — filled trades (체결)
  const transactions = [
    { date:'2026.06.16', time:'11:19', name:'수산세보틱스', ticker:'017550', side:'buy', qty:474, price:2695, amount:1277430 },
    { date:'2026.06.16', time:'11:19', name:'제이브이엠', ticker:'281820', side:'buy', qty:38, price:33600, amount:1276800 },
    { date:'2026.06.16', time:'09:05', name:'롯데웰푸드', ticker:'280360', side:'sell', qty:11, price:116000, amount:1276000 },
    { date:'2026.06.16', time:'09:05', name:'에이피알', ticker:'278470', side:'sell', qty:7, price:182300, amount:1276100 },
    { date:'2026.06.16', time:'09:04', name:'한컴', ticker:'092790', side:'sell', qty:55, price:23200, amount:1276000 },
    { date:'2026.06.16', time:'09:04', name:'보성파워텍', ticker:'006910', side:'sell', qty:210, price:6080, amount:1276800 },
    { date:'2026.06.09', time:'11:21', name:'현대글로비스', ticker:'086280', side:'buy', qty:9, price:141500, amount:1273500 },
    { date:'2026.06.09', time:'09:06', name:'금호석유', ticker:'011780', side:'sell', qty:8, price:159000, amount:1272000 },
    { date:'2026.06.02', time:'11:18', name:'대한전선', ticker:'001440', side:'buy', qty:92, price:13850, amount:1274200 },
    { date:'2026.06.02', time:'09:05', name:'코스맥스', ticker:'192820', side:'sell', qty:5, price:254500, amount:1272500 },
  ];

  // 주문내역 — most recent rebalance plan/execution
  const orders = [
    { date:'2026.06.16', name:'제이브이엠', ticker:'281820', side:'buy', qty:38, price:33600, status:'filled', reason:'신규 편입 · 랭크 18위' },
    { date:'2026.06.16', name:'수산세보틱스', ticker:'017550', side:'buy', qty:474, price:2695, status:'filled', reason:'신규 편입 · 랭크 26위' },
    { date:'2026.06.16', name:'보성파워텍', ticker:'006910', side:'sell', qty:210, price:6080, status:'filled', reason:'랭크 이탈 · 비중 축소' },
    { date:'2026.06.16', name:'한컴', ticker:'092790', side:'sell', qty:55, price:23200, status:'filled', reason:'랭크 이탈' },
    { date:'2026.06.16', name:'에이피알', ticker:'278470', side:'sell', qty:7, price:182300, status:'filled', reason:'스탑로스 · 익절' },
    { date:'2026.06.16', name:'롯데웰푸드', ticker:'382800', side:'sell', qty:11, price:116000, status:'filled', reason:'랭크 이탈' },
  ];

  // 예상 배당금 — dividend forecast
  const dividends = [
    { name:'KT&G', ticker:'033780', qty:13, dps:5200, total:67600, yield:2.77, payMonth:'4월', exDate:'2026.12.27' },
    { name:'기아', ticker:'000270', qty:15, dps:6500, total:97500, yield:3.82, payMonth:'4월', exDate:'2026.12.30' },
    { name:'코리안리', ticker:'003690', qty:92, dps:850, total:78200, yield:6.05, payMonth:'4월', exDate:'2026.12.27' },
    { name:'삼성물산', ticker:'028260', qty:3, dps:4300, total:12900, yield:0.87, payMonth:'4월', exDate:'2026.12.30' },
    { name:'현대모비스', ticker:'012330', qty:2, dps:4500, total:9000, yield:0.68, payMonth:'4월', exDate:'2026.12.30' },
    { name:'KCC', ticker:'002380', qty:3, dps:10000, total:30000, yield:1.77, payMonth:'4월', exDate:'2026.12.27' },
    { name:'KT&G(중간)', ticker:'033780', qty:13, dps:1200, total:15600, yield:0.64, payMonth:'8월', exDate:'2026.06.30' },
    { name:'효성', ticker:'004800', qty:10, dps:5000, total:50000, yield:2.51, payMonth:'4월', exDate:'2026.12.27' },
  ];

  // 리포트 — broker research summaries (from hankyung/mirae overlays)
  const reports = [
    { date:'2026.06.16', name:'삼성E&A', ticker:'028050', broker:'한경컨센서스', opinion:'positive', confidence:1.0, target:73000, title:'뭘 고를지 몰라 다 준비해봤어', thesis:'삼성E&A를 건설업종 최선호주로, 투자의견 매수, 목표주가 73,000원 제시.', risk:'중동 발주 둔화 + 저가 수주', held:true },
    { date:'2026.06.16', name:'현대모비스', ticker:'012330', broker:'한경컨센서스', opinion:'positive', confidence:1.0, target:null, title:'로봇 하드웨어 티어 1 공급자의 길', thesis:'BD의 중장기 생산량 확대가 휴머노이드 핵심부품 매출 성장으로 이어진다.', risk:'로봇 하드웨어 공급자 경쟁 심화', held:true },
    { date:'2026.06.16', name:'현대건설', ticker:'000720', broker:'한경컨센서스', opinion:'positive', confidence:1.0, target:195000, title:'원전으로 한 번 더 도약', thesis:'글로벌 원전 시장 확대 수혜 기대, 목표주가 195,000원으로 커버리지 개시.', risk:'국내 발주 둔화 우려', held:false },
    { date:'2026.06.11', name:'산일전기', ticker:'062040', broker:'미래에셋', opinion:'positive', confidence:1.0, target:null, title:'Bloom으로 열린 성장, 밸류에이션은 아직 낮다', thesis:'변압기 매출 확대와 생산 효율화가 이익 성장을 견인할 전망.', risk:'2027F PER 23배 수준', held:true },
    { date:'2026.06.11', name:'NAVER', ticker:'035420', broker:'한경컨센서스', opinion:'positive', confidence:1.0, target:null, title:'긍정적 모멘텀 추가', thesis:'인프라 외부 공급 확대로 중장기 신규 성장 동력·수익성 개선에 기여.', risk:'글로벌 AI 서비스 경쟁', held:false },
    { date:'2026.06.16', name:'대덕전자', ticker:'353200', broker:'미래에셋', opinion:'positive', confidence:1.0, target:null, title:'아직도 전반전', thesis:'FC-BGA 가동률 80% 육박, 전방 업황 회복과 증설 효과 지속.', risk:'중립 비중 10% 내외', held:false },
    { date:'2026.06.16', name:'네패스', ticker:'033640', broker:'한경컨센서스', opinion:'mixed', confidence:0.9, target:null, title:'Fab tour 후기', thesis:'CPB 기술력 기반 긍정적 체질 개선, 세 가지 성장 축 제시.', risk:'하반기 모바일 반도체 수요 둔화', held:false },
    { date:'2026.06.15', name:'POSCO홀딩스', ticker:'005490', broker:'미래에셋', opinion:'positive', confidence:1.0, target:null, title:'자회사 호조가 주가를 지지할 전망', thesis:'자회사 호조가 주가를 지지하나 본업 철강 개선은 여전히 더디다.', risk:'글로벌 무역 장벽 강화', held:false },
  ];

  // 수익분석 — factor budget for the whole portfolio (avg)
  const factorBudget = [
    { key:'value', label:'가치 Value', score:18.2, max:25 },
    { key:'quality', label:'퀄리티 Quality', score:14.6, max:25 },
    { key:'momentum', label:'모멘텀 Momentum', score:13.8, max:20 },
    { key:'yield', label:'배당 Yield', score:3.7, max:5 },
    { key:'technical', label:'기술적 Technical', score:11.1, max:15 },
    { key:'auxiliary', label:'보조 Auxiliary', score:1.6, max:10 },
  ];

  // sector allocation
  const sectors = [
    { label:'지주', value:18.9, color:'var(--blue-500)' },
    { label:'자동차/부품', value:15.0, color:'var(--red-500)' },
    { label:'전기장비', value:9.0, color:'var(--green-500)' },
    { label:'해운', value:8.5, color:'var(--amber-500)' },
    { label:'소재/화학', value:7.2, color:'var(--purple-500)' },
    { label:'기타', value:41.4, color:'var(--grey-300)' },
  ];

  window.QB_DATA = { won, summary, market, equityCurve, equityLabels, positions, transactions, orders, dividends, reports, factorBudget, sectors };
})();
