/* @ds-bundle: {"format":3,"namespace":"QuntbotDesignSystem_ce5871","components":[{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"TickerBadge","sourcePath":"components/core/TickerBadge.jsx"},{"name":"DeltaValue","sourcePath":"components/data/DeltaValue.jsx"},{"name":"Donut","sourcePath":"components/data/Donut.jsx"},{"name":"FactorBar","sourcePath":"components/data/FactorBar.jsx"},{"name":"Sparkline","sourcePath":"components/data/Sparkline.jsx"},{"name":"StatTile","sourcePath":"components/data/StatTile.jsx"},{"name":"SegmentedControl","sourcePath":"components/navigation/SegmentedControl.jsx"},{"name":"Tabs","sourcePath":"components/navigation/Tabs.jsx"}],"sourceHashes":{"components/core/Badge.jsx":"e18c4c166d82","components/core/Button.jsx":"ca258b5d6564","components/core/Card.jsx":"24d350a61eae","components/core/TickerBadge.jsx":"239a12f44d23","components/data/DeltaValue.jsx":"8b2b86fd34f2","components/data/Donut.jsx":"ce965a168ab1","components/data/FactorBar.jsx":"da2c72abd4f2","components/data/Sparkline.jsx":"c7c58a123594","components/data/StatTile.jsx":"50b34dfa8fbe","components/navigation/SegmentedControl.jsx":"21d23b0e08a9","components/navigation/Tabs.jsx":"b2499bcc26e4","ui_kits/toss-invest/AnalysisScreen.jsx":"84e9abea7606","ui_kits/toss-invest/AppShell.jsx":"98876a6203bc","ui_kits/toss-invest/AssetScreen.jsx":"4c08c9f3fc25","ui_kits/toss-invest/DividendScreen.jsx":"70accee0f03e","ui_kits/toss-invest/OrderScreen.jsx":"a12fc3020c11","ui_kits/toss-invest/ReportScreen.jsx":"ad0e0902b40b","ui_kits/toss-invest/TransactionScreen.jsx":"d0b040a19dca","ui_kits/toss-invest/data.js":"2f2f4f573c5d","ui_kits/toss-invest/icons.jsx":"fb72dfd0f0a1"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.QuntbotDesignSystem_ce5871 = window.QuntbotDesignSystem_ce5871 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Small status / opinion pill. Tones map to quntbot semantics:
 * buy(매수)=red, sell(매도)=blue, hold(중립)=grey, plus neutral
 * info/success/warn variants.
 */
function Badge({
  children,
  tone = 'neutral',
  size = 'md',
  solid = false,
  style = {},
  ...rest
}) {
  const tones = {
    buy: {
      soft: ['var(--red-50)', 'var(--red-600)'],
      solid: ['var(--red-500)', '#fff']
    },
    sell: {
      soft: ['var(--blue-50)', 'var(--blue-700)'],
      solid: ['var(--blue-500)', '#fff']
    },
    hold: {
      soft: ['var(--grey-100)', 'var(--grey-700)'],
      solid: ['var(--grey-600)', '#fff']
    },
    info: {
      soft: ['var(--blue-50)', 'var(--blue-700)'],
      solid: ['var(--blue-500)', '#fff']
    },
    success: {
      soft: ['var(--green-50)', '#0e9b63'],
      solid: ['var(--green-500)', '#fff']
    },
    warn: {
      soft: ['var(--amber-50)', '#b06800'],
      solid: ['var(--amber-500)', '#fff']
    },
    research: {
      soft: ['var(--purple-50)', '#6d3fd4'],
      solid: ['var(--purple-500)', '#fff']
    },
    neutral: {
      soft: ['var(--grey-100)', 'var(--grey-600)'],
      solid: ['var(--grey-700)', '#fff']
    }
  };
  const t = tones[tone] || tones.neutral;
  const [bg, fg] = solid ? t.solid : t.soft;
  const sizes = {
    sm: {
      fontSize: 11,
      padding: '2px 7px',
      radius: 6
    },
    md: {
      fontSize: 12,
      padding: '4px 9px',
      radius: 7
    },
    lg: {
      fontSize: 13,
      padding: '5px 11px',
      radius: 8
    }
  };
  const s = sizes[size] || sizes.md;
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      background: bg,
      color: fg,
      fontFamily: 'var(--font-sans)',
      fontSize: s.fontSize,
      fontWeight: 'var(--fw-semibold)',
      lineHeight: 1,
      padding: s.padding,
      borderRadius: s.radius,
      whiteSpace: 'nowrap',
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * quntbot primary button. Toss-style: bold weight, 12px radius,
 * soft press scale, blue primary fill.
 */
function Button({
  children,
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  disabled = false,
  iconLeft = null,
  iconRight = null,
  style = {},
  ...rest
}) {
  const sizes = {
    sm: {
      padding: '0 14px',
      height: 36,
      fontSize: 14,
      radius: 'var(--r-sm)'
    },
    md: {
      padding: '0 18px',
      height: 44,
      fontSize: 15,
      radius: 'var(--r-md)'
    },
    lg: {
      padding: '0 24px',
      height: 54,
      fontSize: 17,
      radius: 'var(--r-lg)'
    }
  };
  const variants = {
    primary: {
      background: 'var(--action-primary)',
      color: 'var(--text-on-accent)',
      border: '1px solid transparent'
    },
    secondary: {
      background: 'var(--grey-100)',
      color: 'var(--grey-800)',
      border: '1px solid transparent'
    },
    tonal: {
      background: 'var(--action-primary-soft)',
      color: 'var(--action-primary)',
      border: '1px solid transparent'
    },
    ghost: {
      background: 'transparent',
      color: 'var(--grey-700)',
      border: '1px solid transparent'
    },
    outline: {
      background: 'var(--surface-card)',
      color: 'var(--grey-800)',
      border: '1px solid var(--border-strong)'
    }
  };
  const s = sizes[size] || sizes.md;
  const v = variants[variant] || variants.primary;
  return /*#__PURE__*/React.createElement("button", _extends({
    disabled: disabled,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 8,
      height: s.height,
      padding: s.padding,
      width: fullWidth ? '100%' : 'auto',
      fontFamily: 'var(--font-sans)',
      fontSize: s.fontSize,
      fontWeight: 'var(--fw-semibold)',
      letterSpacing: 'var(--ls-snug)',
      borderRadius: s.radius,
      cursor: disabled ? 'not-allowed' : 'pointer',
      opacity: disabled ? 0.4 : 1,
      transition: 'transform var(--dur-fast) var(--ease-out), background var(--dur-fast) var(--ease-out), filter var(--dur-fast)',
      ...v,
      ...style
    },
    onMouseDown: e => {
      if (!disabled) e.currentTarget.style.transform = 'scale(0.97)';
    },
    onMouseUp: e => {
      e.currentTarget.style.transform = 'scale(1)';
    },
    onMouseLeave: e => {
      e.currentTarget.style.transform = 'scale(1)';
    }
  }, rest), iconLeft, children, iconRight);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/**
 * Surface container. Default white, 16px radius, hairline border,
 * optional soft shadow and hover lift (for clickable cards).
 */
function Card({
  children,
  padding = 24,
  interactive = false,
  shadow = 'none',
  style = {},
  ...rest
}) {
  const shadows = {
    none: 'none',
    sm: 'var(--shadow-sm)',
    md: 'var(--shadow-md)',
    lg: 'var(--shadow-lg)'
  };
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      background: 'var(--surface-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: 'var(--r-lg)',
      padding,
      boxShadow: shadows[shadow] || 'none',
      transition: 'transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base) var(--ease-out)',
      cursor: interactive ? 'pointer' : 'default',
      ...style
    },
    onMouseEnter: interactive ? e => {
      e.currentTarget.style.boxShadow = 'var(--shadow-md)';
      e.currentTarget.style.transform = 'translateY(-2px)';
    } : undefined,
    onMouseLeave: interactive ? e => {
      e.currentTarget.style.boxShadow = shadows[shadow] || 'none';
      e.currentTarget.style.transform = 'translateY(0)';
    } : undefined
  }, rest), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/TickerBadge.jsx
try { (() => {
const PALETTE = [['#e8f3ff', '#2272eb'], ['#fdeced', '#e42939'], ['#e7f9f1', '#0e9b63'], ['#fff4e0', '#b06800'], ['#f1ecfe', '#6d3fd4'], ['#e5f6fb', '#0f8fb5'], ['#fdeef6', '#c43d8b'], ['#eef2f6', '#4e5968']];

/**
 * Round ticker chip — colored monogram derived from the stock
 * name, in the spirit of Toss's per-stock logo circles. Pass
 * `src` to use a real logo image instead.
 */
function TickerBadge({
  name = '',
  ticker = '',
  src = null,
  size = 40,
  style = {}
}) {
  const seed = (ticker || name).split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  const [bg, fg] = PALETTE[seed % PALETTE.length];
  const glyph = (name || ticker || '?').trim().charAt(0);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      width: size,
      height: size,
      flex: `0 0 ${size}px`,
      borderRadius: '50%',
      background: src ? 'var(--grey-100)' : bg,
      color: fg,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      fontFamily: 'var(--font-sans)',
      fontSize: size * 0.42,
      fontWeight: 'var(--fw-bold)',
      overflow: 'hidden',
      ...style
    }
  }, src ? /*#__PURE__*/React.createElement("img", {
    src: src,
    alt: name,
    style: {
      width: '100%',
      height: '100%',
      objectFit: 'cover'
    }
  }) : glyph);
}
Object.assign(__ds_scope, { TickerBadge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/TickerBadge.jsx", error: String((e && e.message) || e) }); }

// components/data/DeltaValue.jsx
try { (() => {
/**
 * Signed numeric value with Korean-market direction color
 * (up=red, down=blue) and an optional triangle marker.
 * Use for P/L, daily change, and percentages.
 */
function DeltaValue({
  value = 0,
  percent = false,
  showArrow = true,
  showSign = true,
  prefix = '',
  suffix = '',
  size = 15,
  weight = 'var(--fw-semibold)',
  style = {}
}) {
  const dir = value > 0 ? 'up' : value < 0 ? 'down' : 'flat';
  const color = dir === 'up' ? 'var(--up)' : dir === 'down' ? 'var(--down)' : 'var(--flat)';
  const arrow = dir === 'up' ? '▲' : dir === 'down' ? '▼' : '–';
  const abs = Math.abs(value);
  const formatted = abs.toLocaleString('ko-KR', {
    maximumFractionDigits: percent ? 2 : 0,
    minimumFractionDigits: percent ? 2 : 0
  });
  const sign = showSign && !showArrow ? value > 0 ? '+' : value < 0 ? '-' : '' : '';
  return /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 3,
      color,
      fontSize: size,
      fontWeight: weight,
      ...style
    }
  }, showArrow && dir !== 'flat' && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: size * 0.62
    }
  }, arrow), prefix, sign, formatted, percent ? '%' : '', suffix);
}
Object.assign(__ds_scope, { DeltaValue });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/DeltaValue.jsx", error: String((e && e.message) || e) }); }

// components/data/Donut.jsx
try { (() => {
/**
 * Allocation donut. `segments` = [{ label, value, color }].
 * Renders a clean ring with an optional center label.
 */
function Donut({
  segments = [],
  size = 160,
  thickness = 22,
  centerLabel = null,
  centerSub = null,
  gap = 2,
  style = {}
}) {
  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  let offset = 0;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      width: size,
      height: size,
      ...style
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: size,
    height: size,
    style: {
      transform: 'rotate(-90deg)'
    }
  }, /*#__PURE__*/React.createElement("circle", {
    cx: size / 2,
    cy: size / 2,
    r: r,
    fill: "none",
    stroke: "var(--grey-100)",
    strokeWidth: thickness
  }), segments.map((s, i) => {
    const frac = s.value / total;
    const len = Math.max(0, frac * c - gap);
    const dash = `${len} ${c - len}`;
    const el = /*#__PURE__*/React.createElement("circle", {
      key: i,
      cx: size / 2,
      cy: size / 2,
      r: r,
      fill: "none",
      stroke: s.color,
      strokeWidth: thickness,
      strokeDasharray: dash,
      strokeDashoffset: -offset,
      strokeLinecap: "round"
    });
    offset += frac * c;
    return el;
  })), (centerLabel || centerSub) && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 2
    }
  }, centerSub && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--fs-caption)',
      color: 'var(--text-tertiary)'
    }
  }, centerSub), centerLabel && /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      fontSize: 'var(--fs-h3)',
      fontWeight: 'var(--fw-bold)',
      color: 'var(--text-strong)',
      letterSpacing: 'var(--ls-tight)'
    }
  }, centerLabel)));
}
Object.assign(__ds_scope, { Donut });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/Donut.jsx", error: String((e && e.message) || e) }); }

// components/data/FactorBar.jsx
try { (() => {
const FACTOR_COLORS = {
  value: 'var(--blue-500)',
  quality: 'var(--green-500)',
  momentum: 'var(--red-500)',
  yield: 'var(--amber-500)',
  technical: 'var(--purple-500)',
  auxiliary: 'var(--grey-500)'
};

/**
 * Labeled factor-score bar for quntbot's 100-point factor budget
 * (Value 25 / Quality 25 / Momentum 20 / Yield 5 / Technical 15 /
 * Auxiliary 10). Pass `factor` for an auto color, or `color`.
 */
function FactorBar({
  label,
  score = 0,
  max = 25,
  factor = null,
  color = null,
  showValue = true,
  style = {}
}) {
  const pct = Math.max(0, Math.min(100, score / max * 100));
  const fill = color || factor && FACTOR_COLORS[factor] || 'var(--blue-500)';
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'baseline'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--fs-caption)',
      color: 'var(--text-secondary)',
      fontWeight: 'var(--fw-medium)'
    }
  }, label), showValue && /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      fontSize: 'var(--fs-caption)',
      color: 'var(--text-body)',
      fontWeight: 'var(--fw-semibold)'
    }
  }, score.toFixed(1), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--text-tertiary)',
      fontWeight: 'var(--fw-regular)'
    }
  }, " / ", max))), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 8,
      borderRadius: 'var(--r-pill)',
      background: 'var(--grey-100)',
      overflow: 'hidden'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: `${pct}%`,
      height: '100%',
      borderRadius: 'var(--r-pill)',
      background: fill,
      transition: 'width var(--dur-slow) var(--ease-out)'
    }
  })));
}
Object.assign(__ds_scope, { FactorBar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/FactorBar.jsx", error: String((e && e.message) || e) }); }

// components/data/Sparkline.jsx
try { (() => {
/**
 * Lightweight area sparkline / line chart. Pass an array of
 * numbers; color follows up/down semantics by default (compares
 * last vs first), or set `color` explicitly.
 */
function Sparkline({
  data = [],
  width = 120,
  height = 40,
  color = null,
  fill = true,
  strokeWidth = 2,
  style = {}
}) {
  if (!data.length) return /*#__PURE__*/React.createElement("svg", {
    width: width,
    height: height,
    style: style
  });
  const min = Math.min(...data),
    max = Math.max(...data);
  const span = max - min || 1;
  const stepX = width / (data.length - 1 || 1);
  const pts = data.map((v, i) => [i * stepX, height - (v - min) / span * (height - 4) - 2]);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  const area = `${line} L${width} ${height} L0 ${height} Z`;
  const dir = data[data.length - 1] >= data[0] ? 'up' : 'down';
  const c = color || (dir === 'up' ? 'var(--up)' : 'var(--down)');
  const gid = 'spark-' + Math.random().toString(36).slice(2, 8);
  return /*#__PURE__*/React.createElement("svg", {
    width: width,
    height: height,
    style: style,
    preserveAspectRatio: "none"
  }, /*#__PURE__*/React.createElement("defs", null, /*#__PURE__*/React.createElement("linearGradient", {
    id: gid,
    x1: "0",
    y1: "0",
    x2: "0",
    y2: "1"
  }, /*#__PURE__*/React.createElement("stop", {
    offset: "0%",
    stopColor: c,
    stopOpacity: "0.18"
  }), /*#__PURE__*/React.createElement("stop", {
    offset: "100%",
    stopColor: c,
    stopOpacity: "0"
  }))), fill && /*#__PURE__*/React.createElement("path", {
    d: area,
    fill: `url(#${gid})`
  }), /*#__PURE__*/React.createElement("path", {
    d: line,
    fill: "none",
    stroke: c,
    strokeWidth: strokeWidth,
    strokeLinejoin: "round",
    strokeLinecap: "round"
  }));
}
Object.assign(__ds_scope, { Sparkline });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/Sparkline.jsx", error: String((e && e.message) || e) }); }

// components/data/StatTile.jsx
try { (() => {
/**
 * Compact KPI tile: caption label, large tabular value, and an
 * optional delta line. Used across 자산 / 수익분석 summary headers.
 */
function StatTile({
  label,
  value,
  delta = null,
  deltaPercent = false,
  sub = null,
  align = 'left',
  style = {}
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
      textAlign: align,
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--fs-caption)',
      color: 'var(--text-secondary)',
      fontWeight: 'var(--fw-medium)'
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      fontSize: 'var(--fs-h2)',
      fontWeight: 'var(--fw-bold)',
      color: 'var(--text-strong)',
      letterSpacing: 'var(--ls-tight)',
      lineHeight: 1.1
    }
  }, value), delta !== null && /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      gap: 6,
      alignItems: 'baseline',
      justifyContent: align === 'right' ? 'flex-end' : 'flex-start'
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.DeltaValue, {
    value: delta,
    percent: deltaPercent,
    size: 14
  }), sub && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--fs-caption)',
      color: 'var(--text-tertiary)'
    }
  }, sub)), delta === null && sub && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 'var(--fs-caption)',
      color: 'var(--text-tertiary)'
    }
  }, sub));
}
Object.assign(__ds_scope, { StatTile });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/data/StatTile.jsx", error: String((e && e.message) || e) }); }

// components/navigation/SegmentedControl.jsx
try { (() => {
/**
 * Segmented control / pill tabs. `items` = [{ key, label }] or
 * string[]. Controlled via `value` + `onChange`.
 */
function SegmentedControl({
  items = [],
  value,
  onChange = () => {},
  size = 'md',
  style = {}
}) {
  const opts = items.map(it => typeof it === 'string' ? {
    key: it,
    label: it
  } : it);
  const pads = {
    sm: '6px 12px',
    md: '8px 16px',
    lg: '10px 20px'
  };
  const fs = {
    sm: 13,
    md: 14,
    lg: 15
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'inline-flex',
      gap: 2,
      padding: 4,
      background: 'var(--grey-100)',
      borderRadius: 'var(--r-md)',
      ...style
    }
  }, opts.map(o => {
    const active = o.key === value;
    return /*#__PURE__*/React.createElement("button", {
      key: o.key,
      onClick: () => onChange(o.key),
      style: {
        border: 'none',
        cursor: 'pointer',
        padding: pads[size],
        fontSize: fs[size],
        fontFamily: 'var(--font-sans)',
        fontWeight: 'var(--fw-semibold)',
        borderRadius: 'var(--r-sm)',
        background: active ? 'var(--surface-card)' : 'transparent',
        color: active ? 'var(--text-strong)' : 'var(--text-secondary)',
        boxShadow: active ? 'var(--shadow-xs)' : 'none',
        transition: 'all var(--dur-fast) var(--ease-out)'
      }
    }, o.label);
  }));
}
Object.assign(__ds_scope, { SegmentedControl });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/SegmentedControl.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Tabs.jsx
try { (() => {
/**
 * Underline tabs (page-level navigation). `items` = [{ key, label }]
 * or string[]. Controlled via `value` + `onChange`.
 */
function Tabs({
  items = [],
  value,
  onChange = () => {},
  style = {}
}) {
  const opts = items.map(it => typeof it === 'string' ? {
    key: it,
    label: it
  } : it);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 4,
      borderBottom: '1px solid var(--border-subtle)',
      ...style
    }
  }, opts.map(o => {
    const active = o.key === value;
    return /*#__PURE__*/React.createElement("button", {
      key: o.key,
      onClick: () => onChange(o.key),
      style: {
        border: 'none',
        background: 'transparent',
        cursor: 'pointer',
        padding: '12px 16px',
        position: 'relative',
        whiteSpace: 'nowrap',
        fontFamily: 'var(--font-sans)',
        fontSize: 'var(--fs-title)',
        fontWeight: active ? 'var(--fw-bold)' : 'var(--fw-medium)',
        color: active ? 'var(--text-strong)' : 'var(--text-tertiary)',
        transition: 'color var(--dur-fast) var(--ease-out)'
      }
    }, o.label, active && /*#__PURE__*/React.createElement("span", {
      style: {
        position: 'absolute',
        left: 12,
        right: 12,
        bottom: -1,
        height: 2.5,
        background: 'var(--text-strong)',
        borderRadius: 2
      }
    }));
  }));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Tabs.jsx", error: String((e && e.message) || e) }); }

// ui_kits/toss-invest/AnalysisScreen.jsx
try { (() => {
/* 수익분석 — performance analysis. */
function AreaChart({
  data,
  labels,
  height = 240
}) {
  const NS = window.QuntbotDesignSystem_ce5871;
  const w = 760,
    pad = 8;
  const min = Math.min(...data) * 0.985,
    max = Math.max(...data) * 1.01;
  const span = max - min || 1;
  const stepX = (w - pad * 2) / (data.length - 1);
  const pts = data.map((v, i) => [pad + i * stepX, height - 28 - (v - min) / span * (height - 50)]);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  const area = `${line} L${pts[pts.length - 1][0]} ${height - 28} L${pts[0][0]} ${height - 28} Z`;
  const up = data[data.length - 1] >= data[0];
  const c = up ? 'var(--up)' : 'var(--down)';
  return /*#__PURE__*/React.createElement("svg", {
    viewBox: `0 0 ${w} ${height}`,
    width: "100%",
    style: {
      display: 'block'
    },
    preserveAspectRatio: "none"
  }, /*#__PURE__*/React.createElement("defs", null, /*#__PURE__*/React.createElement("linearGradient", {
    id: "ac",
    x1: "0",
    y1: "0",
    x2: "0",
    y2: "1"
  }, /*#__PURE__*/React.createElement("stop", {
    offset: "0%",
    stopColor: c,
    stopOpacity: "0.16"
  }), /*#__PURE__*/React.createElement("stop", {
    offset: "100%",
    stopColor: c,
    stopOpacity: "0"
  }))), [0, 0.5, 1].map((g, i) => /*#__PURE__*/React.createElement("line", {
    key: i,
    x1: pad,
    x2: w - pad,
    y1: 28 + g * (height - 56),
    y2: 28 + g * (height - 56),
    stroke: "var(--grey-100)",
    strokeWidth: "1"
  })), /*#__PURE__*/React.createElement("path", {
    d: area,
    fill: "url(#ac)"
  }), /*#__PURE__*/React.createElement("path", {
    d: line,
    fill: "none",
    stroke: c,
    strokeWidth: "2.5",
    strokeLinejoin: "round",
    strokeLinecap: "round"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: pts[pts.length - 1][0],
    cy: pts[pts.length - 1][1],
    r: "4.5",
    fill: c
  }), labels.map((l, i) => i % 2 === 0 && /*#__PURE__*/React.createElement("text", {
    key: i,
    x: pad + i * stepX,
    y: height - 8,
    fontSize: "11",
    fill: "var(--text-tertiary)",
    textAnchor: "middle",
    fontFamily: "var(--font-sans)"
  }, l)));
}
function AnalysisScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const {
    Card,
    StatTile,
    DeltaValue,
    FactorBar,
    SegmentedControl,
    TickerBadge,
    Badge
  } = NS;
  const {
    summary,
    equityCurve,
    equityLabels,
    factorBudget,
    positions,
    won
  } = window.QB_DATA;
  const [period, setPeriod] = React.useState('1Y');
  const gainers = [...positions].sort((a, b) => b.plRate - a.plRate).slice(0, 3);
  const losers = [...positions].sort((a, b) => a.plRate - b.plRate).slice(0, 3);
  const Mini = ({
    p
  }) => /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      padding: '9px 0'
    }
  }, /*#__PURE__*/React.createElement(TickerBadge, {
    name: p.name,
    ticker: p.ticker,
    size: 34
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      fontWeight: 600,
      color: 'var(--grey-900)'
    }
  }, p.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: 'var(--text-tertiary)'
    }
  }, won(p.value))), /*#__PURE__*/React.createElement(DeltaValue, {
    value: p.plRate,
    percent: true,
    size: 14.5
  }));
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4,1fr)',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: 22
  }, /*#__PURE__*/React.createElement(StatTile, {
    label: "\uCD1D \uD3C9\uAC00\uC190\uC775",
    value: won(summary.totalPL),
    delta: summary.totalPLRate,
    deltaPercent: true
  })), /*#__PURE__*/React.createElement(Card, {
    padding: 22
  }, /*#__PURE__*/React.createElement(StatTile, {
    label: "\uB204\uC801 \uC218\uC775\uB960",
    value: "+9.50%",
    sub: "2024.07 \uC6B4\uC6A9 \uAC1C\uC2DC"
  })), /*#__PURE__*/React.createElement(Card, {
    padding: 22
  }, /*#__PURE__*/React.createElement(StatTile, {
    label: "\uC2E4\uD604\uC190\uC775",
    value: "\u20A90",
    sub: "\uC774\uBC88 \uBD84\uAE30"
  })), /*#__PURE__*/React.createElement(Card, {
    padding: 22
  }, /*#__PURE__*/React.createElement(StatTile, {
    label: "\uCD94\uC815 MDD",
    value: "\u221212.4%",
    sub: "\uBC31\uD14C\uC2A4\uD2B8 \uAE30\uC900"
  }))), /*#__PURE__*/React.createElement(Card, {
    padding: 24
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      marginBottom: 8
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 16,
      fontWeight: 800,
      color: 'var(--grey-900)'
    }
  }, "\uD3C9\uAC00\uAE08\uC561 \uCD94\uC774"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: 10,
      marginTop: 6
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      fontSize: 26,
      fontWeight: 800,
      color: 'var(--grey-900)',
      letterSpacing: '-.03em'
    }
  }, won(summary.totalAsset)), /*#__PURE__*/React.createElement(DeltaValue, {
    value: 21.5,
    percent: true,
    size: 15
  }))), /*#__PURE__*/React.createElement(SegmentedControl, {
    size: "sm",
    value: period,
    onChange: setPeriod,
    items: ['3M', '6M', '1Y', '전체']
  })), /*#__PURE__*/React.createElement(AreaChart, {
    data: equityCurve,
    labels: equityLabels
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1.1fr 1fr',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: 24
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 16,
      fontWeight: 800,
      color: 'var(--grey-900)',
      marginBottom: 4
    }
  }, "\uD329\uD130 \uBC30\uBD84"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      color: 'var(--text-tertiary)',
      marginBottom: 18
    }
  }, "100\uC810 \uD329\uD130 \uC608\uC0B0 \xB7 \uD3EC\uD2B8\uD3F4\uB9AC\uC624 \uD3C9\uADE0"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 14
    }
  }, factorBudget.map(f => /*#__PURE__*/React.createElement(FactorBar, {
    key: f.key,
    label: f.label,
    score: f.score,
    max: f.max,
    factor: f.key
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateRows: '1fr 1fr',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: '18px 24px'
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 7,
      marginBottom: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 14.5,
      fontWeight: 800,
      color: 'var(--grey-900)'
    }
  }, "\uC218\uC775 \uC0C1\uC704"), /*#__PURE__*/React.createElement(Badge, {
    tone: "buy",
    size: "sm"
  }, "TOP 3")), gainers.map(p => /*#__PURE__*/React.createElement(Mini, {
    key: p.ticker,
    p: p
  }))), /*#__PURE__*/React.createElement(Card, {
    padding: '18px 24px'
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 7,
      marginBottom: 2
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 14.5,
      fontWeight: 800,
      color: 'var(--grey-900)'
    }
  }, "\uC218\uC775 \uD558\uC704"), /*#__PURE__*/React.createElement(Badge, {
    tone: "sell",
    size: "sm"
  }, "BOTTOM 3")), losers.map(p => /*#__PURE__*/React.createElement(Mini, {
    key: p.ticker,
    p: p
  }))))));
}
window.AnalysisScreen = AnalysisScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/toss-invest/AnalysisScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/toss-invest/AppShell.jsx
try { (() => {
/* App shell: left sidebar + sticky top bar, Toss-web style. */
const QB_NAV = [{
  key: 'asset',
  label: '자산',
  icon: 'wallet'
}, {
  key: 'analysis',
  label: '수익분석',
  icon: 'pie'
}, {
  key: 'transactions',
  label: '거래내역',
  icon: 'receipt'
}, {
  key: 'orders',
  label: '주문내역',
  icon: 'list'
}, {
  key: 'dividends',
  label: '예상 배당금',
  icon: 'coins'
}, {
  key: 'reports',
  label: '리포트',
  icon: 'file'
}];
function Logo() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 9
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 30,
      height: 30,
      borderRadius: 9,
      background: 'var(--blue-500)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#fff',
      fontWeight: 800,
      fontSize: 17,
      letterSpacing: '-.04em'
    }
  }, "q"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 19,
      fontWeight: 800,
      color: 'var(--grey-900)',
      letterSpacing: '-.03em'
    }
  }, "quntbot"));
}
function Sidebar({
  active,
  onNav
}) {
  const {
    QBIcon
  } = window;
  return /*#__PURE__*/React.createElement("aside", {
    style: {
      width: 'var(--sidebar-w)',
      flex: '0 0 var(--sidebar-w)',
      height: '100vh',
      position: 'sticky',
      top: 0,
      background: 'var(--surface-card)',
      borderRight: '1px solid var(--border-subtle)',
      display: 'flex',
      flexDirection: 'column',
      padding: '22px 14px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '0 10px 22px'
    }
  }, /*#__PURE__*/React.createElement(Logo, null)), /*#__PURE__*/React.createElement("nav", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 2
    }
  }, QB_NAV.map(n => {
    const on = n.key === active;
    return /*#__PURE__*/React.createElement("button", {
      key: n.key,
      onClick: () => onNav(n.key),
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '11px 12px',
        border: 'none',
        borderRadius: 'var(--r-md)',
        cursor: 'pointer',
        textAlign: 'left',
        background: on ? 'var(--action-primary-soft)' : 'transparent',
        color: on ? 'var(--action-primary)' : 'var(--text-secondary)',
        fontFamily: 'var(--font-sans)',
        fontSize: 15,
        fontWeight: on ? 700 : 500,
        transition: 'background var(--dur-fast) var(--ease-out)'
      },
      onMouseEnter: e => {
        if (!on) e.currentTarget.style.background = 'var(--grey-50)';
      },
      onMouseLeave: e => {
        if (!on) e.currentTarget.style.background = 'transparent';
      }
    }, /*#__PURE__*/React.createElement(QBIcon, {
      name: n.icon,
      size: 21,
      strokeWidth: on ? 2.4 : 2
    }), n.label);
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      marginTop: 'auto',
      padding: '14px 12px',
      borderRadius: 'var(--r-md)',
      background: 'var(--grey-50)',
      display: 'flex',
      gap: 10,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(QBIcon, {
    name: "shield",
    size: 20,
    color: "var(--green-500)"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      lineHeight: 1.4,
      color: 'var(--text-secondary)'
    }
  }, /*#__PURE__*/React.createElement("b", {
    style: {
      color: 'var(--grey-800)'
    }
  }, "PAPER \uBAA8\uB4DC"), /*#__PURE__*/React.createElement("br", null), "\uBAA8\uC758\uD22C\uC790\uB85C \uC548\uC804\uD558\uAC8C \uC6B4\uC6A9 \uC911")));
}
function TopBar({
  title
}) {
  const {
    QBIcon
  } = window;
  const {
    market
  } = window.QB_DATA;
  const Idx = ({
    label,
    v,
    chg
  }) => /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'baseline',
      gap: 6,
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12.5,
      color: 'var(--text-tertiary)',
      fontWeight: 600
    }
  }, label), /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      fontSize: 13.5,
      fontWeight: 700,
      color: 'var(--grey-800)'
    }
  }, v.toLocaleString('ko-KR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })), /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      fontSize: 12.5,
      fontWeight: 700,
      color: chg >= 0 ? 'var(--up)' : 'var(--down)'
    }
  }, chg >= 0 ? '+' : '', chg.toFixed(2), "%"));
  return /*#__PURE__*/React.createElement("header", {
    style: {
      height: 'var(--header-h)',
      position: 'sticky',
      top: 0,
      zIndex: 10,
      background: 'rgba(255,255,255,0.82)',
      backdropFilter: 'saturate(180%) blur(12px)',
      borderBottom: '1px solid var(--border-subtle)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 24,
      padding: '0 32px'
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      margin: 0,
      fontSize: 20,
      fontWeight: 800,
      color: 'var(--grey-900)',
      letterSpacing: '-.03em',
      whiteSpace: 'nowrap'
    }
  }, title), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 22,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 18
    }
  }, /*#__PURE__*/React.createElement(Idx, {
    label: "\uCF54\uC2A4\uD53C",
    v: market.kospi.value,
    chg: market.kospi.chg
  }), /*#__PURE__*/React.createElement(Idx, {
    label: "\uCF54\uC2A4\uB2E5",
    v: market.kosdaq.value,
    chg: market.kosdaq.chg
  }), /*#__PURE__*/React.createElement(Idx, {
    label: "\uD658\uC728",
    v: market.usdkrw.value,
    chg: market.usdkrw.chg
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 6
    }
  }, /*#__PURE__*/React.createElement("button", {
    style: iconBtn
  }, /*#__PURE__*/React.createElement(QBIcon, {
    name: "search",
    size: 20,
    color: "var(--grey-600)"
  })), /*#__PURE__*/React.createElement("button", {
    style: iconBtn
  }, /*#__PURE__*/React.createElement(QBIcon, {
    name: "bell",
    size: 20,
    color: "var(--grey-600)"
  })))));
}
const iconBtn = {
  width: 38,
  height: 38,
  borderRadius: 'var(--r-md)',
  border: 'none',
  background: 'transparent',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center'
};
function AppShell({
  active,
  onNav,
  title,
  children
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      minHeight: '100vh',
      background: 'var(--bg-app)'
    }
  }, /*#__PURE__*/React.createElement(Sidebar, {
    active: active,
    onNav: onNav
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0,
      display: 'flex',
      flexDirection: 'column'
    }
  }, /*#__PURE__*/React.createElement(TopBar, {
    title: title
  }), /*#__PURE__*/React.createElement("main", {
    style: {
      flex: 1,
      padding: '28px 32px 56px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 'var(--content-max)',
      margin: '0 auto'
    }
  }, children))));
}
window.AppShell = AppShell;
window.QB_NAV = QB_NAV;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/toss-invest/AppShell.jsx", error: String((e && e.message) || e) }); }

// ui_kits/toss-invest/AssetScreen.jsx
try { (() => {
/* 자산 — portfolio overview (hero). */
function AssetScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const {
    StatTile,
    DeltaValue,
    Donut,
    Sparkline,
    TickerBadge,
    Badge,
    FactorBar,
    SegmentedControl,
    Card
  } = NS;
  const {
    QBIcon
  } = window;
  const {
    summary,
    positions,
    sectors,
    won
  } = window.QB_DATA;
  const [sort, setSort] = React.useState('plRate');
  const [open, setOpen] = React.useState(null);
  const sorted = [...positions].sort((a, b) => (b[sort] || 0) - (a[sort] || 0));
  const SortLabels = {
    plRate: '수익률',
    value: '평가금액',
    weight: '비중'
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1.55fr 1fr',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: 28,
    style: {
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      color: 'var(--text-secondary)',
      fontWeight: 600,
      marginBottom: 8
    }
  }, "\uB0B4 \uD22C\uC790 \uC790\uC0B0"), /*#__PURE__*/React.createElement("div", {
    className: "num",
    style: {
      fontSize: 38,
      fontWeight: 800,
      color: 'var(--grey-900)',
      letterSpacing: '-.03em',
      lineHeight: 1.05
    }
  }, won(summary.totalAsset)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 16,
      marginTop: 12,
      alignItems: 'baseline'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      gap: 6,
      alignItems: 'baseline'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13.5,
      color: 'var(--text-tertiary)'
    }
  }, "\uD3C9\uAC00\uC190\uC775"), /*#__PURE__*/React.createElement(DeltaValue, {
    value: summary.totalPL,
    prefix: "\u20A9",
    showArrow: false,
    size: 16
  }), /*#__PURE__*/React.createElement(DeltaValue, {
    value: summary.totalPLRate,
    percent: true,
    size: 15
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      gap: 6,
      alignItems: 'baseline'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13.5,
      color: 'var(--text-tertiary)'
    }
  }, "\uC624\uB298"), /*#__PURE__*/React.createElement(DeltaValue, {
    value: summary.dayPL,
    prefix: "\u20A9",
    showArrow: false,
    size: 15
  }), /*#__PURE__*/React.createElement(DeltaValue, {
    value: summary.dayPLRate,
    percent: true,
    size: 14
  })))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4,1fr)',
      gap: 16,
      marginTop: 24,
      paddingTop: 20,
      borderTop: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement(StatTile, {
    label: "\uC8FC\uC2DD \uD3C9\uAC00\uAE08\uC561",
    value: won(summary.stockValue)
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "\uC608\uC218\uAE08",
    value: won(summary.cash)
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "\uB9E4\uC785\uAE08\uC561",
    value: won(summary.totalCost)
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "\uBCF4\uC720 \uC885\uBAA9",
    value: summary.holdingCount + '개'
  }))), /*#__PURE__*/React.createElement(Card, {
    padding: 24
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 15,
      fontWeight: 700,
      color: 'var(--grey-900)',
      marginBottom: 4
    }
  }, "\uC790\uC0B0 \uBE44\uC911"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 18
    }
  }, /*#__PURE__*/React.createElement(Donut, {
    size: 132,
    thickness: 20,
    centerSub: "\uC8FC\uC2DD",
    centerLabel: "66%",
    segments: [{
      label: '주식',
      value: summary.stockValue,
      color: 'var(--blue-500)'
    }, {
      label: '현금',
      value: summary.cash,
      color: 'var(--grey-200)'
    }]
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
      flex: 1
    }
  }, sectors.slice(0, 5).map(s => /*#__PURE__*/React.createElement("div", {
    key: s.label,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 9,
      height: 9,
      borderRadius: 3,
      background: s.color
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13,
      color: 'var(--text-body)',
      flex: 1
    }
  }, s.label), /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      fontSize: 13,
      fontWeight: 600,
      color: 'var(--grey-800)'
    }
  }, s.value.toFixed(1), "%"))))))), /*#__PURE__*/React.createElement(Card, {
    padding: 0
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '20px 24px 16px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 17,
      fontWeight: 800,
      color: 'var(--grey-900)'
    }
  }, "\uBCF4\uC720 \uC885\uBAA9 ", /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      color: 'var(--text-tertiary)'
    }
  }, positions.length)), /*#__PURE__*/React.createElement(SegmentedControl, {
    size: "sm",
    value: sort,
    onChange: setSort,
    items: Object.keys(SortLabels).map(k => ({
      key: k,
      label: SortLabels[k]
    }))
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 96px 150px 96px',
      padding: '0 24px 10px',
      fontSize: 12.5,
      color: 'var(--text-tertiary)',
      fontWeight: 600,
      borderBottom: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "\uC885\uBAA9"), /*#__PURE__*/React.createElement("span", {
    style: {
      textAlign: 'right'
    }
  }, "\uCD94\uC138"), /*#__PURE__*/React.createElement("span", {
    style: {
      textAlign: 'right'
    }
  }, "\uD3C9\uAC00\uAE08\uC561"), /*#__PURE__*/React.createElement("span", {
    style: {
      textAlign: 'right'
    }
  }, "\uC218\uC775\uB960")), sorted.map(p => {
    const on = open === p.ticker;
    return /*#__PURE__*/React.createElement("div", {
      key: p.ticker,
      style: {
        borderBottom: '1px solid var(--grey-50)'
      }
    }, /*#__PURE__*/React.createElement("div", {
      onClick: () => setOpen(on ? null : p.ticker),
      style: {
        display: 'grid',
        gridTemplateColumns: '1fr 96px 150px 96px',
        alignItems: 'center',
        padding: '14px 24px',
        cursor: 'pointer'
      },
      onMouseEnter: e => e.currentTarget.style.background = 'var(--grey-50)',
      onMouseLeave: e => e.currentTarget.style.background = 'transparent'
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 12
      }
    }, /*#__PURE__*/React.createElement(TickerBadge, {
      name: p.name,
      ticker: p.ticker,
      size: 40
    }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 7
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 15,
        fontWeight: 700,
        color: 'var(--grey-900)'
      }
    }, p.name), p.rank && /*#__PURE__*/React.createElement(Badge, {
      tone: "hold",
      size: "sm"
    }, "\uB7AD\uD06C ", p.rank), p.status === 'executed' && /*#__PURE__*/React.createElement(Badge, {
      tone: "success",
      size: "sm"
    }, "\uC2E0\uADDC")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12.5,
        color: 'var(--text-tertiary)'
      }
    }, p.ticker, " \xB7 ", p.qty, "\uC8FC \xB7 \uBE44\uC911 ", p.weight.toFixed(1), "%"))), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        justifyContent: 'flex-end'
      }
    }, /*#__PURE__*/React.createElement(Sparkline, {
      data: p.spark,
      width: 84,
      height: 32
    })), /*#__PURE__*/React.createElement("div", {
      style: {
        textAlign: 'right'
      }
    }, /*#__PURE__*/React.createElement("div", {
      className: "num",
      style: {
        fontSize: 15,
        fontWeight: 700,
        color: 'var(--grey-900)'
      }
    }, won(p.value)), /*#__PURE__*/React.createElement("div", {
      className: "num",
      style: {
        fontSize: 12.5,
        color: 'var(--text-tertiary)'
      }
    }, won(p.price))), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-end',
        gap: 1
      }
    }, /*#__PURE__*/React.createElement(DeltaValue, {
      value: p.plRate,
      percent: true,
      size: 15
    }), /*#__PURE__*/React.createElement(DeltaValue, {
      value: p.pl,
      prefix: "\u20A9",
      showArrow: false,
      size: 12.5
    }))), on && /*#__PURE__*/React.createElement("div", {
      style: {
        padding: '4px 24px 22px 76px',
        background: 'var(--grey-50)'
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13,
        fontWeight: 700,
        color: 'var(--grey-800)',
        margin: '14px 0 12px'
      }
    }, "\uD329\uD130 \uC810\uC218 \xB7 \uC885\uD569 ", p.score ? p.score.toFixed(1) : '—', "/100"), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'grid',
        gridTemplateColumns: '1fr 1fr 1fr',
        gap: '14px 28px'
      }
    }, /*#__PURE__*/React.createElement(FactorBar, {
      label: "\uAC00\uCE58 Value",
      score: p.factors.value,
      max: 25,
      factor: "value"
    }), /*#__PURE__*/React.createElement(FactorBar, {
      label: "\uD004\uB9AC\uD2F0 Quality",
      score: p.factors.quality,
      max: 25,
      factor: "quality"
    }), /*#__PURE__*/React.createElement(FactorBar, {
      label: "\uBAA8\uBA58\uD140 Momentum",
      score: p.factors.momentum,
      max: 20,
      factor: "momentum"
    }), /*#__PURE__*/React.createElement(FactorBar, {
      label: "\uBC30\uB2F9 Yield",
      score: p.factors.yield,
      max: 5,
      factor: "yield"
    }), /*#__PURE__*/React.createElement(FactorBar, {
      label: "\uAE30\uC220\uC801 Technical",
      score: p.factors.technical,
      max: 15,
      factor: "technical"
    }), /*#__PURE__*/React.createElement(FactorBar, {
      label: "\uBCF4\uC870 Auxiliary",
      score: p.factors.auxiliary,
      max: 10,
      factor: "auxiliary"
    }))));
  })));
}
window.AssetScreen = AssetScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/toss-invest/AssetScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/toss-invest/DividendScreen.jsx
try { (() => {
/* 예상 배당금 — dividend forecast. */
function DividendScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const {
    Card,
    StatTile,
    TickerBadge,
    Badge
  } = NS;
  const {
    QBIcon
  } = window;
  const {
    dividends,
    won
  } = window.QB_DATA;
  const total = dividends.reduce((a, d) => a + d.total, 0);
  const byMonth = dividends.reduce((acc, d) => {
    acc[d.payMonth] = (acc[d.payMonth] || 0) + d.total;
    return acc;
  }, {});
  const months = ['4월', '8월'];
  const maxMonth = Math.max(...Object.values(byMonth));
  const sorted = [...dividends].sort((a, b) => b.total - a.total);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1.3fr 1fr',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: 28
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      color: 'var(--text-secondary)',
      fontWeight: 600,
      marginBottom: 8
    }
  }, "\uC62C\uD574 \uC608\uC0C1 \uBC30\uB2F9\uAE08"), /*#__PURE__*/React.createElement("div", {
    className: "num",
    style: {
      fontSize: 36,
      fontWeight: 800,
      color: 'var(--grey-900)',
      letterSpacing: '-.03em'
    }
  }, won(total)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13.5,
      color: 'var(--text-tertiary)',
      marginTop: 8
    }
  }, "\uC138\uC804 \uAE30\uC900 \xB7 \uD3C9\uADE0 \uBC30\uB2F9\uC218\uC775\uB960 ", /*#__PURE__*/React.createElement("b", {
    style: {
      color: 'var(--up)'
    }
  }, "2.4%"), " \xB7 ", dividends.length, "\uAC1C \uC885\uBAA9"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 14,
      marginTop: 22,
      alignItems: 'flex-end',
      height: 90
    }
  }, months.map(m => /*#__PURE__*/React.createElement("div", {
    key: m,
    style: {
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      fontSize: 13,
      fontWeight: 700,
      color: 'var(--grey-800)'
    }
  }, won(byMonth[m] || 0)), /*#__PURE__*/React.createElement("div", {
    style: {
      width: '100%',
      maxWidth: 120,
      height: byMonth[m] / maxMonth * 60 + 8,
      background: 'var(--blue-500)',
      borderRadius: 8
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12.5,
      color: 'var(--text-tertiary)'
    }
  }, m))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 2
    }
  }))), /*#__PURE__*/React.createElement(Card, {
    padding: 24,
    style: {
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'center',
      gap: 18
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 44,
      height: 44,
      borderRadius: 12,
      background: 'var(--amber-50)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    }
  }, /*#__PURE__*/React.createElement(QBIcon, {
    name: "coins",
    size: 24,
    color: "var(--amber-500)"
  })), /*#__PURE__*/React.createElement(StatTile, {
    label: "\uB2E4\uAC00\uC624\uB294 \uBC30\uB2F9\uB77D",
    value: "6\uC6D4 30\uC77C",
    sub: "KT&G \uC911\uAC04\uBC30\uB2F9 \xB7 2\uAC1C \uC885\uBAA9"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 1,
      background: 'var(--border-subtle)'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 44,
      height: 44,
      borderRadius: 12,
      background: 'var(--green-50)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    }
  }, /*#__PURE__*/React.createElement(QBIcon, {
    name: "calendar",
    size: 24,
    color: "var(--green-500)"
  })), /*#__PURE__*/React.createElement(StatTile, {
    label: "\uC5F0 \uD658\uC0B0 \uC218\uC775 \uAE30\uC5EC",
    value: "+0.36%p",
    sub: "\uD3EC\uD2B8\uD3F4\uB9AC\uC624 \uB300\uBE44"
  })))), /*#__PURE__*/React.createElement(Card, {
    padding: 0
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '18px 24px 14px',
      fontSize: 16,
      fontWeight: 800,
      color: 'var(--grey-900)'
    }
  }, "\uC885\uBAA9\uBCC4 \uC608\uC0C1 \uBC30\uB2F9"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 90px 110px 90px',
      padding: '0 24px 10px',
      fontSize: 12.5,
      color: 'var(--text-tertiary)',
      fontWeight: 600,
      borderBottom: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement("span", null, "\uC885\uBAA9"), /*#__PURE__*/React.createElement("span", {
    style: {
      textAlign: 'right'
    }
  }, "\uC8FC\uB2F9 \uBC30\uB2F9"), /*#__PURE__*/React.createElement("span", {
    style: {
      textAlign: 'right'
    }
  }, "\uC608\uC0C1 \uBC30\uB2F9\uAE08"), /*#__PURE__*/React.createElement("span", {
    style: {
      textAlign: 'right'
    }
  }, "\uC218\uC775\uB960")), sorted.map((d, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 90px 110px 90px',
      alignItems: 'center',
      padding: '13px 24px',
      borderBottom: i < sorted.length - 1 ? '1px solid var(--grey-50)' : 'none'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12
    }
  }, /*#__PURE__*/React.createElement(TickerBadge, {
    name: d.name,
    ticker: d.ticker,
    size: 38
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14.5,
      fontWeight: 700,
      color: 'var(--grey-900)'
    }
  }, d.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: 'var(--text-tertiary)'
    }
  }, d.qty, "\uC8FC \xB7 ", d.payMonth, " \uC9C0\uAE09 \xB7 \uBC30\uB2F9\uB77D ", d.exDate))), /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      textAlign: 'right',
      fontSize: 14,
      color: 'var(--text-body)'
    }
  }, won(d.dps)), /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      textAlign: 'right',
      fontSize: 15,
      fontWeight: 700,
      color: 'var(--grey-900)'
    }
  }, won(d.total)), /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      textAlign: 'right',
      fontSize: 14,
      fontWeight: 700,
      color: 'var(--up)'
    }
  }, d.yield.toFixed(2), "%")))));
}
window.DividendScreen = DividendScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/toss-invest/DividendScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/toss-invest/OrderScreen.jsx
try { (() => {
/* 주문내역 — most recent rebalance plan + execution. */
function OrderScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const {
    Card,
    Badge,
    TickerBadge,
    DeltaValue
  } = NS;
  const {
    QBIcon
  } = window;
  const {
    orders,
    won
  } = window.QB_DATA;
  const buys = orders.filter(o => o.side === 'buy'),
    sells = orders.filter(o => o.side === 'sell');
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: 24,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 48,
      height: 48,
      borderRadius: 14,
      background: 'var(--action-primary-soft)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    }
  }, /*#__PURE__*/React.createElement(QBIcon, {
    name: "refresh",
    size: 26,
    color: "var(--blue-500)"
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 16.5,
      fontWeight: 800,
      color: 'var(--grey-900)'
    }
  }, "\uC8FC\uAC04 \uB9AC\uBC38\uB7F0\uC2F1"), /*#__PURE__*/React.createElement(Badge, {
    tone: "success",
    size: "sm"
  }, "\uC2E4\uD589 \uC644\uB8CC"), /*#__PURE__*/React.createElement(Badge, {
    tone: "info",
    size: "sm"
  }, "PAPER")), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      color: 'var(--text-tertiary)',
      marginTop: 3
    }
  }, "2026.06.16 11:19 \xB7 \uB9E4\uC218 ", buys.length, " \xB7 \uB9E4\uB3C4 ", sells.length, " \xB7 \uC2E4\uD328 0 \xB7 \uACC4\uD68D \uC77C\uCE58")), /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'right'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: 'var(--text-tertiary)'
    }
  }, "\uB2E4\uC74C \uC608\uC815"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14.5,
      fontWeight: 700,
      color: 'var(--grey-800)'
    }
  }, "2026.06.23 (\uC6D4)"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 16
    }
  }, [['매수 주문', buys, 'buy'], ['매도 주문', sells, 'sell']].map(([title, list, side]) => /*#__PURE__*/React.createElement(Card, {
    key: side,
    padding: 0
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '18px 24px 12px',
      display: 'flex',
      alignItems: 'center',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: side,
    solid: true
  }, side === 'buy' ? '매수' : '매도'), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 15.5,
      fontWeight: 800,
      color: 'var(--grey-900)'
    }
  }, title), /*#__PURE__*/React.createElement("span", {
    className: "num",
    style: {
      fontSize: 14,
      color: 'var(--text-tertiary)',
      marginLeft: 'auto'
    }
  }, list.length, "\uAC74")), list.map((o, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 12,
      padding: '13px 24px',
      borderTop: '1px solid var(--grey-50)'
    }
  }, /*#__PURE__*/React.createElement(TickerBadge, {
    name: o.name,
    ticker: o.ticker,
    size: 38
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14.5,
      fontWeight: 700,
      color: 'var(--grey-900)'
    }
  }, o.name), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: 'var(--text-tertiary)',
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis'
    }
  }, o.reason)), /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'right'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "num",
    style: {
      fontSize: 14,
      fontWeight: 700,
      color: 'var(--grey-900)'
    }
  }, o.qty, "\uC8FC"), /*#__PURE__*/React.createElement("div", {
    className: "num",
    style: {
      fontSize: 12,
      color: 'var(--text-tertiary)'
    }
  }, won(o.price)))))))));
}
window.OrderScreen = OrderScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/toss-invest/OrderScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/toss-invest/ReportScreen.jsx
try { (() => {
/* 리포트 — broker research summaries (research-report overlay). */
function ReportScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const {
    Card,
    Badge,
    TickerBadge,
    StatTile,
    Tabs
  } = NS;
  const {
    QBIcon
  } = window;
  const {
    reports,
    won
  } = window.QB_DATA;
  const [tab, setTab] = React.useState('all');
  const filtered = reports.filter(r => tab === 'all' || tab === 'held' && r.held || tab === 'positive' && r.opinion === 'positive');
  const opinionMap = {
    positive: ['buy', '매수'],
    mixed: ['hold', '중립'],
    negative: ['sell', '매도']
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 20
    }
  }, /*#__PURE__*/React.createElement(Card, {
    padding: 26,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 28
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 13,
      flex: '0 0 auto'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 46,
      height: 46,
      borderRadius: 13,
      background: 'var(--purple-50)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center'
    }
  }, /*#__PURE__*/React.createElement(QBIcon, {
    name: "sparkles",
    size: 24,
    color: "var(--purple-500)"
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 16.5,
      fontWeight: 800,
      color: 'var(--grey-900)'
    }
  }, "\uB9AC\uC11C\uCE58 \uC694\uC57D"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: 'var(--text-tertiary)'
    }
  }, "\uD55C\uACBD\xB7\uBBF8\uB798\uC5D0\uC14B \uCEE8\uC13C\uC11C\uC2A4 1,000\uAC74 \uC790\uB3D9 \uBD84\uC11D"))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: 'repeat(4,1fr)',
      gap: 24,
      flex: 1,
      paddingLeft: 28,
      borderLeft: '1px solid var(--border-subtle)'
    }
  }, /*#__PURE__*/React.createElement(StatTile, {
    label: "\uBD84\uC11D \uB9AC\uD3EC\uD2B8",
    value: "996",
    sub: "\uBCF8\uBB38 \uCD94\uCD9C"
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "\uB9E4\uC218 \uC758\uACAC",
    value: "175",
    sub: "positive"
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "\uC911\uB9BD \uC758\uACAC",
    value: "810",
    sub: "mixed"
  }), /*#__PURE__*/React.createElement(StatTile, {
    label: "\uBCF4\uC720 \uC885\uBAA9 \uAD00\uB828",
    value: "42",
    sub: "\uD3EC\uD2B8\uD3F4\uB9AC\uC624"
  }))), /*#__PURE__*/React.createElement(Tabs, {
    value: tab,
    onChange: setTab,
    items: [{
      key: 'all',
      label: '전체'
    }, {
      key: 'held',
      label: '보유 종목'
    }, {
      key: 'positive',
      label: '매수 의견'
    }]
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 16
    }
  }, filtered.map((r, i) => {
    const [tone, label] = opinionMap[r.opinion] || ['hold', '중립'];
    return /*#__PURE__*/React.createElement(Card, {
      key: i,
      padding: 22,
      interactive: true,
      shadow: "sm",
      style: {
        display: 'flex',
        flexDirection: 'column',
        gap: 13
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 11
      }
    }, /*#__PURE__*/React.createElement(TickerBadge, {
      name: r.name,
      ticker: r.ticker,
      size: 42
    }), /*#__PURE__*/React.createElement("div", {
      style: {
        flex: 1,
        minWidth: 0
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 7
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 15.5,
        fontWeight: 800,
        color: 'var(--grey-900)'
      }
    }, r.name), r.held && /*#__PURE__*/React.createElement(Badge, {
      tone: "info",
      size: "sm"
    }, "\uBCF4\uC720")), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 12.5,
        color: 'var(--text-tertiary)'
      }
    }, r.broker, " \xB7 ", r.date)), /*#__PURE__*/React.createElement(Badge, {
      tone: tone,
      solid: true
    }, label)), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 15,
        fontWeight: 700,
        color: 'var(--grey-900)',
        lineHeight: 1.35,
        letterSpacing: '-.01em'
      }
    }, r.title), /*#__PURE__*/React.createElement("div", {
      style: {
        fontSize: 13.5,
        color: 'var(--text-body)',
        lineHeight: 1.5,
        textWrap: 'pretty'
      }
    }, r.thesis), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'flex-start',
        gap: 7,
        padding: '10px 12px',
        background: 'var(--grey-50)',
        borderRadius: 'var(--r-md)'
      }
    }, /*#__PURE__*/React.createElement(QBIcon, {
      name: "shield",
      size: 16,
      color: "var(--amber-500)",
      style: {
        flex: '0 0 16px',
        marginTop: 1
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 12.5,
        color: 'var(--text-secondary)',
        lineHeight: 1.45
      }
    }, /*#__PURE__*/React.createElement("b", {
      style: {
        color: 'var(--grey-700)'
      }
    }, "\uB9AC\uC2A4\uD06C"), " \xB7 ", r.risk)), /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        paddingTop: 2
      }
    }, /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 12.5,
        color: 'var(--text-tertiary)'
      }
    }, "\uC2E0\uB8B0\uB3C4 ", (r.confidence * 100).toFixed(0), "%"), r.target && /*#__PURE__*/React.createElement("span", {
      className: "num",
      style: {
        fontSize: 13.5,
        fontWeight: 700,
        color: 'var(--up)'
      }
    }, "\uBAA9\uD45C\uAC00 ", won(r.target))));
  })));
}
window.ReportScreen = ReportScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/toss-invest/ReportScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/toss-invest/TransactionScreen.jsx
try { (() => {
/* 거래내역 — filled trades, grouped by date. */
function TransactionScreen() {
  const NS = window.QuntbotDesignSystem_ce5871;
  const {
    Card,
    Badge,
    TickerBadge,
    SegmentedControl
  } = NS;
  const {
    transactions,
    won
  } = window.QB_DATA;
  const [filter, setFilter] = React.useState('all');
  const rows = transactions.filter(t => filter === 'all' || t.side === filter);
  const groups = rows.reduce((acc, t) => {
    (acc[t.date] = acc[t.date] || []).push(t);
    return acc;
  }, {});
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      color: 'var(--text-secondary)'
    }
  }, "\uCD5C\uADFC 30\uC77C \uCCB4\uACB0\uB41C \uAC70\uB798\uC785\uB2C8\uB2E4. \uBAA8\uB4E0 \uC8FC\uBB38\uC740 PAPER \uBAA8\uB4DC\uB85C \uC2E4\uD589\uB429\uB2C8\uB2E4."), /*#__PURE__*/React.createElement(SegmentedControl, {
    size: "sm",
    value: filter,
    onChange: setFilter,
    items: [{
      key: 'all',
      label: '전체'
    }, {
      key: 'buy',
      label: '매수'
    }, {
      key: 'sell',
      label: '매도'
    }]
  })), Object.entries(groups).map(([date, list]) => /*#__PURE__*/React.createElement(Card, {
    key: date,
    padding: 0
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '14px 24px',
      fontSize: 13.5,
      fontWeight: 700,
      color: 'var(--text-secondary)',
      borderBottom: '1px solid var(--border-subtle)'
    }
  }, date), list.map((t, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      padding: '14px 24px',
      borderBottom: i < list.length - 1 ? '1px solid var(--grey-50)' : 'none'
    }
  }, /*#__PURE__*/React.createElement(TickerBadge, {
    name: t.name,
    ticker: t.ticker,
    size: 40
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 7
    }
  }, /*#__PURE__*/React.createElement(Badge, {
    tone: t.side === 'buy' ? 'buy' : 'sell',
    solid: true,
    size: "sm"
  }, t.side === 'buy' ? '매수' : '매도'), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 15,
      fontWeight: 700,
      color: 'var(--grey-900)'
    }
  }, t.name)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12.5,
      color: 'var(--text-tertiary)',
      marginTop: 2
    }
  }, t.time, " \xB7 ", t.qty, "\uC8FC \xB7 ", won(t.price))), /*#__PURE__*/React.createElement("div", {
    style: {
      textAlign: 'right'
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "num",
    style: {
      fontSize: 15.5,
      fontWeight: 700,
      color: t.side === 'buy' ? 'var(--up)' : 'var(--down)'
    }
  }, t.side === 'buy' ? '-' : '+', won(t.amount)), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: 'var(--text-tertiary)'
    }
  }, "\uCCB4\uACB0 \uC644\uB8CC")))))));
}
window.TransactionScreen = TransactionScreen;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/toss-invest/TransactionScreen.jsx", error: String((e && e.message) || e) }); }

// ui_kits/toss-invest/data.js
try { (() => {
/* ============================================================
   quntbot — shared mock data for the Toss-style UI kit.
   Sourced from the real public_portfolio_snapshot + research
   summaries (anonymized values). Exposes window.QB_DATA.
   ============================================================ */
(function () {
  const won = n => '₩' + Math.round(n).toLocaleString('ko-KR');
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
    asOf: '2026.06.16 13:03'
  };
  const market = {
    status: '정규장',
    kospi: {
      value: 8751.45,
      chg: 8.08
    },
    kosdaq: {
      value: 1019.06,
      chg: 5.30
    },
    usdkrw: {
      value: 1513.18,
      chg: -0.83
    }
  };

  // equity-curve-ish series for the analysis chart (월별 평가금액, 만원)
  const equityCurve = [8120, 8240, 8050, 8390, 8610, 8470, 8720, 8980, 8830, 9150, 9420, 9867];
  const equityLabels = ['7월', '8월', '9월', '10월', '11월', '12월', '1월', '2월', '3월', '4월', '5월', '6월'];
  const positions = [{
    ticker: '028050',
    name: '삼성E&A',
    qty: 24,
    avg: 43651,
    price: 56800,
    value: 1363200,
    cost: 1047624,
    pl: 315572,
    plRate: 30.12,
    rank: 6,
    score: 66.7,
    weight: 2.10,
    sector: '건설',
    factors: {
      value: 14.9,
      quality: 13.6,
      momentum: 16.7,
      yield: 3.4,
      technical: 15.0,
      auxiliary: 3.1
    },
    spark: [44, 46, 45, 49, 52, 50, 54, 57]
  }, {
    ticker: '005850',
    name: '에스엘',
    qty: 18,
    avg: 60558,
    price: 77400,
    value: 1393200,
    cost: 1090044,
    pl: 303154,
    plRate: 27.81,
    rank: 16,
    score: 63.3,
    weight: 2.14,
    sector: '자동차부품',
    factors: {
      value: 19.4,
      quality: 13.5,
      momentum: 14.9,
      yield: 4.6,
      technical: 10.0,
      auxiliary: 1.0
    },
    spark: [61, 63, 62, 66, 70, 72, 75, 77]
  }, {
    ticker: '028260',
    name: '삼성물산',
    qty: 3,
    avg: 407250,
    price: 493000,
    value: 1479000,
    cost: 1221750,
    pl: 257250,
    plRate: 21.06,
    rank: 27,
    score: 59.4,
    weight: 2.27,
    sector: '지주',
    factors: {
      value: 13.1,
      quality: 14.7,
      momentum: 16.4,
      yield: 2.3,
      technical: 10.0,
      auxiliary: 2.8
    },
    spark: [407, 420, 415, 450, 470, 460, 485, 493]
  }, {
    ticker: '034730',
    name: 'SK',
    qty: 2,
    avg: 566000,
    price: 670000,
    value: 1340000,
    cost: 1132000,
    pl: 208000,
    plRate: 18.37,
    rank: 23,
    score: 60.1,
    weight: 2.06,
    sector: '지주',
    factors: {
      value: 15.7,
      quality: 7.5,
      momentum: 17.8,
      yield: 3.3,
      technical: 12.5,
      auxiliary: 3.3
    },
    spark: [566, 580, 575, 610, 640, 630, 660, 670]
  }, {
    ticker: '033100',
    name: '제룡전기',
    qty: 60,
    avg: 48855,
    price: 55400,
    value: 3324000,
    cost: 2931300,
    pl: 392650,
    plRate: 13.39,
    rank: 22,
    score: 60.1,
    weight: 5.11,
    sector: '전기장비',
    factors: {
      value: 14.0,
      quality: 22.5,
      momentum: 13.2,
      yield: 3.8,
      technical: 10.0,
      auxiliary: -3.3
    },
    spark: [48, 50, 49, 52, 54, 53, 55, 55]
  }, {
    ticker: '004800',
    name: '효성',
    qty: 10,
    avg: 175840,
    price: 199300,
    value: 1993000,
    cost: 1758400,
    pl: 234600,
    plRate: 13.34,
    rank: 11,
    score: 65.0,
    weight: 3.06,
    sector: '지주',
    factors: {
      value: 20.1,
      quality: 15.0,
      momentum: 12.3,
      yield: 4.1,
      technical: 12.5,
      auxiliary: 1.0
    },
    spark: [176, 180, 178, 188, 195, 192, 197, 199]
  }, {
    ticker: '062040',
    name: '산일전기',
    qty: 5,
    avg: 225500,
    price: 254000,
    value: 1270000,
    cost: 1127500,
    pl: 142500,
    plRate: 12.64,
    rank: 28,
    score: 59.0,
    weight: 1.95,
    sector: '전기장비',
    factors: {
      value: 4.1,
      quality: 23.7,
      momentum: 14.8,
      yield: 2.1,
      technical: 10.0,
      auxiliary: 4.3
    },
    spark: [225, 235, 230, 245, 250, 248, 252, 254]
  }, {
    ticker: '000270',
    name: '기아',
    qty: 15,
    avg: 151306,
    price: 170300,
    value: 2554500,
    cost: 2269590,
    pl: 284910,
    plRate: 12.55,
    rank: 9,
    score: 66.1,
    weight: 3.93,
    sector: '자동차',
    factors: {
      value: 21.5,
      quality: 16.3,
      momentum: 11.6,
      yield: 4.8,
      technical: 10.0,
      auxiliary: 2.0
    },
    spark: [151, 158, 154, 163, 168, 165, 169, 170]
  }, {
    ticker: '002380',
    name: 'KCC',
    qty: 3,
    avg: 505000,
    price: 565000,
    value: 1695000,
    cost: 1515000,
    pl: 180000,
    plRate: 11.88,
    rank: 25,
    score: 59.8,
    weight: 2.61,
    sector: '화학',
    factors: {
      value: 24.3,
      quality: 12.2,
      momentum: 10.5,
      yield: 4.2,
      technical: 7.5,
      auxiliary: 1.0
    },
    spark: [505, 520, 515, 540, 555, 550, 562, 565]
  }, {
    ticker: '007340',
    name: 'DN오토모티브',
    qty: 50,
    avg: 41168,
    price: 45500,
    value: 2275000,
    cost: 2058400,
    pl: 216600,
    plRate: 10.52,
    rank: 7,
    score: 66.5,
    weight: 3.50,
    sector: '자동차부품',
    factors: {
      value: 21.4,
      quality: 13.6,
      momentum: 14.1,
      yield: 4.0,
      technical: 12.5,
      auxiliary: 1.0
    },
    spark: [41, 43, 42, 44, 45, 44, 45, 45]
  }, {
    ticker: '011200',
    name: 'HMM',
    qty: 67,
    avg: 19930,
    price: 21700,
    value: 1453900,
    cost: 1335310,
    pl: 118590,
    plRate: 8.88,
    rank: null,
    score: null,
    weight: 2.24,
    sector: '해운',
    factors: {
      value: 21.3,
      quality: 16.0,
      momentum: 5.7,
      yield: 4.5,
      technical: 7.5,
      auxiliary: 2.0
    },
    spark: [19, 20, 20, 21, 21, 21, 21, 21]
  }, {
    ticker: '028670',
    name: '팬오션',
    qty: 477,
    avg: 5057,
    price: 5460,
    value: 2604420,
    cost: 2412189,
    pl: 191850,
    plRate: 7.95,
    rank: 19,
    score: 61.1,
    weight: 4.00,
    sector: '해운',
    factors: {
      value: 23.3,
      quality: 9.8,
      momentum: 9.2,
      yield: 4.3,
      technical: 12.5,
      auxiliary: 2.0
    },
    spark: [5.0, 5.2, 5.1, 5.3, 5.4, 5.3, 5.4, 5.4]
  }, {
    ticker: '033780',
    name: 'KT&G',
    qty: 13,
    avg: 177400,
    price: 187700,
    value: 2440100,
    cost: 2306200,
    pl: 133900,
    plRate: 5.81,
    rank: 20,
    score: 60.7,
    weight: 3.75,
    sector: '필수소비재',
    factors: {
      value: 15.1,
      quality: 16.8,
      momentum: 10.8,
      yield: 4.4,
      technical: 12.5,
      auxiliary: 1.0
    },
    spark: [177, 180, 178, 185, 187, 186, 188, 187]
  }, {
    ticker: '012330',
    name: '현대모비스',
    qty: 2,
    avg: 625000,
    price: 657500,
    value: 1315000,
    cost: 1250000,
    pl: 65000,
    plRate: 5.20,
    rank: 10,
    score: 65.3,
    weight: 2.02,
    sector: '자동차부품',
    factors: {
      value: 18.5,
      quality: 14.3,
      momentum: 15.5,
      yield: 3.0,
      technical: 10.0,
      auxiliary: 3.9
    },
    spark: [625, 640, 632, 650, 658, 655, 660, 657]
  }, {
    ticker: '001800',
    name: '오리온홀딩스',
    qty: 67,
    avg: 27200,
    price: 27750,
    value: 1859250,
    cost: 1822400,
    pl: 36850,
    plRate: 2.02,
    rank: 2,
    score: 71.3,
    weight: 2.86,
    sector: '지주',
    factors: {
      value: 21.0,
      quality: 16.3,
      momentum: 15.7,
      yield: 4.7,
      technical: 12.5,
      auxiliary: 1.0
    },
    spark: [27, 27.5, 27.2, 27.8, 27.7, 27.6, 27.8, 27.7]
  }, {
    ticker: '003690',
    name: '코리안리',
    qty: 92,
    avg: 13902,
    price: 14060,
    value: 1293520,
    cost: 1278984,
    pl: 14536,
    plRate: 1.13,
    rank: 12,
    score: 64.6,
    weight: 1.99,
    sector: '보험',
    factors: {
      value: 22.8,
      quality: 5.5,
      momentum: 18.0,
      yield: 4.8,
      technical: 12.5,
      auxiliary: 1.0
    },
    spark: [13.9, 14.0, 13.9, 14.1, 14.0, 14.0, 14.1, 14.0]
  }, {
    ticker: '017550',
    name: '수산세보틱스',
    qty: 474,
    avg: 2709,
    price: 2720,
    value: 1289280,
    cost: 1284066,
    pl: 5214,
    plRate: 0.40,
    rank: 26,
    score: 59.6,
    weight: 1.98,
    sector: '기계',
    factors: {
      value: 21.2,
      quality: 13.7,
      momentum: 12.8,
      yield: 1.7,
      technical: 12.5,
      auxiliary: -2.3
    },
    spark: [2.7, 2.71, 2.70, 2.72, 2.72, 2.71, 2.72, 2.72],
    status: 'executed'
  }, {
    ticker: '023160',
    name: '태광',
    qty: 40,
    avg: 31032,
    price: 31000,
    value: 1240000,
    cost: 1241280,
    pl: -1280,
    plRate: -0.10,
    rank: 29,
    score: 58.8,
    weight: 1.91,
    sector: '기계',
    factors: {
      value: 19.5,
      quality: 17.6,
      momentum: 9.7,
      yield: 3.7,
      technical: 5.0,
      auxiliary: 3.3
    },
    spark: [31, 31.2, 31.1, 31.0, 31.0, 31.1, 31.0, 31.0]
  }, {
    ticker: '000240',
    name: '한국앤컴퍼니',
    qty: 87,
    avg: 30750,
    price: 28850,
    value: 2509950,
    cost: 2675250,
    pl: -165300,
    plRate: -6.18,
    rank: 1,
    score: 77.3,
    weight: 3.86,
    sector: '지주',
    factors: {
      value: 23.6,
      quality: 18.2,
      momentum: 17.3,
      yield: 4.7,
      technical: 12.5,
      auxiliary: 1.0
    },
    spark: [30.7, 30.0, 30.4, 29.2, 28.8, 29.0, 28.9, 28.8]
  }];

  // 거래내역 — filled trades (체결)
  const transactions = [{
    date: '2026.06.16',
    time: '11:19',
    name: '수산세보틱스',
    ticker: '017550',
    side: 'buy',
    qty: 474,
    price: 2695,
    amount: 1277430
  }, {
    date: '2026.06.16',
    time: '11:19',
    name: '제이브이엠',
    ticker: '281820',
    side: 'buy',
    qty: 38,
    price: 33600,
    amount: 1276800
  }, {
    date: '2026.06.16',
    time: '09:05',
    name: '롯데웰푸드',
    ticker: '280360',
    side: 'sell',
    qty: 11,
    price: 116000,
    amount: 1276000
  }, {
    date: '2026.06.16',
    time: '09:05',
    name: '에이피알',
    ticker: '278470',
    side: 'sell',
    qty: 7,
    price: 182300,
    amount: 1276100
  }, {
    date: '2026.06.16',
    time: '09:04',
    name: '한컴',
    ticker: '092790',
    side: 'sell',
    qty: 55,
    price: 23200,
    amount: 1276000
  }, {
    date: '2026.06.16',
    time: '09:04',
    name: '보성파워텍',
    ticker: '006910',
    side: 'sell',
    qty: 210,
    price: 6080,
    amount: 1276800
  }, {
    date: '2026.06.09',
    time: '11:21',
    name: '현대글로비스',
    ticker: '086280',
    side: 'buy',
    qty: 9,
    price: 141500,
    amount: 1273500
  }, {
    date: '2026.06.09',
    time: '09:06',
    name: '금호석유',
    ticker: '011780',
    side: 'sell',
    qty: 8,
    price: 159000,
    amount: 1272000
  }, {
    date: '2026.06.02',
    time: '11:18',
    name: '대한전선',
    ticker: '001440',
    side: 'buy',
    qty: 92,
    price: 13850,
    amount: 1274200
  }, {
    date: '2026.06.02',
    time: '09:05',
    name: '코스맥스',
    ticker: '192820',
    side: 'sell',
    qty: 5,
    price: 254500,
    amount: 1272500
  }];

  // 주문내역 — most recent rebalance plan/execution
  const orders = [{
    date: '2026.06.16',
    name: '제이브이엠',
    ticker: '281820',
    side: 'buy',
    qty: 38,
    price: 33600,
    status: 'filled',
    reason: '신규 편입 · 랭크 18위'
  }, {
    date: '2026.06.16',
    name: '수산세보틱스',
    ticker: '017550',
    side: 'buy',
    qty: 474,
    price: 2695,
    status: 'filled',
    reason: '신규 편입 · 랭크 26위'
  }, {
    date: '2026.06.16',
    name: '보성파워텍',
    ticker: '006910',
    side: 'sell',
    qty: 210,
    price: 6080,
    status: 'filled',
    reason: '랭크 이탈 · 비중 축소'
  }, {
    date: '2026.06.16',
    name: '한컴',
    ticker: '092790',
    side: 'sell',
    qty: 55,
    price: 23200,
    status: 'filled',
    reason: '랭크 이탈'
  }, {
    date: '2026.06.16',
    name: '에이피알',
    ticker: '278470',
    side: 'sell',
    qty: 7,
    price: 182300,
    status: 'filled',
    reason: '스탑로스 · 익절'
  }, {
    date: '2026.06.16',
    name: '롯데웰푸드',
    ticker: '382800',
    side: 'sell',
    qty: 11,
    price: 116000,
    status: 'filled',
    reason: '랭크 이탈'
  }];

  // 예상 배당금 — dividend forecast
  const dividends = [{
    name: 'KT&G',
    ticker: '033780',
    qty: 13,
    dps: 5200,
    total: 67600,
    yield: 2.77,
    payMonth: '4월',
    exDate: '2026.12.27'
  }, {
    name: '기아',
    ticker: '000270',
    qty: 15,
    dps: 6500,
    total: 97500,
    yield: 3.82,
    payMonth: '4월',
    exDate: '2026.12.30'
  }, {
    name: '코리안리',
    ticker: '003690',
    qty: 92,
    dps: 850,
    total: 78200,
    yield: 6.05,
    payMonth: '4월',
    exDate: '2026.12.27'
  }, {
    name: '삼성물산',
    ticker: '028260',
    qty: 3,
    dps: 4300,
    total: 12900,
    yield: 0.87,
    payMonth: '4월',
    exDate: '2026.12.30'
  }, {
    name: '현대모비스',
    ticker: '012330',
    qty: 2,
    dps: 4500,
    total: 9000,
    yield: 0.68,
    payMonth: '4월',
    exDate: '2026.12.30'
  }, {
    name: 'KCC',
    ticker: '002380',
    qty: 3,
    dps: 10000,
    total: 30000,
    yield: 1.77,
    payMonth: '4월',
    exDate: '2026.12.27'
  }, {
    name: 'KT&G(중간)',
    ticker: '033780',
    qty: 13,
    dps: 1200,
    total: 15600,
    yield: 0.64,
    payMonth: '8월',
    exDate: '2026.06.30'
  }, {
    name: '효성',
    ticker: '004800',
    qty: 10,
    dps: 5000,
    total: 50000,
    yield: 2.51,
    payMonth: '4월',
    exDate: '2026.12.27'
  }];

  // 리포트 — broker research summaries (from hankyung/mirae overlays)
  const reports = [{
    date: '2026.06.16',
    name: '삼성E&A',
    ticker: '028050',
    broker: '한경컨센서스',
    opinion: 'positive',
    confidence: 1.0,
    target: 73000,
    title: '뭘 고를지 몰라 다 준비해봤어',
    thesis: '삼성E&A를 건설업종 최선호주로, 투자의견 매수, 목표주가 73,000원 제시.',
    risk: '중동 발주 둔화 + 저가 수주',
    held: true
  }, {
    date: '2026.06.16',
    name: '현대모비스',
    ticker: '012330',
    broker: '한경컨센서스',
    opinion: 'positive',
    confidence: 1.0,
    target: null,
    title: '로봇 하드웨어 티어 1 공급자의 길',
    thesis: 'BD의 중장기 생산량 확대가 휴머노이드 핵심부품 매출 성장으로 이어진다.',
    risk: '로봇 하드웨어 공급자 경쟁 심화',
    held: true
  }, {
    date: '2026.06.16',
    name: '현대건설',
    ticker: '000720',
    broker: '한경컨센서스',
    opinion: 'positive',
    confidence: 1.0,
    target: 195000,
    title: '원전으로 한 번 더 도약',
    thesis: '글로벌 원전 시장 확대 수혜 기대, 목표주가 195,000원으로 커버리지 개시.',
    risk: '국내 발주 둔화 우려',
    held: false
  }, {
    date: '2026.06.11',
    name: '산일전기',
    ticker: '062040',
    broker: '미래에셋',
    opinion: 'positive',
    confidence: 1.0,
    target: null,
    title: 'Bloom으로 열린 성장, 밸류에이션은 아직 낮다',
    thesis: '변압기 매출 확대와 생산 효율화가 이익 성장을 견인할 전망.',
    risk: '2027F PER 23배 수준',
    held: true
  }, {
    date: '2026.06.11',
    name: 'NAVER',
    ticker: '035420',
    broker: '한경컨센서스',
    opinion: 'positive',
    confidence: 1.0,
    target: null,
    title: '긍정적 모멘텀 추가',
    thesis: '인프라 외부 공급 확대로 중장기 신규 성장 동력·수익성 개선에 기여.',
    risk: '글로벌 AI 서비스 경쟁',
    held: false
  }, {
    date: '2026.06.16',
    name: '대덕전자',
    ticker: '353200',
    broker: '미래에셋',
    opinion: 'positive',
    confidence: 1.0,
    target: null,
    title: '아직도 전반전',
    thesis: 'FC-BGA 가동률 80% 육박, 전방 업황 회복과 증설 효과 지속.',
    risk: '중립 비중 10% 내외',
    held: false
  }, {
    date: '2026.06.16',
    name: '네패스',
    ticker: '033640',
    broker: '한경컨센서스',
    opinion: 'mixed',
    confidence: 0.9,
    target: null,
    title: 'Fab tour 후기',
    thesis: 'CPB 기술력 기반 긍정적 체질 개선, 세 가지 성장 축 제시.',
    risk: '하반기 모바일 반도체 수요 둔화',
    held: false
  }, {
    date: '2026.06.15',
    name: 'POSCO홀딩스',
    ticker: '005490',
    broker: '미래에셋',
    opinion: 'positive',
    confidence: 1.0,
    target: null,
    title: '자회사 호조가 주가를 지지할 전망',
    thesis: '자회사 호조가 주가를 지지하나 본업 철강 개선은 여전히 더디다.',
    risk: '글로벌 무역 장벽 강화',
    held: false
  }];

  // 수익분석 — factor budget for the whole portfolio (avg)
  const factorBudget = [{
    key: 'value',
    label: '가치 Value',
    score: 18.2,
    max: 25
  }, {
    key: 'quality',
    label: '퀄리티 Quality',
    score: 14.6,
    max: 25
  }, {
    key: 'momentum',
    label: '모멘텀 Momentum',
    score: 13.8,
    max: 20
  }, {
    key: 'yield',
    label: '배당 Yield',
    score: 3.7,
    max: 5
  }, {
    key: 'technical',
    label: '기술적 Technical',
    score: 11.1,
    max: 15
  }, {
    key: 'auxiliary',
    label: '보조 Auxiliary',
    score: 1.6,
    max: 10
  }];

  // sector allocation
  const sectors = [{
    label: '지주',
    value: 18.9,
    color: 'var(--blue-500)'
  }, {
    label: '자동차/부품',
    value: 15.0,
    color: 'var(--red-500)'
  }, {
    label: '전기장비',
    value: 9.0,
    color: 'var(--green-500)'
  }, {
    label: '해운',
    value: 8.5,
    color: 'var(--amber-500)'
  }, {
    label: '소재/화학',
    value: 7.2,
    color: 'var(--purple-500)'
  }, {
    label: '기타',
    value: 41.4,
    color: 'var(--grey-300)'
  }];
  window.QB_DATA = {
    won,
    summary,
    market,
    equityCurve,
    equityLabels,
    positions,
    transactions,
    orders,
    dividends,
    reports,
    factorBudget,
    sectors
  };
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/toss-invest/data.js", error: String((e && e.message) || e) }); }

// ui_kits/toss-invest/icons.jsx
try { (() => {
/* Lucide-style line icons (24x24, stroke 2, currentColor).
   Mirrors Toss's clean single-weight line iconography. */
const QB_ICON_PATHS = {
  wallet: '<path d="M19 7V5a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H5a2 2 0 0 1-2-2V5"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/><path d="M18 12a.5.5 0 0 0 0 1 .5.5 0 0 0 0-1"/>',
  receipt: '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M8 7h8"/><path d="M8 11h8"/><path d="M8 15h5"/>',
  list: '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/><path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/>',
  coins: '<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/><path d="m16.71 13.88.7.71-2.82 2.82"/>',
  trending: '<path d="M16 7h6v6"/><path d="m22 7-8.5 8.5-5-5L2 17"/>',
  file: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  chevronRight: '<path d="m9 18 6-6-6-6"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  pie: '<path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/>',
  refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/>',
  shield: '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1Z"/><path d="m9 12 2 2 4-4"/>',
  sparkles: '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.963 0z"/>',
  dot: '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
  calendar: '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
  arrowUpRight: '<path d="M7 7h10v10"/><path d="M7 17 17 7"/>'
};
function QBIcon({
  name,
  size = 22,
  color = 'currentColor',
  strokeWidth = 2,
  style = {}
}) {
  const p = QB_ICON_PATHS[name] || '';
  return /*#__PURE__*/React.createElement("svg", {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: color,
    strokeWidth: strokeWidth,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: style,
    dangerouslySetInnerHTML: {
      __html: p
    }
  });
}
window.QBIcon = QBIcon;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/toss-invest/icons.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.TickerBadge = __ds_scope.TickerBadge;

__ds_ns.DeltaValue = __ds_scope.DeltaValue;

__ds_ns.Donut = __ds_scope.Donut;

__ds_ns.FactorBar = __ds_scope.FactorBar;

__ds_ns.Sparkline = __ds_scope.Sparkline;

__ds_ns.StatTile = __ds_scope.StatTile;

__ds_ns.SegmentedControl = __ds_scope.SegmentedControl;

__ds_ns.Tabs = __ds_scope.Tabs;

})();
