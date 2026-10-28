// Shared Chart.js setup: colours from the CSS tokens, thin lines, recessive grid, crosshair tooltip.
(function () {
  const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const money = v => '$' + Math.round(v).toLocaleString('en-US');
  const pct = v => (v > 0 ? '+' : '') + v.toFixed(1) + '%';

  // series: [{label, data, color: '--series-1', dashed}]; kind: 'money' | 'pct'
  window.yamsLine = function (canvasId, labels, series, kind) {
    const fmt = kind === 'pct' ? pct : money;
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.font.size = 12;
    Chart.defaults.color = css('--muted');
    return new Chart(document.getElementById(canvasId), {
      type: 'line',
      data: {
        labels,
        datasets: series.map(s => ({
          label: s.label, data: s.data, borderColor: css(s.color), backgroundColor: css(s.color),
          borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, pointHoverBorderWidth: 2,
          pointHoverBorderColor: css('--surface'), borderDash: s.dashed ? [6, 4] : [], tension: 0,
        })),
      },
      options: {
        maintainAspectRatio: false, animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },  // the page renders an HTML legend next to the title
          tooltip: {
            backgroundColor: css('--surface'), titleColor: css('--ink'), bodyColor: css('--ink-2'),
            borderColor: css('--line-strong'), borderWidth: 1, padding: 10, boxPadding: 4, usePointStyle: true,
            callbacks: { label: c => ` ${c.dataset.label}: ${fmt(c.parsed.y)}` },
          },
        },
        scales: {
          x: { grid: { display: false }, border: { color: css('--line-strong') },
               ticks: { maxTicksLimit: 7, maxRotation: 0, autoSkipPadding: 16 } },
          y: { grid: { color: css('--grid') }, border: { display: false }, ticks: { callback: fmt, maxTicksLimit: 6 } },
        },
      },
      plugins: [{  // vertical crosshair on hover
        id: 'crosshair',
        afterDatasetsDraw(chart) {
          const a = chart.tooltip && chart.tooltip.getActiveElements();
          if (!a || !a.length) return;
          const x = a[0].element.x, { top, bottom } = chart.chartArea, ctx = chart.ctx;
          ctx.save(); ctx.strokeStyle = css('--axis'); ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
          ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke(); ctx.restore();
        },
      }],
    });
  };

  const alpha = (hex, a) => {
    const n = parseInt(hex.replace('#', ''), 16);
    return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  };

  // Forecast fan: shaded P10–P90 and P25–P75 bands + median for "apply", dashed median for "keep".
  window.yamsFan = function (canvasId, fan) {
    const p = fan.proposed, h = fan.hold, c1 = css('--series-1'), c0 = css('--axis');
    const band = (data, fillTo, a, label) => ({ label, data, fill: fillTo, backgroundColor: alpha(c1, a),
      borderWidth: 0, pointRadius: 0, pointHoverRadius: 0 });
    const chart = yamsLine(canvasId, fan.dates, [], 'money');
    chart.data.datasets = [
      band(p.p90, 3, 0.13, 'Apply · good case (P90)'),  // filled down to P10 (dataset 3)
      band(p.p75, 2, 0.22, null),                         // filled down to P25 (dataset 2)
      band(p.p25, false, 0, null),
      band(p.p10, false, 0, 'Apply · bad case (P10)'),
      { label: 'Apply · middle (median)', data: p.p50, borderColor: c1, backgroundColor: c1, borderWidth: 2,
        pointRadius: 0, pointHoverRadius: 4, tension: 0 },
      { label: 'Keep · middle (median)', data: h.p50, borderColor: c0, backgroundColor: c0, borderWidth: 2,
        borderDash: [6, 4], pointRadius: 0, pointHoverRadius: 4, tension: 0 },
    ];
    const o = chart.options.plugins;
    o.filler = { propagate: false };
    o.tooltip.filter = i => i.dataset.label !== null;
    o.tooltip.itemSort = (a, b) => b.parsed.y - a.parsed.y;
    chart.update();
    return chart;
  };

  window.yamsDrawdown = a => { let m = -Infinity; return a.map(v => { m = Math.max(m, v); return +(100 * (v / m - 1)).toFixed(2); }); };
})();
