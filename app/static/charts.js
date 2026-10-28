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

  window.yamsDrawdown = a => { let m = -Infinity; return a.map(v => { m = Math.max(m, v); return +(100 * (v / m - 1)).toFixed(2); }); };
})();
